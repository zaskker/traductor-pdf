import fitz
import pytest

from src.application.dtos.export import BackgroundAnalysisRequest, BackgroundClassification
from src.domain.value_objects.geometry import Rect
from src.infrastructure.pdf.background_analyzer import PyMuPDFRegionBackgroundAnalyzer


@pytest.fixture(scope="module")
def sample_pdf_path(tmp_path_factory):
    pdf_path = tmp_path_factory.mktemp("data") / "test_bg.pdf"
    doc = fitz.open()

    # Page 1: Uniform White
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 1, 1), fill=(1, 1, 1))

    # Page 2: Uniform Color (Red)
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 0, 0), fill=(1, 0, 0))

    # Page 3: Complex (Gradient-like or two colors)
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 100, 200), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(fitz.Rect(100, 0, 200, 200), color=(0, 0, 1), fill=(0, 0, 1))

    # Page 4: Text exclusion test (Red background with black text/blocks in the middle)
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 0, 0), fill=(1, 0, 0))
    # Draw a black box representing text
    page.draw_rect(fitz.Rect(50, 50, 150, 150), color=(0, 0, 0), fill=(0, 0, 0))

    # Page 5: Center line (White with a black line in the middle)
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 1, 1), fill=(1, 1, 1))
    page.draw_line(fitz.Point(0, 100), fitz.Point(200, 100), color=(0, 0, 0))

    # Page 6: Vector shapes (White with a circle in the middle)
    page = doc.new_page(width=200, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 1, 1), fill=(1, 1, 1))
    page.draw_circle(fitz.Point(100, 100), 50, color=(0, 0, 0), fill=(0, 0, 0))

    # Page 7: Rotation 90 and Asymmetric CropBox
    page = doc.new_page(width=300, height=300)
    # Paint it all green
    page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(0, 1, 0), fill=(0, 1, 0))
    page.set_rotation(90)
    page.set_cropbox(fitz.Rect(20, 30, 280, 270))

    # Page 8: Raster image background
    page = doc.new_page(width=200, height=200)
    # Create a small checkerboard pixmap
    pix = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 10, 10), False)
    pix.clear_with(255)
    for y in range(10):
        for x in range(10):
            if (x + y) % 2 == 0:
                pix.set_pixel(x, y, (0, 0, 0))
    page.insert_image(fitz.Rect(0, 0, 200, 200), pixmap=pix)

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


@pytest.fixture(scope="module")
def rotation_pdf_path(tmp_path_factory):
    pdf_path = tmp_path_factory.mktemp("data") / "test_rotation.pdf"
    doc = fitz.open()

    rotations = [0, 90, 180, 270]

    # Pages 1 to 4: simple rotation
    for rot in rotations:
        page = doc.new_page(width=300, height=300)
        # Background: Green
        page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(0, 1, 0), fill=(0, 1, 0))
        # Text block: Black (from 100, 100 to 200, 200)
        page.draw_rect(fitz.Rect(100, 100, 200, 200), color=(0, 0, 0), fill=(0, 0, 0))
        page.set_rotation(rot)

    # Pages 5 to 8: rotation + asymmetric cropbox
    for rot in rotations:
        page = doc.new_page(width=300, height=300)
        # Background: Green
        page.draw_rect(fitz.Rect(0, 0, 300, 300), color=(0, 1, 0), fill=(0, 1, 0))
        # Text block: Black (from 100, 100 to 200, 200)
        page.draw_rect(fitz.Rect(100, 100, 200, 200), color=(0, 0, 0), fill=(0, 0, 0))
        page.set_rotation(rot)
        # CropBox from 20, 30 to 280, 270
        page.set_cropbox(fitz.Rect(20, 30, 280, 270))

    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


def test_bg_perfect_white(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        target_rect=Rect(10, 10, 100, 100),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]

    assert result.classification == BackgroundClassification.UNIFORM_WHITE
    assert result.background_rgb == (255, 255, 255)


def test_bg_uniform_color(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=2,
        target_rect=Rect(10, 10, 100, 100),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]

    assert result.classification == BackgroundClassification.UNIFORM_COLOR
    assert result.background_rgb == (255, 0, 0)


def test_bg_complex_background(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=3,
        target_rect=Rect(50, 50, 150, 150),  # Spans both red and blue
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]

    assert result.classification == BackgroundClassification.COMPLEX_BACKGROUND


def test_bg_text_exclusion(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    # If we don't exclude the black text, it should be complex because interior is different
    req_no_exclude = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=4,
        target_rect=Rect(10, 10, 190, 190),
        excluded_fragment_rects=(),
    )
    res_no_exclude = analyzer.analyze_many(sample_pdf_path, (req_no_exclude,))[0]
    assert res_no_exclude.classification == BackgroundClassification.COMPLEX_BACKGROUND

    # If we exclude the black text, it should just see red
    req_exclude = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=4,
        target_rect=Rect(10, 10, 190, 190),
        excluded_fragment_rects=(Rect(50, 50, 150, 150),),
    )
    res_exclude = analyzer.analyze_many(sample_pdf_path, (req_exclude,))[0]
    assert res_exclude.classification == BackgroundClassification.UNIFORM_COLOR
    assert res_exclude.background_rgb == (255, 0, 0)


