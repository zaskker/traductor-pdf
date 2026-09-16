import json
from typing import Any

from src.application.dtos.export import (
    ExportRegionSpec,
    ExportRequest,
    ExportResult,
    ExportTextBlockSpec,
    PdfFingerprint,
)
from src.application.dtos.export_ipc import ProtocolError
from src.application.ports.export_progress import ExportProgress, ExportStage
from src.domain.models.enums import TextAlignment, TextWrapMode
from src.domain.value_objects.geometry import Rect


def _require_type(val: Any, expected_type: type, field_name: str) -> None:
    if type(val) is not expected_type:
        raise ProtocolError(
            f"Field '{field_name}' must be of type {expected_type.__name__}, got {type(val).__name__}"
        )


def _reject_unknown_fields(d: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(d.keys()) - allowed
    if unknown:
        raise ProtocolError(f"Unknown fields in {context}: {unknown}")


def _rect_to_dict(r: Rect) -> dict[str, float]:
    return {"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1}


def _dict_to_rect(d: dict[str, Any]) -> Rect:
    _require_type(d, dict, "pdf_rect")
    _reject_unknown_fields(d, {"x0", "y0", "x1", "y1"}, "Rect")
    for key in ("x0", "y0", "x1", "y1"):
        if key not in d:
            raise ProtocolError(f"Missing '{key}' in Rect")
        if type(d[key]) not in (int, float):
            raise ProtocolError(f"Rect component '{key}' must be numeric")
    return Rect(x0=float(d["x0"]), y0=float(d["y0"]), x1=float(d["x1"]), y1=float(d["y1"]))


def strict_json_loads(json_str: str) -> Any:
    try:
        return json.loads(json_str, parse_constant=_raise_invalid_constant)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Malformed JSON: {e}")


def serialize_export_request(req: ExportRequest) -> str:
    def _block_to_dict(b: ExportTextBlockSpec) -> dict:
        return {
            "rect": _rect_to_dict(b.rect),
            "translated_text": b.translated_text,
            "font_size": b.font_size,
            "font_color": list(b.font_color),
            "alignment": b.alignment.name,
            "wrap_mode": b.wrap_mode.name,
        }

    payload = {
        "source_path": req.source_path,
        "destination_path": req.destination_path,
        "expected_fingerprint": {
            "sha256": req.expected_fingerprint.sha256,
            "size": req.expected_fingerprint.size,
            "page_count": req.expected_fingerprint.page_count,
        },
        "specs": [
            {
                "region_id": spec.region_id,
                "page_number": spec.page_number,
                "pdf_rect": _rect_to_dict(spec.pdf_rect),
                "translated_text": spec.translated_text,
                "font_family": spec.font_family,
                "font_size": spec.font_size,
                "font_color": list(spec.font_color),
                "background_rgb": list(spec.background_rgb),
                "blocks": [_block_to_dict(b) for b in spec.blocks],
            }
            for spec in req.specs
        ],
    }
    return json.dumps(payload, allow_nan=False)


def deserialize_export_request(json_str: str) -> ExportRequest:
    data = strict_json_loads(json_str)

    _require_type(data, dict, "root")
    _reject_unknown_fields(
        data, {"source_path", "destination_path", "expected_fingerprint", "specs"}, "ExportRequest"
    )

    for k in ("source_path", "destination_path", "expected_fingerprint", "specs"):
        if k not in data:
            raise ProtocolError(f"Missing required field in ExportRequest: {k}")

    _require_type(data["source_path"], str, "source_path")
    _require_type(data["destination_path"], str, "destination_path")

    fp_data = data["expected_fingerprint"]
    _require_type(fp_data, dict, "expected_fingerprint")
    _reject_unknown_fields(fp_data, {"sha256", "size", "page_count"}, "PdfFingerprint")
    for k in ("sha256", "size", "page_count"):
        if k not in fp_data:
            raise ProtocolError(f"Missing required field in PdfFingerprint: {k}")

    _require_type(fp_data["sha256"], str, "sha256")
    _require_type(fp_data["size"], int, "size")
    _require_type(fp_data["page_count"], int, "page_count")
    try:
        fingerprint = PdfFingerprint(
            sha256=str(fp_data["sha256"]),
            size=int(fp_data["size"]),
            page_count=int(fp_data["page_count"]),
        )
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"Invalid PdfFingerprint: {e}") from e

    specs = []
    seen_ids = set()
    _require_type(data["specs"], list, "specs")
    if not data["specs"]:
        raise ProtocolError("ExportRequest must have at least one ExportRegionSpec")

    for s in data["specs"]:
        _require_type(s, dict, "spec")
        _reject_unknown_fields(
            s,
            {
                "region_id",
                "page_number",
                "pdf_rect",
                "translated_text",
                "font_family",
                "font_size",
                "font_color",
                "background_rgb",
                "blocks",  # v2: optional structured blocks
            },
            "ExportRegionSpec",
        )
        for k in (
            "region_id",
            "page_number",
            "pdf_rect",
            "translated_text",
            "font_family",
            "font_size",
            "font_color",
            "background_rgb",
        ):
            if k not in s:
                raise ProtocolError(f"Missing required field in ExportRegionSpec: {k}")

        _require_type(s["region_id"], str, "region_id")
        if s["region_id"] in seen_ids:
            raise ProtocolError(f"Duplicate region_id: {s['region_id']}")
        seen_ids.add(s["region_id"])
        _require_type(s["page_number"], int, "page_number")
        _require_type(s["translated_text"], str, "translated_text")
        _require_type(s["font_family"], str, "font_family")
        if type(s["font_size"]) not in (int, float):
            raise ProtocolError("font_size must be numeric")

        rgb = s["background_rgb"]
        _require_type(rgb, list, "background_rgb")
        if len(rgb) != 3:
            raise ProtocolError("background_rgb must have exactly 3 elements")
        for i, val in enumerate(rgb):
            _require_type(val, int, f"background_rgb[{i}]")
            if not (0 <= val <= 255):
                raise ProtocolError(f"background_rgb[{i}] must be 0-255")
                
        f_color = s.get("font_color", [0, 0, 0])
        _require_type(f_color, list, "font_color")
        if len(f_color) != 3:
            raise ProtocolError("font_color must have exactly 3 elements")
        for i, val in enumerate(f_color):
            _require_type(val, int, f"font_color[{i}]")
            if not (0 <= val <= 255):
                raise ProtocolError(f"font_color[{i}] must be 0-255")

        # Deserialize blocks (v2, optional)
        raw_blocks = s.get("blocks", [])
        _require_type(raw_blocks, list, "blocks")
        blocks_list: list[ExportTextBlockSpec] = []
        for rb in raw_blocks:
            _require_type(rb, dict, "block")
            _reject_unknown_fields(
                rb, {"rect", "translated_text", "font_size", "font_color", "alignment", "wrap_mode"}, "ExportTextBlockSpec"
            )
            for k in ("rect", "translated_text", "font_size", "font_color", "alignment", "wrap_mode"):
                if k not in rb:
                    raise ProtocolError(f"Missing '{k}' in ExportTextBlockSpec")
            _require_type(rb["translated_text"], str, "block.translated_text")
            _require_type(rb["alignment"], str, "block.alignment")
            _require_type(rb["wrap_mode"], str, "block.wrap_mode")
            if type(rb["font_size"]) not in (int, float):
                raise ProtocolError("block.font_size must be numeric")
            
            b_color = rb.get("font_color", [0, 0, 0])
            _require_type(b_color, list, "block.font_color")
            if len(b_color) != 3:
                raise ProtocolError("block.font_color must have exactly 3 elements")
            
            try:
                alignment = TextAlignment[rb["alignment"]]
            except KeyError:
                raise ProtocolError(f"Invalid TextAlignment: {rb['alignment']}")
                
            try:
                wrap_mode = TextWrapMode[rb["wrap_mode"]]
            except KeyError:
                raise ProtocolError(f"Invalid TextWrapMode: {rb['wrap_mode']}")

            try:
                blocks_list.append(
                    ExportTextBlockSpec(
                        rect=_dict_to_rect(rb["rect"]),
                        translated_text=rb["translated_text"],
                        font_size=float(rb["font_size"]),
                        font_color=(b_color[0], b_color[1], b_color[2]),
                        alignment=alignment,
                        wrap_mode=wrap_mode,
                    )
                )
            except (ValueError, TypeError) as e:
                raise ProtocolError(f"Invalid ExportTextBlockSpec: {e}") from e

        try:
            specs.append(
                ExportRegionSpec(
                    region_id=s["region_id"],
                    page_number=s["page_number"],
                    pdf_rect=_dict_to_rect(s["pdf_rect"]),
                    translated_text=s["translated_text"],
                    font_family=s["font_family"],
                    font_size=float(s["font_size"]),
                    font_color=(f_color[0], f_color[1], f_color[2]),
                    background_rgb=(rgb[0], rgb[1], rgb[2]),
                    blocks=tuple(blocks_list),
                )
            )
        except (ValueError, TypeError) as e:
            raise ProtocolError(f"Invalid ExportRegionSpec: {e}") from e

    try:
        return ExportRequest(
            source_path=data["source_path"],
            destination_path=data["destination_path"],
            expected_fingerprint=fingerprint,
            specs=tuple(specs),
        )
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"Invalid ExportRequest: {e}") from e


