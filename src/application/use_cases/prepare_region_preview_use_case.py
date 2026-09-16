from dataclasses import dataclass

from src.application.ports.pdf_source_inspector import IPdfSourceInspector
from src.application.services.region_render_spec_planner import RegionRenderSpecPlanner, PlannerContext
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutResult, TextWrapMode
from src.domain.models.enums import FitStatus

from src.domain.value_objects.render_plan import RegionRenderPlan

@dataclass
class PreparedRegionPreview:
    overlay_rect: Rect
    plan: RegionRenderPlan
    background_rgb: tuple[int, int, int]

class PrepareRegionPreviewUseCase:
    def __init__(
        self,
        source_inspector: IPdfSourceInspector,
        planner: RegionRenderSpecPlanner
    ):
        self._source_inspector = source_inspector
        self._planner = planner

    def execute(
        self,
        source_path: str,
        region: TranslationRegion,
        all_regions: list[TranslationRegion]
    ) -> PreparedRegionPreview | None:
        if not region.translated_text:
            return None
            
        inspection = self._source_inspector.inspect(source_path)
        page_num = region.page_id
        
        cropbox = inspection.page_cropboxes.get(page_num)
        native_texts = list(inspection.page_native_texts.get(page_num, ()))
        other_region_rects = [r.selection_rect for r in all_regions if r.page_id == page_num and r.id != region.id]
        
        context = PlannerContext(
            source_path=source_path,
            page_cropbox=cropbox,
            native_obstacles=native_texts,
            other_region_obstacles=other_region_rects
        )
        
        specs, issues = self._planner.plan_regions([region], [context])
        if not specs:
            return None
            
        spec = specs[0]
        
        # We no longer need dummy_layout, we pass the plan directly
        return PreparedRegionPreview(
            overlay_rect=spec.target_rect,
            plan=spec,
            background_rgb=spec.background_rgb
        )