def test_bg_missing_source():
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        target_rect=Rect(10, 10, 100, 100),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many("missing_file.pdf", (req,))[0]
    assert result.classification == BackgroundClassification.UNKNOWN


def test_bg_out_of_bounds_page(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=99,
        target_rect=Rect(10, 10, 100, 100),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.UNKNOWN


def test_bg_empty_rect(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        target_rect=Rect(10, 10, 10, 10),  # degenerate
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.UNKNOWN


def test_background_center_line_is_complex(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=5,
        target_rect=Rect(10, 10, 190, 190),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.COMPLEX_BACKGROUND


def test_background_vector_shape_is_complex(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=6,
        target_rect=Rect(10, 10, 190, 190),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.COMPLEX_BACKGROUND


def test_background_raster_image_is_complex(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=8,
        target_rect=Rect(10, 10, 190, 190),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.COMPLEX_BACKGROUND


def test_background_insufficient_samples_unknown(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        # 5x5 rectangle at 1.0 scale will give 25 pixels.
        # This is less than MIN_VALID_SAMPLES (50).
        target_rect=Rect(10, 10, 15, 15),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.UNKNOWN


def test_background_fragments_cover_almost_all_unknown(sample_pdf_path):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        target_rect=Rect(0, 0, 100, 100),
        # A fragment that covers everything except a 2x2 edge.
        excluded_fragment_rects=(Rect(0, 0, 100, 100),),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.UNKNOWN


def test_background_scale_mapping(sample_pdf_path):
    # Using 2.0 scale, a 5x5 PDF rect becomes a 10x10 pixmap (100 pixels),
    # which is > 50 samples and should NOT return UNKNOWN.
    analyzer = PyMuPDFRegionBackgroundAnalyzer(analysis_scale=2.0)
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=1,
        target_rect=Rect(10, 10, 15, 15),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    # At 2x scale, 5x5 is 10x10 = 100 pixels, which is enough to classify.
    assert result.classification == BackgroundClassification.UNIFORM_WHITE


def test_background_rotation_and_cropbox(sample_pdf_path):
    # The CropBox is (20, 30, 280, 270). The page is rotated 90.
    analyzer = PyMuPDFRegionBackgroundAnalyzer()
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=7,
        # A rect inside the green page.
        target_rect=Rect(50, 50, 100, 100),
        excluded_fragment_rects=(),
    )
    result = analyzer.analyze_many(sample_pdf_path, (req,))[0]
    assert result.classification == BackgroundClassification.UNIFORM_COLOR
    assert result.background_rgb == (0, 255, 0)


@pytest.mark.parametrize("page_num", [1, 2, 3, 4, 5, 6, 7, 8])
def test_background_rotation_exclusion_masking(rotation_pdf_path, page_num):
    analyzer = PyMuPDFRegionBackgroundAnalyzer()

    # If page_num > 4, it has a CropBox of (20, 30, 280, 270)
    # The black block was drawn at (100, 100, 200, 200) absolute.
    # In relative (page.rect) coordinates:
    # Pages 1-4 (no crop): (100, 100, 200, 200)
    # Pages 5-8 (crop 20, 30): (80, 70, 180, 170)

    if page_num > 4:
        ex_rect = Rect(80, 70, 180, 170)
    else:
        ex_rect = Rect(100, 100, 200, 200)

    # 1. With exclusion mask, it should see only the green background
    req_exclude = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=page_num,
        target_rect=Rect(50, 50, 220, 220),  # Inside page.rect
        excluded_fragment_rects=(ex_rect,),
    )
    res_ex = analyzer.analyze_many(rotation_pdf_path, (req_exclude,))[0]
    assert res_ex.classification == BackgroundClassification.UNIFORM_COLOR
    assert res_ex.background_rgb == (0, 255, 0)

    # 2. Control: Without exclusion mask, it should fail due to the black block
    req_no_exclude = BackgroundAnalysisRequest(
        region_id="r2",
        page_number=page_num,
        target_rect=Rect(50, 50, 220, 220),
        excluded_fragment_rects=(),
    )
    res_no = analyzer.analyze_many(rotation_pdf_path, (req_no_exclude,))[0]
    assert res_no.classification == BackgroundClassification.COMPLEX_BACKGROUND


def test_background_rotation_exclusion_with_scale(rotation_pdf_path):
    # rotation 90 (page 2), analysis_scale = 2.0
    analyzer = PyMuPDFRegionBackgroundAnalyzer(analysis_scale=2.0)
    req = BackgroundAnalysisRequest(
        region_id="r1",
        page_number=2,
        target_rect=Rect(50, 50, 250, 250),
        excluded_fragment_rects=(Rect(100, 100, 200, 200),),
    )
    res = analyzer.analyze_many(rotation_pdf_path, (req,))[0]
    assert res.classification == BackgroundClassification.UNIFORM_COLOR
    assert res.background_rgb == (0, 255, 0)
