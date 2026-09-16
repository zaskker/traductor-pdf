import hashlib
import os
import re
import uuid

import pymupdf as fitz

from src.application.dtos.export import ExportRequest, ExportResult
from src.application.errors.export import (
    ExportError,
    ExportFileError,
    ExportValidationError,
    InvalidExportRequestError,
    SourceFingerprintMismatchError,
)
from src.application.ports.export_progress import (
    ExportCancelledError,
    ExportExecutionContext,
    ExportProgress,
    ExportStage,
)
from src.application.ports.translated_pdf_exporter import ITranslatedPdfExporter
from src.infrastructure.pdf.html_text_renderer import HtmlTextRenderer


class PyMuPDFVectorFormPdfExporter(ITranslatedPdfExporter):
    def __init__(self) -> None:
        self._renderer = HtmlTextRenderer()

    @staticmethod
    def _tokenize_text(text: str) -> list[str]:
        return re.findall(r"\w+", text, flags=re.UNICODE)

    @classmethod
    def _select_validation_tokens(cls, text: str) -> tuple[str, ...]:
        tokens = cls._tokenize_text(text)
        large_tokens = [t for t in tokens if len(t) > 3]
        if not large_tokens:
            large_tokens = tokens
        if not large_tokens:
            return ()
        if len(large_tokens) == 1:
            return (large_tokens[0],)

        # Select first and longest remaining
        first = large_tokens[0]
        longest = max(large_tokens[1:], key=len)
        return (first, longest)

    def export(
        self, request: ExportRequest, context: ExportExecutionContext | None = None
    ) -> ExportResult:
        def check_cancel():
            if context and context.cancellation_token:
                context.cancellation_token.throw_if_cancelled()

        def report(
            stage: ExportStage, current_regions: int, current_pages: int, total_pages_known: int = 0
        ):
            if context and context.observer:
                context.observer.on_progress(
                    ExportProgress(
                        stage=stage,
                        completed_regions=current_regions,
                        total_regions=len(request.specs),
                        completed_pages=current_pages,
                        total_pages=total_pages_known,
                    )
                )

        temp_path = None
        check_cancel()
        report(ExportStage.VALIDATING, 0, 0)

        self._validate_request(request)

        source = request.source_path
        dest = request.destination_path

        # Early IO and File System Checks
        try:
            # Reject source == destination
            if os.path.exists(source) and os.path.exists(dest):
                if os.path.samefile(source, dest):
                    raise InvalidExportRequestError(
                        "Source and destination cannot be the same file."
                    )

            norm_source = os.path.normcase(os.path.abspath(source))
            norm_dest = os.path.normcase(os.path.abspath(dest))
            if norm_source == norm_dest:
                raise InvalidExportRequestError("Source and destination absolute paths match.")

            dest_parent = os.path.dirname(norm_dest)
            if not os.path.exists(dest_parent) or not os.path.isdir(dest_parent):
                raise InvalidExportRequestError(
                    f"Destination parent directory is invalid: {dest_parent}"
                )

            # Compute source SHA and size before
            sha_before, size_before = self._compute_sha_and_size(source)

        except (InvalidExportRequestError, SourceFingerprintMismatchError):
            raise
        except Exception as e:
            raise ExportFileError(f"Filesystem or IO error before export: {e}") from e

        if (
            sha_before != request.expected_fingerprint.sha256
            or size_before != request.expected_fingerprint.size
        ):
            raise SourceFingerprintMismatchError("Source SHA or size has changed since preflight.")

        # Create temporary file in the same directory
        temp_stem = os.path.basename(dest)
        temp_path = os.path.join(dest_parent, f".{temp_stem}.{uuid.uuid4().hex}.tmp.pdf")

        if os.path.exists(temp_path):
            raise ExportFileError(f"Temporary path {temp_path} already exists (UUID collision).")

        check_cancel()
        report(ExportStage.PREPARING, 0, 0)

        source_doc_info = []

        try:
            pages_touched = set()
            completed_pages_set = set()
            regions_applied = 0

            try:
                doc = fitz.open(source)
            except Exception as e:
                raise ExportFileError(f"Failed to open source file: {e}") from e

            try:
                if doc.page_count != request.expected_fingerprint.page_count:
                    raise SourceFingerprintMismatchError("Source page count changed.")

                for p in doc:
                    source_doc_info.append(
                        {"mediabox": p.mediabox, "cropbox": p.cropbox, "rotation": p.rotation}
                    )

                # Group specs by page
                specs_by_page = {}
                for spec in request.specs:
                    specs_by_page.setdefault(spec.page_number, []).append(spec)

                pages_to_touch = len(specs_by_page)

                for page_num, specs in specs_by_page.items():
                    check_cancel()

                    if page_num < 1 or page_num > doc.page_count:
                        raise InvalidExportRequestError(f"Page number {page_num} out of bounds")

                    page = doc[page_num - 1]
                    old_rotation = page.rotation
                    
                    # Capture derotation matrix before resetting rotation
                    derot = page.derotation_matrix

                    try:
                        page.set_rotation(0)

                        overlay_doc = fitz.open()
                        try:
                            overlay_page = overlay_doc.new_page(
                                width=page.cropbox.width, height=page.cropbox.height
                            )

                            for spec in specs:
                                # Map spec.pdf_rect (which is in rotated page.rect space)
                                # to unrotated space relative to the cropbox top-left
                                fitz_pdf_rect = fitz.Rect(
                                    spec.pdf_rect.x0,
                                    spec.pdf_rect.y0,
                                    spec.pdf_rect.x1,
                                    spec.pdf_rect.y1,
                                )
                                ur = (fitz_pdf_rect * derot) + (-page.cropbox.x0, -page.cropbox.y0, -page.cropbox.x0, -page.cropbox.y0)
                                
                                # Check bounds against the cropbox-sized overlay page
                                if not ur.intersects(overlay_page.rect):
                                    raise InvalidExportRequestError(
                                        f"Region {spec.region_id} does not intersect visible page {page_num}."
                                    )

                                # Draw background
                                bg_color = tuple(c / 255.0 for c in spec.background_rgb)
                                overlay_page.draw_rect(ur, color=bg_color, fill=bg_color)

                                # Insert text via HtmlTextRenderer
                                if spec.blocks:
                                    any_overflow = False
                                    for block in spec.blocks:
                                        fitz_block_rect = fitz.Rect(
                                            block.rect.x0,
                                            block.rect.y0,
                                            block.rect.x1,
                                            block.rect.y1,
                                        )
                                        b_ur = (fitz_block_rect * derot) + (-page.cropbox.x0, -page.cropbox.y0, -page.cropbox.x0, -page.cropbox.y0)
                                        
                                        result = self._renderer.insert_into_page(
                                            overlay_page,
                                            b_ur,
                                            block.translated_text,
                                            block.font_size,
                                            block.font_color,
                                            block.alignment,
                                            block.wrap_mode,
                                            rotate=old_rotation,
                                        )
                                        if result.overflow:
                                            any_overflow = True
                                    if any_overflow:
                                        raise ExportValidationError(
                                            f"HtmlTextRenderer block overflow for region {spec.region_id}"
                                        )
                                else:
                                    result = self._renderer.insert_into_page(
                                        overlay_page,
                                        ur,
                                        spec.translated_text,
                                        spec.font_size,
                                        spec.font_color,
                                        rotate=old_rotation,
                                    )
                                    if result.overflow:
                                        raise ExportValidationError(
                                            f"HtmlTextRenderer overflow for region {spec.region_id}"
                                        )

                                regions_applied += 1
                                report(
                                    ExportStage.APPLYING,
                                    regions_applied,
                                    len(completed_pages_set),
                                    pages_to_touch,
                                )
                                check_cancel()

                            # Apply the single overlay page to the real page
                            page.show_pdf_page(page.cropbox, overlay_doc, 0)
                            
                        finally:
                            overlay_doc.close()

                        pages_touched.add(page_num)
                        completed_pages_set.add(page_num)
                        report(
                            ExportStage.APPLYING,
                            regions_applied,
                            len(completed_pages_set),
                            pages_to_touch,
                        )

                    finally:
                        page.set_rotation(old_rotation)

                check_cancel()
                report(
                    ExportStage.SAVING, regions_applied, len(completed_pages_set), pages_to_touch
                )

                try:
                    doc.save(temp_path, deflate=True)
                except Exception as e:
                    raise ExportFileError(f"Failed to save temp file: {e}") from e

            finally:
                doc.close()

            check_cancel()
            report(ExportStage.VERIFYING, regions_applied, len(completed_pages_set), pages_to_touch)

            # Validate output
            if not os.path.exists(temp_path):
                raise ExportValidationError("Temporary file was not created.")

            temp_sz = os.path.getsize(temp_path)
            if temp_sz == 0:
                raise ExportValidationError("Temporary file is empty.")

            try:
                val_doc = fitz.open(temp_path)
            except Exception as e:
                raise ExportValidationError(
                    f"Could not open temporary file for validation: {e}"
                ) from e

            try:
                if val_doc.page_count != request.expected_fingerprint.page_count:
                    raise ExportValidationError("Output page count mismatch.")

                # Check MediaBox/CropBox/rotation
                for i, p in enumerate(val_doc):
                    s_info = source_doc_info[i]
                    if (
                        p.mediabox != s_info["mediabox"]
                        or p.cropbox != s_info["cropbox"]
                        or p.rotation != s_info["rotation"]
                    ):
                        raise ExportValidationError(
                            f"Page {i + 1} geometry changed (MediaBox/CropBox/rotation mismatch)."
                        )

                # Verify text tokens
                for spec in request.specs:
                    v_page = val_doc[spec.page_number - 1]
                    clip_rect = (fitz.Rect(
                        spec.pdf_rect.x0, spec.pdf_rect.y0, spec.pdf_rect.x1, spec.pdf_rect.y1
                    ) + (-1.0, -1.0, 1.0, 1.0)) * v_page.derotation_matrix
                    extracted_text = v_page.get_text(clip=clip_rect)
                    extracted_tokens = set(self._tokenize_text(extracted_text))

                    # Check robust tokens
                    if spec.blocks:
                        validation_text = " ".join(block.translated_text for block in spec.blocks)
                    else:
                        validation_text = spec.translated_text
                    
                    tokens = self._select_validation_tokens(validation_text)
                    for token in tokens:
                        if token and token not in extracted_tokens:
                            print(f"FAILED TOKEN: {token!r}")
                            print(f"EXTRACTED TEXT: {extracted_text!r}")
                            print(f"CLIP RECT: {clip_rect}")
                            print(f"DEROT MATRIX: {v_page.derotation_matrix}")
                            raise ExportValidationError(
                                f"Translated text validation failed for region {spec.region_id}"
                            )
            finally:
                val_doc.close()

            # Verify source immutability
            sha_after, size_after = self._compute_sha_and_size(source)
            if sha_after != sha_before or size_after != size_before:
                raise SourceFingerprintMismatchError(
                    "Source file was mutated during export. Aborting."
                )

            # FINALIZING safe point
            check_cancel()
            report(
                ExportStage.FINALIZING, regions_applied, len(completed_pages_set), pages_to_touch
            )

            # Replace atomic - Cancel here is ineffective
            try:
                os.replace(temp_path, dest)
            except Exception as e:
                raise ExportFileError(f"Failed to move temp file to destination: {e}") from e

            result = ExportResult(
                destination_path=dest,
                exported_regions=len(request.specs),
                pages_touched=tuple(sorted(pages_touched)),
            )
            report(ExportStage.COMPLETED, regions_applied, len(completed_pages_set), pages_to_touch)
            return result

        except ExportCancelledError as exc:
            self._cleanup(temp_path, exc)
            raise
        except ExportError as exc:
            self._cleanup(temp_path, exc)
            raise
        except Exception as e:
            wrapped = ExportError(f"Unexpected error during export: {e}")
            wrapped.__cause__ = e
            self._cleanup(temp_path, wrapped)
            raise wrapped

    def _validate_request(self, request: ExportRequest):
        if not request.specs:
            raise InvalidExportRequestError("ExportRequest contains no specs.")

        region_ids = set()
        for spec in request.specs:
            if spec.region_id in region_ids:
                raise InvalidExportRequestError(f"Duplicate region ID: {spec.region_id}")
            region_ids.add(spec.region_id)

    def _compute_sha_and_size(self, path: str):
        sha256 = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
                size += len(chunk)
        return sha256.hexdigest(), size

    def _cleanup(self, path: str | None, exc: Exception | None):
        if not path:
            return
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception as e:
            if exc is not None:
                exc.cleanup_failed = True
                exc.temporary_path = path
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to clean up temporary file {path}: {e}")
