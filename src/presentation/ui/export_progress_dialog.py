from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ExportProgressDialog(QDialog):
    cancel_requested = Signal()
    force_stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporting translated PDF...")
        # Modeless dialog
        self.setModal(False)
        # Avoid closing with ESC
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        self.lbl_stage = QLabel("Starting export...")
        self.lbl_stage.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_stage)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)  # Indeterminate initially
        layout.addWidget(self.progress_bar)

        self.lbl_details = QLabel("")
        layout.addWidget(self.lbl_details)

        self.lbl_force_stop = QLabel("")
        self.lbl_force_stop.setStyleSheet("color: red;")
        self.lbl_force_stop.hide()
        layout.addWidget(self.lbl_force_stop)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_force_stop = QPushButton("Force stop")
        self.btn_force_stop.setStyleSheet("color: red;")
        self.btn_force_stop.hide()
        self.btn_force_stop.clicked.connect(self._on_force_stop)
        btn_layout.addWidget(self.btn_force_stop)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        self._is_cancelling = False
        self._is_finalizing = False

    def update_progress(
        self,
        stage_name: str,
        completed_regions: int,
        total_regions: int,
        completed_pages: int,
        total_pages: int,
    ):
        if self._is_cancelling:
            return

        if stage_name == "FINALIZING":
            self._is_finalizing = True
            self.lbl_stage.setText("Finalizando exportación...")
            self.btn_cancel.setEnabled(False)
            self.progress_bar.setMaximum(0)  # Indeterminate
            self.hide_force_stop()
        else:
            self.lbl_stage.setText(f"Stage: {stage_name.capitalize()}")
            if total_regions > 0:
                self.progress_bar.setMaximum(total_regions)
                self.progress_bar.setValue(completed_regions)
            else:
                self.progress_bar.setMaximum(0)

            details = []
            if total_regions > 0:
                details.append(f"Regions: {completed_regions} / {total_regions}")
            if total_pages > 0:
                details.append(f"Pages touched: {completed_pages} / {total_pages}")

            self.lbl_details.setText(" | ".join(details))

    def _on_cancel(self):
        if self._is_finalizing or self._is_cancelling:
            return

        self._is_cancelling = True
        self.btn_cancel.setEnabled(False)
        self.lbl_stage.setText("Cancelling...")
        self.progress_bar.setMaximum(0)  # Indeterminate
        self.cancel_requested.emit()

    def show_force_stop_option(self):
        if self._is_finalizing:
            return
        self.lbl_force_stop.setText("Export is taking longer to stop.")
        self.lbl_force_stop.show()
        self.btn_force_stop.show()

    def hide_force_stop(self):
        self.lbl_force_stop.hide()
        self.btn_force_stop.hide()

    def _on_force_stop(self):
        if self._is_finalizing:
            return
        self.btn_force_stop.setEnabled(False)
        self.force_stop_requested.emit()

    def closeEvent(self, event):
        if self._is_finalizing:
            # Block close if finalizing
            event.ignore()
            return

        if not self._is_cancelling:
            self._on_cancel()

        # We don't close immediately. We wait for terminal event to close us.
        event.ignore()
