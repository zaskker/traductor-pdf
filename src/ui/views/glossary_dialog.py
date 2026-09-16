import uuid
from datetime import UTC, datetime

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
)

from src.application.services.project_service import ProjectService
from src.domain.models.project import Project
from src.domain.models.glossary import Glossary, GlossaryEntry


class GlossaryDialog(QDialog):
    def __init__(self, project_service: ProjectService, project: Project, parent=None):
        super().__init__(parent)
        self.project_service = project_service
        self.project = project
        self.glossary = None
        self.repo = self.project_service.glossary_repo

        self.setWindowTitle("Glosario del proyecto")
        self.resize(500, 400)
        self._init_ui()
        self._load_glossary()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Término origen", "Traducción obligatoria"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Agregar")
        self.btn_remove = QPushButton("Eliminar")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        layout.addLayout(btn_layout)

        bottom_layout = QHBoxLayout()
        self.btn_save = QPushButton("Guardar")
        self.btn_cancel = QPushButton("Cancelar")
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_cancel)
        bottom_layout.addWidget(self.btn_save)
        layout.addLayout(bottom_layout)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)

    def _load_glossary(self):
        if self.project.active_glossary_id:
            self.glossary = self.repo.get(self.project.active_glossary_id)

        if not self.glossary:
            now = datetime.now(UTC)
            self.glossary = Glossary(
                id=str(uuid.uuid4()),
                project_id=self.project.id,
                name="Project Glossary",
                revision=1,
                created_at=now,
                updated_at=now,
            )

        self.setWindowTitle(f"Glosario del proyecto — Revisión {self.glossary.revision}")

        self.table.setRowCount(0)
        for entry in self.glossary.entries:
            self._add_row(entry.id, entry.source_term, entry.target_term)

    def _add_row(self, entry_id: str, source: str, target: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        item_source = QTableWidgetItem(source)
        item_source.setData(32, entry_id)  # store entry_id in user role
        self.table.setItem(row, 0, item_source)
        
        item_target = QTableWidgetItem(target)
        self.table.setItem(row, 1, item_target)

    def _on_add(self):
        self._add_row("", "", "")
        # Edit new row immediately
        row = self.table.rowCount() - 1
        self.table.editItem(self.table.item(row, 0))

    def _on_remove(self):
        for item in self.table.selectedItems():
            self.table.removeRow(item.row())

    def _on_save(self):
        # We process the UI table state and apply it to the Glossary model, which bumps revision automatically.
        # Track entries currently in model
        existing_ids = {e.id: e for e in self.glossary.entries}
        ui_ids = set()

        try:
            for row in range(self.table.rowCount()):
                item_source = self.table.item(row, 0)
                item_target = self.table.item(row, 1)
                
                source = item_source.text().strip() if item_source else ""
                target = item_target.text().strip() if item_target else ""
                
                # skip empty rows
                if not source and not target:
                    continue
                    
                entry_id = item_source.data(32) if item_source else ""
                
                if entry_id and entry_id in existing_ids:
                    ui_ids.add(entry_id)
                    # Update
                    self.glossary.update_entry(entry_id, source, target)
                else:
                    # New
                    new_id = str(uuid.uuid4())
                    self.glossary.add_entry(GlossaryEntry(new_id, source, target))
                    ui_ids.add(new_id)

            # Remove entries that were deleted in UI
            for e_id in list(existing_ids.keys()):
                if e_id not in ui_ids:
                    self.glossary.remove_entry(e_id)

            self.glossary.updated_at = datetime.now(UTC)
            self.repo.save(self.glossary)
            
            # Link to project if needed
            if self.project.active_glossary_id != self.glossary.id:
                self.project.active_glossary_id = self.glossary.id
                self.project_service._project_repo.save(self.project)

            self.accept()

        except ValueError as e:
            QMessageBox.critical(self, "Error de validación", str(e))
