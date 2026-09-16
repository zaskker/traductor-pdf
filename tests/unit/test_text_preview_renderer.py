import pytest

from src.domain.value_objects.geometry import Rect
from src.application.dtos.export import ExportTextBlockSpec
from src.domain.models.enums import TextAlignment, TextWrapMode
from src.infrastructure.pdf.preview_renderer import PyMuPDFTextPreviewRenderer


def test_renderer_success():
    renderer = PyMuPDFTextPreviewRenderer()

    overlay_rect = Rect(0, 0, 100, 50)
    blocks = (
        ExportTextBlockSpec(
            rect=Rect(0, 0, 100, 50),
            translated_text="Hello Raster",
            font_size=12.0,
            font_color=(0, 0, 0),
            alignment=TextAlignment.LEFT,
            wrap_mode=TextWrapMode.WRAP
        ),
    )

    preview = renderer.render_preview(overlay_rect, blocks, 2.0, (0, 0, 0))

    assert preview.width == 200  # 100 * 2.0
    assert preview.height == 100  # 50 * 2.0
    assert preview.render_scale == 2.0
    assert preview.channels in (3, 4)
    assert preview.stride >= preview.width * preview.channels
    assert len(preview.samples) == preview.height * preview.stride
