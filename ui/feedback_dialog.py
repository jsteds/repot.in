# ui/feedback_dialog.py
"""
Dialog Feedback & Bug Report
Memungkinkan user mengirim laporan bug, saran, atau request fitur langsung
ke developer via WhatsApp dengan pesan yang ter-format otomatis.
"""
import logging
from datetime import datetime
from urllib.parse import quote

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QLineEdit, QFormLayout, QFrame,
    QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QFont, QDesktopServices

from utils.constants import APP_VERSION


class FeedbackDialog(QDialog):
    """
    Dialog untuk mengirim feedback, laporan bug, atau request fitur.
    Pesan akan dikirim via WhatsApp ke nomor developer yang dikonfigurasi.
    """

    FEEDBACK_TYPES = {
        "Laporan Bug": "BUG REPORT",
        "Saran / Masukan": "SARAN",
        "Request Fitur Baru": "REQUEST FITUR",
        "Pertanyaan": "PERTANYAAN",
    }

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Kirim Feedback ke Developer")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Ambil info toko dari config
        config_data = self.config_manager.get_config()
        self.site_code = config_data.get('site_code', '-')
        self.store_name = self.config_manager.get_store_name(self.site_code)
        self.dev_wa = config_data.get('dev_whatsapp', '').strip()

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # --- Header ---
        header = QLabel("Kirim Pesan ke Developer")
        header.setFont(QFont("Segoe UI", 13, QFont.Bold))
        layout.addWidget(header)

        sub = QLabel(
            "Menemukan bug? Punya saran? Atau mau request fitur?\n"
            "Isi form di bawah, dan pesan akan langsung dikirim via WhatsApp."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # --- Form ---
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        # Info toko (read-only)
        self.lbl_store = QLineEdit(f"{self.site_code} — {self.store_name}")
        self.lbl_store.setReadOnly(True)
        self.lbl_store.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        form.addRow("Toko:", self.lbl_store)

        # Tipe feedback
        self.combo_type = QComboBox()
        for label in self.FEEDBACK_TYPES:
            self.combo_type.addItem(label)
        form.addRow("Jenis:", self.combo_type)

        # Judul singkat
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Ringkasan singkat (opsional)")
        self.input_title.setMaxLength(80)
        form.addRow("Judul:", self.input_title)

        # Deskripsi
        self.input_desc = QTextEdit()
        self.input_desc.setPlaceholderText(
            "Jelaskan secara detail:\n"
            "• Apa yang terjadi / yang diinginkan?\n"
            "• Langkah-langkah untuk mereproduksi bug (jika ada)\n"
            "• Dampak terhadap operasional"
        )
        self.input_desc.setMinimumHeight(130)
        self.input_desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form.addRow("Deskripsi:", self.input_desc)

        layout.addLayout(form)

        # --- Nomor WA Developer ---
        if not self.dev_wa:
            warn = QLabel(
                "⚠️  Nomor WhatsApp developer belum dikonfigurasi.\n"
                "   Hubungi developer untuk mengisi 'dev_whatsapp' di pengaturan."
            )
            warn.setStyleSheet("color: #e67e22; font-size: 11px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # --- Buttons ---
        btn_layout = QHBoxLayout()

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setFixedWidth(90)

        self.btn_send = QPushButton("Kirim via WhatsApp")
        self.btn_send.setDefault(True)
        self.btn_send.clicked.connect(self._send_feedback)
        self.btn_send.setEnabled(bool(self.dev_wa))
        self.btn_send.setStyleSheet("""
            QPushButton {
                background-color: #25D366; color: white;
                border: none; border-radius: 5px;
                padding: 8px 18px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #1ebe57; }
            QPushButton:disabled { background-color: #aaa; color: #eee; }
        """)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_send)
        layout.addLayout(btn_layout)

    def _send_feedback(self):
        desc = self.input_desc.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Peringatan", "Deskripsi tidak boleh kosong.")
            self.input_desc.setFocus()
            return

        fb_label = self.combo_type.currentText()
        fb_type  = self.FEEDBACK_TYPES.get(fb_label, "FEEDBACK")
        title    = self.input_title.text().strip()
        now      = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Format pesan WhatsApp
        lines = [
            f"*[REPOT.IN FEEDBACK — {fb_type}]*",
            "",
            f"*Toko*     : {self.site_code} — {self.store_name}",
            f"*Versi*    : v{APP_VERSION}",
            f"*Waktu*    : {now}",
        ]
        if title:
            lines.append(f"*Judul*    : {title}")
        lines += [
            "",
            f"*Detail:*",
            desc,
            "",
            "_(Pesan ini dikirim dari dalam aplikasi Repot.in)_"
        ]

        message = "\n".join(lines)

        # Buka WhatsApp
        wa_number = self.dev_wa.replace("+", "").replace("-", "").replace(" ", "")
        url = f"https://wa.me/{wa_number}?text={quote(message)}"
        success = QDesktopServices.openUrl(QUrl(url))

        if success:
            QMessageBox.information(
                self, "Berhasil",
                "WhatsApp terbuka dengan pesan yang sudah terisi.\n"
                "Silakan tekan 'Kirim' di WhatsApp untuk mengirimkan feedback."
            )
            self.accept()
        else:
            QMessageBox.warning(
                self, "Gagal",
                "Tidak dapat membuka WhatsApp.\n"
                "Pastikan WhatsApp Desktop atau browser tersedia."
            )
