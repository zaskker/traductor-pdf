import re
import hashlib
import unicodedata

def normalize_source_text(text: str) -> str:
    if not text:
        return ""
    # NFC Unicode normalization
    text = unicodedata.normalize('NFC', text)
    # Trim
    text = text.strip()
    # Collapse whitespace (including newlines) into a single space
    text = re.sub(r'\s+', ' ', text)
    return text

def hash_source_text(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
