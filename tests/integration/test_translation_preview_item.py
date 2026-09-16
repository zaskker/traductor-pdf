import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QImage
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from src.ui.components.translation_preview_item import TranslationPreviewItem
from src.domain.value_objects.render_plan import RegionRenderPlan, TextBlockPlan
from src.domain.value_objects.geometry import Rect
from src.domain.models.enums import FitStatus, TextAlignment
from src.ui.components.pdf_view_widget import PdfViewWidget
from src.domain.models.region import TranslationRegion

def test_preview_reg01_basic_render(qtbot):
    block = TextBlockPlan(
        rect=Rect(0, 0, 100, 20),
        text="Test",
        font_size=12.0,
        font_family="Arial",
        alignment=TextAlignment.LEFT
    )
    plan = RegionRenderPlan(
        region_id="r1",
        page_number=1,
        target_rect=Rect(0, 0, 100, 20),
        blocks=(block,),
        background_rgb=(255, 255, 255),
        fit_status=FitStatus.FIT
    )
    
    item = TranslationPreviewItem(
        region_id="r1",
        rendered_rect=QRectF(0, 0, 100, 20),
        layout=plan,
        fallback_text="Test"
    )
    assert item is not None
    # Just render it to ensure no AttributeError
    img = QImage(100, 20, QImage.Format_ARGB32)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    try:
        item.paint(painter, opt, None)
    finally:
        painter.end()

def test_preview_reg02_multi_block(qtbot):
    b1 = TextBlockPlan(rect=Rect(0, 0, 100, 20), text="T1", font_size=12.0, font_family="Arial")
    b2 = TextBlockPlan(rect=Rect(0, 20, 100, 40), text="T2", font_size=16.0, font_family="Times")
    plan = RegionRenderPlan(
        region_id="r1", page_number=1, target_rect=Rect(0, 0, 100, 40),
        blocks=(b1, b2), background_rgb=(255, 255, 255), fit_status=FitStatus.FIT
    )
    
    item = TranslationPreviewItem(
        region_id="r1", rendered_rect=QRectF(0, 0, 100, 40), layout=plan, fallback_text="T1 T2"
    )
    
    img = QImage(100, 40, QImage.Format_ARGB32)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    try:
        item.paint(painter, opt, None)
    finally:
        painter.end()

def test_preview_reg03_decimal_font_size(qtbot):
    b1 = TextBlockPlan(rect=Rect(0, 0, 100, 20), text="Decimal", font_size=8.5, font_family="Arial")
    plan = RegionRenderPlan(
        region_id="r1", page_number=1, target_rect=Rect(0, 0, 100, 20),
        blocks=(b1,), background_rgb=(255, 255, 255), fit_status=FitStatus.FIT
    )
    
    item = TranslationPreviewItem(
        region_id="r1", rendered_rect=QRectF(0, 0, 100, 20), layout=plan, fallback_text="Decimal"
    )
    
    img = QImage(100, 20, QImage.Format_ARGB32)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    try:
        item.paint(painter, opt, None)
    finally:
        painter.end()

def test_preview_reg04_empty_plan(qtbot):
    plan = RegionRenderPlan(
        region_id="r1", page_number=1, target_rect=Rect(0, 0, 100, 20),
        blocks=(), background_rgb=(255, 255, 255), fit_status=FitStatus.FIT
    )
    
    item = TranslationPreviewItem(
        region_id="r1", rendered_rect=QRectF(0, 0, 100, 20), layout=plan, fallback_text="Empty"
    )
    
    img = QImage(100, 20, QImage.Format_ARGB32)
    painter = QPainter(img)
    opt = QStyleOptionGraphicsItem()
    try:
        item.paint(painter, opt, None)
    finally:
        painter.end()

def test_preview_reg05_integration(qtbot):
    widget = PdfViewWidget()
    qtbot.addWidget(widget)
    
    class FakeMapper:
        def pdf_rect_to_rendered(self, r):
            return r
            
    widget.get_mapper_func = lambda: FakeMapper()
    
    block = TextBlockPlan(rect=Rect(0, 0, 100, 20), text="Test", font_size=12.0, font_family="Arial")
    plan = RegionRenderPlan(
        region_id="r1", page_number=1, target_rect=Rect(0, 0, 100, 20),
        blocks=(block,), background_rgb=(255, 255, 255), fit_status=FitStatus.FIT
    )
    
    def get_preview(rid):
        return plan, None, None, (255,255,255)
        
    widget.get_text_preview_func = get_preview
    widget.set_preview_mode(True)
    
    region = TranslationRegion(
        id="r1", project_id="p1", page_id=1,
        selection_rect=Rect(0, 0, 100, 20),
        translated_text="Test"
    )
    from src.domain.models.enums import RegionStatus
    region.status = RegionStatus.TRANSLATED
    
    widget.set_saved_regions([region])
    
    # Check that a TranslationPreviewItem was added
    preview_items = [i for i in widget.scene.items() if isinstance(i, TranslationPreviewItem)]
    assert len(preview_items) == 1
    assert preview_items[0]._layout == plan
