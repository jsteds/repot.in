"""
File Downloader Dialog — Repotin
Mengunduh file pendukung dari Google Drive berdasarkan manifest online.
"""
import os
import json
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QMessageBox,
    QAbstractItemView, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor

from utils.constants import MANIFEST_DRIVE_ID, BASE_DIR


# ─── URL Helper ────────────────────────────────────────────────────────────────
def drive_download_url(file_id: str) -> str:
    # Always attempt standard Drive download format first. If it's a Spreadsheet, 
    # the user must provide the published CSV link or explicitly a sheet export link.
    # For now, stick to the standard universal downloader.
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ─── Worker: Fetch Manifest ────────────────────────────────────────────────────
class ManifestFetchWorker(QThread):
    finished = pyqtSignal(list)   # list of file dicts
    error    = pyqtSignal(str)

    def __init__(self, manifest_drive_id: str):
        super().__init__()
        self.manifest_drive_id = manifest_drive_id

    def run(self):
        try:
            url = drive_download_url(self.manifest_drive_id)
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.finished.emit(data.get("files", []))
        except requests.exceptions.ConnectionError:
            self.error.emit("Tidak ada koneksi internet. Periksa jaringan Anda.")
        except requests.exceptions.Timeout:
            self.error.emit("Waktu permintaan habis. Server tidak merespons.")
        except Exception as e:
            self.error.emit(f"Gagal mengambil manifest: {str(e)}")


