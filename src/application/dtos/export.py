from dataclasses import dataclass, field
from enum import Enum, auto

from src.domain.models.enums import TextAlignment, TextWrapMode
from src.domain.value_objects.geometry import Rect

# IPC protocol version. Increment when wire schema changes incompatibly.
EXPORT_PROTOCOL_VERSION = 3


class BackgroundClassification(Enum):
    UNIFORM_WHITE = auto()
    UNIFORM_COLOR = auto()
    COMPLEX_BACKGROUND = auto()
    UNKNOWN = auto()


class PreflightIssueCode(Enum):
    PROJECT_LOCKED = auto()
    SOURCE_MISSING = auto()
    FINGERPRINT_MISMATCH = auto()
    PAGE_COUNT_MISMATCH = auto()
    NO_EXPORTABLE_REGIONS = auto()
    PENDING_REGIONS = auto()
    OVERFLOW = auto()
    OVERLAP = auto()
    COMPLEX_BACKGROUND = auto()
    UNKNOWN_BACKGROUND = auto()
    INVALID_PAGE_NUMBER = auto()
    ENCRYPTED_SOURCE = auto()
    SIGNED_SOURCE = auto()
    INVALID_REGION_STATUS = auto()
    UNAPPROVED_REGIONS = auto()


class PreflightSeverity(Enum):
    BLOCKER = auto()
    WARNING = auto()


class PendingRegionPolicy(Enum):
    BLOCK = auto()
    EXPORT_TRANSLATED_ONLY = auto()


class ApprovalExportPolicy(Enum):
    """Policy that determines which translated regions are eligible for export
    based on their review/approval status (TRANS-05).

    APPROVED_ONLY (default/recommended): Only regions where
        approved_translation_revision == translation_revision are exported.
    ALL_VALID_TRANSLATED: All regions with a valid translation are exported
        regardless of approval status.

    Note: This policy is orthogonal to render eligibility (SAFE-08).
    A region must satisfy BOTH render constraints AND this approval policy
    to appear in the final ExportRequest specs.
    """
    APPROVED_ONLY = auto()
    ALL_VALID_TRANSLATED = auto()


@dataclass(frozen=True)
class PdfFingerprint:
    sha256: str
    size: int
    page_count: int


@dataclass(frozen=True)
class BackgroundAnalysisRequest:
    region_id: str
    page_number: int  # 1-based
    target_rect: Rect
    excluded_fragment_rects: tuple[Rect, ...]


@dataclass(frozen=True)
class BackgroundAnalysis:
    region_id: str
    classification: BackgroundClassification
    background_rgb: tuple[int, int, int] | None = None

    def __post_init__(self):
        if self.classification == BackgroundClassification.UNIFORM_WHITE:
            if self.background_rgb != (255, 255, 255):
                raise ValueError("background_rgb must be (255, 255, 255) for UNIFORM_WHITE")
        elif self.classification == BackgroundClassification.UNIFORM_COLOR:
            if not self.background_rgb:
                raise ValueError("background_rgb required for UNIFORM_COLOR")
            if len(self.background_rgb) != 3:
                raise ValueError("background_rgb must have exactly 3 components")
            for c in self.background_rgb:
                if not isinstance(c, int):
                    raise ValueError("RGB components must be ints")
                if not (0 <= c <= 255):
                    raise ValueError(f"Invalid RGB component: {c}")


@dataclass(frozen=True)
class ExportTextBlockSpec:
    """
    A single logical text block within an export region.

    Derived from source SourceFragment grouping (block_index).
    rect is in absolute PDF coordinates (same space as ExportRegionSpec.pdf_rect).
    translated_text is the full translated text for this block, including any
    list prefix that was detected and preserved by the export pipeline.
    """

    rect: Rect
    translated_text: str  # full block text (prefix + body if list item)
    font_size: float
    font_color: tuple[int, int, int] = (0, 0, 0)
    alignment: TextAlignment = TextAlignment.LEFT
    wrap_mode: TextWrapMode = TextWrapMode.WRAP
    structure: str = "UNKNOWN"

    def __post_init__(self):
        import math

        if self.rect.width <= 0 or self.rect.height <= 0:
            raise ValueError("ExportTextBlockSpec: degenerate rect")
        if not self.translated_text or not self.translated_text.strip():
            raise ValueError("ExportTextBlockSpec: translated_text empty")
        if math.isnan(self.font_size) or math.isinf(self.font_size) or self.font_size <= 0:
            raise ValueError("ExportTextBlockSpec: font_size must be positive finite")

        if len(self.font_color) != 3:
            raise ValueError("font_color must have exactly 3 components")
        for c in self.font_color:
            if not isinstance(c, int):
                raise ValueError("RGB components must be ints")
            if not (0 <= c <= 255):
                raise ValueError(f"Invalid RGB component: {c}")


