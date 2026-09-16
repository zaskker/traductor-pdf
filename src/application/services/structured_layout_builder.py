from dataclasses import dataclass

from src.application.dtos.export import ExportTextBlockSpec
from src.application.services.block_grouper import group_source_fragments_into_blocks
from src.application.services.list_prefix_detector import detect_list_prefix
from src.domain.models.enums import TextAlignment
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
import re

from src.domain.value_objects.render_plan import BlockStructure

@dataclass
class BlockPrepInfo:
    src_rect: Rect
    translated_text: str
    is_single_line: bool
    alignment: TextAlignment
    candidate_rect: Rect
    structure: BlockStructure = BlockStructure.UNKNOWN

class StructuredLayoutBuilder:
    ALIGNMENT_TOLERANCE_PT = 2.0
    SAFE_PADDING_PT = 2.0

    @classmethod
    def prepare_blocks(
        cls, 
        region: TranslationRegion, 
        cropbox: Rect | None = None, 
        obstacles: list[Rect] | None = None
    ) -> list[BlockPrepInfo]:
        if obstacles is None:
            obstacles = []
            
        if not region.translated_text or not region.translated_text.strip():
            return []

        source_blocks = group_source_fragments_into_blocks(region.source_fragments)

        if not source_blocks:
            return [BlockPrepInfo(
                src_rect=region.selection_rect,
                translated_text=region.translated_text,
                is_single_line=False,
                alignment=TextAlignment.LEFT,
                candidate_rect=region.selection_rect
            )]

        translations = []
        if len(source_blocks) == 1:
            translations = [region.translated_text]
        else:
            BLOCK_MARKER_RE = re.compile(r"\[\[BLOCK_(\d{4})\]\]\s*")
            marker_matches = list(BLOCK_MARKER_RE.finditer(region.translated_text))
            if marker_matches and len(marker_matches) == len(source_blocks):
                for i, m in enumerate(marker_matches):
                    start = m.end()
                    end = marker_matches[i + 1].start() if i + 1 < len(marker_matches) else len(region.translated_text)
                    translations.append(region.translated_text[start:end].strip())
            else:
                split_blocks = re.split(r'\n\s*\n', region.translated_text.strip())
                if len(split_blocks) == len(source_blocks):
                    translations = [b.strip() for b in split_blocks]
                else:
                    return [BlockPrepInfo(
                        src_rect=region.selection_rect,
                        translated_text=region.translated_text,
                        is_single_line=False,
                        alignment=TextAlignment.LEFT,
                        candidate_rect=region.selection_rect
                    )]

        region_rect = region.selection_rect
        prep_infos = []

        for i, (src_block, translated) in enumerate(zip(source_blocks, translations)):
            if not translated:
                continue

            src_rect = src_block.bbox
            next_y = source_blocks[i + 1].bbox.y0 if i + 1 < len(source_blocks) else region_rect.y1
            available_height = max(next_y - src_rect.y0, src_rect.height)

            block_rect = Rect(
                x0=region_rect.x0,
                y0=src_rect.y0,
                x1=region_rect.x1,
                y1=src_rect.y0 + available_height,
            )

            is_single_line = len(src_block.lines) == 1
            prefix_result = detect_list_prefix(src_block.text)
            structure = BlockStructure.UNKNOWN
            
            if prefix_result:
                structure = BlockStructure.LIST
                trans_prefix = detect_list_prefix(translated)
                if not trans_prefix:
                    translated = prefix_result.prefix.rstrip() + " " + translated.lstrip()
            elif "\n\n" in translated:
                structure = BlockStructure.PARAGRAPH
            else:
                structure = BlockStructure.UNKNOWN

            # Infer alignment
            alignment = TextAlignment.LEFT
            margin_left = src_rect.x0 - region_rect.x0
            margin_right = region_rect.x1 - src_rect.x1
            
            meaningful_margin = 5.0
            width_ratio = src_rect.width / region_rect.width if region_rect.width > 0 else 1.0
            
            if not prefix_result and abs(margin_left - margin_right) <= cls.ALIGNMENT_TOLERANCE_PT and min(margin_left, margin_right) >= meaningful_margin and width_ratio < 0.85:
                alignment = TextAlignment.CENTER
            elif margin_right > margin_left * 2:
                alignment = TextAlignment.LEFT
            elif margin_left > margin_right * 2:
                alignment = TextAlignment.RIGHT
            
            # Expansion logic for single line
            candidate_rect = block_rect

            prep_infos.append(BlockPrepInfo(
                src_rect=block_rect,
                translated_text=translated,
                is_single_line=is_single_line,
                alignment=alignment,
                candidate_rect=candidate_rect,
                structure=structure
            ))

        if not prep_infos:
            return [BlockPrepInfo(
                src_rect=region.selection_rect,
                translated_text=region.translated_text,
                is_single_line=False,
                alignment=TextAlignment.LEFT,
                candidate_rect=region.selection_rect
            )]

        return prep_infos

    @staticmethod
    def union_rects(rects: list[Rect]) -> Rect | None:
        if not rects:
            return None
        x0 = min(r.x0 for r in rects)
        y0 = min(r.y0 for r in rects)
        x1 = max(r.x1 for r in rects)
        y1 = max(r.y1 for r in rects)
        return Rect(x0, y0, x1, y1)
