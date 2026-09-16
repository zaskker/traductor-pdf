import copy
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.services.prompt_builder import TranslationPromptBuilder
from src.application.services.token_protector import TokenProtector
from src.application.dtos.translation_execution_config import TranslationExecutionConfig
from src.domain.interfaces.persistence import ITranslationRegionRepository, IProjectRepository, IGlossaryRepository
from src.domain.interfaces.translation_memory import ITranslationMemoryRepository
from src.domain.interfaces.translation import (
    InvalidTranslationResultError,
    GlossaryMismatchError,
    StructuralMarkerMismatchError,
    ITranslationEngine,
)
from src.domain.models.enums import RegionStatus
from src.domain.models.region import TranslationRegion
from src.application.services.block_grouper import group_source_fragments_into_blocks
from src.domain.services.translation_memory_utils import normalize_source_text, hash_source_text
from src.application.services.glossary_matcher import GlossaryMatcher
import re
import uuid


@dataclass
class TranslateRegionRequest:
    region_id: str
    source_language: str = "en"
    target_language: str = "es"
    project_locked: bool = False
    config: "TranslationExecutionConfig" = None


class TranslateRegionUseCase:
    def __init__(
        self,
        engine: ITranslationEngine,
        repository: ITranslationRegionRepository,
        project_repository: IProjectRepository,
        glossary_repository: IGlossaryRepository,
        token_protector: TokenProtector,
        prompt_builder: TranslationPromptBuilder,
        memory_repository: ITranslationMemoryRepository = None,
    ):
        self.engine = engine
        self.repository = repository
        self.project_repository = project_repository
        self.glossary_repository = glossary_repository
        self.token_protector = token_protector
        self.prompt_builder = prompt_builder
        self.memory_repository = memory_repository

    def execute(
        self, request: TranslateRegionRequest
    ) -> tuple[TranslationRegion, TranslationRegion]:
        if request.project_locked:
            raise ValueError("Cannot translate because the project is locked.")

        old_region = self.repository.get(request.region_id)
        if not old_region:
            raise ValueError(f"Region {request.region_id} not found.")

        # Copy to avoid mutating the cached object if repository returns a shared reference
        old_region_snapshot = copy.deepcopy(old_region)

        if not old_region_snapshot.source_text or not old_region_snapshot.source_text.strip():
            raise ValueError("Region source text is empty. Cannot translate.")

        # Check source blocks
        blocks = group_source_fragments_into_blocks(old_region_snapshot.source_fragments)
        structured_mode = len(blocks) > 1

        if structured_mode:
            from src.application.services.structured_translation_codec import StructuredTranslationCodec
            source_text_to_protect, expected_markers = StructuredTranslationCodec.build_engine_input(blocks)
        else:
            source_text_to_protect = old_region_snapshot.source_text
            expected_markers = []

        # 0. Load Glossary
        if request.config:
            active_glossary_revision = request.config.glossary_revision
            active_glossary_id = request.config.glossary_id
            glossary_entries = request.config.glossary_entries
        else:
            active_glossary_id = None
            active_glossary_revision = None
            glossary_entries = []
            
            project = self.project_repository.get(old_region_snapshot.project_id) if self.project_repository else None
            if project and project.active_glossary_id and self.glossary_repository:
                active_glossary_id = project.active_glossary_id
                gloss = self.glossary_repository.get(active_glossary_id)
                if gloss:
                    active_glossary_revision = gloss.revision
                    glossary_entries = list(gloss.entries)
                        
        relevant_entries = []
        matcher = None
        matches = []
        
        if glossary_entries:
            matcher = GlossaryMatcher(glossary_entries)
            # blocks list for matcher
            blocks_for_matcher = []
            if structured_mode:
                for i, b in enumerate(blocks):
                    blocks_for_matcher.append((b.block_index, b.text))
            else:
                blocks_for_matcher.append((0, old_region_snapshot.source_text))
            
            matches = matcher.match_source_blocks(blocks_for_matcher)
            relevant_entries = matcher.get_relevant_entries(blocks_for_matcher)
        # TRANS-06: Translation Memory
        corpus_references = []
        exact_matches = {}
        conflict = False
        
        if self.memory_repository:
            project = self.project_repository.get(old_region_snapshot.project_id)
            target_lang = request.config.target_language if request.config else request.target_language
            for block in blocks:
                norm_src = normalize_source_text(block.text)
                hash_src = hash_source_text(norm_src)
                entries = self.memory_repository.get_by_project_and_hash(project.id, target_lang, hash_src)
                
                if entries:
                    unique_targets = list({e.target_text for e in entries})
                    if len(unique_targets) == 1:
                        target = unique_targets[0]
                        # Verify against glossary
                        if matcher and relevant_entries:
                            glossary_errors = matcher.validate_translation(matches, [(block.block_index, target)])
                            if not glossary_errors:
                                exact_matches[block.block_index] = (target, entries[0].original_translation_engine, entries[0].original_translation_model)
                                corpus_references.append((block.text, target))
                            else:
                                conflict = True
                        else:
                            exact_matches[block.block_index] = (target, entries[0].original_translation_engine, entries[0].original_translation_model)
                            corpus_references.append((block.text, target))
                    else:
                        conflict = True
                        for t in unique_targets[:3]:
                            if matcher and relevant_entries:
                                glossary_errors = matcher.validate_translation(matches, [(block.block_index, t)])
                                if glossary_errors:
                                    continue
                            if len(corpus_references) < 3:
                                corpus_references.append((block.text, t))

        # Check for Direct Reuse
        direct_reuse = self.memory_repository is not None and len(exact_matches) == len(blocks) and not conflict and len(blocks) > 0
        
        if direct_reuse:
            if structured_mode:
                parsed_blocks = [exact_matches[b.block_index][0] for b in blocks]
                final_text = StructuredTranslationCodec.persist_visible_text(parsed_blocks)
            else:
                final_text = exact_matches[0][0]
                parsed_blocks = [final_text]
            result_engine = exact_matches[blocks[0].block_index][1] if blocks else "memory"
            result_model = exact_matches[blocks[0].block_index][2] if blocks else "memory"
        else:
            # 1. Protect tokens
            protected_text = self.token_protector.protect(source_text_to_protect)

            # 2. Build instructions
            base_system_prompt = self.prompt_builder.build_system_prompt(
                source_language=request.config.source_language if request.config else request.source_language,
                target_language=request.config.target_language if request.config else request.target_language,
                structured_mode=structured_mode,
                glossary_entries=relevant_entries,
                corpus_references=corpus_references[:3]
            )
            user_prompt = self.prompt_builder.build_user_prompt(protected_text.text)

            engine_to_use = request.config.engine if request.config else self.engine
            
            max_attempts = 2 if structured_mode else 1
            current_system_prompt = base_system_prompt
            
            from src.application.logger import logger
            
            for attempt in range(1, max_attempts + 1):
                # Stale validation before retry (only applicable if attempt > 1)
                if attempt > 1:
                    latest_region = self.repository.get(request.region_id)
                    print(f"LATEST: {latest_region.updated_at}, OLD: {old_region_snapshot.updated_at}")
                    if not latest_region or latest_region.updated_at != old_region_snapshot.updated_at:
                        raise ValueError("Region was modified or deleted while waiting for retry.")

                result = engine_to_use.translate(
                    system_prompt=current_system_prompt,
                    user_prompt=user_prompt,
                )

                if not result.translated_text or not result.translated_text.strip():
                    raise InvalidTranslationResultError("Engine returned an empty translation.")

                if result.translated_text.strip() == user_prompt.strip():
                    raise InvalidTranslationResultError("Engine returned an exact copy of the user prompt.")

                # 3. Restore tokens
                restored_text = self.token_protector.restore(result.translated_text, protected_text)

                if restored_text.strip() == old_region_snapshot.source_text.strip():
                    # Do not unconditionally reject trivial texts that might legitimately be identical (e.g. "PDF", "Wi-Fi", names).
                    if len(old_region_snapshot.source_text.strip()) > 15:
                        raise InvalidTranslationResultError("Engine returned an exact copy of the source text.")

                # Validate markers if structured mode
                if structured_mode:
                    try:
                        parsed_blocks = StructuredTranslationCodec.parse_engine_result(restored_text, expected_markers)
                        
                        # Check for empty blocks (except if source was empty)
                        for i, block_content in enumerate(parsed_blocks):
                            source_block_content = blocks[i].text.strip()
                            if not block_content and source_block_content:
                                raise InvalidTranslationResultError(f"Block {expected_markers[i]} is empty in translation.")
                        
                        final_text = StructuredTranslationCodec.persist_visible_text(parsed_blocks)
                        break # Success
                    except StructuralMarkerMismatchError as e:
                        logger.warning(f"Structural marker mismatch on attempt {attempt}. Expected: {e.expected_markers}, Found: {e.found_markers}. Engine: {result.engine_name}/{result.model_name}")
                        if attempt < max_attempts:
                            current_system_prompt = self.prompt_builder.build_corrective_system_prompt(base_system_prompt, expected_markers)
                            continue
                        else:
                            raise e
                else:
                    final_text = restored_text
                    break

            # 3.5 Validate Glossary
            if matcher and relevant_entries:
                translated_blocks_for_matcher = []
                if structured_mode:
                    for i, block_content in enumerate(parsed_blocks):
                        translated_blocks_for_matcher.append((blocks[i].block_index, block_content))
                else:
                    translated_blocks_for_matcher.append((0, final_text))
                
                glossary_errors = matcher.validate_translation(matches, translated_blocks_for_matcher)
                if glossary_errors:
                    raise GlossaryMismatchError("\n".join(glossary_errors))
            
            result_engine = result.engine_name
            result_model = result.model_name

        # 4. Build new snapshot
        new_region_snapshot = copy.deepcopy(old_region_snapshot)
        new_region_snapshot.translated_text = final_text
        new_region_snapshot.status = RegionStatus.TRANSLATED
        new_region_snapshot.is_manually_edited = False
        new_region_snapshot.updated_at = datetime.now(UTC)
        new_region_snapshot.translation_engine = result_engine
        new_region_snapshot.translation_engine_version = result_model
        new_region_snapshot.translation_model = result_model
        
        # DATA-03: Metadata
        new_region_snapshot.prompt_template_version = "v1"
        new_region_snapshot.translation_options = {
            "schema_version": 1,
            "target_language": request.config.target_language if request.config else request.target_language,
            "structured_mode": structured_mode,
            "translation_origin": "CORPUS_EXACT" if direct_reuse else "ENGINE"
        }
        
        # DATA-03: Translation Revision
        if not new_region_snapshot.translation_revision:
            new_region_snapshot.translation_revision = 1
        else:
            new_region_snapshot.translation_revision += 1

        # TRANS-04: Glossary metadata
        new_region_snapshot.glossary_id = active_glossary_id
        new_region_snapshot.glossary_revision = active_glossary_revision

        # DATA-02: Stable Block IDs
        old_blocks = old_region_snapshot.translated_blocks or []
        reuse_ids = len(old_blocks) == len(blocks)
        new_translated_blocks = []
        
        if structured_mode:
            for i, block_content in enumerate(parsed_blocks):
                block_id = old_blocks[i]["id"] if reuse_ids else uuid.uuid4().hex
                new_translated_blocks.append({
                    "id": block_id,
                    "source_block_index": blocks[i].block_index,
                    "text": block_content
                })
        else:
            # len(blocks) is 0 or 1
            if blocks:
                block_id = old_blocks[0]["id"] if reuse_ids and old_blocks else uuid.uuid4().hex
                new_translated_blocks.append({
                    "id": block_id,
                    "source_block_index": blocks[0].block_index,
                    "text": final_text
                })
        
        new_region_snapshot.translated_blocks = new_translated_blocks

        return old_region_snapshot, new_region_snapshot
