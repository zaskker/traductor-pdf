import pymupdf as fitz

from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper
from src.domain.value_objects.geometry import Point, Rect


class PyMuPDFCoordinateMapper(IPdfCoordinateMapper):
    """
    Implementación del coordinate mapper usando fitz.Matrix internamente.
    """

    def __init__(self, render_matrix: fitz.Matrix):
        self._matrix = render_matrix
        self._inv_matrix = ~render_matrix

    def rendered_point_to_pdf(self, pt: Point) -> Point:
        f_pt = fitz.Point(pt.x, pt.y) * self._inv_matrix
        return Point(f_pt.x, f_pt.y)

    def pdf_point_to_rendered(self, pt: Point) -> Point:
        f_pt = fitz.Point(pt.x, pt.y) * self._matrix
        return Point(f_pt.x, f_pt.y)

    def rendered_rect_to_pdf(self, rect: Rect) -> Rect:
        # Mapear 4 esquinas para máxima precisión geométrica sin boundingRect expansion ciega
        p1 = self.rendered_point_to_pdf(Point(rect.x0, rect.y0))
        p2 = self.rendered_point_to_pdf(Point(rect.x1, rect.y0))
        p3 = self.rendered_point_to_pdf(Point(rect.x0, rect.y1))
        p4 = self.rendered_point_to_pdf(Point(rect.x1, rect.y1))

        return Rect(
            x0=min(p1.x, p2.x, p3.x, p4.x),
            y0=min(p1.y, p2.y, p3.y, p4.y),
            x1=max(p1.x, p2.x, p3.x, p4.x),
            y1=max(p1.y, p2.y, p3.y, p4.y),
        )

    def pdf_rect_to_rendered(self, rect: Rect) -> Rect:
        p1 = self.pdf_point_to_rendered(Point(rect.x0, rect.y0))
        p2 = self.pdf_point_to_rendered(Point(rect.x1, rect.y0))
        p3 = self.pdf_point_to_rendered(Point(rect.x0, rect.y1))
        p4 = self.pdf_point_to_rendered(Point(rect.x1, rect.y1))

        return Rect(
            x0=min(p1.x, p2.x, p3.x, p4.x),
            y0=min(p1.y, p2.y, p3.y, p4.y),
            x1=max(p1.x, p2.x, p3.x, p4.x),
            y1=max(p1.y, p2.y, p3.y, p4.y),
        )
