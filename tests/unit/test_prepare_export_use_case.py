import datetime

import pytest

from src.application.dtos.export import (
    BackgroundAnalysis,
    BackgroundClassification,
    PdfFingerprint,
    PdfSourceInspection,
    PendingRegionPolicy,
    PreflightIssueCode,
    PreflightSeverity,
)
from src.application.use_cases.prepare_pdf_export_use_case import PreparePdfExportUseCase
from src.domain.models.enums import FitStatus, RegionStatus
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutResult


class DummyProjectRepo:
    def __init__(self, project=None):
        self.project = project
        self.projects = {project.id: project} if project else {}

    def get(self, project_id: str):
        return self.projects.get(project_id)


class DummyRegionRepo:
    def __init__(self, regions=None):
        self.regions = regions or []

    def get_all(self, project_id: str):
        return [r for r in self.regions if r.project_id == project_id]


class DummySourceInspector:
    def __init__(self, inspection):
        self.inspection = inspection

    def inspect(self, source_path: str):
        return self.inspection


class DummyBackgroundAnalyzer:
    def __init__(self, results_dict):
        # results_dict is {region_id: BackgroundAnalysis}
        self.results_dict = results_dict

    def analyze_many(self, source_path: str, requests):
        return tuple(
            self.results_dict.get(
                req.region_id, BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN)
            )
            for req in requests
        )


class DummyLayoutEngine:
    def __init__(self, results_dict):
        # results_dict is {region_id: TextLayoutResult}
        self.results_dict = results_dict

    def layout_text(self, input_data):
        return self.results_dict.get(input_data.text, TextLayoutResult(12.0, FitStatus.FIT, ()))


@pytest.fixture
def dummy_pdf(tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"dummy pdf content")
    return str(pdf)


@pytest.fixture
def base_project(dummy_pdf):
    return Project(
        id="p1",
        name="test",
        pdf_path=dummy_pdf,
        pdf_sha256="hash",
        pdf_size=100,
        pdf_page_count=1,
        last_viewed_page=0,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )


@pytest.fixture
def default_inspection():
    return PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=1),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=False,
    )


def build_region(
    id="r1", status=RegionStatus.TRANSLATED, text="translated", page_id=1, rect=Rect(0, 0, 100, 100)
):
    region = TranslationRegion(
        id=id,
        project_id="p1",
        page_id=page_id,
        selection_rect=rect,
        translated_text=text,
        source_text="source",
        source_fragments=(),
        translation_revision=1,
        approved_translation_revision=1,
    )
    region.status = status
    return region


def build_use_case(base_project, regions, inspection, bg_results, layout_results):
    return PreparePdfExportUseCase(
        DummyProjectRepo(base_project),
        DummyRegionRepo(regions),
        DummySourceInspector(inspection),
        DummyBackgroundAnalyzer(bg_results),
        DummyLayoutEngine(layout_results),
    )


# 1. Success Real & page_id 1-based
def test_preflight_success_real(base_project, default_inspection):
    region = build_region(page_id=1)
    bg_results = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255))
    }
    layout_results = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [region], default_inspection, bg_results, layout_results)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export
    assert len(outcome.report.issues) == 0
    assert outcome.request is not None
    assert outcome.request.specs[0].page_number == 1  # 1-based page


# 2. Source missing
def test_preflight_source_missing(base_project, default_inspection):
    base_project.pdf_path = "non_existent.pdf"
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    assert outcome.report.issues[0].code == PreflightIssueCode.SOURCE_MISSING


# 3. Project Locked (SHA mismatch)
def test_preflight_sha_mismatch(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="wrong_hash", size=100, page_count=1),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=False,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    codes = [i.code for i in outcome.report.issues]
    assert PreflightIssueCode.FINGERPRINT_MISMATCH in codes
    assert PreflightIssueCode.PROJECT_LOCKED in codes


# 4. Project Locked (Size mismatch)
def test_preflight_size_mismatch(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=999, page_count=1),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=False,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    codes = [i.code for i in outcome.report.issues]
    assert PreflightIssueCode.FINGERPRINT_MISMATCH in codes
    assert PreflightIssueCode.PROJECT_LOCKED in codes


# 5. Page count mismatch
def test_preflight_page_count_mismatch(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=2),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=False,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    codes = [i.code for i in outcome.report.issues]
    assert PreflightIssueCode.PAGE_COUNT_MISMATCH in codes


# 6. Encrypted
def test_preflight_encrypted(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=1),
        is_encrypted=True,
        needs_authentication=False,
        has_digital_signatures=False,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    assert PreflightIssueCode.ENCRYPTED_SOURCE in [i.code for i in outcome.report.issues]


# 7. Needs authentication
def test_preflight_needs_authentication(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=1),
        is_encrypted=False,
        needs_authentication=True,
        has_digital_signatures=False,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    assert PreflightIssueCode.ENCRYPTED_SOURCE in [i.code for i in outcome.report.issues]


# 8. Signed
def test_preflight_signed(base_project, default_inspection):
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=1),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=True,
    )
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    assert PreflightIssueCode.SIGNED_SOURCE in [i.code for i in outcome.report.issues]


