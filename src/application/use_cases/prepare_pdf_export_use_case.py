import os
import re
from dataclasses import dataclass

from src.application.dtos.export import (
    ApprovalExportPolicy,
    BackgroundAnalysisRequest,
    BackgroundClassification,
    ExportRegionSpec,
    ExportRequest,
    ExportTextBlockSpec,
    PendingRegionPolicy,
    PreflightIssue,
    PreflightIssueCode,
    PreflightOutcome,
    PreflightReport,
    PreflightSeverity,
)
from src.application.ports.pdf_source_inspector import IPdfSourceInspector
from src.application.ports.region_background_analyzer import IRegionBackgroundAnalyzer
from src.application.ports.text_layout_engine import ITextLayoutEngine
from src.application.services.block_grouper import group_source_fragments_into_blocks
from src.application.services.list_prefix_detector import detect_list_prefix
from src.domain.models.enums import FitStatus, RegionStatus, TextAlignment
from src.domain.value_objects.geometry import Rect
from src.domain.value_objects.layout import TextLayoutInput
from src.application.services.structured_layout_builder import StructuredLayoutBuilder, BlockPrepInfo

OVERLAP_AREA_EPSILON_PT2 = 1.0
ALIGNMENT_TOLERANCE_PT = 2.0
SAFE_PADDING_PT = 2.0
DEFAULT_MIN_FONT_SIZE = 6.0
DEFAULT_MAX_FONT_SIZE = 24.0
DEFAULT_FONT_FAMILY = "notos"