@dataclass(frozen=True)
class ExportRegionSpec:
    region_id: str
    page_number: int
    pdf_rect: Rect
    translated_text: str
    font_family: str
    font_size: float
    font_color: tuple[int, int, int]
    background_rgb: tuple[int, int, int]
    # Structured block layout (Hotfix 4). When non-empty, the export pipeline
    # uses block-level rendering instead of whole-region single textbox.
    # Each block preserves the relative geometry of its source fragments.
    blocks: tuple[ExportTextBlockSpec, ...] = field(default_factory=tuple)

    def __post_init__(self):
        import math

        if not self.region_id or not self.region_id.strip():
            raise ValueError("region_id empty")
        if self.page_number < 1:
            raise ValueError("page_number < 1")
        if self.pdf_rect.width <= 0 or self.pdf_rect.height <= 0:
            raise ValueError("degenerate pdf_rect")
        if not self.translated_text or not self.translated_text.strip():
            raise ValueError("translated_text empty")
        if not self.font_family or not self.font_family.strip():
            raise ValueError("font_family empty")
        if math.isnan(self.font_size) or math.isinf(self.font_size) or self.font_size <= 0:
            raise ValueError("font_size must be a positive finite number")

        if len(self.background_rgb) != 3:
            raise ValueError("background_rgb must have exactly 3 components")
        for c in self.background_rgb:
            if not isinstance(c, int):
                raise ValueError("RGB components must be ints")
            if not (0 <= c <= 255):
                raise ValueError(f"Invalid RGB component: {c}")

        if len(self.font_color) != 3:
            raise ValueError("font_color must have exactly 3 components")
        for c in self.font_color:
            if not isinstance(c, int):
                raise ValueError("RGB components must be ints")
            if not (0 <= c <= 255):
                raise ValueError(f"Invalid RGB component: {c}")


@dataclass(frozen=True)
class ExportRequest:
    source_path: str
    destination_path: str
    expected_fingerprint: PdfFingerprint
    specs: tuple[ExportRegionSpec, ...]


@dataclass(frozen=True)
class ExportResult:
    destination_path: str
    exported_regions: int
    pages_touched: tuple[int, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PreflightIssue:
    code: PreflightIssueCode
    severity: PreflightSeverity
    region_id: str | None = None
    page_number: int | None = None
    related_region_id: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PreflightReport:
    can_export: bool
    issues: tuple[PreflightIssue, ...]
    exportable_regions: int
    pending_regions: int
    blocking_regions: int


@dataclass(frozen=True)
class PreflightOutcome:
    report: PreflightReport
    request: ExportRequest | None = None

    def __post_init__(self):
        if not self.report.can_export and self.request is not None:
            raise ValueError("request must be None if can_export is False")
        if self.report.can_export and not self.request:
            raise ValueError("request must exist if can_export is True")
        if self.request and not self.request.specs:
            raise ValueError("request must have specs if can_export is True")


@dataclass(frozen=True)
class PdfSourceInspection:
    fingerprint: PdfFingerprint
    is_encrypted: bool
    needs_authentication: bool
    has_digital_signatures: bool
    # page_number (1-based) -> CropBox rect
    page_cropboxes: dict[int, Rect] = field(default_factory=dict)
    # page_number (1-based) -> list of text block rects
    page_native_texts: dict[int, tuple[Rect, ...]] = field(default_factory=dict)
