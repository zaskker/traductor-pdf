from dataclasses import dataclass
from src.application.dtos.export import (
    BackgroundAnalysisRequest,
    BackgroundClassification,
    ExportRegionSpec,
    ExportTextBlockSpec,
)
from src.application.ports.region_background_analyzer import IRegionBackgroundAnalyzer
from src.application.ports.text_layout_engine import ITextLayoutEngine
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutInput
from src.domain.models.enums import FitStatus
from src.application.services.structured_layout_builder import StructuredLayoutBuilder
from src.domain.value_objects.render_plan import RegionRenderPlan, TextBlockPlan

@dataclass
class PlannerContext:
    source_path: str
    page_cropbox: Rect | None
    native_obstacles: list[Rect]
    other_region_obstacles: list[Rect]

class RegionRenderSpecPlanner:
    DEFAULT_MIN_FONT_SIZE = 6.0
    DEFAULT_MAX_FONT_SIZE = 24.0
    DEFAULT_FONT_FAMILY = "notos"

    def __init__(
        self,
        background_analyzer: IRegionBackgroundAnalyzer,
        layout_engine: ITextLayoutEngine,
    ):
        self._background_analyzer = background_analyzer
        self._layout_engine = layout_engine

    def plan_regions(self, regions: list[TranslationRegion], contexts: list[PlannerContext]) -> tuple[list[RegionRenderPlan], list["PreflightIssue"]]:
        from src.application.dtos.export import PreflightIssue, PreflightIssueCode, PreflightSeverity

        region_prep_data = {}
        bg_requests_candidate = []
        
        for region, context in zip(regions, contexts):
            obstacles = context.native_obstacles + context.other_region_obstacles
            blocks_info = StructuredLayoutBuilder.prepare_blocks(region, context.page_cropbox, obstacles)
            
            candidate_overlay_rect = StructuredLayoutBuilder.union_rects([b.candidate_rect for b in blocks_info])
            if not candidate_overlay_rect:
                candidate_overlay_rect = region.selection_rect
                
            candidate_overlay_rect = StructuredLayoutBuilder.union_rects([candidate_overlay_rect, region.selection_rect])
            excludes = tuple(frag.bbox for frag in region.source_fragments if frag.bbox)
            
            region_prep_data[region.id] = {
                "blocks_info": blocks_info,
                "candidate_overlay_rect": candidate_overlay_rect,
                "original_selection_rect": region.selection_rect,
                "excludes": excludes
            }

            bg_requests_candidate.append(
                BackgroundAnalysisRequest(
                    region_id=region.id,
                    page_number=region.page_id,
                    target_rect=candidate_overlay_rect,
                    excluded_fragment_rects=excludes,
                )
            )

        if not bg_requests_candidate:
            return [], []

        # Analyze candidates
        source_path = contexts[0].source_path
        bg_results_candidate = self._background_analyzer.analyze_many(source_path, tuple(bg_requests_candidate))
        bg_map_candidate = {res.region_id: res for res in bg_results_candidate}

        # Fallbacks
        bg_requests_fallback = []
        for region in regions:
            bg_res = bg_map_candidate.get(region.id)
            if not bg_res or bg_res.classification in (BackgroundClassification.COMPLEX_BACKGROUND, BackgroundClassification.UNKNOWN):
                prep_data = region_prep_data[region.id]
                bg_requests_fallback.append(
                    BackgroundAnalysisRequest(
                        region_id=region.id,
                        page_number=region.page_id,
                        target_rect=prep_data["original_selection_rect"],
                        excluded_fragment_rects=prep_data["excludes"],
                    )
                )

        bg_map_fallback = {}
        if bg_requests_fallback:
            bg_results_fallback = self._background_analyzer.analyze_many(source_path, tuple(bg_requests_fallback))
            bg_map_fallback = {res.region_id: res for res in bg_results_fallback}

        specs = []
        issues = []
        
        for region in regions:
            prep_data = region_prep_data[region.id]
            bg_res = bg_map_candidate.get(region.id)
            
            is_fallback = False
            if not bg_res or bg_res.classification in (BackgroundClassification.COMPLEX_BACKGROUND, BackgroundClassification.UNKNOWN):
                is_fallback = True
                bg_res = bg_map_fallback.get(region.id)

            if not bg_res or bg_res.classification in (BackgroundClassification.COMPLEX_BACKGROUND, BackgroundClassification.UNKNOWN):
                code = PreflightIssueCode.UNKNOWN_BACKGROUND
                if bg_res and bg_res.classification == BackgroundClassification.COMPLEX_BACKGROUND:
                    code = PreflightIssueCode.COMPLEX_BACKGROUND
                issues.append(
                    PreflightIssue(
                        code=code,
                        severity=PreflightSeverity.BLOCKER,
                        region_id=region.id,
                        page_number=region.page_id,
                        message=f"Background rejected: {bg_res.classification.name if bg_res else 'None'}"
                    )
                )
                continue

            max_font_size = region.get_dominant_font_size(default_max_font_size=self.DEFAULT_MAX_FONT_SIZE, default_min_font_size=self.DEFAULT_MIN_FONT_SIZE)
            
            font_color_hex = region.get_dominant_font_color(default_color="#000000")
            font_color = (0, 0, 0)
            if len(font_color_hex) == 7 and font_color_hex.startswith("#"):
                try:
                    r = int(font_color_hex[1:3], 16)
                    g = int(font_color_hex[3:5], 16)
                    b = int(font_color_hex[5:7], 16)
                    font_color = (r, g, b)
                except ValueError:
                    pass

            final_blocks = []
            layout_overflow = False
            for binfo in prep_data["blocks_info"]:
                effective_rect = binfo.src_rect if is_fallback else binfo.candidate_rect
                
                input_data = TextLayoutInput(
                    text=binfo.translated_text,
                    target_rect=effective_rect,
                    min_font_size=self.DEFAULT_MIN_FONT_SIZE,
                    max_font_size=max_font_size,
                    font_family=self.DEFAULT_FONT_FAMILY,
                    is_single_line_source=binfo.is_single_line,
                    alignment=binfo.alignment,
                    structure=getattr(binfo, "structure", None)
                )
                
                layout_res = self._layout_engine.layout_text(input_data)
                if layout_res.status == FitStatus.OVERFLOW:
                    layout_overflow = True
                    break
                    
                final_blocks.append(
                    TextBlockPlan(
                        rect=effective_rect,
                        text=binfo.translated_text,
                        font_size=layout_res.font_size,
                        font_family=self.DEFAULT_FONT_FAMILY,
                        font_color=font_color,
                        alignment=binfo.alignment,
                        wrap_mode=layout_res.wrap_mode,
                        structure=getattr(binfo, "structure", None)  # will be added to BlockPrepInfo next
                    )
                )

            effective_overlay_rect = StructuredLayoutBuilder.union_rects([b.rect for b in final_blocks] + [region.selection_rect])

            if layout_overflow:
                issues.append(
                    PreflightIssue(
                        code=PreflightIssueCode.OVERFLOW,
                        severity=PreflightSeverity.BLOCKER,
                        region_id=region.id,
                        page_number=region.page_id,
                        message="Text layout overflowed bounding box"
                    )
                )
                
                specs.append(
                    RegionRenderPlan(
                        region_id=region.id,
                        page_number=region.page_id,
                        target_rect=effective_overlay_rect,
                        blocks=tuple(final_blocks),
                        background_rgb=bg_res.background_rgb,
                        fit_status=FitStatus.OVERFLOW
                    )
                )
                continue

            specs.append(
                RegionRenderPlan(
                    region_id=region.id,
                    page_number=region.page_id,
                    target_rect=effective_overlay_rect,
                    blocks=tuple(final_blocks),
                    background_rgb=bg_res.background_rgb,
                    fit_status=FitStatus.FIT
                )
            )

        return specs, issues
