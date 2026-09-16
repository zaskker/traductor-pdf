from src.domain.value_objects.layout import RenderedTextPreview
from src.ui.components.translation_preview_item import qimage_from_rendered_text_preview


def test_qimage_from_rendered_text_preview_aligned():
    preview = RenderedTextPreview(
        samples=b"\xff\x00\x00" * 4 * 2,  # 4 pixels wide * 2 rows * 3 channels = 24 bytes
        width=4,
        height=2,
        channels=3,
        stride=12,
        render_scale=1.0,
    )

    img = qimage_from_rendered_text_preview(preview)

    assert img.width() == 4
    assert img.height() == 2
    assert not img.isNull()

    # Check pixels
    for y in range(2):
        for x in range(4):
            assert img.pixelColor(x, y).red() == 255
            assert img.pixelColor(x, y).green() == 0
            assert img.pixelColor(x, y).blue() == 0


def test_qimage_from_rendered_text_preview_unaligned():
    # Width = 3, Channels = 3.
    # Minimum bytes per row = 9.
    # Let's use stride = 10, which means there's 1 padding byte per row.
    # We construct a buffer with 2 rows.
    # Row 1: 3 pixels of Red (255, 0, 0), padding = \x00
    # Row 2: 3 pixels of Green (0, 255, 0), padding = \x00
    row1 = b"\xff\x00\x00" * 3 + b"\x00"
    row2 = b"\x00\xff\x00" * 3 + b"\x00"
    samples = row1 + row2

    preview = RenderedTextPreview(
        samples=samples, width=3, height=2, channels=3, stride=10, render_scale=1.0
    )

    img = qimage_from_rendered_text_preview(preview)

    assert img.width() == 3
    assert img.height() == 2
    assert not img.isNull()

    # Check pixels in Row 1 (all should be red)
    for x in range(3):
        color = img.pixelColor(x, 0)
        assert color.red() == 255
        assert color.green() == 0
        assert color.blue() == 0

    # Check pixels in Row 2 (all should be green)
    # If stride was ignored (assumed 12 due to 32-bit alignment), this would fail because
    # row 2's data would start at offset 12 instead of 10.
    for x in range(3):
        color = img.pixelColor(x, 1)
        assert color.red() == 0
        assert color.green() == 255
        assert color.blue() == 0


def test_qimage_from_rendered_text_preview_pymupdf_like():
    # PyMuPDF typically uses tight packing for RGB (stride = width * 3)
    # width = 101, channels = 3, stride = 303 (not aligned to 4)
    # 303 % 4 = 3 != 0
    # Let's fill the buffer with alternating colors per row
    row_bytes = []
    for y in range(4):
        if y % 2 == 0:
            row_bytes.append(b"\x00\x00\xff" * 101)  # Blue
        else:
            row_bytes.append(b"\xff\xff\x00" * 101)  # Yellow

    samples = b"".join(row_bytes)

    preview = RenderedTextPreview(
        samples=samples, width=101, height=4, channels=3, stride=303, render_scale=2.0
    )

    img = qimage_from_rendered_text_preview(preview)

    assert img.width() == 101
    assert img.height() == 4

    for y in range(4):
        for x in range(101):
            c = img.pixelColor(x, y)
            if y % 2 == 0:
                assert c.red() == 0 and c.green() == 0 and c.blue() == 255
            else:
                assert c.red() == 255 and c.green() == 255 and c.blue() == 0
