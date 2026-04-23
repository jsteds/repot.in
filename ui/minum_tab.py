# ui/minum_tab.py
import os
import json
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDateEdit, QGroupBox, QMessageBox, QFrame, QSizePolicy, QSplitter
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont, QColor

from utils.constants import MINUM_DATA_FILE
from utils.employee_utils import EmployeeDB, ROLE_ADMIN

EXCLUDED_JABATAN = ["Area Manager"]


class MinumTab(QWidget):
    """Tab untuk mencatat giliran pembelian air minum galon per Periode/siklus."""

    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        self.db = EmployeeDB()
        self.data = {"Periode": 1, "purchases": []}
        self._load_data()
        self._init_ui()
        self._refresh_ui()

    # ─────────────────────────────────────────
    # DATA MANAGEMENT
    # ─────────────────────────────────────────

    def _load_data(self):
        """Load data dari JSON. Buat file baru jika belum ada."""
        if os.path.exists(MINUM_DATA_FILE):
            try:
                with open(MINUM_DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                    if "Periode" not in self.data:
                        self.data["Periode"] = 1
                    if "purchases" not in self.data:
                        self.data["purchases"] = []
                logging.info(f"[Minum] Data loaded: Periode {self.data['Periode']}, "
                             f"{len(self.data['purchases'])} purchases.")
            except Exception as e:
                logging.error(f"[Minum] Gagal load data: {e}")
                self.data = {"Periode": 1, "purchases": []}
        else:
            self._save_data()

    def _save_data(self):
        """Simpan data ke JSON."""
        try:
            os.makedirs(os.path.dirname(MINUM_DATA_FILE), exist_ok=True)
            with open(MINUM_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"[Minum] Gagal simpan data: {e}")
            QMessageBox.critical(self, "Error", f"Gagal menyimpan data:\n{e}")

    def _get_members(self):
        """Ambil daftar anggota dari DB, kecuali Area Manager dan Admin."""
        all_employees = self.db.get_all_employees()
        members = [
            emp for emp in all_employees
            if emp['jabatan'] not in EXCLUDED_JABATAN
            and emp['role_aplikasi'] != ROLE_ADMIN
        ]
        return members

    def _get_current_Periode_purchases(self):
        """Ambil set NIK yang sudah beli di Periode saat ini."""
        current_Periode = self.data["Periode"]
        bought_niks = set()
        for p in self.data["purchases"]:
            if p.get("Periode") == current_Periode:
                bought_niks.add(p.get("member_nik"))
        return bought_niks

    def _get_Periode_purchases(self, Periode_num):
        """Ambil pembelian untuk Periode tertentu."""
        return [p for p in self.data["purchases"] if p.get("Periode") == Periode_num]

    def _get_all_Periodes(self):
        """Dapatkan daftar semua nomor Periode yang pernah ada."""
        Periodes = sorted(set(p.get("Periode", 1) for p in self.data["purchases"]), reverse=True)
        return Periodes if Periodes else [self.data["Periode"]]

    # ─────────────────────────────────────────
    # UI INIT
    # ─────────────────────────────────────────

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # ── Header ──────────────────────────────
        header_layout = QHBoxLayout()

        self.title_label = QLabel("💧 Jadwal Galon")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.Periode_label = QLabel("Periode 1")
        self.Periode_label.setObjectName("PeriodeLabel")
        Periode_font = QFont()
        Periode_font.setPointSize(12)
        self.Periode_label.setFont(Periode_font)
        self.Periode_label.setStyleSheet(
            "color: #2980b9; font-weight: bold; "
            "background: #eaf4fb; padding: 4px 12px; border-radius: 8px;"
        )

        self.sync_btn = QPushButton("🔄 Sync Anggota")
        self.sync_btn.setFixedHeight(32)
        self.sync_btn.setToolTip("Sinkronisasi ulang daftar anggota dari data karyawan")
        self.sync_btn.clicked.connect(self._sync_members)

        header_layout.addWidget(self.title_label)
        header_layout.addSpacing(12)
        header_layout.addWidget(self.Periode_label)
        header_layout.addStretch()
        header_layout.addWidget(self.sync_btn)
        main_layout.addLayout(header_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #dde; margin: 2px 0px;")
        main_layout.addWidget(sep)

        # ── Splitter: Atas (Status) + Bawah (Riwayat) ──
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # ── Panel Atas: Status Periode Saat Ini ──────────
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        status_label = QLabel("📋 Status Periode Saat Ini")
        status_label.setStyleSheet("font-weight: bold; color: #444;")
        top_layout.addWidget(status_label)

        self.status_table = QTableWidget()
        self.status_table.setObjectName("minumStatusTable")
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["Nama Karyawan", "Status", "Tanggal Beli"])
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.status_table.setAlternatingRowColors(True)
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        top_layout.addWidget(self.status_table)

        # ── Form Catat Pembelian ──
        form_group = QGroupBox("Catat Pembelian Baru")
        form_layout = QHBoxLayout(form_group)
        form_layout.setSpacing(10)

        form_layout.addWidget(QLabel("Anggota:"))
        self.member_combo = QComboBox()
        self.member_combo.setMinimumWidth(160)
        self.member_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form_layout.addWidget(self.member_combo)

        form_layout.addSpacing(8)
        form_layout.addWidget(QLabel("Tanggal Beli:"))
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setDisplayFormat("dd MMMM yyyy")
        self.date_picker.setFixedWidth(160)
        form_layout.addWidget(self.date_picker)

        form_layout.addSpacing(8)
        self.record_btn = QPushButton("✅  Catat Pembelian")
        self.record_btn.setObjectName("recordMinumBtn")
        self.record_btn.setFixedHeight(34)
        self.record_btn.setStyleSheet(
            "QPushButton#recordMinumBtn { background-color: #27ae60; color: white; "
            "font-weight: bold; border-radius: 5px; padding: 0 16px; }"
            "QPushButton#recordMinumBtn:hover { background-color: #2ecc71; }"
        )
        self.record_btn.clicked.connect(self._record_purchase)
        form_layout.addWidget(self.record_btn)

        top_layout.addWidget(form_group)
        splitter.addWidget(top_panel)

        # ── Panel Bawah: Riwayat ──────────────────────
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        history_header = QHBoxLayout()
        history_lbl = QLabel("📜 Riwayat Periode")
        history_lbl.setStyleSheet("font-weight: bold; color: #444;")
        history_header.addWidget(history_lbl)
        history_header.addStretch()
        history_header.addWidget(QLabel("Pilih Periode:"))
        self.Periode_filter_combo = QComboBox()
        self.Periode_filter_combo.setFixedWidth(120)
        self.Periode_filter_combo.currentIndexChanged.connect(self._refresh_history_table)
        history_header.addWidget(self.Periode_filter_combo)
        bottom_layout.addLayout(history_header)

        self.history_table = QTableWidget()
        self.history_table.setObjectName("minumHistoryTable")
        self.history_table.setColumnCount(3)
        self.history_table.setHorizontalHeaderLabels(["Nama Karyawan", "Periode", "Tanggal Beli"])
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        hist_header = self.history_table.horizontalHeader()
        hist_header.setSectionResizeMode(0, QHeaderView.Stretch)
        hist_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hist_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        bottom_layout.addWidget(self.history_table)

        splitter.addWidget(bottom_panel)
        splitter.setSizes([350, 200])

        main_layout.addWidget(splitter, 1)

    # ─────────────────────────────────────────
    # UI REFRESH
    # ─────────────────────────────────────────

    def _refresh_ui(self):
        """Refresh seluruh UI dari data terkini."""
        self._refresh_member_combo()
        self._refresh_status_table()
        self._refresh_Periode_filter()
        self._refresh_history_table()
        current_Periode = self.data["Periode"]
        self.Periode_label.setText(f"Periode {current_Periode}")

    def _refresh_member_combo(self):
        """Isi ulang combo anggota dari DB."""
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        members = self._get_members()
        for m in members:
            self.member_combo.addItem(m['nama_lengkap'], userData=m['nik'])
        self.member_combo.blockSignals(False)

    def _refresh_status_table(self):
        """Update tabel status Periode saat ini."""
        members = self._get_members()
        bought_niks = self._get_current_Periode_purchases()

        # Buat map nik → tanggal beli
        current_Periode = self.data["Periode"]
        bought_map = {}
        for p in self.data["purchases"]:
            if p.get("Periode") == current_Periode:
                bought_map[p["member_nik"]] = p.get("tanggal", "-")

        self.status_table.setRowCount(0)
        for m in members:
            nik = m['nik']
            row = self.status_table.rowCount()
            self.status_table.insertRow(row)

            name_item = QTableWidgetItem(m['nama_lengkap'])
            name_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

            if nik in bought_niks:
                status_item = QTableWidgetItem("✅ Sudah Beli")
                status_item.setForeground(QColor("#27ae60"))
                tanggal_str = bought_map.get(nik, "-")
                try:
                    dt = datetime.strptime(tanggal_str, "%Y-%m-%d")
                    tanggal_display = dt.strftime("%d %b %Y")
                except Exception:
                    tanggal_display = tanggal_str
                date_item = QTableWidgetItem(tanggal_display)
            else:
                status_item = QTableWidgetItem("⏳ Belum Beli")
                status_item.setForeground(QColor("#e67e22"))
                date_item = QTableWidgetItem("-")

            status_item.setTextAlignment(Qt.AlignCenter)
            date_item.setTextAlignment(Qt.AlignCenter)

            self.status_table.setItem(row, 0, name_item)
            self.status_table.setItem(row, 1, status_item)
            self.status_table.setItem(row, 2, date_item)

    def _refresh_Periode_filter(self):
        """Isi ulang combo filter riwayat Periode."""
        self.Periode_filter_combo.blockSignals(True)
        self.Periode_filter_combo.clear()
        Periodes = self._get_all_Periodes()
        for r in Periodes:
            self.Periode_filter_combo.addItem(f"Periode {r}", userData=r)
        self.Periode_filter_combo.blockSignals(False)

    def _refresh_history_table(self):
        """Update tabel riwayat sesuai Periode yang dipilih di filter."""
        self.history_table.setRowCount(0)
        idx = self.Periode_filter_combo.currentIndex()
        if idx < 0:
            return
        selected_Periode = self.Periode_filter_combo.itemData(idx)
        purchases = self._get_Periode_purchases(selected_Periode)
        for p in purchases:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            self.history_table.setItem(row, 0, QTableWidgetItem(p.get("member_name", "-")))
            self.history_table.setItem(row, 1, QTableWidgetItem(str(p.get("Periode", "-"))))
            tanggal_str = p.get("tanggal", "-")
            try:
                dt = datetime.strptime(tanggal_str, "%Y-%m-%d")
                tanggal_display = dt.strftime("%d %b %Y")
            except Exception:
                tanggal_display = tanggal_str
            self.history_table.setItem(row, 2, QTableWidgetItem(tanggal_display))

    # ─────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────

    def _record_purchase(self):
        """Catat pembelian untuk anggota yang dipilih."""
        if self.member_combo.count() == 0:
            QMessageBox.warning(self, "Tidak Ada Anggota",
                                "Belum ada anggota terdaftar. Klik 'Sync Anggota' terlebih dahulu.")
            return

        member_nik = self.member_combo.currentData()
        member_name = self.member_combo.currentText()
        tanggal = self.date_picker.date().toString("yyyy-MM-dd")
        current_Periode = self.data["Periode"]

        # Validasi: cek apakah sudah beli di Periode ini
        bought_niks = self._get_current_Periode_purchases()
        if member_nik in bought_niks:
            QMessageBox.warning(
                self, "⚠️ Sudah Tercatat",
                f"<b>{member_name}</b> sudah tercatat membeli di <b>Periode {current_Periode}</b>.\n\n"
                f"Tunggu sampai semua anggota selesai agar Periode baru dimulai."
            )
            return

        # Konfirmasi
        reply = QMessageBox.question(
            self, "Konfirmasi Pembelian",
            f"Catat pembelian galon oleh:\n\n"
            f"  👤 Anggota : <b>{member_name}</b>\n"
            f"  📅 Tanggal : {self.date_picker.date().toString('dd MMMM yyyy')}\n"
            f"  🔢 Periode   : {current_Periode}\n\n"
            f"Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # Simpan
        self.data["purchases"].append({
            "Periode": current_Periode,
            "member_nik": member_nik,
            "member_name": member_name,
            "tanggal": tanggal
        })
        self._save_data()
        logging.info(f"[Minum] Catat: {member_name} (NIK:{member_nik}) Periode {current_Periode} tgl {tanggal}")

        # Cek apakah Periode selesai
        self._check_Periode_completion()
        self._refresh_ui()

    def _check_Periode_completion(self):
        """Cek apakah semua anggota sudah beli di Periode ini. Jika ya, advance ke Periode baru."""
        members = self._get_members()
        if not members:
            return

        bought_niks = self._get_current_Periode_purchases()
        all_niks = {m['nik'] for m in members}

        if all_niks == bought_niks:
            # Semua sudah beli!
            completed_Periode = self.data["Periode"]
            self.data["Periode"] = completed_Periode + 1
            self._save_data()

            # Pop-up notifikasi Periode selesai
            QMessageBox.information(
                self, "🎉 Periode Selesai!",
                f"<b>Periode {completed_Periode} telah selesai!</b><br><br>"
                f"Semua {len(members)} anggota sudah membeli galon. "
                f"Giliran berikutnya dimulai pada <b>Periode {self.data['Periode']}</b>.<br><br>"
                f"Semangat beli galon! 💧"
            )
            logging.info(f"[Minum] Periode {completed_Periode} selesai. Mulai Periode {self.data['Periode']}.")

    def _sync_members(self):
        """Sinkronisasi daftar anggota dari DB karyawan."""
        members = self._get_members()
        self._refresh_member_combo()
        self._refresh_status_table()
        QMessageBox.information(
            self, "Sync Berhasil",
            f"✅ Daftar anggota berhasil disinkronisasi.\n\n"
            f"Total anggota aktif: <b>{len(members)}</b> orang\n"
            f"(Area Manager dan Admin dikecualikan)"
        )
        logging.info(f"[Minum] Sync: {len(members)} anggota dimuat.")