def serialize_export_result(res: ExportResult) -> str:
    payload = {
        "destination_path": res.destination_path,
        "exported_regions": res.exported_regions,
        "pages_touched": list(res.pages_touched),
        "warnings": list(res.warnings),
    }
    return json.dumps(payload, allow_nan=False)


def deserialize_export_result(json_str: str) -> ExportResult:
    data = strict_json_loads(json_str)
    _require_type(data, dict, "ExportResult root")

    _reject_unknown_fields(
        data, {"destination_path", "exported_regions", "pages_touched", "warnings"}, "ExportResult"
    )
    for k in ("destination_path", "exported_regions", "pages_touched", "warnings"):
        if k not in data:
            raise ProtocolError(f"Missing {k} in ExportResult")

    _require_type(data["destination_path"], str, "destination_path")
    _require_type(data["exported_regions"], int, "exported_regions")
    _require_type(data["pages_touched"], list, "pages_touched")
    _require_type(data["warnings"], list, "warnings")

    for p in data["pages_touched"]:
        _require_type(p, int, "pages_touched item")
    for w in data["warnings"]:
        _require_type(w, str, "warnings item")

    try:
        return ExportResult(
            destination_path=str(data["destination_path"]),
            exported_regions=int(data["exported_regions"]),
            pages_touched=tuple(data["pages_touched"]),
            warnings=tuple(data["warnings"]),
        )
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"Invalid ExportResult: {e}") from e


