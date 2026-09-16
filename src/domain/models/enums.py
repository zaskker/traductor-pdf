from enum import Enum, auto


class RegionType(Enum):
    TEXT_NATIVE = auto()
    IMAGE_TEXT = auto()
    PROTECTED = auto()
    MIXED = auto()


class RegionStatus(Enum):
    PENDING = auto()
    TRANSLATED = auto()
    REVIEWED = auto()
    READY_FOR_EXPORT = auto()
    EXPORTED = auto()
    ERROR = auto()
    IGNORED = auto()


class ExtractionMethod(str, Enum):
    NONE = "none"
    NATIVE_TEXT = "native_text"
    OCR = "ocr"


class FitStatus(Enum):
    FIT = auto()
    OVERFLOW = auto()
    PENDING = auto()


class ReviewStatus(Enum):
    UNTRANSLATED = auto()
    UNREVIEWED = auto()
    REVIEWED = auto()
    APPROVED = auto()


class TextAlignment(Enum):
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


class TextWrapMode(Enum):
    NOWRAP = auto()
    WRAP = auto()
