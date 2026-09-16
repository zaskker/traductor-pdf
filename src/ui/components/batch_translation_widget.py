from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

class BatchTranslationWidget(QWidget):
    translate_all_requested = Signal()
    cancel_batch_requested = Signal()
    retry_failed_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active = False
        self._has_failed = False
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.translate_btn = QPushButton("Traducir pendientes")
        self.translate_btn.clicked.connect(self.translate_all_requested.emit)
        layout.addWidget(self.translate_btn)
        
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self.cancel_batch_requested.emit)
        self.cancel_btn.setVisible(False)
        layout.addWidget(self.cancel_btn)
        
        self.retry_btn = QPushButton("Reintentar fallidas")
        self.retry_btn.clicked.connect(self.retry_failed_requested.emit)
        self.retry_btn.setVisible(False)
        layout.addWidget(self.retry_btn)
        
        self.set_inactive()
        
    @Slot(int, int)
    def update_progress(self, completed: int, total: int):
        self.status_label.setText(f"Traduciendo {completed} / {total}")
        self.status_label.setVisible(True)
        
    @Slot(dict)
    def on_batch_finished(self, summary: dict):
        self._is_active = False
        succeeded = summary.get("SUCCEEDED", 0)
        failed = summary.get("FAILED", 0)
        skipped = summary.get("SKIPPED", 0)
        
        text = f"Completadas: {succeeded}"
        if failed > 0 or skipped > 0:
            text += f", Fallidas: {failed}, Omitidas: {skipped}"
            self._has_failed = True
        else:
            self._has_failed = False
            
        self.status_label.setText(text)
        self.status_label.setVisible(True)
        self.translate_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.retry_btn.setVisible(self._has_failed)

    def set_active(self):
        self._is_active = True
        self._has_failed = False
        self.translate_btn.setVisible(False)
        self.retry_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.status_label.setVisible(True)
        
    def set_inactive(self):
        self._is_active = False
        self.status_label.setVisible(False)
        self.translate_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.retry_btn.setVisible(self._has_failed)
        
    def set_has_pending(self, has_pending: bool):
        if not self._is_active:
            self.translate_btn.setEnabled(has_pending)
