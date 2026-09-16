import re
from dataclasses import dataclass
from src.domain.models.glossary import GlossaryEntry


@dataclass
class MatchResult:
    entry: GlossaryEntry
    block_index: int


class GlossaryMatcher:
    def __init__(self, entries: list[GlossaryEntry]):
        # Order by source_term length descending for longest-match-first
        self.entries = sorted(entries, key=lambda e: len(e.source_term), reverse=True)
        
        # Pre-compile boundary-aware regex for each entry
        # \b doesn't work well with non-ascii or punctuation, so we use a more robust approach
        self._patterns = {}
        for entry in self.entries:
            # Escape regex characters
            escaped_term = re.escape(entry.source_term.strip())
            # Replace whitespace with a regex that allows any amount of whitespace
            normalized_pattern = re.sub(r'\\\s+', r'\\s+', escaped_term)
            # Boundary aware: lookbehind for non-alphanumeric or start of string, lookahead for non-alphanumeric or end of string.
            # Using \b is simpler if terms are purely words, but let's be robust. 
            # We want to match "network" but not inside "computer network" (longest-match handles this by matching "computer network" first).
            # We want to match "red" but not inside "pared".
            pattern = rf'(?<!\w){normalized_pattern}(?!\w)'
            self._patterns[entry.id] = re.compile(pattern, re.IGNORECASE)
            
    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text.strip())

    def match_source_blocks(self, source_blocks: list[tuple[int, str]]) -> list[MatchResult]:
        """
        Returns a list of MatchResult, indicating which entries apply to which source block.
        Implements longest-match-first by masking out matched portions of the text.
        source_blocks is a list of (block_index, block_text)
        """
        results = []
        for block_index, text in source_blocks:
            working_text = text
            # Iterate entries (already sorted longest first)
            for entry in self.entries:
                pattern = self._patterns[entry.id]
                
                # Find all non-overlapping matches in the working text
                matches = list(pattern.finditer(working_text))
                if matches:
                    results.append(MatchResult(entry=entry, block_index=block_index))
                    # Mask out the matched portions so shorter entries don't match them
                    # e.g., "computer network" matched -> replace with spaces so "network" doesn't match
                    masked = list(working_text)
                    for match in matches:
                        start, end = match.span()
                        for i in range(start, end):
                            masked[i] = ' '
                    working_text = "".join(masked)
        
        return results

    def get_relevant_entries(self, source_blocks: list[tuple[int, str]]) -> list[GlossaryEntry]:
        """
        Returns the unique list of entries that appear in the source blocks.
        """
        matches = self.match_source_blocks(source_blocks)
        seen = set()
        unique = []
        for match in matches:
            if match.entry.id not in seen:
                seen.add(match.entry.id)
                unique.append(match.entry)
        
        # Sort again by longest-match first for deterministic prompt order
        return sorted(unique, key=lambda e: len(e.source_term), reverse=True)

    def validate_translation(self, matches: list[MatchResult], translated_blocks: list[tuple[int, str]]) -> list[str]:
        """
        Validates that for every match in a source block, the target block contains the target_term.
        Returns a list of error messages. Empty list means validation passed.
        """
        errors = []
        # Index translated blocks by block_index
        translated_map = {idx: text for idx, text in translated_blocks}
        
        for match in matches:
            target_text = translated_map.get(match.block_index, "")
            # We want boundary-aware, case-insensitive match for the target term as well
            escaped_target = re.escape(match.entry.target_term.strip())
            normalized_target = re.sub(r'\\\s+', r'\\s+', escaped_target)
            target_pattern = rf'(?<!\w){normalized_target}(?!\w)'
            
            if not re.search(target_pattern, target_text, re.IGNORECASE):
                errors.append(
                    f"Glossary mismatch: expected '{match.entry.target_term}' for '{match.entry.source_term}' "
                    f"in block {match.block_index}."
                )
        return errors
