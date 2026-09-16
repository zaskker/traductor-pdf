class StructuredTranslationCodec:
    @staticmethod
    def build_engine_input(source_blocks) -> tuple[str, list[str]]:
        if not source_blocks:
            return "", []
        structured_text_parts = []
        expected_markers = []
        for i, block in enumerate(source_blocks):
            marker = f"[[BLOCK_{i:04d}]]"
            structured_text_parts.append(f"{marker}\n{block.text}")
            expected_markers.append(marker)
        return "\n\n".join(structured_text_parts), expected_markers

    @staticmethod
    def parse_engine_result(translated_text: str, expected_markers: list[str]) -> tuple[str, ...]:
        import re
        from src.domain.interfaces.translation import InvalidTranslationResultError, StructuralMarkerMismatchError

        found_markers = re.findall(r"\[\[BLOCK_\d{4}\]\]", translated_text)
        if found_markers != expected_markers:
            raise StructuralMarkerMismatchError(
                f"Structural marker mismatch. Expected {expected_markers}, found {found_markers}",
                expected_markers=expected_markers,
                found_markers=found_markers
            )
            
        first_marker_idx = translated_text.find(expected_markers[0])
        if first_marker_idx > 0 and translated_text[:first_marker_idx].strip():
            raise InvalidTranslationResultError("Garbage text found before the first block marker.")
            
        blocks = []
        for i, marker in enumerate(expected_markers):
            start_idx = translated_text.find(marker) + len(marker)
            if i < len(expected_markers) - 1:
                end_idx = translated_text.find(expected_markers[i+1])
            else:
                end_idx = len(translated_text)
            
            block_content = translated_text[start_idx:end_idx].strip()
            blocks.append(block_content)
            
        return tuple(blocks)

    @staticmethod
    def persist_visible_text(blocks: tuple[str, ...]) -> str:
        return "\n\n".join(blocks)