class PreparePdfExportUseCase:
    def __init__(
        self,
        project_repo,
        region_repo,
        source_inspector: IPdfSourceInspector,
        background_analyzer: IRegionBackgroundAnalyzer,
        layout_engine: ITextLayoutEngine,
    ):
        self._project_repo = project_repo
        self._region_repo = region_repo
        self._source_inspector = source_inspector
        self._background_analyzer = background_analyzer
        self._layout_engine = layout_engine

    def execute(
        self,
        project_id: str,
        destination_path: str,
        pending_policy: PendingRegionPolicy = PendingRegionPolicy.BLOCK,
        approval_policy: ApprovalExportPolicy = ApprovalExportPolicy.APPROVED_ONLY,
    ) -> PreflightOutcome:
        issues = []

        project = self._project_repo.get(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        source_path = project.pdf_path
        if not os.path.exists(source_path):
            issues.append(
                PreflightIssue(PreflightIssueCode.SOURCE_MISSING, PreflightSeverity.BLOCKER)
            )
            return PreflightOutcome(PreflightReport(False, tuple(issues), 0, 0, len(issues)))

        inspection = self._source_inspector.inspect(source_path)

        if (
            inspection.fingerprint.sha256 != project.pdf_sha256
            or inspection.fingerprint.size != project.pdf_size
        ):
            issues.append(
                PreflightIssue(PreflightIssueCode.FINGERPRINT_MISMATCH, PreflightSeverity.BLOCKER)
            )
            issues.append(
                PreflightIssue(
                    PreflightIssueCode.PROJECT_LOCKED,
                    PreflightSeverity.BLOCKER,
                    message="Project fingerprint mismatch",
                )
            )

        if inspection.fingerprint.page_count != project.pdf_page_count:
            issues.append(
                PreflightIssue(PreflightIssueCode.PAGE_COUNT_MISMATCH, PreflightSeverity.BLOCKER)
            )

        if inspection.is_encrypted:
            issues.append(
                PreflightIssue(PreflightIssueCode.ENCRYPTED_SOURCE, PreflightSeverity.BLOCKER)
            )
        if inspection.needs_authentication:
            issues.append(
                PreflightIssue(
                    PreflightIssueCode.ENCRYPTED_SOURCE,
                    PreflightSeverity.BLOCKER,
                    message="Source needs authentication",
                )
            )
        if inspection.has_digital_signatures:
            issues.append(
                PreflightIssue(PreflightIssueCode.SIGNED_SOURCE, PreflightSeverity.BLOCKER)
            )

        if any(iss.severity == PreflightSeverity.BLOCKER for iss in issues):
            return PreflightOutcome(PreflightReport(False, tuple(issues), 0, 0, len(issues)))

        all_regions = self._region_repo.get_all(project_id)

        candidates = []
        pending_regions = []

        for r in all_regions:
            if (
                r.status == RegionStatus.TRANSLATED
                and r.translated_text
                and r.translated_text.strip()
            ):
                candidates.append(r)
            elif r.status == RegionStatus.PENDING:
                pending_regions.append(r)
            else:
                issues.append(
                    PreflightIssue(
                        PreflightIssueCode.INVALID_REGION_STATUS,
                        PreflightSeverity.WARNING,
                        region_id=r.id,
                        message=f"Status {r.status.name} is not exportable MVP",
                    )
                )

        # TRANS-05: Apply approval policy filter
        # This is orthogonal to SAFE-08 render eligibility. A region must satisfy both.
        if approval_policy == ApprovalExportPolicy.APPROVED_ONLY:
            from src.domain.models.enums import ReviewStatus
            unapproved = [r for r in candidates if r.review_status != ReviewStatus.APPROVED]
            if unapproved:
                issues.append(
                    PreflightIssue(
                        PreflightIssueCode.UNAPPROVED_REGIONS,
                        PreflightSeverity.WARNING,
                        message=f"{len(unapproved)} translated region(s) not approved",
                    )
                )
            candidates = [r for r in candidates if r.review_status == ReviewStatus.APPROVED]

        if pending_regions:
            if pending_policy == PendingRegionPolicy.BLOCK:
                issues.append(
                    PreflightIssue(
                        PreflightIssueCode.PENDING_REGIONS,
                        PreflightSeverity.BLOCKER,
                        message=f"{len(pending_regions)} pending regions",
                    )
                )
            else:
                issues.append(
                    PreflightIssue(
                        PreflightIssueCode.PENDING_REGIONS,
                        PreflightSeverity.WARNING,
                        message=f"{len(pending_regions)} pending regions skipped",
                    )
                )

        if not candidates:
            issues.append(
                PreflightIssue(PreflightIssueCode.NO_EXPORTABLE_REGIONS, PreflightSeverity.BLOCKER)
            )

        # Precompute other region rects for collision avoidance
        region_rects_by_page = {}
        for r in all_regions:
            region_rects_by_page.setdefault(r.page_id, []).append(r.selection_rect)

        # Extract the planner logic to the new shared planner
        from src.application.services.region_render_spec_planner import RegionRenderSpecPlanner, PlannerContext
        
        planner = RegionRenderSpecPlanner(
            background_analyzer=self._background_analyzer,
            layout_engine=self._layout_engine
        )
        
        contexts = []
        candidate_map = {}
        for region in candidates:
            candidate_map[region.id] = region
            page_num = region.page_id
            cropbox = inspection.page_cropboxes.get(page_num)
            native_texts = list(inspection.page_native_texts.get(page_num, ()))
            other_region_rects = [r for r in region_rects_by_page.get(page_num, []) if r != region.selection_rect]
            
            contexts.append(PlannerContext(
                source_path=source_path,
                page_cropbox=cropbox,
                native_obstacles=native_texts,
                other_region_obstacles=other_region_rects
            ))
            
        plans, planner_issues = planner.plan_regions(candidates, contexts)
        
        if planner_issues:
            issues.extend(planner_issues)

        if any(iss.severity == PreflightSeverity.BLOCKER for iss in issues):
            return PreflightOutcome(
                PreflightReport(False, tuple(issues), len([p for p in plans if p.fit_status == FitStatus.FIT]), len(pending_regions), len([i for i in issues if i.severity == PreflightSeverity.BLOCKER]))
            )

        # Map to ExportRegionSpec and filter OVERFLOW
        specs = []
        for plan in plans:
            if plan.fit_status == FitStatus.FIT:
                blocks = tuple(
                    ExportTextBlockSpec(
                        rect=b.rect,
                        translated_text=b.text,
                        font_size=b.font_size,
                        font_color=b.font_color,
                        alignment=b.alignment,
                        wrap_mode=b.wrap_mode,
                        structure=b.structure.name
                    ) for b in plan.blocks
                )
                specs.append(
                    ExportRegionSpec(
                        region_id=plan.region_id,
                        page_number=plan.page_number,
                        pdf_rect=plan.target_rect,
                        translated_text=candidate_map[plan.region_id].translated_text,
                        font_family=plan.blocks[0].font_family if plan.blocks else DEFAULT_FONT_FAMILY,
                        font_size=plan.blocks[0].font_size if plan.blocks else DEFAULT_MIN_FONT_SIZE,
                        font_color=plan.blocks[0].font_color if plan.blocks else (0, 0, 0),
                        background_rgb=plan.background_rgb,
                        blocks=blocks
                    )
                )

        # 5. Collision detection between exported specs
        specs_by_page = {}
        for spec in specs:
            specs_by_page.setdefault(spec.page_number, []).append(spec)

        for page_num, p_specs in specs_by_page.items():
            for i in range(len(p_specs)):
                for j in range(i + 1, len(p_specs)):
                    r1 = p_specs[i].pdf_rect
                    r2 = p_specs[j].pdf_rect

                    dx = min(r1.x1, r2.x1) - max(r1.x0, r2.x0)
                    dy = min(r1.y1, r2.y1) - max(r1.y0, r2.y0)
                    if dx > 0 and dy > 0:
                        intersection_area = dx * dy
                        if intersection_area > OVERLAP_AREA_EPSILON_PT2:
                            issues.append(
                                PreflightIssue(
                                    PreflightIssueCode.OVERLAP,
                                    PreflightSeverity.BLOCKER,
                                    region_id=p_specs[i].region_id,
                                    related_region_id=p_specs[j].region_id,
                                    page_number=page_num,
                                    message=f"Intersection area: {intersection_area}",
                                )
                            )

        if any(iss.severity == PreflightSeverity.BLOCKER for iss in issues):
            sorted_issues = tuple(sorted(issues, key=lambda x: (x.severity.value, x.page_number or 0, x.region_id or "", x.code.value)))
            return PreflightOutcome(
                PreflightReport(False, sorted_issues, len(specs), len(pending_regions), len([i for i in issues if i.severity == PreflightSeverity.BLOCKER]))
            )

        sorted_specs = tuple(sorted(specs, key=lambda s: (s.page_number, s.pdf_rect.y0, s.pdf_rect.x0, s.region_id)))
        sorted_issues = tuple(sorted(issues, key=lambda x: (x.severity.value, x.page_number or 0, x.region_id or "", x.code.value)))

        report = PreflightReport(
            can_export=True,
            issues=sorted_issues,
            exportable_regions=len(sorted_specs),
            pending_regions=len(pending_regions),
            blocking_regions=0,
        )

        request = ExportRequest(
            source_path=source_path,
            destination_path=destination_path,
            expected_fingerprint=inspection.fingerprint,
            specs=sorted_specs,
        )

        return PreflightOutcome(report, request)

        return dx > 0 and dy > 0