# 9. No regions
def test_preflight_no_regions(base_project, default_inspection):
    uc = build_use_case(base_project, [], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")
    assert not outcome.report.can_export
    assert outcome.report.issues[0].code == PreflightIssueCode.NO_EXPORTABLE_REGIONS


# 10. PENDING BLOCK
def test_preflight_pending_block(base_project, default_inspection):
    region = build_region(status=RegionStatus.PENDING)
    uc = build_use_case(base_project, [region], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf", pending_policy=PendingRegionPolicy.BLOCK)
    assert not outcome.report.can_export
    issues = [i for i in outcome.report.issues if i.code == PreflightIssueCode.PENDING_REGIONS]
    assert issues[0].severity == PreflightSeverity.BLOCKER


# 11. PENDING EXPORT_TRANSLATED_ONLY
def test_preflight_pending_allow(base_project, default_inspection):
    r1 = build_region(id="r1", status=RegionStatus.PENDING)
    r2 = build_region(id="r2", status=RegionStatus.TRANSLATED)
    bg = {"r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255))}
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute(
        "p1", "dest.pdf", pending_policy=PendingRegionPolicy.EXPORT_TRANSLATED_ONLY
    )

    assert outcome.report.can_export
    issues = [i for i in outcome.report.issues if i.code == PreflightIssueCode.PENDING_REGIONS]
    assert issues[0].severity == PreflightSeverity.WARNING
    assert len(outcome.request.specs) == 1


# 12. TRANSLATED empty
def test_preflight_translated_empty(base_project, default_inspection):
    r1 = build_region(id="r1", status=RegionStatus.TRANSLATED, text="   ")
    uc = build_use_case(base_project, [r1], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")

    assert not outcome.report.can_export
    codes = [i.code for i in outcome.report.issues]
    assert PreflightIssueCode.NO_EXPORTABLE_REGIONS in codes
    assert PreflightIssueCode.INVALID_REGION_STATUS in codes


# 13. OVERFLOW
def test_preflight_overflow(base_project, default_inspection):
    r1 = build_region()
    bg = {"r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255))}
    layout = {"translated": TextLayoutResult(12.0, FitStatus.OVERFLOW, ())}

    uc = build_use_case(base_project, [r1], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert not outcome.report.can_export
    assert outcome.report.issues[0].code == PreflightIssueCode.OVERFLOW


# 14. Various statuses
@pytest.mark.parametrize(
    "status",
    [
        RegionStatus.REVIEWED,
        RegionStatus.READY_FOR_EXPORT,
        RegionStatus.EXPORTED,
        RegionStatus.ERROR,
        RegionStatus.IGNORED,
    ],
)
def test_preflight_various_statuses(base_project, default_inspection, status):
    r1 = build_region(status=status)
    uc = build_use_case(base_project, [r1], default_inspection, {}, {})
    outcome = uc.execute("p1", "dest.pdf")

    assert not outcome.report.can_export
    assert PreflightIssueCode.INVALID_REGION_STATUS in [i.code for i in outcome.report.issues]


# 15. Backgrounds
@pytest.mark.parametrize(
    "bg_class, is_exportable",
    [
        (BackgroundClassification.UNIFORM_WHITE, True),
        (BackgroundClassification.UNIFORM_COLOR, True),
        (BackgroundClassification.COMPLEX_BACKGROUND, False),
        (BackgroundClassification.UNKNOWN, False),
    ],
)
def test_preflight_backgrounds(base_project, default_inspection, bg_class, is_exportable):
    r1 = build_region()
    rgb = (255, 255, 255) if bg_class == BackgroundClassification.UNIFORM_WHITE else (128, 128, 128)
    bg = {"r1": BackgroundAnalysis("r1", bg_class, rgb)}
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export == is_exportable


# 16. Overlaps
def test_preflight_overlaps_greater_than_epsilon(base_project, default_inspection):
    r1 = build_region(id="r1", rect=Rect(0, 0, 10, 10))
    r2 = build_region(id="r2", rect=Rect(5, 5, 15, 15))  # Intersection is 5x5 = 25 pt2

    bg = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
        "r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
    }
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert not outcome.report.can_export
    assert PreflightIssueCode.OVERLAP in [i.code for i in outcome.report.issues]


def test_preflight_overlaps_less_than_epsilon(base_project, default_inspection):
    r1 = build_region(id="r1", rect=Rect(0, 0, 10, 10))
    r2 = build_region(id="r2", rect=Rect(9.5, 9.5, 15, 15))  # Intersection is 0.5x0.5 = 0.25 pt2

    bg = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
        "r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
    }
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export


def test_preflight_touching_edges(base_project, default_inspection):
    r1 = build_region(id="r1", rect=Rect(0, 0, 10, 10))
    r2 = build_region(id="r2", rect=Rect(10, 0, 20, 10))  # Touching

    bg = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
        "r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
    }
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export


def test_preflight_different_pages(base_project, default_inspection):
    base_project.pdf_page_count = 2
    default_inspection = PdfSourceInspection(
        fingerprint=PdfFingerprint(sha256="hash", size=100, page_count=2),
        is_encrypted=False,
        needs_authentication=False,
        has_digital_signatures=False,
    )
    r1 = build_region(id="r1", rect=Rect(0, 0, 10, 10), page_id=1)
    r2 = build_region(id="r2", rect=Rect(0, 0, 10, 10), page_id=2)  # Same coords, diff page

    bg = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
        "r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
    }
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export


def test_preflight_deterministic_ordering(base_project, default_inspection):
    r1 = build_region(id="r1", rect=Rect(100, 100, 200, 200))
    r2 = build_region(id="r2", rect=Rect(0, 0, 10, 10))

    bg = {
        "r1": BackgroundAnalysis("r1", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
        "r2": BackgroundAnalysis("r2", BackgroundClassification.UNIFORM_WHITE, (255, 255, 255)),
    }
    layout = {"translated": TextLayoutResult(12.0, FitStatus.FIT, ())}

    uc = build_use_case(base_project, [r1, r2], default_inspection, bg, layout)
    outcome = uc.execute("p1", "dest.pdf")

    assert outcome.report.can_export
    # Ordering is by page_id, y0, x0, region_id
    assert outcome.request.specs[0].region_id == "r2"
    assert outcome.request.specs[1].region_id == "r1"
