import pytest

from src.application.dtos.export import (
    ExportRegionSpec,
    ExportRequest,
    ExportResult,
    PdfFingerprint,
    ExportTextBlockSpec,
)
from src.domain.models.enums import TextAlignment, TextWrapMode
from src.application.dtos.export_ipc import ProtocolError
from src.domain.value_objects.geometry import Rect
from src.infrastructure.process.serialization import (
    deserialize_export_request,
    deserialize_export_result,
    serialize_export_request,
    serialize_export_result,
)


def test_export_request_serialization_roundtrip():
    req = ExportRequest(
        source_path="C:\\test\\source.pdf",
        destination_path="C:\\test\\dest.pdf",
        expected_fingerprint=PdfFingerprint(sha256="abc1234", size=1024, page_count=5),
        specs=(
            ExportRegionSpec(
                region_id="r1",
                page_number=1,
                pdf_rect=Rect(10.5, 20.0, 100.5, 200.0),
                translated_text="Traducción con acentos y https://example.com/docs",
                font_family="helv",
                font_size=12.0,
                font_color=(0, 0, 0),
                background_rgb=(255, 200, 100),
            ),
        ),
    )

    serialized = serialize_export_request(req)
    assert "C:\\\\test\\\\source.pdf" in serialized

    deserialized = deserialize_export_request(serialized)

    assert deserialized.source_path == req.source_path
    assert deserialized.destination_path == req.destination_path
    assert deserialized.expected_fingerprint == req.expected_fingerprint
    assert len(deserialized.specs) == 1
    assert deserialized.specs[0].region_id == "r1"
    assert deserialized.specs[0].pdf_rect.x0 == 10.5
    assert deserialized.specs[0].translated_text == req.specs[0].translated_text
    assert deserialized.specs[0].background_rgb == (255, 200, 100)


def test_export_request_rejects_nan():
    # Inject NaN into JSON
    bad_json = """
    {
        "source_path": "a",
        "destination_path": "b",
        "expected_fingerprint": {"sha256": "a", "size": 1, "page_count": 1},
        "specs": [
            {
                "region_id": "r1",
                "page_number": 1,
                "pdf_rect": {"x0": NaN, "y0": 0, "x1": 100, "y1": 100},
                "translated_text": "t",
                "font_family": "f",
                "font_size": 12.0,
                "background_rgb": [255, 255, 255]
            }
        ]
    }
    """
    with pytest.raises(ProtocolError, match="Invalid JSON constant: NaN"):
        deserialize_export_request(bad_json)


def test_export_request_rejects_infinity():
    bad_json = """
    {
        "source_path": "a",
        "destination_path": "b",
        "expected_fingerprint": {"sha256": "a", "size": 1, "page_count": 1},
        "specs": [
            {
                "region_id": "r1",
                "page_number": 1,
                "pdf_rect": {"x0": 0, "y0": 0, "x1": Infinity, "y1": 100},
                "translated_text": "t",
                "font_family": "f",
                "font_size": 12.0,
                "background_rgb": [255, 255, 255]
            }
        ]
    }
    """
    with pytest.raises(ProtocolError, match="Invalid JSON constant: Infinity"):
        deserialize_export_request(bad_json)


def test_export_result_serialization_roundtrip():
    res = ExportResult(
        destination_path="C:\\test\\dest.pdf",
        exported_regions=10,
        pages_touched=(1, 3, 5),
        warnings=("warn1",),
    )
    serialized = serialize_export_result(res)
    deserialized = deserialize_export_result(serialized)

    assert deserialized.destination_path == res.destination_path
    assert deserialized.exported_regions == res.exported_regions
    assert deserialized.pages_touched == (1, 3, 5)
    assert deserialized.warnings == ("warn1",)


def test_ipc_v3_preserves_block_layout_decisions():
    req = ExportRequest(
        source_path="C:\\test\\source.pdf",
        destination_path="C:\\test\\dest.pdf",
        expected_fingerprint=PdfFingerprint(sha256="abc1234", size=1024, page_count=5),
        specs=(
            ExportRegionSpec(
                region_id="r1",
                page_number=1,
                pdf_rect=Rect(10.5, 20.0, 100.5, 200.0),
                translated_text="dummy",
                font_family="helv",
                font_size=12.0,
                font_color=(0, 0, 0),
                background_rgb=(255, 200, 100),
                blocks=(
                    ExportTextBlockSpec(
                        rect=Rect(10, 20, 100, 50),
                        translated_text="block1",
                        font_size=12.0,
                        font_color=(0, 0, 0),
                        alignment=TextAlignment.CENTER,
                        wrap_mode=TextWrapMode.NOWRAP,
                    ),
                    ExportTextBlockSpec(
                        rect=Rect(10, 60, 100, 200),
                        translated_text="block2",
                        font_size=12.0,
                        font_color=(0, 0, 0),
                        alignment=TextAlignment.RIGHT,
                        wrap_mode=TextWrapMode.WRAP,
                    ),
                )
            ),
        ),
    )

    serialized = serialize_export_request(req)
    deserialized = deserialize_export_request(serialized)
    
    assert len(deserialized.specs[0].blocks) == 2
    
    b1 = deserialized.specs[0].blocks[0]
    assert b1.alignment == TextAlignment.CENTER
    assert b1.wrap_mode == TextWrapMode.NOWRAP

    b2 = deserialized.specs[0].blocks[1]
    assert b2.alignment == TextAlignment.RIGHT
    assert b2.wrap_mode == TextWrapMode.WRAP


def test_ipc_v3_rejects_invalid_enums():
    bad_json = """
    {
        "source_path": "a",
        "destination_path": "b",
        "expected_fingerprint": {"sha256": "a", "size": 1, "page_count": 1},
        "specs": [
            {
                "region_id": "r1",
                "page_number": 1,
                "pdf_rect": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                "translated_text": "t",
                "font_family": "f",
                "font_size": 12.0,
                "background_rgb": [255, 255, 255],
                "blocks": [
                    {
                        "rect": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                        "translated_text": "t",
                        "font_size": 12.0,
                        "alignment": "MIDDLE",
                        "wrap_mode": "FOO"
                    }
                ]
            }
        ]
    }
    """
    with pytest.raises(ProtocolError):
        deserialize_export_request(bad_json)


def test_ipc_v3_rejects_missing_alignment():
    bad_json = """
    {
        "source_path": "a",
        "destination_path": "b",
        "expected_fingerprint": {"sha256": "a", "size": 1, "page_count": 1},
        "specs": [
            {
                "region_id": "r1",
                "page_number": 1,
                "pdf_rect": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                "translated_text": "t",
                "font_family": "f",
                "font_size": 12.0,
                "background_rgb": [255, 255, 255],
                "blocks": [
                    {
                        "rect": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                        "translated_text": "t",
                        "font_size": 12.0
                    }
                ]
            }
        ]
    }
    """
    with pytest.raises(ProtocolError):
        deserialize_export_request(bad_json)

