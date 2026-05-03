# ui/feedback_dialog.py
"""
Dialog Feedback & Bug Report
Mengirim laporan bug, saran, atau request fitur langsung ke Google Sheets
melalui Google Apps Script Web App.  Jika offline, data disimpan lokal
dan di-upload otomatis saat startup berikutnya.
"""
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QLineEdit, QFormLayout, QFrame,
    QMessageBox, QSizePolicy, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from utils.constants import APP_VERSION, FEEDBACK_SHEET_URL

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Worker thread — kirim HTTP POST di background agar UI tidak freeze
# ──────────────────────────────────────────────────────────────────────────────
class _SubmitWorker(QThread):
    done = pyqtSignal(bool)   # True = berhasil online, False = disimpan lokal

    def __init__(self, payload: dict, sheet_url: str):
        super().__init__()
        self.payload   = payload
        self.sheet_url = sheet_url

    def run(self):
        from modules.feedback_manager import submit_feedback
        ok = submit_feedback(self.payload, self.sheet_url)
        self.done.emit(ok)


# ──────────────────────────────────────────────────────────────────────────────
# Dialog utama
# ──────────────────────────────────────────────────────────────────────────────
class FeedbackDialog(QDialog):
    """
    Form feedback yang mengirim langsung ke Google Sheets.
    Jika koneksi bermasalah, data tersimpan lokal dan di-upload otomatis
    saat startup aplikasi berikutnya.
    """

    FEEDBACK_TYPES = [
        "Laporan Bug",
        "Saran / Masukan",
        "Request Fitur Baru",
        "Pertanyaan",
    ]

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Kirim Feedback ke Developer")
        self.setMinimumWidth(540)
        self.setMinimumHeight(450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        cfg = self.config_manager.get_config()
        self.site_code  = cfg.get("site_code", "-")
        self.store_name = self.config_manager.get_store_name(self.site_code)
        # URL sudah di-compile ke dalam aplikasi — tidak perlu konfigurasi user
        self.sheet_url  = FEEDBACK_SHEET_URL

        self._worker = None
        self._init_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(22, 18, 22, 18)

        # Header
        hdr = QLabel("Kirim Feedback ke Developer")
        hdr.setFont(QFont("Segoe UI", 13, QFont.Bold))
        root.addWidget(hdr)

        sub = QLabel(
            "Temukan bug? Punya saran? Atau ingin request fitur?\n"
            "Isi form di bawah. Data akan langsung tersimpan ke spreadsheet developer."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        # Toko (read-only)
        self.lbl_store = QLineEdit(f"{self.site_code} — {self.store_name}")
        self.lbl_store.setReadOnly(True)
        self.lbl_store.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        form.addRow("Toko:", self.lbl_store)

        # Jenis
        self.combo_type = QComboBox()
        self.combo_type.addItems(self.FEEDBACK_TYPES)
        form.addRow("Jenis:", self.combo_type)

        # Judul
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Ringkasan singkat (opsional)")
        self.input_title.setMaxLength(100)
        form.addRow("Judul:", self.input_title)

        # Deskripsi
        self.input_desc = QTextEdit()
        self.input_desc.setPlaceholderText(
            "Jelaskan secara detail:\n"
            "• Apa yang terjadi / yang diinginkan?\n"
            "• Langkah untuk mereproduksi bug (jika ada)\n"
            "• Dampak terhadap operasional"
        )
        self.input_desc.setMinimumHeight(140)
        self.input_desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form.addRow("Deskripsi:", self.input_desc)

        root.addLayout(form)

        # Progress bar (tersembunyi sampai submit)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # indeterminate
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { border: none; background: #e0e0e0; }"
            "QProgressBar::chunk { background: #2980b9; }"
        )
        root.addWidget(self.progress)

        # Status label
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #555;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.lbl_status)

        # Tombol
        btn_row = QHBoxLayout()

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setFixedWidth(90)

        self.btn_send = QPushButton("📤  Kirim Feedback")
        self.btn_send.setDefault(True)
        self.btn_send.clicked.connect(self._on_send)
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white;
                border: none; border-radius: 6px;
                padding: 8px 22px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover   { background-color: #2471a3; }
            QPushButton:pressed { background-color: #1a5276; }
            QPushButton:disabled { background-color: #a0b4c8; color: #ddd; }
        """)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_send)
        root.addLayout(btn_row)

    # ── Slot ──────────────────────────────────────────────────────────────────
    def _on_send(self):
        desc = self.input_desc.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Peringatan", "Deskripsi tidak boleh kosong.")
            self.input_desc.setFocus()
            return

        from modules.feedback_manager import build_payload
        payload = build_payload(
            site_code    = self.site_code,
            store_name   = self.store_name,
            feedback_type= self.combo_type.currentText(),
            title        = self.input_title.text().strip(),
            description  = desc,
        )

        # Tampilkan loading state
        self.btn_send.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(True)
        self.lbl_status.setText("Mengirim feedback…")

        # Jalankan di thread terpisah
        self._worker = _SubmitWorker(payload, self.sheet_url)
        self._worker.done.connect(self._on_submit_done)
        self._worker.start()

    def _on_submit_done(self, online: bool):
        self.progress.setVisible(False)
        self.btn_send.setEnabled(True)
        self.btn_cancel.setEnabled(True)

        if online:
            QMessageBox.information(
                self, "Tengkyu!",
                "Feedback berhasil dikirim ke jst_eds.\n"
                "caaalm, kalo ada waktu gue baca."
            )
        else:
            QMessageBox.information(
                self, "Tersimpan Lokal",
                "Tidak dapat terhubung ke server saat ini.\n"
                "Feedback disimpan di perangkat ini dan akan dikirim\n"
                "otomatis saat aplikasi dibuka kembali dengan koneksi internet."
            )
        self.accept()
