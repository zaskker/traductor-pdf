from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.domain.models.region import TranslationRegion
from src.ui.components.batch_translation_widget import BatchTranslationWidget


class RegionListPanel(QDockWidget):
    delete_region_requested = Signal(str)  # region_id
    region_selected = Signal(str)  # region_id

    def __init__(self, parent=None):
        super().__init__("Saved Regions", parent)
        self._setup_ui()
        self._regions: list[TranslationRegion] = []

    def _setup_ui(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        btn_layout.addWidget(self.delete_btn)

        layout.addLayout(btn_layout)

        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

        self.batch_widget = BatchTranslationWidget()
        layout.addWidget(self.batch_widget)

        self.setWidget(widget)

    def _on_selection_changed(self):
        selected = self.list_widget.selectedItems()
        self.delete_btn.setEnabled(len(selected) > 0)
        if selected:
            region_id = selected[0].data(99)
            self.region_selected.emit(region_id)

    def select_region(self, region_id: str | None):
        # Desconectar temporalmente para evitar loop de señales
        self.list_widget.itemSelectionChanged.disconnect(self._on_selection_changed)

        self.list_widget.clearSelection()
        if region_id:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(99) == region_id:
                    item.setSelected(True)
                    break

        self.delete_btn.setEnabled(len(self.list_widget.selectedItems()) > 0)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_delete_clicked(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            return

        region_id = selected[0].data(99)  # role 99
        self.delete_region_requested.emit(region_id)

    def set_regions(self, regions: list[TranslationRegion]):
        self.list_widget.clear()
        self._regions = regions

        for idx, region in enumerate(regions):
            from src.domain.models.enums import ReviewStatus
            
            review_indicator = ""
            if region.review_status == ReviewStatus.UNTRANSLATED:
                review_indicator = "[Sin traducir]"
            elif region.review_status == ReviewStatus.UNREVIEWED:
                review_indicator = "[Sin revisar]"
            elif region.review_status == ReviewStatus.REVIEWED:
                review_indicator = "[Revisada]"
            elif region.review_status == ReviewStatus.APPROVED:
                review_indicator = "[✓ Aprobada]"

            text = f"#{idx + 1} Page {region.page_id} - {region.status.name} {review_indicator}"
            item = QListWidgetItem(text)
            item.setData(99, region.id)  # store id for retrieval
            
            # Simple color tint based on review status
            if region.review_status == ReviewStatus.UNREVIEWED:
                from PySide6.QtGui import QColor, QBrush
                item.setForeground(QBrush(QColor("#e67e22"))) # Orange
            elif region.review_status == ReviewStatus.REVIEWED:
                from PySide6.QtGui import QColor, QBrush
                item.setForeground(QBrush(QColor("#2980b9"))) # Blue
            elif region.review_status == ReviewStatus.APPROVED:
                from PySide6.QtGui import QColor, QBrush
                item.setForeground(QBrush(QColor("#27ae60"))) # Green
                
            self.list_widget.addItem(item)
