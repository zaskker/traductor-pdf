from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.application.dtos.rendered_page import RenderedPage

if TYPE_CHECKING:
    from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper


class IPdfDocument(ABC):
    """
    Puerto de infraestructura para operaciones con archivos PDF.
    Encapsula por completo la librería subyacente (ej. PyMuPDF).
    """

    @abstractmethod
    def open(self, file_path: str) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def get_page_count(self) -> int:
        pass

    @abstractmethod
    def render_page(self, page_index: int, render_scale: float = 1.0) -> RenderedPage:
        """
        Renderiza la página indicada (0-based) y devuelve una estructura neutral.
        """

    @abstractmethod
    def get_coordinate_mapper(
        self, page_index: int, render_scale: float = 1.0
    ) -> "IPdfCoordinateMapper":
        """
        Devuelve el mapper neutral asociado a una página y un factor de render.
        """
