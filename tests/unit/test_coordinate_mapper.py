import pymupdf as fitz

from src.domain.value_objects.geometry import Point, Rect
from src.infrastructure.pdf.coordinate_mapper import PyMuPDFCoordinateMapper


def test_mapper_identity():
    # Matrix 1.0 (no scaling)
    matrix = fitz.Matrix(1.0, 1.0)
    mapper = PyMuPDFCoordinateMapper(matrix)

    pt_pdf = Point(100.0, 50.0)
    pt_rendered = mapper.pdf_point_to_rendered(pt_pdf)

    assert pt_rendered.x == 100.0
    assert pt_rendered.y == 50.0

    pt_recovered = mapper.rendered_point_to_pdf(pt_rendered)
    assert pt_recovered.x == 100.0
    assert pt_recovered.y == 50.0


def test_mapper_scaling():
    # Matrix 2.0
    matrix = fitz.Matrix(2.0, 2.0)
    mapper = PyMuPDFCoordinateMapper(matrix)

    rect_pdf = Rect(10.0, 10.0, 50.0, 50.0)
    rect_rendered = mapper.pdf_rect_to_rendered(rect_pdf)

    assert rect_rendered.x0 == 20.0
    assert rect_rendered.y0 == 20.0
    assert rect_rendered.x1 == 100.0
    assert rect_rendered.y1 == 100.0

    rect_recovered = mapper.rendered_rect_to_pdf(rect_rendered)
    assert rect_recovered.x0 == 10.0
    assert rect_recovered.y0 == 10.0
    assert rect_recovered.x1 == 50.0
    assert rect_recovered.y1 == 50.0


def test_mapper_rotation():
    # Matrix rotated 90 degrees
    matrix = fitz.Matrix(90)
    mapper = PyMuPDFCoordinateMapper(matrix)

    rect_pdf = Rect(10.0, 20.0, 30.0, 40.0)
    # The mathematical bounds of a 90 deg rotation
    rect_rendered = mapper.pdf_rect_to_rendered(rect_pdf)

    # We just ensure it roundtrips precisely
    rect_recovered = mapper.rendered_rect_to_pdf(rect_rendered)

    # Float precision comparison
    assert abs(rect_recovered.x0 - 10.0) < 1e-5
    assert abs(rect_recovered.y0 - 20.0) < 1e-5
    assert abs(rect_recovered.x1 - 30.0) < 1e-5
    assert abs(rect_recovered.y1 - 40.0) < 1e-5
