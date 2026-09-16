import hashlib
import os

import fitz

from src.application.dtos.export import PdfFingerprint, PdfSourceInspection
from src.application.ports.pdf_source_inspector import IPdfSourceInspector
from src.domain.value_objects.geometry import Rect


class PyMuPDFPdfSourceInspector(IPdfSourceInspector):
    def inspect(self, source_path: str) -> PdfSourceInspection:
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Compute SHA-256 and size
        sha256 = hashlib.sha256()
        size = 0
        with open(source_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
                size += len(chunk)
        digest = sha256.hexdigest()

        page_cropboxes = {}
        page_native_texts = {}

        with fitz.open(source_path) as doc:
            page_count = doc.page_count
            is_encrypted = doc.is_encrypted
            needs_pass = doc.needs_pass
            # has_digital_signatures is roughly evaluated.
            # PyMuPDF has `doc.is_signed` or `doc.get_sigflags()`.
            # We will use doc.is_signed if available, else we check sigflags.
            has_sigs = getattr(doc, "is_signed", False)
            if not has_sigs and hasattr(doc, "get_sigflags"):
                has_sigs = doc.get_sigflags() > 0

            for page_num in range(1, page_count + 1):
                page = doc[page_num - 1]
                # Use page.rect which is the visible rotated space, matching get_text() coordinates
                pr = page.rect
                page_cropboxes[page_num] = Rect(pr.x0, pr.y0, pr.x1, pr.y1)

                # Extract native text blocks for collision detection
                text_blocks = []
                # Use get_text("blocks") which returns (x0, y0, x1, y1, "text", block_no, block_type)
                # block_type 0 is text
                for b in page.get_text("blocks"):
                    if b[6] == 0:
                        text_blocks.append(Rect(b[0], b[1], b[2], b[3]))
                page_native_texts[page_num] = tuple(text_blocks)

        fingerprint = PdfFingerprint(sha256=digest, size=size, page_count=page_count)
        return PdfSourceInspection(
            fingerprint=fingerprint,
            is_encrypted=is_encrypted,
            needs_authentication=needs_pass,
            has_digital_signatures=has_sigs,
            page_cropboxes=page_cropboxes,
            page_native_texts=page_native_texts,
        )
