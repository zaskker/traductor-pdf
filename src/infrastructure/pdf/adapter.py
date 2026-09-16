import os

import pymupdf as fitz

from src.application.dtos.rendered_page import RenderedPage
from src.application.ports.pdf_coordinate_mapper import IPdfCoordinateMapper
from src.application.ports.pdf_document import IPdfDocument
from src.application.ports.text_extractor import ITextExtractor
from src.infrastructure.pdf.coordinate_mapper import PyMuPDFCoordinateMapper


class PyMuPDFDocument(IPdfDocument):
    def __init__(self):
        self._doc: fitz.Document | None = None
        self._file_path: str | None = None

    def open(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")
            
        try:
            doc = fitz.open(file_path)
            if doc.needs_pass:
                doc.close()
                raise ValueError("Este PDF está protegido con contraseña y no puede abrirse en esta versión.")
        except ValueError as e:
            raise e
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Failed to open PDF: {e}")
            
        self.close()  # Close any existing open document
        self._doc = doc
        self._file_path = file_path

    def close(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None
            self._file_path = None

    def get_page_count(self) -> int:
        if not self._doc:
            return 0
        return len(self._doc)

    def render_page(self, page_index: int, render_scale: float = 1.0) -> RenderedPage:
        if not self._doc:
            raise RuntimeError("Document is not open")

        if page_index < 0 or page_index >= len(self._doc):
            raise IndexError(f"Page index out of range: {page_index}")

        page = self._doc[page_index]
        matrix = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Determine format (usually RGB or RGBA)
        fmt = "RGB888"
        if pix.alpha:
            fmt = "RGBA8888"

        # We need the logical dimensions for tracking
        logical_width = page.rect.width
        logical_height = page.rect.height

        return RenderedPage(
            page_number=page_index + 1,  # 1-based internally for the DTO
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            samples=pix.samples,
            format=fmt,
            render_scale=render_scale,
            logical_width=logical_width,
            logical_height=logical_height,
        )

    def get_coordinate_mapper(
        self, page_index: int, render_scale: float = 1.0
    ) -> IPdfCoordinateMapper:
        if not self._doc:
            raise RuntimeError("Document is not open")
        if page_index < 0 or page_index >= len(self._doc):
            raise IndexError(f"Page index out of range: {page_index}")

        page = self._doc[page_index]
        matrix = fitz.Matrix(render_scale, render_scale)

        return PyMuPDFCoordinateMapper(matrix)

    def extract_text_dict_native(
        self, page_index: int, clip_coords: tuple[float, float, float, float], flags: int
    ) -> dict:
        """Internal Infrastructure API, never exposed above Infrastructure."""
        if not self._doc:
            raise RuntimeError("Document is not open")
        if page_index < 0 or page_index >= len(self._doc):
            raise ValueError(f"Page index out of range: {page_index}")

        page = self._doc[page_index]
        clip = fitz.Rect(*clip_coords)
        return page.get_text("dict", clip=clip, flags=flags)

    def extract_words_native(
        self, page_index: int, clip_coords: tuple[float, float, float, float]
    ) -> list:
        """Internal Infrastructure API, never exposed above Infrastructure."""
        if not self._doc:
            raise RuntimeError("Document is not open")
        if page_index < 0 or page_index >= len(self._doc):
            raise ValueError(f"Page index out of range: {page_index}")

        page = self._doc[page_index]
        clip = fitz.Rect(*clip_coords)
        return page.get_text("words", clip=clip)

    def get_text_extractor(self) -> ITextExtractor:
        from src.infrastructure.pdf.text_extractor import PyMuPDFTextExtractor

        return PyMuPDFTextExtractor(self)