# ─── Worker: Download Single File ─────────────────────────────────────────────
class FileDownloadWorker(QThread):
    progress  = pyqtSignal(int)        # 0–100
    finished  = pyqtSignal(str)        # local path
    error     = pyqtSignal(str)

    def __init__(self, drive_id: str, target_path: str, direct_url: str = None):
        super().__init__()
        self.drive_id    = drive_id
        self.target_path = target_path
        self.direct_url  = direct_url  # If provided, skip Drive ID logic and use this URL

    def run(self):
        try:
            # Use a direct URL if provided, otherwise fall back to Drive ID
            url = self.direct_url if self.direct_url else drive_download_url(self.drive_id)
            session = requests.Session()
            
            # First request to get the initial response (might be the file, might be a warning page)
            response = session.get(url, stream=True, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            # Google Drive large file warning bypass logic:
            # For large files, Drive returns an HTML page with a form that must be submitted.
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type:
                # Read the HTML content (this is safe because warning pages are small)
                content = response.content.decode('utf-8', errors='ignore')
                
                import re
                from urllib.parse import urljoin
                
                # Look for the download confirmation form
                action_match = re.search(r'<form[^>]*action="([^"]+)"', content)
                if action_match:
                    action_url = action_match.group(1)
                    
                    # Extract hidden input fields like 'id', 'export', 'confirm', 'uuid'
                    inputs = re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', content)
                    params = {name: value for name, value in inputs}
                    
                    # Handle relative URLs
                    if action_url.startswith('/'):
                        action_url = urljoin("https://drive.google.com", action_url)
                        
                    # Make the second request with the confirmation tokens
                    response = session.get(action_url, params=params, stream=True, timeout=30)
                    response.raise_for_status()

            total = int(response.headers.get("content-length", 0))
            downloaded = 0

            os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
            with open(self.target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(int(downloaded / total * 100))

            self.progress.emit(100)
            
            # Post-download verification
            try:
                with open(self.target_path, 'rb') as f:
                    chunk = f.read(1024).lower()
                    if b'<!doctype html' in chunk or b'<html' in chunk:
                        os.remove(self.target_path)
                        raise ValueError(
                            "File yang diunduh adalah halaman web HTML dari Google Drive. "
                            "Ini biasanya terjadi jika file Anda tidak disetel ke 'Siapa saja yang memiliki link (Anyone with link)'. "
                            "Silakan periksa izin akses file tersebut di Google Drive Anda."
                        )
            except Exception as read_err:
                if isinstance(read_err, ValueError):
                    raise read_err
                # Ignore generic read errors here for now

            self.finished.emit(self.target_path)
        except requests.exceptions.ConnectionError:
            self.error.emit("Tidak ada koneksi internet.")
        except Exception as e:
            self.error.emit(str(e))
            


# ─── Main Dialog ───────────────────────────────────────────────────────────────
class DownloaderDialog(QDialog):

    # Column indices
    COL_NAME    = 0
    COL_CAT     = 1
    COL_DESC    = 2
    COL_STATUS  = 3
    COL_ACTION  = 4

    STATUS_AVAILABLE  = "✅  Tersedia"
    STATUS_MISSING    = "🔴  Belum Diunduh"
    STATUS_LOADING    = "⏳  Mengunduh..."
    STATUS_ERROR      = "❌  Gagal"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unduh File Online")
        self.resize(720, 480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._manifest_files: list = []
        self._active_workers: list = []   # keep references alive
        self._init_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        self.setStyleSheet("font-family: 'Segoe UI', Arial, sans-serif;")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(14)

        # ── Header ─────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        icon_lbl = QLabel("📥")
        icon_lbl.setStyleSheet("font-size: 24px;")
        title_lbl = QLabel("File Downloader")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a73e8;")
        sub_lbl = QLabel("Unduh file pendukung aplikasi dari server online")
        sub_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px;")

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addSpacing(8)
        header.addLayout(title_col)
        header.addStretch()

        self.btn_check = QPushButton("🔍  Cek File Online")
        self.btn_check.setFixedHeight(36)
        self.btn_check.setCursor(Qt.PointingHandCursor)
        self.btn_check.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f9cf9, stop:1 #1a73e8);
                color: white; font-weight: bold; font-size: 12px;
                border-radius: 8px; border: none; padding: 0 16px;
            }
            QPushButton:hover { background: #1557b0; }
            QPushButton:disabled { background: #cfd8dc; color: #90a4ae; }
        """)
        self.btn_check.clicked.connect(self._fetch_manifest)
        header.addWidget(self.btn_check)
        root.addLayout(header)

        # ── Divider ────────────────────────────────────────────────────────────
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background: #4A4C50; max-height: 1px; border: none;")
        root.addWidget(div)

        # ── Status label ───────────────────────────────────────────────────────
        self.status_lbl = QLabel("Klik 'Cek File Online' untuk memulai.")
        self.status_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
        root.addWidget(self.status_lbl)

        # ── Table ──────────────────────────────────────────────────────────────
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Nama File", "Kategori", "Deskripsi", "Status", "Aksi"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2B2D30;
                alternate-background-color: #34495e;
                color: #EAEAEA;
                border: 1px solid #4A4C50;
                border-radius: 8px;
                font-size: 12px;
                outline: none;
            }
            QTableWidget::item { padding: 8px; border: none; }
            QTableWidget::item:selected { background-color: #3A78D0; color: #FFFFFF; }
            QHeaderView::section {
                background-color: #1E1F22;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 11px;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #4A4C50;
            }
        """)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.table)

        # ── Bottom bar ─────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #7f8c8d; font-size: 11px;")

        self.btn_download_all = QPushButton("⬇  Unduh Semua yang Belum Ada")
        self.btn_download_all.setFixedHeight(36)
        self.btn_download_all.setCursor(Qt.PointingHandCursor)
        self.btn_download_all.setEnabled(False)
        self.btn_download_all.setStyleSheet("""
            QPushButton {
                background-color: #e8f5e9;
                color: #2e7d32;
                border: 1.5px solid #a5d6a7;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #c8e6c9; }
            QPushButton:disabled { background: #2B2D30; color: #666; border-color: #4A4C50; }
        """)
        self.btn_download_all.clicked.connect(self._download_all_missing)

        bottom.addWidget(self.lbl_count)
        bottom.addStretch()
        bottom.addWidget(self.btn_download_all)
        root.addLayout(bottom)

    # ── Logic ─────────────────────────────────────────────────────────────────
    def _fetch_manifest(self):
        if not MANIFEST_DRIVE_ID or MANIFEST_DRIVE_ID == "GANTI_DENGAN_MANIFEST_ID":
            QMessageBox.warning(self, "Konfigurasi Diperlukan",
                "ID manifest Google Drive belum diatur.\n\n"
                "Buka utils/constants.py dan isi nilai MANIFEST_DRIVE_ID.")
            return

        self.btn_check.setEnabled(False)
        self.btn_download_all.setEnabled(False)
        self.table.setRowCount(0)
        self.status_lbl.setText("⏳ Mengambil daftar file dari server...")

        self._worker_manifest = ManifestFetchWorker(MANIFEST_DRIVE_ID)
        self._worker_manifest.finished.connect(self._on_manifest_fetched)
        self._worker_manifest.error.connect(self._on_manifest_error)
        self._worker_manifest.start()

    def _on_manifest_fetched(self, files: list):
        self._manifest_files = files
        self.btn_check.setEnabled(True)

        if not files:
            self.status_lbl.setText("Tidak ada file yang tersedia dalam manifest.")
            return

        self.table.setRowCount(0)
        missing_count = 0

        for entry in files:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name        = entry.get("name", "")
            category    = entry.get("category", "")
            description = entry.get("description", "")
            folder      = entry.get("target_folder", "")
            drive_id    = entry.get("drive_id", "")
            direct_url  = entry.get("url", None)   # Optional direct URL override

            local_path  = os.path.join(BASE_DIR, folder, name)
            is_present  = os.path.isfile(local_path)
            status_text = self.STATUS_AVAILABLE if is_present else self.STATUS_MISSING
            if not is_present:
                missing_count += 1

            # Columns
            name_item = QTableWidgetItem(name)
            name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.table.setItem(row, self.COL_NAME,   name_item)
            self.table.setItem(row, self.COL_CAT,    QTableWidgetItem(category))
            self.table.setItem(row, self.COL_DESC,   QTableWidgetItem(description))

            status_item = QTableWidgetItem(status_text)
            if is_present:
                status_item.setForeground(QColor("#2e7d32"))
            else:
                status_item.setForeground(QColor("#c62828"))
            self.table.setItem(row, self.COL_STATUS, status_item)

            # Action column: progress bar + button in a widget
            action_widget = self._make_action_widget(row, drive_id, local_path, is_present, direct_url)
            self.table.setCellWidget(row, self.COL_ACTION, action_widget)
            self.table.setRowHeight(row, 46)

        total = len(files)
        self.lbl_count.setText(f"{total - missing_count}/{total} file tersedia lokal")
        self.btn_download_all.setEnabled(missing_count > 0)
        self.status_lbl.setText(f"✅ Berhasil memuat {total} file dari manifest.")

    def _on_manifest_error(self, msg: str):
        self.btn_check.setEnabled(True)
        self.status_lbl.setText(f"❌ {msg}")
        QMessageBox.critical(self, "Gagal Mengambil Manifest", msg)

    def _make_action_widget(self, row: int, drive_id: str, local_path: str, already_present: bool, direct_url: str = None) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        progress = QProgressBar()
        progress.setFixedHeight(14)
        progress.setRange(0, 100)
        progress.setValue(100 if already_present else 0)
        progress.setTextVisible(False)
        progress.setStyleSheet("""
            QProgressBar {
                background: #e0e0e0; border-radius: 7px; border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4caf50, stop:1 #81c784);
                border-radius: 7px;
            }
        """)
        progress.setVisible(not already_present)

        has_source = bool(direct_url) or bool(drive_id and drive_id != "GANTI_DENGAN_FILE_ID_DARI_DRIVE")
        btn = QPushButton("Unduh")
        btn.setFixedHeight(26)
        btn.setFixedWidth(64)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setEnabled(not already_present and has_source)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                border-radius: 5px; border: none; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background-color: #1557b0; }
            QPushButton:disabled { background: #3d3f42; color: #666; }
        """)
        if already_present:
            btn.setText("✓")
            btn.setStyleSheet(btn.styleSheet() + "QPushButton { background: #e8f5e9; color: #2e7d32; }")
        else:
            btn.clicked.connect(lambda _, r=row, d=drive_id, p=local_path, b=btn, pb=progress, u=direct_url:
                                self._start_single_download(r, d, p, b, pb, u))

        layout.addWidget(progress, 1)
        layout.addWidget(btn)
        return container

    def _start_single_download(self, row: int, drive_id: str, local_path: str,
                                btn: QPushButton, progress: QProgressBar, direct_url: str = None):
        if not direct_url and (not drive_id or drive_id == "GANTI_DENGAN_FILE_ID_DARI_DRIVE"):
            QMessageBox.information(self, "Belum Dikonfigurasi",
                "Drive ID atau URL untuk file ini belum diisi di manifest.")
            return

        btn.setEnabled(False)
        btn.setText("...")
        progress.setVisible(True)
        progress.setValue(0)
        self.table.item(row, self.COL_STATUS).setText(self.STATUS_LOADING)
        self.table.item(row, self.COL_STATUS).setForeground(QColor("#f57c00"))

        worker = FileDownloadWorker(drive_id, local_path, direct_url=direct_url)
        worker.progress.connect(progress.setValue)
        worker.finished.connect(lambda path, r=row, b=btn, pb=progress:
                                self._on_download_done(r, path, b, pb))
        worker.error.connect(lambda msg, r=row, b=btn:
                             self._on_download_error(r, msg, b))
        self._active_workers.append(worker)
        worker.start()

    def _on_download_done(self, row: int, path: str, btn: QPushButton, progress: QProgressBar):
        self.table.item(row, self.COL_STATUS).setText(self.STATUS_AVAILABLE)
        self.table.item(row, self.COL_STATUS).setForeground(QColor("#2e7d32"))
        btn.setText("✓")
        btn.setEnabled(False)
        btn.setStyleSheet("""
            QPushButton {
                background: #e8f5e9; color: #2e7d32;
                border-radius: 5px; border: none; font-size: 11px;
            }
        """)
        progress.setVisible(False)
        self._refresh_count()

    def _on_download_error(self, row: int, msg: str, btn: QPushButton):
        self.table.item(row, self.COL_STATUS).setText(self.STATUS_ERROR)
        self.table.item(row, self.COL_STATUS).setForeground(QColor("#c62828"))
        btn.setEnabled(True)
        btn.setText("Coba Lagi")
        QMessageBox.critical(self, "Gagal Mengunduh", msg)

    def _download_all_missing(self):
        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, self.COL_STATUS)
            if status_item and status_item.text() == self.STATUS_MISSING:
                widget = self.table.cellWidget(row, self.COL_ACTION)
                if widget:
                    btn = widget.findChild(QPushButton)
                    if btn and btn.isEnabled():
                        btn.click()

    def _refresh_count(self):
        total   = self.table.rowCount()
        present = sum(
            1 for r in range(total)
            if self.table.item(r, self.COL_STATUS) and
               self.STATUS_AVAILABLE in self.table.item(r, self.COL_STATUS).text()
        )
        self.lbl_count.setText(f"{present}/{total} file tersedia lokal")
        if present == total:
            self.btn_download_all.setEnabled(False)
