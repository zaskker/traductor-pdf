import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout


class ExportSuccessDialog(QDialog):
    def __init__(self, parent, dest_path: str, exported_regions: int, pages_touched: int):
        super().__init__(parent)
        self.setWindowTitle("Export Successful")
        self.setModal(True)
        self.resize(450, 150)

        self.dest_path = dest_path

        layout = QVBoxLayout(self)

        lbl_msg = QLabel(
            f"PDF exported successfully.\n\nRegions: {exported_regions}\nPages touched: {pages_touched}"
        )
        layout.addWidget(lbl_msg)

        # Path layout
        path_layout = QHBoxLayout()
        lbl_path = QLabel("Destination:")
        txt_path = QLineEdit(dest_path)
        txt_path.setReadOnly(True)
        path_layout.addWidget(lbl_path)
        path_layout.addWidget(txt_path)
        layout.addLayout(path_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_open_pdf = QPushButton("Open PDF")
        btn_open_folder = QPushButton("Open Folder")
        btn_close = QPushButton("Close")

        btn_open_pdf.clicked.connect(self._open_pdf)
        btn_open_folder.clicked.connect(self._open_folder)
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(btn_open_pdf)
        btn_layout.addWidget(btn_open_folder)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _open_pdf(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.dest_path))
        self.accept()

    def _open_folder(self):
        folder_path = os.path.dirname(self.dest_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
        self.accept()
