from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.domain.value_objects.extraction import TextExtractionResult


class SourcePanel(QDockWidget):
    save_region_requested = Signal()
    delete_region_requested = Signal(str)
    translate_region_requested = Signal(str)
    # TRANS-05: Review/approval signals — carry (region_id, expected_translation_revision)
    review_requested = Signal(str, int)
    approve_requested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__("Source Text", parent)
        self._setup_ui()
        self.on_debug_toggled = None  # Callable[[bool], None]
        self._current_result: TextExtractionResult | None = None
        self._current_saved_region = None
        self._project_unlocked = False
        self._is_translating = False
        self._edit_mode = False
        self.on_edit_translation = None

    def _setup_ui(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Meta info header
        header_layout = QHBoxLayout()
        self.meta_label = QLabel("Fragments: 0 | Type: NONE")
        self.meta_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.meta_label)

        self.debug_checkbox = QCheckBox("Show Debug Fragments")
        self.debug_checkbox.stateChanged.connect(self._on_debug_changed)
        header_layout.addWidget(self.debug_checkbox)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Warnings
        self.warnings_label = QLabel("")
        self.warnings_label.setStyleSheet("color: red; font-weight: bold;")
        self.warnings_label.hide()
        layout.addWidget(self.warnings_label)

        # Source Text view
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("No native text selected...")
        layout.addWidget(QLabel("Source Text:"))
        layout.addWidget(self.text_edit)

        # Translated Text view
        self.translated_text_edit = QTextEdit()
        self.translated_text_edit.setReadOnly(True)
        self.translated_text_edit.setPlaceholderText("No translation yet...")
        self.translated_text_edit.textChanged.connect(self._on_translated_text_changed)
        self.translated_text_label = QLabel("Translated Text:")
        layout.addWidget(self.translated_text_label)
        layout.addWidget(self.translated_text_edit)
        self.translated_text_label.hide()
        self.translated_text_edit.hide()

        # Action Buttons Layout
        actions_layout = QHBoxLayout()

        # Save Button
        self.save_button = QPushButton("Save Region")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_region_requested.emit)
        actions_layout.addWidget(self.save_button)

        # Delete Button (for saved regions)
        self.delete_button = QPushButton("Delete Region")
        self.delete_button.hide()
        self.delete_button.clicked.connect(self._on_delete_clicked)
        actions_layout.addWidget(self.delete_button)

        # Translate Button (for saved regions)
        self.translate_button = QPushButton("Translate")
        self.translate_button.hide()
        self.translate_button.clicked.connect(self._on_translate_clicked)
        actions_layout.addWidget(self.translate_button)

        # Edit/Apply/Cancel Buttons
        self.edit_button = QPushButton("Edit Translation")
        self.edit_button.hide()
        self.edit_button.clicked.connect(self._on_edit_clicked)
        actions_layout.addWidget(self.edit_button)

        self.apply_button = QPushButton("Apply Edits")
        self.apply_button.hide()
        self.apply_button.clicked.connect(self._on_apply_clicked)
        actions_layout.addWidget(self.apply_button)

        self.cancel_button = QPushButton("Cancel Edits")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        actions_layout.addWidget(self.cancel_button)

        layout.addLayout(actions_layout)

        # TRANS-05: Review/Approval row
        review_layout = QHBoxLayout()

        self.review_status_label = QLabel("")
        self.review_status_label.setObjectName("review_status_label")
        review_layout.addWidget(self.review_status_label)
        review_layout.addStretch()

        self.mark_reviewed_button = QPushButton("Marcar como revisada")
        self.mark_reviewed_button.setObjectName("mark_reviewed_button")
        self.mark_reviewed_button.hide()
        self.mark_reviewed_button.clicked.connect(self._on_mark_reviewed_clicked)
        review_layout.addWidget(self.mark_reviewed_button)

        self.approve_button = QPushButton("Aprobar")
        self.approve_button.setObjectName("approve_button")
        self.approve_button.hide()
        self.approve_button.clicked.connect(self._on_approve_clicked)
        review_layout.addWidget(self.approve_button)

        layout.addLayout(review_layout)

        self.setWidget(widget)

    def set_project_unlocked(self, unlocked: bool):
        self._project_unlocked = unlocked
        self._update_save_button_state()

    def _update_save_button_state(self):
        has_text = self._current_result is not None and len(self._current_result.fragments) > 0
        self.save_button.setEnabled(self._project_unlocked and has_text)

        if self._current_saved_region:
            self.delete_button.setEnabled(
                self._project_unlocked and not self._is_translating and not self._edit_mode
            )
            self.translate_button.setEnabled(
                self._project_unlocked
                and not self._is_translating
                and not self._edit_mode
                and bool(self._current_saved_region.source_text.strip())
            )

            from src.domain.models.enums import RegionStatus

            can_edit = (
                self._project_unlocked
                and not self._is_translating
                and not self._edit_mode
                and self._current_saved_region.status != RegionStatus.PENDING
            )
            self.edit_button.setEnabled(can_edit)

            self.apply_button.setEnabled(self._edit_mode and self.is_dirty())
            self.cancel_button.setEnabled(self._edit_mode)

    def _on_delete_clicked(self):
        if not self._current_saved_region:
            return
        if not self.resolve_dirty_draft():
            return
        self.delete_region_requested.emit(self._current_saved_region.id)

    def _on_translate_clicked(self):
        if not self._current_saved_region:
            return

        if not self.resolve_dirty_draft():
            return

        from PySide6.QtWidgets import QMessageBox

        from src.domain.models.enums import RegionStatus

        if (
            self._current_saved_region.status != RegionStatus.PENDING
            and self._current_saved_region.is_manually_edited
        ):
            reply = QMessageBox.warning(
                self,
                "Overwrite Manual Edit",
                "This translation was manually edited. Translating again will overwrite your changes. Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.translate_region_requested.emit(self._current_saved_region.id)

    def _on_debug_changed(self, state):
        if self.on_debug_toggled:
            self.on_debug_toggled(self.debug_checkbox.isChecked())

    def show_saved_region(self, region):
        self._current_saved_region = region
        self._is_translating = False
        self._edit_mode = False
        self.translated_text_edit.setReadOnly(True)
        if not region:
            self.delete_button.hide()
            self.translate_button.hide()
            self.edit_button.hide()
            self.apply_button.hide()
            self.cancel_button.hide()
            self.save_button.show()
            self.text_edit.clear()
            self.translated_text_edit.clear()
            self.translated_text_label.hide()
            self.translated_text_edit.hide()
            self.meta_label.setText("Fragments: 0 | Type: NONE")
            self._update_review_ui()
            return

        self.save_button.hide()
        self.delete_button.show()
        self.translate_button.show()

        from src.domain.models.enums import RegionStatus

        if region.status != RegionStatus.PENDING:
            self.edit_button.show()
        else:
            self.edit_button.hide()

        self.apply_button.hide()
        self.cancel_button.hide()
        self.translated_text_label.show()
        self.translated_text_edit.show()

        if region.status != RegionStatus.PENDING:
            self.translate_button.setText("Translate Again")
        else:
            self.translate_button.setText("Translate")

        # Update label if manually edited
        if region.is_manually_edited:
            self.translated_text_label.setText("Translated Text: [Manually Edited]")
        else:
            self.translated_text_label.setText("Translated Text:")

        self.text_edit.setPlainText(region.source_text)
        self.translated_text_edit.setPlainText(region.translated_text)

        self.meta_label.setText(
            f"Page: {region.page_id} | Status: {region.status.name} | Fragments: {len(region.source_fragments)}"
        )
        self.warnings_label.hide()
        self._update_save_button_state()
        self._update_review_ui()

    def set_translation_in_flight(self, region_id: str, in_flight: bool):
        if self._current_saved_region and self._current_saved_region.id == region_id:
            self._is_translating = in_flight
            if in_flight:
                self.translate_button.setText("Translating...")
            else:
                from src.domain.models.enums import RegionStatus

                if self._current_saved_region.status != RegionStatus.PENDING:
                    self.translate_button.setText("Translate Again")
                else:
                    self.translate_button.setText("Translate")
            self._update_save_button_state()
            self._update_review_ui()

    def update_result(self, result: TextExtractionResult | None):
        self._current_result = result
        if not result:
            self.text_edit.clear()
            self.translated_text_edit.clear()
            self.translated_text_label.hide()
            self.translated_text_edit.hide()
            self.translate_button.hide()
            self.edit_button.hide()
            self.apply_button.hide()
            self.cancel_button.hide()
            self.meta_label.setText("Fragments: 0 | Type: NONE")
            self.warnings_label.hide()
            self._update_save_button_state()
            self._update_review_ui()
            if self.debug_checkbox.isChecked() and self.on_debug_toggled:
                self.on_debug_toggled(True)
            return

        self.text_edit.setPlainText(result.text)
        self.meta_label.setText(
            f"Fragments: {len(result.fragments)} | Type: {result.extraction_method.value}"
        )

        if result.warnings:
            self.warnings_label.setText(f"Warnings: {', '.join(result.warnings)}")
            self.warnings_label.show()
        else:
            self.warnings_label.hide()

        # Re-trigger debug draw if checkbox is on
        if self.debug_checkbox.isChecked() and self.on_debug_toggled:
            self.on_debug_toggled(True)

        self._update_save_button_state()
        self._update_review_ui()

    def _update_review_ui(self):
        """Update review status label and contextual action buttons based on current region."""
        region = self._current_saved_region
        if not region:
            self.review_status_label.setText("")
            self.mark_reviewed_button.hide()
            self.approve_button.hide()
            return

        from src.domain.models.enums import ReviewStatus

        status = region.review_status
        in_edit = self._edit_mode
        is_translating = self._is_translating

        # Status label text + styling
        _LABELS = {
            ReviewStatus.UNTRANSLATED: ("Sin traducir", "color: #888;"),
            ReviewStatus.UNREVIEWED: ("Sin revisar", "color: #e67e22; font-weight: bold;"),
            ReviewStatus.REVIEWED: ("Revisada", "color: #2980b9; font-weight: bold;"),
            ReviewStatus.APPROVED: ("✓ Aprobada", "color: #27ae60; font-weight: bold;"),
        }
        text, style = _LABELS[status]
        self.review_status_label.setText(text)
        self.review_status_label.setStyleSheet(style)

        # Show contextual buttons (hidden during edit/translation)
        can_act = (
            self._project_unlocked
            and not in_edit
            and not is_translating
        )

        if status == ReviewStatus.UNREVIEWED and can_act:
            self.mark_reviewed_button.show()
            self.approve_button.hide()
        elif status == ReviewStatus.REVIEWED and can_act:
            self.mark_reviewed_button.hide()
            self.approve_button.show()
        else:
            self.mark_reviewed_button.hide()
            self.approve_button.hide()

    def _on_mark_reviewed_clicked(self):
        region = self._current_saved_region
        if not region or region.translation_revision is None:
            return
        self.review_requested.emit(region.id, region.translation_revision)

    def _on_approve_clicked(self):
        region = self._current_saved_region
        if not region or region.translation_revision is None:
            return
        self.approve_requested.emit(region.id, region.translation_revision)

    # Edit manual translation methods
    def _on_edit_clicked(self):
        self._edit_mode = True
        self.translated_text_edit.setReadOnly(False)
        self.translated_text_edit.setFocus()
        self.edit_button.hide()
        self.translate_button.hide()
        self.delete_button.hide()
        self.apply_button.show()
        self.cancel_button.show()
        self._update_save_button_state()

    def _on_apply_clicked(self):
        if not self.is_dirty():
            self._on_cancel_clicked()
            return

        success = self.apply_draft()
        if success:
            # UI state will refresh via show_saved_region once ViewModel broadcasts the change
            pass

    def _on_cancel_clicked(self):
        self._edit_mode = False
        self.translated_text_edit.setReadOnly(True)
        if self._current_saved_region:
            self.translated_text_edit.setPlainText(self._current_saved_region.translated_text)

        self.apply_button.hide()
        self.cancel_button.hide()
        self.edit_button.show()
        self.translate_button.show()
        self.delete_button.show()
        self._update_save_button_state()

    def _on_translated_text_changed(self):
        if self._edit_mode:
            self._update_save_button_state()

    def is_dirty(self) -> bool:
        if not self._edit_mode or not self._current_saved_region:
            return False
        return self.translated_text_edit.toPlainText() != self._current_saved_region.translated_text

    def apply_draft(self) -> bool:
        """Saves draft synchronously and returns True. If we had error propagation, we'd check it here."""
        if self.is_dirty():
            if self.on_edit_translation:
                success = self.on_edit_translation(
                    self._current_saved_region.id, self.translated_text_edit.toPlainText()
                )
                if not success:
                    # Operation failed (e.g. database error), preserve draft state
                    return False
            # We clear the edit mode immediately to unlock UI.
            self._edit_mode = False
            self.translated_text_edit.setReadOnly(True)
            return True
        return True

    def discard_draft(self):
        self._on_cancel_clicked()

    def resolve_dirty_draft(self) -> bool:
        """
        Shows a prompt if dirty. Returns True if caller should continue, False if caller should cancel.
        """
        if not self.is_dirty():
            return True

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved manual edits. What do you want to do?",
            QMessageBox.StandardButton.Apply
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Apply,
        )

        if reply == QMessageBox.StandardButton.Apply:
            return self.apply_draft()
        elif reply == QMessageBox.StandardButton.Discard:
            self.discard_draft()
            return True
        else:
            return False
