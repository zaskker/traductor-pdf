from abc import ABC, abstractmethod

from src.domain.value_objects.geometry import Point, Rect


class IPdfCoordinateMapper(ABC):
    """
    Abstracción neutral para transformar coordenadas entre el espacio
    de píxeles renderizados (RenderedPage) y el espacio lógico del PDF.
    """

    @abstractmethod
    def rendered_point_to_pdf(self, pt: Point) -> Point:
        pass

    @abstractmethod
    def pdf_point_to_rendered(self, pt: Point) -> Point:
        pass

    @abstractmethod
    def rendered_rect_to_pdf(self, rect: Rect) -> Rect:
        """
        Debe implementarse mapeando las 4 esquinas individuales y
        reconstruyendo el bounding box para evitar expansión artificial.
        """

    @abstractmethod
    def pdf_rect_to_rendered(self, rect: Rect) -> Rect:
        pass
