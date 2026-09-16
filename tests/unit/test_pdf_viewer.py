import pytest

from src.application.dtos.rendered_page import RenderedPage
from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper
from src.application.ports.pdf_document import IPdfDocument
from src.application.services.pdf_viewer_service import PdfViewerService
from src.domain.value_objects.geometry import Point, Rect
from src.ui.viewmodels.pdf_viewer_viewmodel import PdfViewerViewModel, ZoomMode


class FakeMapper(IPdfCoordinateMapper):
    def rendered_point_to_pdf(self, pt: Point) -> Point:
        return Point(pt.x / 1.5, pt.y / 1.5)

    def pdf_point_to_rendered(self, pt: Point) -> Point:
        return Point(pt.x * 1.5, pt.y * 1.5)

    def rendered_rect_to_pdf(self, rect: Rect) -> Rect:
        return Rect(rect.x0 / 1.5, rect.y0 / 1.5, rect.x1 / 1.5, rect.y1 / 1.5)

    def pdf_rect_to_rendered(self, rect: Rect) -> Rect:
        return Rect(rect.x0 * 1.5, rect.y0 * 1.5, rect.x1 * 1.5, rect.y1 * 1.5)


class FakePdfDocument(IPdfDocument):
    def __init__(self, num_pages=5):
        self._is_open = False
        self._num_pages = num_pages

    def open(self, file_path: str) -> None:
        if file_path == "invalid":
            raise RuntimeError("Invalid file")
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def get_page_count(self) -> int:
        return self._num_pages if self._is_open else 0

    def render_page(self, page_index: int, render_scale: float = 1.0) -> RenderedPage:
        if not self._is_open or page_index < 0 or page_index >= self._num_pages:
            raise IndexError()
        return RenderedPage(
            page_number=page_index + 1,
            width=800,
            height=600,
            stride=800 * 3,
            samples=b"",
            format="RGB888",
            render_scale=render_scale,
            logical_width=800,
            logical_height=600,
        )

    def get_coordinate_mapper(
        self, page_index: int, render_scale: float = 1.0
    ) -> IPdfCoordinateMapper:
        return FakeMapper()


def test_service_navigation():
    adapter = FakePdfDocument(3)
    service = PdfViewerService(adapter)

    assert service.get_page_count() == 0

    service.open_document("valid.pdf")
    assert service.get_page_count() == 3
    assert service.get_current_page_number() == 1

    assert service.next_page() is True
    assert service.get_current_page_number() == 2

    assert service.next_page() is True
    assert service.next_page() is False  # Already at last page
    assert service.get_current_page_number() == 3

    assert service.previous_page() is True
    assert service.get_current_page_number() == 2

    assert service.go_to_page(1) is True
    assert service.get_current_page_number() == 1

    assert service.go_to_page(99) is False
    assert service.go_to_page(0) is False
    assert service.get_current_page_number() == 1


def test_viewmodel_initial_state():
    adapter = FakePdfDocument()
    service = PdfViewerService(adapter)
    vm = PdfViewerViewModel(service)

    assert vm.document_loaded is False
    assert vm.current_page == 0
    assert vm.page_count == 0
    assert vm.zoom_mode == ZoomMode.FIT_WIDTH
    assert vm.zoom_factor == 1.0


def test_viewmodel_zoom_state():
    adapter = FakePdfDocument()
    service = PdfViewerService(adapter)
    vm = PdfViewerViewModel(service)

    vm.zoom_in()
    assert vm.zoom_mode == ZoomMode.CUSTOM
    assert vm.zoom_factor == 1.25

    vm.zoom_out()
    assert vm.zoom_factor == 1.0

    vm.set_zoom_mode(ZoomMode.ACTUAL_SIZE)
    assert vm.zoom_factor == 1.0
    assert vm.zoom_mode == ZoomMode.ACTUAL_SIZE

    # Check limits
    vm.set_custom_zoom(10.0)
    assert vm.zoom_factor == 4.0

    vm.set_custom_zoom(0.1)
    assert vm.zoom_factor == 0.25


def test_viewmodel_open_close(monkeypatch):
    monkeypatch.setattr('os.path.exists', lambda x: True)
    import pymupdf
    class FakeDoc:
        needs_pass = False
        def close(self): pass
    monkeypatch.setattr(pymupdf, 'open', lambda x: FakeDoc())
    adapter = FakePdfDocument(5)
    service = PdfViewerService(adapter)
    vm = PdfViewerViewModel(service)

    events = []
    vm.document_loaded_changed.connect(lambda x: events.append(("loaded", x)))
    vm.current_page_changed.connect(lambda x: events.append(("page", x)))

    vm.open_document("test.pdf")
    assert vm.document_loaded is True
    assert vm.current_page == 1
    assert vm.page_count == 5

    assert ("loaded", True) in events
    assert ("page", 1) in events

    vm.close_document()
    assert vm.document_loaded is False
    assert ("loaded", False) in events


def test_service_zero_pages():
    adapter = FakePdfDocument(0)
    service = PdfViewerService(adapter)

    with pytest.raises(ValueError, match="0 pages"):
        service.open_document("test.pdf")

    assert service.get_page_count() == 0
    assert service._is_open is False


def test_viewmodel_out_of_bounds_navigation(monkeypatch):
    monkeypatch.setattr('os.path.exists', lambda x: True)
    import pymupdf
    class FakeDoc:
        needs_pass = False
        def close(self): pass
    monkeypatch.setattr(pymupdf, 'open', lambda x: FakeDoc())
    adapter = FakePdfDocument(3)
    service = PdfViewerService(adapter)
    vm = PdfViewerViewModel(service)

    vm.open_document("test.pdf")
    assert vm.current_page == 1

    success = vm.go_to_page(999)
    assert success is False
    assert vm.current_page == 1

    success = vm.go_to_page(0)
    assert success is False
    assert vm.current_page == 1


def test_viewmodel_selection(monkeypatch):
    monkeypatch.setattr('os.path.exists', lambda x: True)
    import pymupdf
    class FakeDoc:
        needs_pass = False
        def close(self): pass
    monkeypatch.setattr(pymupdf, 'open', lambda x: FakeDoc())
    adapter = FakePdfDocument(3)
    service = PdfViewerService(adapter)
    vm = PdfViewerViewModel(service)

    vm.open_document("test.pdf")

    assert vm.is_selection_mode is False
    assert vm.current_selection is None

    events = []
    vm.selection_mode_changed.connect(lambda x: events.append(("mode", x)))
    vm.selection_changed.connect(lambda x: events.append(("selection", x)))

    vm.set_selection_mode(True)
    assert vm.is_selection_mode is True
    assert ("mode", True) in events

    # Commit selection (render space is 800x600, zoom 1.5 default)
    # rendered_rect in FakePdfDocument is scaled by render_scale
    rendered_rect = Rect(0, 0, 150, 150)
    vm.commit_selection(rendered_rect)

    assert vm.current_selection is not None
    assert vm.current_selection.page_number == 1
    # PDF rect should be scaled back by 1.5
    assert abs(vm.current_selection.pdf_rect.x1 - 100.0) < 1e-4

    # Change page clears selection
    vm.next_page()
    assert vm.current_selection is None
