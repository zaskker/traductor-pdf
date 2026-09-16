import fitz

from src.application.dtos.export import (
    BackgroundAnalysis,
    BackgroundAnalysisRequest,
    BackgroundClassification,
)
from src.application.ports.region_background_analyzer import IRegionBackgroundAnalyzer

ANALYSIS_SCALE = 1.0
MIN_VALID_SAMPLES = 50
PERIMETER_WIDTH = 2
TEXT_EXCLUSION_PADDING = 2
MAX_PERIMETER_VARIANCE = 5.0
MAX_INTERIOR_VARIANCE = 5.0
MIN_DOMINANT_RATIO = 0.95


class PyMuPDFRegionBackgroundAnalyzer(IRegionBackgroundAnalyzer):
    def __init__(self, analysis_scale: float = 1.0):
        self._analysis_scale = analysis_scale

    def analyze_many(
        self,
        source_path: str,
        requests: tuple[BackgroundAnalysisRequest, ...],
    ) -> tuple[BackgroundAnalysis, ...]:

        results = []
        try:
            doc = fitz.open(source_path)
        except Exception:
            for req in requests:
                results.append(BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN))
            return tuple(results)

        with doc:
            for req in requests:
                try:
                    if req.page_number < 1 or req.page_number > doc.page_count:
                        results.append(
                            BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN)
                        )
                        continue

                    page = doc[req.page_number - 1]
                    rect = fitz.Rect(
                        req.target_rect.x0,
                        req.target_rect.y0,
                        req.target_rect.x1,
                        req.target_rect.y1,
                    )

                    if rect.width <= 0 or rect.height <= 0:
                        results.append(
                            BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN)
                        )
                        continue

                    old_rotation = page.rotation
                    try:
                        page.set_rotation(0)

                        # Check for intersecting images
                        has_complex_objects = False
                        for img in page.get_image_info():
                            img_rect = fitz.Rect(img["bbox"])
                            if img_rect.intersects(rect):
                                has_complex_objects = True
                                break

                        # Check for intersecting drawings (lines, complex vectors)
                        # We only flag as COMPLEX objects that are truly visual overlays:
                        # - Pure stroke drawings (type "s") = lines, arcs with no fill
                        # - Drawings with multiple items (paths) that are complex shapes
                        # We do NOT flag simple filled rects (type "fs" or "f") as complex;
                        # the raster pixel analysis below will handle non-uniform fills.
                        if not has_complex_objects:
                            for drawing in page.get_drawings():
                                draw_rect = drawing.get("rect")
                                if draw_rect is None or not draw_rect.intersects(rect):
                                    continue
                                
                                dtype = drawing.get("type", "")
                                # "s" = pure stroke (line, arc, polyline without fill)
                                # "fs" = fill + stroke (rect, circle outline+fill) — only stroke if color != fill
                                if dtype == "s":
                                    # Pure stroke - no fill, just a line/path → complex
                                    has_complex_objects = True
                                    break
                                # For "fs" or "f": check if items contain only rect/quad ops
                                # (indicating a simple filled background rect, not a complex shape)
                                items = drawing.get("items", [])
                                has_non_rect = any(op not in ("re", "qu") for op, *_ in items)
                                if has_non_rect:
                                    # Complex vector shape (circle, arc, curve) → complex
                                    has_complex_objects = True
                                    break

                        if has_complex_objects:
                            results.append(
                                BackgroundAnalysis(req.region_id, BackgroundClassification.COMPLEX_BACKGROUND)
                            )
                            continue

                        matrix = fitz.Matrix(self._analysis_scale, self._analysis_scale)
                        pix = page.get_pixmap(clip=rect, matrix=matrix)
                        s, n, w, h, stride = pix.samples, pix.n, pix.width, pix.height, pix.stride
                    finally:
                        page.set_rotation(old_rotation)

                    pixels = []
                    perimeter = []

                    # Convert exclude rects to pixmap local coords and apply padding
                    local_excludes = []
                    for ex in req.excluded_fragment_rects:
                        ex_x0 = (
                            int((ex.x0 - rect.x0) * self._analysis_scale) - TEXT_EXCLUSION_PADDING
                        )
                        ex_y0 = (
                            int((ex.y0 - rect.y0) * self._analysis_scale) - TEXT_EXCLUSION_PADDING
                        )
                        ex_x1 = (
                            int((ex.x1 - rect.x0) * self._analysis_scale) + TEXT_EXCLUSION_PADDING
                        )
                        ex_y1 = (
                            int((ex.y1 - rect.y0) * self._analysis_scale) + TEXT_EXCLUSION_PADDING
                        )
                        local_excludes.append((ex_x0, ex_y0, ex_x1, ex_y1))

                    for y in range(h):
                        row = s[y * stride : y * stride + w * n]
                        for x in range(w):
                            excluded = False
                            for ex_x0, ex_y0, ex_x1, ex_y1 in local_excludes:
                                if ex_x0 <= x <= ex_x1 and ex_y0 <= y <= ex_y1:
                                    excluded = True
                                    break

                            if excluded:
                                continue

                            c = tuple(row[x * n : x * n + min(n, 3)])
                            pixels.append(c)
                            if (
                                y < PERIMETER_WIDTH
                                or y >= h - PERIMETER_WIDTH
                                or x < PERIMETER_WIDTH
                                or x >= w - PERIMETER_WIDTH
                            ):
                                perimeter.append(c)

                    total_pixels = w * h
                    if total_pixels > 0:
                        excluded_ratio = (total_pixels - len(pixels)) / total_pixels
                    else:
                        excluded_ratio = 1.0

                    if (
                        len(pixels) < MIN_VALID_SAMPLES
                        or len(perimeter) < MIN_VALID_SAMPLES
                        or excluded_ratio > 0.95
                    ):
                        results.append(
                            BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN)
                        )
                        continue

                    def variance(colors):
                        if not colors:
                            return 0
                        mean = [sum(c[i] for c in colors) / len(colors) for i in range(3)]
                        var = sum(
                            sum((c[i] - mean[i]) ** 2 for i in range(3)) for c in colors
                        ) / len(colors)
                        return var

                    p_var = variance(perimeter)
                    i_var = variance(pixels)

                    dom = max(set(perimeter), key=perimeter.count)
                    dom_ratio = perimeter.count(dom) / len(perimeter)

                    if (
                        p_var <= MAX_PERIMETER_VARIANCE
                        and i_var <= MAX_INTERIOR_VARIANCE
                        and dom_ratio >= MIN_DOMINANT_RATIO
                    ):
                        if dom == (255, 255, 255):
                            results.append(
                                BackgroundAnalysis(
                                    req.region_id, BackgroundClassification.UNIFORM_WHITE, dom
                                )
                            )
                        else:
                            results.append(
                                BackgroundAnalysis(
                                    req.region_id, BackgroundClassification.UNIFORM_COLOR, dom
                                )
                            )
                    else:
                        results.append(
                            BackgroundAnalysis(
                                req.region_id, BackgroundClassification.COMPLEX_BACKGROUND
                            )
                        )
                except Exception:
                    # Fail-safe to UNKNOWN
                    results.append(
                        BackgroundAnalysis(req.region_id, BackgroundClassification.UNKNOWN)
                    )

        return tuple(results)
