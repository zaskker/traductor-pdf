from src.application.dtos.rendered_page import RenderedPage
from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper
from src.application.ports.pdf_document import IPdfDocument


class PdfViewerService:
    """
    Coordina las operaciones del visor PDF utilizando el adaptador de infraestructura.
    Mantiene estado mínimo necesario a nivel de aplicación (ej. qué documento está abierto).
    """

    def __init__(self, pdf_adapter: IPdfDocument):
        self._pdf = pdf_adapter
        self._current_page_index = 0
        self._is_open = False

    def open_document(self, file_path: str) -> None:
        self._pdf.open(file_path)
        if self._pdf.get_page_count() <= 0:
            self._pdf.close()
            raise ValueError("The PDF document has 0 pages or is invalid.")
        self._current_page_index = 0
        self._is_open = True

    def close_document(self) -> None:
        self._pdf.close()
        self._current_page_index = 0
        self._is_open = False

    def get_page_count(self) -> int:
        if not self._is_open:
            return 0
        return self._pdf.get_page_count()

    def render_current_page(self, render_scale: float = 1.0) -> RenderedPage | None:
        if not self._is_open or self.get_page_count() == 0:
            return None
        return self._pdf.render_page(self._current_page_index, render_scale)

    def get_coordinate_mapper(self, render_scale: float = 1.0) -> IPdfCoordinateMapper | None:
        if not self._is_open or self.get_page_count() == 0:
            return None
        return self._pdf.get_coordinate_mapper(self._current_page_index, render_scale)

    def next_page(self) -> bool:
        if not self._is_open:
            return False
        if self._current_page_index < self.get_page_count() - 1:
            self._current_page_index += 1
            return True
        return False

    def previous_page(self) -> bool:
        if not self._is_open:
            return False
        if self._current_page_index > 0:
            self._current_page_index -= 1
            return True
        return False

    def go_to_page(self, page_number: int) -> bool:
        """
        Navega a una página específica.
        page_number es 1-based.
        """
        if not self._is_open:
            return False
        target_index = page_number - 1
        if 0 <= target_index < self.get_page_count():
            self._current_page_index = target_index
            return True
        return False

    def get_current_page_number(self) -> int:
        """
        Devuelve el número de página actual (1-based).
        Devuelve 0 si no hay documento abierto.
        """
        if not self._is_open or self.get_page_count() == 0:
            return 0
        return self._current_page_index + 1
