import os
import pytest
import pymupdf as fitz
from src.infrastructure.pdf.adapter import PyMuPDFDocument
from src.domain.value_objects.geometry import Rect

@pytest.fixture
def synthetic_pdf_path(tmp_path):
    pdf_path = tmp_path / "synthetic_geom.pdf"
    doc = fitz.open()
    # MediaBox 600x600
    page = doc.new_page(width=600, height=600)
    # CropBox (150, 100) -> (450, 400), size: 300x300
    page.set_cropbox(fitz.Rect(150, 100, 450, 400))
    # We add text "Target" exactly at visual top-left (10, 10) from the CropBox
    # Note: page.insert_text uses page.rect coordinates, which start at (0,0) for the CropBox
    page.insert_text((10, 20), "Target", fontsize=12)
    # Neighbor text outside the intended selection, e.g. at (160, 120) visually
    page.insert_text((160, 120), "Neighbor", fontsize=12)
    
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_geometry_cropbox_extraction(synthetic_pdf_path):
    doc = PyMuPDFDocument()
    doc.open(synthetic_pdf_path)
    
    try:
        mapper = doc.get_coordinate_mapper(0, render_scale=1.0)
        
        # We select a region in the visual UI (rendered_rect).
        # We want to select "Target" which is near the top-left of the visible area.
        # Say we select from (0, 0) to (50, 50) in visual pixels.
        ui_selection = Rect(0, 0, 50, 50)
        
        # We map it to PDF coordinates
        pdf_rect = mapper.rendered_rect_to_pdf(ui_selection)
        
        # And we extract text
        extractor = doc.get_text_extractor()
        extraction = extractor.extract(1, pdf_rect)
        extracted_text = extraction.text
        
        # We EXPECT it to extract "Target" and NOT "Neighbor"
        # However, due to the bug, pdf_rect will be shifted by (150, 100)
        # So it will look at (150, 100, 200, 150) in page.rect, which overlaps "Neighbor"
        # and misses "Target" completely!
        
        assert "Target" in extracted_text, f"Failed to extract target text. Extracted: '{extracted_text}'. PDF rect was: {pdf_rect}"
        assert "Neighbor" not in extracted_text, f"Extracted neighbor incorrectly! Extracted: '{extracted_text}'"
        
    finally:
        doc.close()

def test_geometry_cropbox_rotated_extraction(tmp_path):
    pdf_path = tmp_path / "synthetic_rotated.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=600)
    page.set_cropbox(fitz.Rect(150, 100, 450, 400)) # 300x300 visual
    page.set_rotation(90)
    # Visual top-left in the rotated page (which is top-right of unrotated)
    page.insert_text((10, 20), "RotatedTarget", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    
    pdf_doc = PyMuPDFDocument()
    pdf_doc.open(str(pdf_path))
    
    try:
        mapper = pdf_doc.get_coordinate_mapper(0, render_scale=1.0)
        ui_selection = Rect(0, 0, 100, 50)
        pdf_rect = mapper.rendered_rect_to_pdf(ui_selection)
        
        extractor = pdf_doc.get_text_extractor()
        extraction = extractor.extract(1, pdf_rect)
        extracted_text = extraction.text
        
        assert "RotatedTarget" in extracted_text, f"Failed. Extracted: '{extracted_text}'. Rect: {pdf_rect}"
    finally:
        pdf_doc.close()
