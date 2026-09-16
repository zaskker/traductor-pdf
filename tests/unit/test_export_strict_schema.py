import json
import time

import pytest

from src.application.dtos.export_ipc import ProtocolError
from src.infrastructure.process.serialization import deserialize_export_request


def _get_base_valid_payload():
    return {
        "source_path": "C:\\test.pdf",
        "destination_path": "C:\\dest.pdf",
        "expected_fingerprint": {"sha256": "1234abcd", "size": 1024, "page_count": 1},
        "specs": [
            {
                "region_id": "r1",
                "page_number": 1,
                "pdf_rect": {"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
                "translated_text": "hello",
                "font_family": "helv",
                "font_size": 12.0,
                "font_color": [0, 0, 0],
                "background_rgb": [255, 255, 255],
            }
        ],
    }


def test_deserialize_rejects_malformed_json():
    with pytest.raises(ProtocolError, match="Malformed JSON"):
        deserialize_export_request("{bad_json")


def test_deserialize_rejects_missing_field():
    payload = _get_base_valid_payload()
    del payload["source_path"]
    with pytest.raises(ProtocolError, match="Missing required field in ExportRequest: source_path"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_wrong_numeric_type():
    payload = _get_base_valid_payload()
    payload["expected_fingerprint"]["size"] = "1024"  # String instead of int
    with pytest.raises(ProtocolError, match="Field 'size' must be of type int"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_bool_as_int():
    payload = _get_base_valid_payload()
    payload["expected_fingerprint"]["size"] = (
        True  # bool is int subclass in python, but our check is exact
    )
    with pytest.raises(ProtocolError, match="Field 'size' must be of type int, got bool"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_invalid_rgb_length():
    payload = _get_base_valid_payload()
    payload["specs"][0]["background_rgb"] = [255, 255]
    with pytest.raises(ProtocolError, match="background_rgb must have exactly 3 elements"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_invalid_rgb_value():
    payload = _get_base_valid_payload()
    payload["specs"][0]["background_rgb"] = [256, 255, 255]
    with pytest.raises(ProtocolError, match="background_rgb\\[0\\] must be 0-255"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_invalid_rect():
    payload = _get_base_valid_payload()
    del payload["specs"][0]["pdf_rect"]["x0"]
    with pytest.raises(ProtocolError, match="Missing 'x0' in Rect"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_empty_specs():
    payload = _get_base_valid_payload()
    payload["specs"] = []
    with pytest.raises(
        ProtocolError, match="ExportRequest must have at least one ExportRegionSpec"
    ):
        deserialize_export_request(json.dumps(payload))


def test_dto_value_error_wrapping():
    payload = _get_base_valid_payload()
    # Region ID empty
    payload["specs"][0]["region_id"] = ""
    with pytest.raises(ProtocolError, match="Invalid ExportRegionSpec: region_id empty"):
        deserialize_export_request(json.dumps(payload))

    # Reversed Rect
    payload = _get_base_valid_payload()
    payload["specs"][0]["pdf_rect"]["x0"] = 100.0
    payload["specs"][0]["pdf_rect"]["x1"] = 0.0
    with pytest.raises(ProtocolError, match="Invalid ExportRegionSpec.*Coordenadas inv.lidas"):
        deserialize_export_request(json.dumps(payload))

    # Invalid page number
    payload = _get_base_valid_payload()
    payload["specs"][0]["page_number"] = -1
    with pytest.raises(ProtocolError, match="Invalid ExportRegionSpec: page_number < 1"):
        deserialize_export_request(json.dumps(payload))


def test_deserialize_rejects_json_constants():
    # NaN
    payload = _get_base_valid_payload()
    payload["expected_fingerprint"]["size"] = float("nan")
    with pytest.raises(ProtocolError, match="Invalid JSON constant: NaN"):
        deserialize_export_request(json.dumps(payload, allow_nan=True))

    # Infinity
    payload = _get_base_valid_payload()
    payload["expected_fingerprint"]["size"] = float("inf")
    with pytest.raises(ProtocolError, match="Invalid JSON constant: Infinity"):
        deserialize_export_request(json.dumps(payload, allow_nan=True))

    # -Infinity
    payload = _get_base_valid_payload()
    payload["expected_fingerprint"]["size"] = float("-inf")
    with pytest.raises(ProtocolError, match="Invalid JSON constant: -Infinity"):
        deserialize_export_request(json.dumps(payload, allow_nan=True))


def test_literal_technical_text_is_valid():
    payload = _get_base_valid_payload()

    # "NaN" string
    payload["specs"][0]["translated_text"] = "NaN"
    req = deserialize_export_request(json.dumps(payload))
    assert req.specs[0].translated_text == "NaN"

    # "Infinity" string
    payload["specs"][0]["translated_text"] = "Infinity"
    req = deserialize_export_request(json.dumps(payload))
    assert req.specs[0].translated_text == "Infinity"

    # "IEEE Infinity and NaN values"
    payload["specs"][0]["translated_text"] = "IEEE Infinity and NaN values"
    req = deserialize_export_request(json.dumps(payload))
    assert req.specs[0].translated_text == "IEEE Infinity and NaN values"


def test_large_request_serialization_5000_specs():
    payload = _get_base_valid_payload()

    specs = []
    for i in range(5000):
        spec = dict(payload["specs"][0])
        spec["region_id"] = f"r{i}"
        specs.append(spec)

    payload["specs"] = specs
    json_str = json.dumps(payload)

    start = time.time()
    req = deserialize_export_request(json_str)
    duration = time.time() - start

    assert len(req.specs) == 5000
    print(f"Deserialization of 5000 specs took {duration:.3f}s, size={len(json_str) / 1024:.1f} KB")