def serialize_progress(prog: ExportProgress) -> str:
    payload = {
        "stage": prog.stage.name,
        "completed_regions": prog.completed_regions,
        "total_regions": prog.total_regions,
        "completed_pages": prog.completed_pages,
        "total_pages": prog.total_pages,
    }
    return json.dumps(payload, allow_nan=False)


def deserialize_progress(json_str: str) -> ExportProgress:
    data = strict_json_loads(json_str)
    _require_type(data, dict, "progress root")

    for k in ("stage", "completed_regions", "total_regions", "completed_pages", "total_pages"):
        if k not in data:
            raise ProtocolError(f"Missing {k} in ExportProgress")

    _require_type(data["stage"], str, "stage")
    for k in ("completed_regions", "total_regions", "completed_pages", "total_pages"):
        _require_type(data[k], int, k)

    try:
        stage = ExportStage[data["stage"]]
    except KeyError:
        raise ProtocolError(f"Invalid stage: {data['stage']}")

    if (
        data["completed_regions"] < 0
        or data["total_regions"] < 0
        or data["completed_pages"] < 0
        or data["total_pages"] < 0
    ):
        raise ProtocolError("Progress counters cannot be negative")

    if data["completed_regions"] > data["total_regions"]:
        raise ProtocolError("completed_regions > total_regions")

    if data["completed_pages"] > data["total_pages"]:
        raise ProtocolError("completed_pages > total_pages")

    try:
        return ExportProgress(
            stage=stage,
            completed_regions=data["completed_regions"],
            total_regions=data["total_regions"],
            completed_pages=data["completed_pages"],
            total_pages=data["total_pages"],
        )
    except (ValueError, TypeError) as e:
        raise ProtocolError(f"Invalid ExportProgress: {e}") from e


def _raise_invalid_constant(c: str) -> None:
    raise ProtocolError(f"Invalid JSON constant: {c}")
