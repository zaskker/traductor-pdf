import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.domain.interfaces.translation import TokenRestorationError


@dataclass(frozen=True)
class ProtectedText:
    text: str
    placeholders: Mapping[str, str]


class TokenProtector:
    """
    Protects technical tokens (URLs, paths, CLI flags, inline code, variables)
    from being translated by replacing them with deterministic placeholders.
    """

    # We use a combined regex to enforce priority and prevent overlapping matches.
    # The order of the patterns defines the priority.
    _PATTERN = re.compile(
        r"(\[\[TP_\d+\]\])"  # 1. Existing TP placeholders (prevent collisions)
        r"|(`[^`]+`)"  # 2. Inline code
        r"|(https?://\S*[a-zA-Z0-9/_\-])"  # 3. URLs
        r"|(</?[a-zA-Z0-9_-]+(?:[^>]*?)>)"  # 4. HTML/XML Tags
        r"|((?<!\w)[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"  # 5. Emails
        r"|((?<!\w)[a-zA-Z0-9_-]+\.(?:json|xml|yaml|yml|txt|py|js|html|css|csv|ini|md)(?!\w))"  # 6. File extensions
        r"|((?<!\w)[a-zA-Z]:\\\S*[a-zA-Z0-9/_\-])"  # 7. Windows paths
        r"|((?<!\w)(?:/[a-zA-Z0-9_.-]+)+/?)"  # 8. POSIX paths
        r"|((?<!\w)(?:--[a-zA-Z0-9_.-]+(?:=\S*[a-zA-Z0-9_\-])?|-[a-zA-Z0-9]))"  # 9. CLI flags
        r"|(\$[a-zA-Z0-9_]+|\$\{[a-zA-Z0-9_]+\}|%[a-zA-Z0-9_]+%)"  # 10. Variables
    )

    def protect(self, text: str) -> ProtectedText:
        if not text:
            return ProtectedText(text="", placeholders=MappingProxyType({}))

        placeholders_dict: dict[str, str] = {}
        counter = 1

        def replacer(match: re.Match) -> str:
            nonlocal counter
            matched_text = match.group(0)
            placeholder = f"[[TP_{counter:04d}]]"
            placeholders_dict[placeholder] = matched_text
            counter += 1
            return placeholder

        protected_text = self._PATTERN.sub(replacer, text)
        return ProtectedText(text=protected_text, placeholders=MappingProxyType(placeholders_dict))

    def restore(self, translated_text: str, protected: ProtectedText) -> str:
        if not translated_text:
            return translated_text

        if not protected.placeholders:
            return translated_text

        # Validate that all expected placeholders exist EXACTLY ONCE
        for placeholder in protected.placeholders:
            count = translated_text.count(placeholder)
            if count == 0:
                raise TokenRestorationError(f"Missing placeholder in translation: {placeholder}")
            if count > 1:
                raise TokenRestorationError(f"Duplicate placeholder in translation: {placeholder}")

        # Check for unknown or modified placeholders
        # Look for any [[TP_...]] in the translated text
        found_placeholders = re.findall(r"\[\[TP_\d+\]\]", translated_text)
        for found in found_placeholders:
            if found not in protected.placeholders:
                raise TokenRestorationError(f"Unknown or modified placeholder found: {found}")

        # Restore using a single-pass regex substitution to avoid recursive collisions
        pattern = re.compile("|".join(re.escape(p) for p in protected.placeholders))

        restored_text = pattern.sub(
            lambda match: protected.placeholders[match.group(0)],
            translated_text,
        )

        return restored_text
