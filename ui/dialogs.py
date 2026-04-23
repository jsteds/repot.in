# ui/dialogs.py
import sys
import json
import logging
import os
import re
import pandas as pd  # Diperlukan untuk menyimpan preferensi
from collections import defaultdict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit, 
    QPushButton, QMessageBox, QInputDialog, QDialogButtonBox, QWidget,
    QCheckBox, QLineEdit, QGridLayout,QSizePolicy, QListWidget, QListWidgetItem, QFormLayout, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame, QStyle, QTextBrowser, QFileDialog, QDateEdit
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont, QColor
from utils.app_utils import get_base_article_name
from utils.constants import (
    REPORT_TEMPLATE_FILE, EDSPAYED_DATA_FILE, 
    ARTICLE_PREFS_FILE, COL_ARTICLE_NAME, PLACEHOLDER_FILE
)



class NewSeriesGroupDialog(QDialog):
    """
    Dialog for managing custom New Series groups and their metric visibility.
    Left pane: List of Groups.
    Right pane: Configuration for the selected group.
    """
    def __init__(self, articles: list, pre_selected_data: list = None, available_templates: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kelola Grup New Series")
        self.resize(900, 650)
        
        # Inisialisasi Data
        if not isinstance(articles, list): articles = []
        self.all_full_names = sorted(list(set(articles)))
        self.available_templates = available_templates or []
        
        # Format pre_selected_data: [{"group_name": "...", "articles": [...], "format": "Grouped", "metrics": {...}, "templates": [...]}]
        self.group_data = pre_selected_data if pre_selected_data else []
        self.current_group_idx = -1
        
        # Base name map untuk kemudahan centang (sama seperti sebelumnya)
        self.base_name_map = defaultdict(list)
        for name in self.all_full_names:
            base_name = get_base_article_name(name)
            self.base_name_map[base_name].append(name)

        self._init_ui()
        self._populate_group_list()
        self._center_on_parent()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Splitter untuk membagi layout Kiri (Grup) dan Kanan (Konfigurasi)
        splitter = QSplitter(Qt.Horizontal)
        
        # --- PANEL KIRI: DAFTAR GRUP ---
        left_widget = QWidget(); left_layout = QVBoxLayout(left_widget); left_layout.setContentsMargins(0,0,10,0)
        
        self.group_list_widget = QListWidget()
        self.group_list_widget.currentRowChanged.connect(self._on_group_selected)
        left_layout.addWidget(QLabel("<b>Daftar Grup:</b>"))
        left_layout.addWidget(self.group_list_widget)
        
        # Tombol CRUD untuk Grup
        btn_layout = QHBoxLayout()
        self.add_group_btn = QPushButton("➕ Tambah"); self.add_group_btn.clicked.connect(self._add_group)
        self.del_group_btn = QPushButton("🗑️ Hapus"); self.del_group_btn.clicked.connect(self._delete_group)
        btn_layout.addWidget(self.add_group_btn); btn_layout.addWidget(self.del_group_btn)
        left_layout.addLayout(btn_layout)
        
        # --- PANEL KANAN: KONFIGURASI GRUP TERPILIH ---
        self.right_widget = QWidget(); right_layout = QVBoxLayout(self.right_widget); right_layout.setContentsMargins(10,0,0,0)
        
        # Nama Grup
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nama Grup:"))
        self.group_name_input = QLineEdit()
        self.group_name_input.textChanged.connect(self._on_group_name_changed)
        name_layout.addWidget(self.group_name_input)
        right_layout.addLayout(name_layout)
        
        # Format Tampilan
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format Laporan:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Grouped (1 Baris Total)", "Detailed (Rincian per Item)"])
        self.format_combo.currentTextChanged.connect(self._on_setting_changed)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        right_layout.addLayout(format_layout)
        
        # Opsi Metrik
        metrics_groupbox = QWidget()
        metrics_layout = QGridLayout(metrics_groupbox)
        metrics_layout.setContentsMargins(0, 5, 0, 5)
        
        self.cb_qty_today = QCheckBox("SC Today (Qty)"); self.cb_qty_today.stateChanged.connect(self._on_setting_changed)
        self.cb_qty_mtd = QCheckBox("SC MTD (Qty)"); self.cb_qty_mtd.stateChanged.connect(self._on_setting_changed)
        self.cb_tc_today = QCheckBox("TC Today (Trx)"); self.cb_tc_today.stateChanged.connect(self._on_setting_changed)
        self.cb_tc_mtd = QCheckBox("TC MTD (Trx)"); self.cb_tc_mtd.stateChanged.connect(self._on_setting_changed)
        self.cb_sales_today = QCheckBox("Sales Today"); self.cb_sales_today.stateChanged.connect(self._on_setting_changed)
        self.cb_sales_mtd = QCheckBox("Sales MTD"); self.cb_sales_mtd.stateChanged.connect(self._on_setting_changed)
        self.cb_contrib = QCheckBox("% Kontribusi"); self.cb_contrib.stateChanged.connect(self._on_setting_changed)
        
        metrics_layout.addWidget(self.cb_qty_today, 0, 0); metrics_layout.addWidget(self.cb_qty_mtd, 0, 1)
        metrics_layout.addWidget(self.cb_tc_today, 1, 0); metrics_layout.addWidget(self.cb_tc_mtd, 1, 1)
        metrics_layout.addWidget(self.cb_sales_today, 2, 0); metrics_layout.addWidget(self.cb_sales_mtd, 2, 1)
        metrics_layout.addWidget(self.cb_contrib, 3, 0)
        
        right_layout.addWidget(QLabel("<b>Metrik yang ditampilkan:</b>"))
        right_layout.addWidget(metrics_groupbox)
        
        # Pemisah
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line)
        
        # ---- TEMPLATE ASSIGNMENT SECTION ----
        right_layout.addWidget(QLabel("<b>🗂️ Tampilkan di Template:</b>"))
        
        self.template_list_widget = QListWidget()
        self.template_list_widget.setMaximumHeight(90)
        self.template_list_widget.itemChanged.connect(self._on_template_assignment_changed)
        
        self._repopulate_template_list()
        
        self.template_info_lbl = QLabel("ℹ️ Jika tidak ada yang dipilih, grup tampil di semua template.")
        self.template_info_lbl.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        right_layout.addWidget(self.template_list_widget)
        right_layout.addWidget(self.template_info_lbl)
        
        # Pemisah
        line2 = QFrame(); line2.setFrameShape(QFrame.HLine); line2.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line2)
        
        # Pemilihan Artikel dalam Grup
        right_layout.addWidget(QLabel("<b>Pilih Artikel untuk Grup Ini:</b>"))
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Cari nama artikel...")
        self.search_box.textChanged.connect(self._repopulate_article_list)
        search_layout.addWidget(self.search_box)
        
        self.group_checkbox = QCheckBox("Gabungkan varian ukuran (Tampilan Sederhana)")
        self.group_checkbox.stateChanged.connect(self._repopulate_article_list)
        search_layout.addWidget(self.group_checkbox)
        right_layout.addLayout(search_layout)
        
        self.article_list_widget = QListWidget()
        self.article_list_widget.itemChanged.connect(self._on_article_checked)
        right_layout.addWidget(self.article_list_widget)
        
        # Info Label for Articles
        self.info_label = QLabel("Belum ada artikel dipilih")
        self.info_label.setStyleSheet("color: #0277bd; font-weight: bold; font-size: 11px;")
        right_layout.addWidget(self.info_label)
        
        # Disable Right Panel Initially
        self.right_widget.setEnabled(False)
        
        splitter.addWidget(left_widget); splitter.addWidget(self.right_widget)
        splitter.setSizes([300, 600])
        main_layout.addWidget(splitter, 1) # stretch 1
        
        # Tombol Utama
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("Simpan & Terapkan")
        self.button_box.button(QDialogButtonBox.Cancel).setText("Batal")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def _center_on_parent(self):
        if self.parent():
            parent_geo = self.parent().frameGeometry()
            dialog_geo = self.frameGeometry()
            dialog_geo.moveCenter(parent_geo.center())
            self.move(dialog_geo.topLeft())

    # --- GROUP MANAGEMENT ---
    def _populate_group_list(self):
        self.group_list_widget.blockSignals(True)
        self.group_list_widget.clear()
        for idx, group in enumerate(self.group_data):
            self.group_list_widget.addItem(group.get('group_name', f"Group {idx+1}"))
        self.group_list_widget.blockSignals(False)
        
        if self.group_data:
            self.group_list_widget.setCurrentRow(0)
        else:
            self.right_widget.setEnabled(False)

    def _add_group(self):
        new_group = {
            "group_name": f"Grup Baru {len(self.group_data) + 1}",
            "articles": [],
            "format": "Grouped",
            "metrics": {"qty_today": True, "qty_mtd": True, "tc_today": False, "tc_mtd": False, "sales_today": False, "sales_mtd": False, "contrib": False},
            "templates": []  # Kosong = tampil di semua template
        }
        self.group_data.append(new_group)
        self._populate_group_list()
        self.group_list_widget.setCurrentRow(len(self.group_data) - 1)

    def _delete_group(self):
        row = self.group_list_widget.currentRow()
        if row >= 0:
            del self.group_data[row]
            self.current_group_idx = -1
            self._populate_group_list()

    def _on_group_selected(self, row):
        if row < 0 or row >= len(self.group_data):
            self.right_widget.setEnabled(False)
            return
            
        self.current_group_idx = row
        self.right_widget.setEnabled(True)
        group = self.group_data[row]
        
        # Load Name & Format
        self.group_name_input.blockSignals(True)
        self.group_name_input.setText(group.get("group_name", ""))
        self.group_name_input.blockSignals(False)
        
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentText("Grouped (1 Baris Total)" if group.get("format") == "Grouped" else "Detailed (Rincian per Item)")
        self.format_combo.blockSignals(False)
        
        # Load Metrics
        metrics = group.get("metrics", {})
        self.cb_qty_today.blockSignals(True); self.cb_qty_today.setChecked(metrics.get("qty_today", True)); self.cb_qty_today.blockSignals(False)
        self.cb_qty_mtd.blockSignals(True); self.cb_qty_mtd.setChecked(metrics.get("qty_mtd", True)); self.cb_qty_mtd.blockSignals(False)
        self.cb_tc_today.blockSignals(True); self.cb_tc_today.setChecked(metrics.get("tc_today", False)); self.cb_tc_today.blockSignals(False)
        self.cb_tc_mtd.blockSignals(True); self.cb_tc_mtd.setChecked(metrics.get("tc_mtd", False)); self.cb_tc_mtd.blockSignals(False)
        self.cb_sales_today.blockSignals(True); self.cb_sales_today.setChecked(metrics.get("sales_today", False)); self.cb_sales_today.blockSignals(False)
        self.cb_sales_mtd.blockSignals(True); self.cb_sales_mtd.setChecked(metrics.get("sales_mtd", False)); self.cb_sales_mtd.blockSignals(False)
        self.cb_contrib.blockSignals(True); self.cb_contrib.setChecked(metrics.get("contrib", False)); self.cb_contrib.blockSignals(False)
        
        # Load Template Assignments
        assigned_templates = set(group.get("templates", []))
        self.template_list_widget.blockSignals(True)
        for i in range(self.template_list_widget.count()):
            item = self.template_list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in assigned_templates else Qt.Unchecked)
        self.template_list_widget.blockSignals(False)
        
        # Populate Articles List for this group
        self._repopulate_article_list()

    def _on_group_name_changed(self, text):
        if self.current_group_idx >= 0:
            self.group_data[self.current_group_idx]["group_name"] = text
            self.group_list_widget.item(self.current_group_idx).setText(text)

    def _on_setting_changed(self):
        if self.current_group_idx >= 0:
            grp = self.group_data[self.current_group_idx]
            grp["format"] = "Grouped" if "Grouped" in self.format_combo.currentText() else "Detailed"
            grp["metrics"] = {
                "qty_today": self.cb_qty_today.isChecked(),
                "qty_mtd": self.cb_qty_mtd.isChecked(),
                "tc_today": self.cb_tc_today.isChecked(),
                "tc_mtd": self.cb_tc_mtd.isChecked(),
                "sales_today": self.cb_sales_today.isChecked(),
                "sales_mtd": self.cb_sales_mtd.isChecked(),
                "contrib": self.cb_contrib.isChecked()
            }

    def _repopulate_template_list(self):
        """Mengisi ulang daftar template dari self.available_templates."""
        self.template_list_widget.blockSignals(True)
        self.template_list_widget.clear()
        for tpl_name in self.available_templates:
            item = QListWidgetItem(tpl_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.template_list_widget.addItem(item)
        self.template_list_widget.blockSignals(False)

    def _on_template_assignment_changed(self, item):
        """Simpan daftar template yang dicentang ke grup aktif."""
        if self.current_group_idx >= 0:
            selected_templates = []
            for i in range(self.template_list_widget.count()):
                ti = self.template_list_widget.item(i)
                if ti.checkState() == Qt.Checked:
                    selected_templates.append(ti.text())
            self.group_data[self.current_group_idx]["templates"] = selected_templates

    # --- ARTICLE LIST MANAGEMENT ---
    def _repopulate_article_list(self):
        if self.current_group_idx < 0: return
        
        self.article_list_widget.blockSignals(True)
        self.article_list_widget.clear()
        
        group_articles = set(self.group_data[self.current_group_idx].get("articles", []))
        search_term = self.search_box.text().lower()
        is_grouped = self.group_checkbox.isChecked()
        
        # Filter and render
        source_map = self.base_name_map if is_grouped else {name: [name] for name in self.all_full_names}
        items_to_display = {d: f for d, f in source_map.items() if search_term in d.lower()}
        items_to_display = dict(sorted(items_to_display.items()))

        for display_name, full_names in items_to_display.items():
            selected_count = sum(1 for fn in full_names if fn in group_articles)
            total_count = len(full_names)
            
            item_text = f"{display_name}  [{total_count} varian]" if is_grouped and total_count > 1 else display_name
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, full_names)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            
            if selected_count == total_count: item.setCheckState(Qt.Checked)
            elif selected_count > 0: item.setCheckState(Qt.PartiallyChecked)
            else: item.setCheckState(Qt.Unchecked)
                
            self.article_list_widget.addItem(item)
            
        self._update_info_label(len(group_articles))
        self.article_list_widget.blockSignals(False)

    def _on_article_checked(self, item):
        if self.current_group_idx < 0: return
        
        full_names = item.data(Qt.UserRole)
        is_checked = item.checkState() == Qt.Checked
        
        # Use set for easy addition/removal, then convert back to list
        current_selection = set(self.group_data[self.current_group_idx].get("articles", []))
        
        for name in full_names:
            if is_checked: current_selection.add(name)
            else: current_selection.discard(name)
            
        self.group_data[self.current_group_idx]["articles"] = list(current_selection)
        self._update_info_label(len(current_selection))

    def _update_info_label(self, count):
        self.info_label.setText(f"Tertaut ({count}) artikel ke grup ini." if count > 0 else "Belum ada artikel dipilih.")

    # --- FINALIZATION ---
    def get_selection_data(self) -> list:
        return self.group_data
# ==========================================
# 2. TEMPLATE EDITOR DIALOG (DIPERBAIKI)
# ==========================================
# Helper Dialog untuk Input Placeholder
class PlaceholderInputDialog(QDialog):
    def __init__(self, parent=None, code="", desc="", current_group=None, available_groups=None):
        super().__init__(parent)
        self.setWindowTitle("Placeholder Editor")
        self.setFixedSize(450, 220) # Sedikit lebih tinggi
        layout = QFormLayout(self)
        
        # Input Kategori (Editable ComboBox)
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True) # <-- Fitur Kunci: Bisa ketik manual
        self.group_combo.setInsertPolicy(QComboBox.NoInsert) # Jangan otomatis tambah ke list combo dulu
        self.group_combo.setPlaceholderText("Pilih atau ketik Kategori Baru...")
        
        if available_groups:
            # Bersihkan nama grup dari "--- " dan " ---" untuk tampilan
            clean_groups = [g.replace("---", "").strip() for g in available_groups]
            self.group_combo.addItems(clean_groups)
            
            # Set selection awal
            if current_group:
                clean_current = current_group.replace("---", "").strip()
                self.group_combo.setCurrentText(clean_current)
        
        self.code_edit = QLineEdit(code)
        self.code_edit.setPlaceholderText("{kode_anda}")
        
        self.desc_edit = QLineEdit(desc)
        self.desc_edit.setPlaceholderText("Deskripsi singkat...")
        
        layout.addRow("Kategori:", self.group_combo)
        layout.addRow("Kode:", self.code_edit)
        layout.addRow("Deskripsi:", self.desc_edit)
        
        # Info label
        info_label = QLabel("<i>*Ketik nama kategori baru di atas untuk membuat grup baru.</i>")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addRow("", info_label)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
    def get_data(self):
        # Ambil teks kategori, bersihkan, dan format standar
        raw_group = self.group_combo.currentText().strip()
        # Hapus dash jika user mengetiknya manual agar tidak double
        clean_group_name = raw_group.replace("-", "").strip().upper()
        
        if not clean_group_name:
            clean_group_name = "LAIN-LAIN" # Fallback jika kosong
            
        formatted_group = f"--- {clean_group_name} ---"
        
        return self.code_edit.text().strip(), self.desc_edit.text().strip(), formatted_group

class TemplateEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kelola Template Laporan")
        self.resize(950, 600) 
        self.templates = {}
        self.placeholders_data = [] 
        self.current_template_name = None
        
        # --- Styling Global ---
        # Styling global telah dihapus agar mengikuti tema aplikasi (Light/Dark mode)
        
        self._load_placeholders() 
        self._init_ui()
        self._load_templates()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- Header Controls ---
        control_frame = QFrame()
        control_frame.setStyleSheet("border-radius: 8px; border: 1px solid gray;")
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(15, 10, 15, 10)
        
        control_layout.addWidget(QLabel("<b>Template Aktif:</b>"))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(250)
        self.template_combo.currentTextChanged.connect(self._on_template_selected)
        control_layout.addWidget(self.template_combo)
        
        self.new_btn = QPushButton("➕ Buat Baru")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setStyleSheet("""
            QPushButton { background-color: #007bff; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; min-width: 80px; }
            QPushButton:hover { background-color: #0056b3; }
        """)
        self.new_btn.clicked.connect(self._create_new_template)
        control_layout.addWidget(self.new_btn)
        
        self.delete_btn = QPushButton("🗑️ Hapus")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet("""
            QPushButton { background-color: #dc3545; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; min-width: 70px; }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.delete_btn.clicked.connect(self._delete_template)
        control_layout.addWidget(self.delete_btn)
        
        control_layout.addStretch()
        main_layout.addWidget(control_frame)
        
        # --- Splitter ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(10)
        splitter.setStyleSheet("QSplitter::handle { background-color: gray; }")
        
        # Kiri: Editor
        editor_widget = QWidget(); editor_layout = QVBoxLayout(editor_widget); editor_layout.setContentsMargins(0,0,10,0)
        editor_layout.addWidget(QLabel("<b>Format Struktur Laporan:</b>"))
        self.editor_text = QTextEdit()
        self.editor_text.setPlaceholderText("Ketik format laporan di sini...")
        self.editor_text.setFont(QFont("Consolas", 11))
        editor_layout.addWidget(self.editor_text)
        
        # Kanan: Placeholder Manager
        placeholder_widget = QWidget(); placeholder_layout = QVBoxLayout(placeholder_widget); placeholder_layout.setContentsMargins(10,0,0,0)
        placeholder_layout.addWidget(QLabel("<b>Daftar Placeholder Tersedia:</b>"))
        
        # --- Search & Filter Bar ---
        filter_bar = QHBoxLayout()
        self.ph_search = QLineEdit()
        self.ph_search.setPlaceholderText("🔍 Cari placeholder...")
        self.ph_search.setClearButtonEnabled(True)
        self.ph_search.textChanged.connect(self._filter_placeholders)
        filter_bar.addWidget(self.ph_search)
        
        self.ph_category_combo = QComboBox()
        self.ph_category_combo.setMinimumWidth(140)
        self.ph_category_combo.addItem("📋 Semua Kategori")
        # Populate category combo from group headers in placeholders
        for code, _ in self._get_default_placeholders():
            if code.startswith("---"):
                cat_label = code.replace("---", "").strip()
                self.ph_category_combo.addItem(cat_label)
        self.ph_category_combo.currentIndexChanged.connect(self._filter_placeholders)
        filter_bar.addWidget(self.ph_category_combo)
        placeholder_layout.addLayout(filter_bar)
        # --- End Search & Filter ---
        
        self.placeholder_table = QTableWidget()
        self.placeholder_table.setColumnCount(2)
        self.placeholder_table.setHorizontalHeaderLabels(["Kode", "Deskripsi"])
        self.placeholder_table.verticalHeader().setVisible(False)
        header = self.placeholder_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents); header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.placeholder_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.placeholder_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.placeholder_table.itemDoubleClicked.connect(self._insert_placeholder)
        
        self._populate_placeholder_table() 
        
        placeholder_layout.addWidget(self.placeholder_table)
        
        # Tombol CRUD Placeholder
        ph_btn_layout = QHBoxLayout()
        
        self.ph_add_btn = QPushButton("Tambah")
        self.ph_add_btn.clicked.connect(self._add_placeholder)
        
        self.ph_edit_btn = QPushButton("Edit")
        self.ph_edit_btn.clicked.connect(self._edit_placeholder)
        
        self.ph_del_btn = QPushButton("Hapus")
        self.ph_del_btn.clicked.connect(self._delete_placeholder)
        
        self.ph_reset_btn = QPushButton("Reset Default")
        self.ph_reset_btn.clicked.connect(self._reset_placeholders)
        
        mini_btn_style = """
            QPushButton { border-radius: 3px; padding: 4px 10px; font-size: 11px; font-weight: bold; }
        """
        for btn in [self.ph_add_btn, self.ph_edit_btn, self.ph_del_btn, self.ph_reset_btn]:
            btn.setStyleSheet(mini_btn_style)
            ph_btn_layout.addWidget(btn)
            
        placeholder_layout.addLayout(ph_btn_layout)
        
        hint_label = QLabel("💡 <i>Tips: Klik ganda baris di tabel untuk menyisipkan kode ke editor.</i>")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        placeholder_layout.addWidget(hint_label)
        
        splitter.addWidget(editor_widget); splitter.addWidget(placeholder_widget)
        splitter.setSizes([600, 350]) 
        main_layout.addWidget(splitter, 1) 

        # --- Footer ---
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        save_btn = btn_box.button(QDialogButtonBox.Save)
        save_btn.setText("Simpan")
        save_btn.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; border: none; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #218838; }
        """)
        close_btn = btn_box.button(QDialogButtonBox.Close)
        close_btn.setText("Tutup")
        close_btn.setStyleSheet("""
            QPushButton { background-color: #6c757d; color: white; border: none; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6268; }
        """)
        
        btn_box.accepted.connect(self._save_current_template)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    # --- LOGIC MANAJEMEN PLACEHOLDER ---
    def _get_default_placeholders(self):
        return [
            ("--- INFO UTAMA ---", ""), 
            ("{site_code}", "Kode Toko"), ("{store_name}", "Nama Toko"), ("{day_date_full}", "Tanggal Laporan"), ("{day_date_month}", "Nama Bulan Berjalan"),
            ("--- SALES HARIAN ---", ""), 
            ("{day_net}", "Net Sales Hari Ini"), ("{day_gross}", "Gross Sales Hari Ini"), ("{day_tc}", "Total Check Hari Ini"), ("{day_ac}", "Average Check Hari Ini"),
            ("{day_ouast_sales}", "Sales OUAST/Makanan Hari ini"), ("{day_ouast_pct}", "% Sales OUAST Hari ini"),
            ("--- SALES MTD ---", ""), 
            ("{mtd_nett_sales}", "Net Sales MTD"), ("{mtd_gross}", "Gross Sales MTD"), ("{mtd_tc}", "Total Check MTD"), ("{mtd_ac}", "Average Check MTD"),
            ("{mtd_ouast_sales}", "Sales OUAST/Makanan MTD"), ("{mtd_ouast_pct}", "% Sales OUAST MTD"),
            ("--- TARGET & ACHIEVEMENT ---", ""), 
            ("{target_bulanan}", "Target Bulan Ini"), ("{target_weekday}", "Target Harian (Weekday)"), ("{target_weekend}", "Target Harian (Weekend)"),
            ("{target_harian}", "Target Proporsi Hari Ini"), ("{target_mtd}", "Target Proporsi MTD"),
            ("{target_tc}", "Target TC Hari Ini"), ("{target_sc}", "Target SC Hari Ini"),
            ("{target_large}", "Target Large Hari Ini"), ("{target_topping}", "Target Topping Hari Ini"),
            ("{target_spunbond}", "Target Spunbond Hari Ini"), ("{target_ouast}", "Target OUAST Hari Ini"),
            ("{delta_today}", "Selisih Sales Hari Ini vs Target"), ("{delta_mtd}", "Selisih Sales MTD vs Target"),
            ("{ach}", "% Achievement MTD"), ("{std_ach}", "% Target Standard (Time Elapsed)"), ("{ach_diff}", "Selisih % Achievement"),
            ("--- KOMPARASI ---", ""), 
            ("{lw_nett}", "Sales Last Week (LW)"), ("{growth_lw_pct}", "% Growth vs LW"), 
            ("{lm_nett}", "Sales Last Month (LM)"), ("{growth_lm_pct}", "% Growth vs LM (Harian)"),
            ("{lm_nett_mtd}", "Sales Last Month MTD"), ("{growth_lm_mtd_pct}", "% Growth vs LM (MTD)"),
            ("{ly_nett}", "Sales Last Year (LY)"), ("{ssg}", "% SSG vs LY (Harian)"),
            ("{ly_nett_mtd}", "Sales Last Year MTD"), ("{ssg_mtd}", "% SSG vs LY (MTD)"),
            ("--- SALES PER CHANNEL (HARIAN) ---", ""),
            ("{day_sales_instore}", "Sales Instore"), ("{day_tc_instore}", "TC Instore"), ("{day_ac_instore}", "AC Instore"), ("{day_sales_instore_pct}", "% Sales Instore"),
            ("{day_sales_ojol}", "Sales Ojol Total"), ("{day_tc_ojol}", "TC Ojol Total"), ("{day_ac_ojol}", "AC Ojol Total"), ("{day_sales_ojol_pct}", "% Sales Ojol"),
            ("{day_fnb_order_sales}", "Sales F&B/App"), ("{day_tc_fnb_order}", "TC F&B/App"), ("{day_ac_fnb_order}", "AC F&B/App"), ("{day_fnb_order_sales_pct}", "% Sales F&B/App"),
            ("{day_sales_gobiz}", "Sales Gobiz"), ("{day_tc_gobiz}", "TC Gobiz"), ("{day_gobiz_sales_pct}", "% Sales Gobiz"),
            ("{day_sales_grab}", "Sales GrabFood"), ("{day_tc_grab}", "TC GrabFood"), ("{day_grab_sales_pct}", "% Sales GrabFood"),
            ("{day_sales_shopeefood}", "Sales ShopeeFood"), ("{day_tc_shopeefood}", "TC ShopeeFood"), ("{day_shopeefood_sales_pct}", "% Sales ShopeeFood"),
            ("--- SALES PER CHANNEL (MTD) ---", ""),
            ("{mtd_sales_instore}", "Sales Instore MTD"), ("{mtd_tc_instore}", "TC Instore MTD"), ("{mtd_ac_instore}", "AC Instore MTD"), ("{mtd_sales_instore_pct}", "% Sales Instore MTD"),
            ("{mtd_sales_ojol}", "Sales Ojol Total MTD"), ("{mtd_tc_ojol}", "TC Ojol Total MTD"), ("{mtd_ac_ojol}", "AC Ojol Total MTD"), ("{mtd_sales_ojol_pct}", "% Sales Ojol MTD"),
            ("{mtd_fnb_order_sales}", "Sales F&B/App MTD"), ("{mtd_tc_fnb_order}", "TC F&B/App MTD"), ("{mtd_ac_fnb_order}", "AC F&B/App MTD"), ("{mtd_fnb_order_sales_pct}", "% Sales F&B/App MTD"),
            ("{mtd_sales_gobiz}", "Sales Gobiz MTD"), ("{mtd_tc_gobiz}", "TC Gobiz MTD"), ("{mtd_gobiz_sales_pct}", "% Sales Gobiz MTD"),
            ("{mtd_sales_grab}", "Sales GrabFood MTD"), ("{mtd_tc_grab}", "TC GrabFood MTD"), ("{mtd_grab_sales_pct}", "% Sales GrabFood MTD"),
            ("{mtd_sales_shopeefood}", "Sales ShopeeFood MTD"), ("{mtd_tc_shopeefood}", "TC ShopeeFood MTD"), ("{mtd_shopeefood_sales_pct}", "% Sales ShopeeFood MTD"),
            ("--- QUANTITY CENGKRAMA (HARIAN) ---", ""),
            ("{day_qty_large}", "Qty Cup Large"), ("{day_pct_large}", "% Cup Large vs Total Cup"),
            ("{day_qty_regular}", "Qty Cup Regular"), ("{day_pct_regular}", "% Cup Regular vs Total Cup"),
            ("{day_qty_small}", "Qty Cup Small"), ("{day_pct_small}", "% Cup Small vs Total Cup"),
            ("{day_qty_popcan}", "Qty Popcan"), ("{day_pct_popcan}", "% Popcan vs Total Cup"),
            ("{day_combined_large_popcan}", "Gabungan Qty Large + Popcan"), ("{day_combined_regular_small}", "Gabungan Qty Regular + Small"),
            ("{day_total_sc}", "Total Sold Cup (Semua Ukuran)"),
            ("{day_qty_topping}", "Qty Topping"), ("{day_pct_topping}", "% Topping vs Total Cup"),
            ("{day_qty_foods}", "Qty Foods"), ("{day_pct_foods}", "% Foods vs Total Cup"),
            ("{day_qty_snack}", "Qty Snack"), ("{day_pct_snack}", "% Snack vs TC"),
            ("{day_qty_gb}", "Qty Goodie Bag"), ("{day_pct_gb}", "% Goodie Bag vs Total Cup"),
            ("{day_qty_merch}", "Qty Merchandise"), 
            ("--- QUANTITY CENGKRAMA (MTD) ---", ""),
            ("{mtd_qty_large}", "Qty Cup Large MTD"), ("{mtd_pct_large}", "% Cup Large vs Total Cup MTD"),
            ("{mtd_qty_regular}", "Qty Cup Regular MTD"), ("{mtd_pct_regular}", "% Cup Regular vs Total Cup MTD"),
            ("{mtd_qty_small}", "Qty Cup Small MTD"), ("{mtd_pct_small}", "% Cup Small vs Total Cup MTD"),
            ("{mtd_qty_popcan}", "Qty Popcan MTD"), ("{mtd_pct_popcan}", "% Popcan vs Total Cup MTD"),
            ("{mtd_combined_large_popcan}", "Gabungan Qty Large + Popcan MTD"), ("{mtd_combined_regular_small}", "Gabungan Qty Regular + Small MTD"),
            ("{mtd_total_sc}", "Total Sold Cup MTD"),
            ("{mtd_qty_topping}", "Qty Topping MTD"), ("{mtd_pct_topping}", "% Topping vs Total Cup MTD"),
            ("{mtd_qty_foods}", "Qty Foods MTD"), ("{mtd_pct_foods}", "% Foods vs Total Cup MTD"),
            ("{mtd_qty_snack}", "Qty Snack MTD"), ("{mtd_pct_snack}", "% Snack vs TC MTD"),
            ("{mtd_qty_gb}", "Qty Goodie Bag MTD"), ("{mtd_pct_gb}", "% Goodie Bag vs Total Cup MTD"),
            ("{mtd_qty_merch}", "Qty Merchandise MTD"), 
            ("{day_instore_sold_cup}", "Instore Qty Semua Cup"), ("{mtd_instore_sold_cup}", "Instore Qty Semua Cup MTD"),
            ("{day_instore_large}", "Instore Qty Cup Large"), ("{mtd_instore_large}", "Instore Qty Cup Large MTD"),
            ("{day_instore_pct_large}", "Instore % Cup Large"), ("{mtd_instore_pct_large}", "Instore % Cup Large MTD"),
            ("{day_instore_reguler}", "Instore Qty Cup Reguler"), ("{mtd_instore_reguler}", "Instore Qty Cup Reguler MTD"),
            ("{day_instore_pct_reguler}", "Instore % Cup Reguler"), ("{mtd_instore_pct_reguler}", "Instore % Cup Reguler MTD"),
            ("{day_instore_topping}", "Instore Qty Topping"), ("{mtd_instore_topping}", "Instore Qty Topping MTD"),
            ("{day_instore_pct_topping}", "Instore % Topping"), ("{mtd_instore_pct_topping}", "Instore % Topping MTD"),
            
            ("--- OUAST HARIAN ---", ""),
            ("{day_ouast_instore_nett}", "Sales OUAST Instore"), ("{day_ouast_instore_pct}", "% Sales OUAST Instore"),
            ("--- OUAST MTD ---", ""),
            ("{mtd_ouast_instore_nett}", "Sales OUAST Instore MTD"), ("{mtd_ouast_instore_pct}", "% Sales OUAST Instore MTD"),
            
            ("--- KOMPARASI DETAIL (LAST WEEK) ---", ""),
            ("{lw_ac}", "AC Last Week"),("{lw_tc}", "TC Last Week"),
            ("{lw_instore_nett}", "LW Sales Instore"), ("{lw_instore_ac}", "LW AC Instore"), ("{lw_instore_tc}", "LW TC Instore"),
            ("{lw_ojol_nett}", "LW Sales Ojol"), ("{lw_ojol_ac}", "LW AC Ojol"), ("{lw_ojol_tc}", "LW TC Ojol"),
            ("{lw_ouast_nett}", "LW OUAST Total"), ("{lw_ouast_instore_nett}", "LW OUAST Instore"),
            ("{lw_pct_growth_nett}", "% Growth Net vs LW"), ("{lw_pct_growth_instore_nett}", "% Growth Instore vs LW"),
            ("{lw_pct_growth_ojol_nett}", "% Growth Ojol vs LW"), ("{lw_pct_growth_ouast_nett}", "% Growth OUAST vs LW"),
            ("{lw_pct_growth_ouast_instore_nett}", "% Growth OUAST Instore vs LW"),
            
            ("--- KOMPARASI DETAIL (LAST MONTH) ---", ""),
            ("{lm_ac}", "AC Last Month"),("{lm_tc}", "TC Last Month"),
            ("{lm_instore_nett}", "LM Sales Instore"), ("{lm_instore_ac}", "LM AC Instore"), ("{lm_instore_tc}", "LM TC Instore"),
            ("{lm_ojol_nett}", "LM Sales Ojol"), ("{lm_ojol_ac}", "LM AC Ojol"), ("{lm_ojol_tc}", "LM TC Ojol"),
            ("{lm_ouast_nett}", "LM OUAST Total"), ("{lm_ouast_instore_nett}", "LM OUAST Instore"),
            ("{lm_pct_growth_nett}", "% Growth Net vs LM"), ("{lm_pct_growth_instore_nett}", "% Growth Instore vs LM"),
            ("{lm_pct_growth_ojol_nett}", "% Growth Ojol vs LM"), ("{lm_pct_growth_ouast_nett}", "% Growth OUAST vs LM"),
            ("{lm_pct_growth_ouast_instore_nett}", "% Growth OUAST Instore vs LM"),
            
            ("--- KOMPARASI DETAIL (LAST YEAR) ---", ""),
            ("{ly_ac}", "AC Last Year"),("{ly_tc}", "TC Last Year"),
            ("{ly_instore_nett}", "LY Sales Instore"), ("{ly_instore_ac}", "LY AC Instore"), ("{ly_instore_tc}", "LY TC Instore"),
            ("{ly_ojol_nett}", "LY Sales Ojol"), ("{ly_ojol_ac}", "LY AC Ojol"), ("{ly_ojol_tc}", "LY TC Ojol"),
            ("{ly_ouast_nett}", "LY OUAST Total"), ("{ly_ouast_instore_nett}", "LY OUAST Instore"),
            ("{ly_pct_growth_nett}", "% Growth Net vs LY"), ("{ly_pct_growth_instore_nett}", "% Growth Instore vs LY"),
            ("{ly_pct_growth_ojol_nett}", "% Growth Ojol vs LY"), ("{ly_pct_growth_ouast_nett}", "% Growth OUAST vs LY"),
            ("{ly_pct_growth_ouast_instore_nett}", "% Growth OUAST Instore vs LY"),

            ("--- PERSENTASE TC & CHANNEL ---", ""),
            ("{day_tc_instore_pct}", "% TC Instore Harian"), ("{mtd_tc_instore_pct}", "% TC Instore MTD"),
            ("{day_tc_ojol_pct}", "% TC Ojol Harian"), ("{mtd_tc_ojol_pct}", "% TC Ojol MTD"),
            ("{day_tc_fnb_order_pct}", "% TC F&B/App Harian"), ("{mtd_tc_fnb_order_pct}", "% TC F&B/App MTD"),

            ("--- OTOMATIS GENERATE ---", ""), 
            ("{auto_analysis_text}", "Teks Analisa Otomatis (AI)"),
            ("{promo_block}", "List Promo"), 
            ("{new_series_block}", "List Artikel New Series")
        ]

    def _load_placeholders(self):
        defaults = self._get_default_placeholders()
        if os.path.exists(PLACEHOLDER_FILE):
            try:
                with open(PLACEHOLDER_FILE, 'r') as f:
                    saved = json.load(f)
                # Merge: add any default codes that are not in saved file
                saved_codes = {item[0] for item in saved if isinstance(item, (list, tuple)) and len(item) == 2}
                for item in defaults:
                    if item[0] not in saved_codes:
                        saved.append(item)
                self.placeholders_data = saved
            except Exception as e:
                logging.error(f"Gagal load placeholder: {e}")
                self.placeholders_data = defaults
        else:
            self.placeholders_data = defaults
            self._save_placeholders()

    def _save_placeholders(self):
        try:
            os.makedirs(os.path.dirname(PLACEHOLDER_FILE), exist_ok=True)
            with open(PLACEHOLDER_FILE, 'w') as f: json.dump(self.placeholders_data, f, indent=4)
        except Exception as e: logging.error(f"Gagal simpan placeholder: {e}")

    def _populate_placeholder_table(self, data=None):
        items = data if data is not None else self.placeholders_data
        self.placeholder_table.setRowCount(len(items))
        for i, (code, desc) in enumerate(items):
            code_item = QTableWidgetItem(code); desc_item = QTableWidgetItem(desc)
            if code.startswith("---"):
                f = QFont(); f.setBold(True)
                code_item.setFont(f); code_item.setTextAlignment(Qt.AlignCenter)
                desc_item.setFlags(Qt.NoItemFlags)
                self.placeholder_table.setSpan(i, 0, 1, 2)
            else: 
                code_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.placeholder_table.setItem(i, 0, code_item); self.placeholder_table.setItem(i, 1, desc_item)

    def _filter_placeholders(self):
        """Filter placeholder table by search text and/or selected category."""
        search_text = self.ph_search.text().strip().lower() if hasattr(self, 'ph_search') else ''
        cat_index = self.ph_category_combo.currentIndex() if hasattr(self, 'ph_category_combo') else 0
        cat_text = self.ph_category_combo.currentText().strip() if cat_index > 0 else ''
        
        # Build filtered list
        result = []
        current_group = None
        group_header_added = False
        
        for code, desc in self.placeholders_data:
            if code.startswith('---'):
                current_group = code.replace('---', '').strip()
                group_header_added = False  # reset for each new group
                continue  # will add header lazily when first item in group matches
            
            # Category filter
            if cat_text and current_group != cat_text:
                continue
            
            # Text search
            if search_text:
                if search_text not in code.lower() and search_text not in desc.lower():
                    continue
            
            # Add group header lazily before first matching item
            if not group_header_added and current_group:
                result.append((f"--- {current_group} ---", ''))
                group_header_added = True
            result.append((code, desc))
        
        # If no filter active, show all
        if not search_text and not cat_text:
            self._populate_placeholder_table(self.placeholders_data)
        else:
            self._populate_placeholder_table(result)

    def _get_placeholder_groups(self):
        return [item[0] for item in self.placeholders_data if item[0].startswith("---")]

    def _find_group_index(self, group_name):
        for i, (code, _) in enumerate(self.placeholders_data):
            if code == group_name: return i
        return -1

    def _add_placeholder(self):
        groups = self._get_placeholder_groups()
        d = PlaceholderInputDialog(self, available_groups=groups)
        if d.exec_() == QDialog.Accepted:
            code, desc, group = d.get_data()
            if code and desc:
                if not (code.startswith("{") and code.endswith("}")) and not code.startswith("---"):
                    code = "{" + code + "}"
                
                # Cek apakah grup sudah ada
                group_idx = self._find_group_index(group)
                
                if group_idx == -1:
                    # GRUP BARU: Tambahkan Header Grup dulu, baru Item
                    self.placeholders_data.append((group, "")) # Header
                    self.placeholders_data.append((code, desc)) # Item
                else:
                    # GRUP LAMA: Sisipkan di akhir grup tersebut
                    insert_pos = group_idx + 1
                    while insert_pos < len(self.placeholders_data):
                        if self.placeholders_data[insert_pos][0].startswith("---"): break
                        insert_pos += 1
                    self.placeholders_data.insert(insert_pos, (code, desc))
                
                self._save_placeholders()
                self._populate_placeholder_table()

    def _edit_placeholder(self):
        row = self.placeholder_table.currentRow()
        if row < 0: return
        old_code, old_desc = self.placeholders_data[row]
        if old_code.startswith("---"): QMessageBox.warning(self, "Edit", "Tidak bisa mengedit header grup."); return

        current_group = None
        for i in range(row, -1, -1):
            if self.placeholders_data[i][0].startswith("---"):
                current_group = self.placeholders_data[i][0]
                break
        
        groups = self._get_placeholder_groups()
        d = PlaceholderInputDialog(self, old_code, old_desc, current_group, groups)
        
        if d.exec_() == QDialog.Accepted:
            new_code, new_desc, new_group = d.get_data()
            if new_code and new_desc:
                if not (new_code.startswith("{") and new_code.endswith("}")): new_code = "{" + new_code + "}"
                
                if new_group != current_group:
                    del self.placeholders_data[row] # Hapus dari posisi lama
                    
                    # Cek grup baru
                    group_idx = self._find_group_index(new_group)
                    if group_idx == -1:
                        # Grup Baru: Tambah di akhir
                        self.placeholders_data.append((new_group, ""))
                        self.placeholders_data.append((new_code, new_desc))
                    else:
                        # Grup Lama: Sisipkan
                        insert_pos = group_idx + 1
                        while insert_pos < len(self.placeholders_data):
                            if self.placeholders_data[insert_pos][0].startswith("---"): break
                            insert_pos += 1
                        self.placeholders_data.insert(insert_pos, (new_code, new_desc))
                else:
                    self.placeholders_data[row] = (new_code, new_desc) # Update di tempat
                
                self._save_placeholders()
                self._populate_placeholder_table()

    def _delete_placeholder(self):
        row = self.placeholder_table.currentRow()
        if row < 0: return
        code = self.placeholders_data[row][0]
        if code.startswith("---"): QMessageBox.warning(self, "Hapus", "Tidak bisa menghapus header grup."); return
        if QMessageBox.question(self, "Hapus", f"Hapus placeholder '{code}'?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            del self.placeholders_data[row]
            self._save_placeholders(); self._populate_placeholder_table()

    def _reset_placeholders(self):
        if QMessageBox.question(self, "Reset", "Kembalikan ke daftar default?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            self.placeholders_data = self._get_default_placeholders()
            self._save_placeholders(); self._populate_placeholder_table()

    # --- LOGIC EDITOR ---
    def _insert_placeholder(self, item):
        row = item.row(); code = self.placeholder_table.item(row, 0).text()
        if not code.startswith("---"): self.editor_text.insertPlainText(code); self.editor_text.setFocus()

    def _load_templates(self):
        try:
            if os.path.exists(REPORT_TEMPLATE_FILE):
                with open(REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as f: self.templates = json.load(f)
            else: self.templates = self._get_default_templates(); self._save_to_file()
            self.template_combo.blockSignals(True); self.template_combo.clear(); self.template_combo.addItems(list(self.templates.keys())); self.template_combo.blockSignals(False)
            if self.templates: self.template_combo.setCurrentIndex(0); self._on_template_selected(self.template_combo.currentText())
        except: pass

    def _get_default_templates(self):
        return {
            "Default Template": {
                "structure": [
                    "REPORT SALES",
                    "{store_name}",
                    "",
                    "Tanggal\t\t: {day_date_full}",
                    "",
                    "ALL CHANEL CHATIME",
                    "Target\t\t: {target_bulanan}",
                    "Nett\t\t: {day_net} | {mtd_nett_sales}",
                    "SR Chatime\t\t: {ach}",
                    "SA\t\t: {std_ach}",
                    "+/- Chatime\t\t: {ach_diff}",
                    "TC\t\t: {day_tc} | {mtd_tc}",
                    "AC \t\t: {day_ac} | {mtd_ac}",
                    "SOLD CUP\t\t: {day_total_sc} | {mtd_total_sc}",
                    "Large\t\t: {day_qty_large} | {mtd_qty_large}",
                    "%\t\t: {day_pct_large} | {mtd_pct_large}",
                    "Reguler\t\t: {day_qty_regular} | {mtd_qty_regular}",
                    "%\t\t: {day_pct_regular} | {mtd_pct_regular}",
                    "TOPPING\t\t: {day_qty_topping} | {mtd_qty_topping}",
                    "%\t\t: {day_pct_topping} | {mtd_pct_topping}",
                    "",
                    "INSTORE CHANEL CHATIME",
                    "Nett\t\t: {day_sales_instore} | {mtd_sales_instore}",
                    "%\t\t: {day_sales_instore_pct} | {mtd_sales_instore_pct}",
                    "TC\t\t: {day_tc_instore} | {mtd_tc_instore}",
                    "AC \t\t: {day_ac_instore} | {mtd_ac_instore}",
                    "SOLD CUP\t\t: {day_instore_sold_cup} | {mtd_instore_sold_cup}",
                    "Large\t\t: {day_instore_large} | {mtd_instore_large}",
                    "%\t\t: {day_instore_pct_large} | {mtd_instore_pct_large}",
                    "Reguler\t\t: {day_instore_reguler} | {mtd_instore_reguler}",
                    "%\t\t: {day_instore_pct_reguler} | {mtd_instore_pct_reguler}",
                    "TOPPING\t\t: {day_instore_topping} | {mtd_instore_topping}",
                    "%\t\t: {day_instore_pct_topping} | {mtd_instore_pct_topping}",
                    "",
                    "OJOL CHANEL CHATIME",
                    "Total Ojol Chatime",
                    "Nett\t\t: {day_sales_ojol} | {mtd_sales_ojol}",
                    "%\t\t: {day_sales_ojol_pct} | {mtd_sales_ojol_pct}",
                    "TC\t\t: {day_tc_ojol} | {mtd_tc_ojol}",
                    "AC \t\t: {day_ac_ojol} | {mtd_ac_ojol}",
                    "",
                    "APPS CHANEL",
                    "Nett\t\t: {day_fnb_order_sales} | {mtd_fnb_order_sales}",
                    "%\t\t: {day_fnb_order_sales_pct} | {mtd_fnb_order_sales_pct}",
                    "TC\t\t: {day_tc_fnb_order} | {mtd_tc_fnb_order}",
                    "AC \t\t: {day_ac_fnb_order} | {mtd_ac_fnb_order}",
                    "",
                    "OUAST",
                    "ALL Nett\t\t: {day_ouast_sales} | {mtd_ouast_sales}",
                    "%\t\t: {day_ouast_pct} | {mtd_ouast_pct}",
                    "INSTORE Nett\t\t: {day_ouast_instore_nett} | {mtd_ouast_instore_nett}",
                    "%\t\t: {day_ouast_instore_pct} | {mtd_ouast_instore_pct}",
                    "",
                    "COMPARATION",
                    "LAST WEEK",
                    "LW NETT ALL : {lw_nett} / {lw_pct_growth_nett}",
                    "LW NETT INSTORE : {lw_instore_nett} / {lw_pct_growth_instore_nett}",
                    "LW NETT OJOL : {lw_ojol_nett} / {lw_pct_growth_ojol_nett}",
                    "LW OUAST ALL : {lw_ouast_nett} / {lw_pct_growth_ouast_nett}",
                    "LW OUAST INSTORE : {lw_ouast_instore_nett} / {lw_pct_growth_ouast_instore_nett}",
                    "",
                    "LAST MONTH",
                    "LM NETT ALL : {lm_nett} / {lm_pct_growth_nett}",
                    "LM NETT INSTORE : {lm_instore_nett} / {lm_pct_growth_instore_nett}",
                    "LM NETT OJOL : {lm_ojol_nett} / {lm_pct_growth_ojol_nett}",
                    "LM OUAST ALL : {lm_ouast_nett} / {lm_pct_growth_ouast_nett}",
                    "LM OUAST INSTORE : {lm_ouast_instore_nett} / {lm_pct_growth_ouast_instore_nett}",
                    "",
                    "LAST YEAR",
                    "LY NETT ALL : {ly_nett} / {ly_pct_growth_nett}",
                    "LY NETT INSTORE : {ly_instore_nett} / {ly_pct_growth_instore_nett}",
                    "LY NETT OJOL : {ly_ojol_nett} / {ly_pct_growth_ojol_nett}",
                    "LY OUAST ALL : {ly_ouast_nett} / {ly_pct_growth_ouast_nett}",
                    "LY OUAST INSTORE : {ly_ouast_instore_nett} / {ly_pct_growth_ouast_instore_nett}",
                    "",
                    "[PROMO INFO]",
                    "{promo_block}",
                    "",
                    "[NEW SERIES]",
                    "{new_series_block}"
                ]
            }
        }

    def _on_template_selected(self, name):
        if not name: return
        self.current_template_name = name; data = self.templates.get(name, {}); self.editor_text.setPlainText("\n".join(data.get('structure', [])))

    def _create_new_template(self):
        name, ok = QInputDialog.getText(self, "Template Baru", "Masukkan nama template:")
        if ok and name:
            if name not in self.templates:
                self.templates[name] = {"structure": []}; self.template_combo.addItem(name); self.template_combo.setCurrentText(name); self.editor_text.clear(); self.editor_text.setFocus()
            else: QMessageBox.warning(self, "Gagal", "Nama template sudah ada.")

    def _delete_template(self):
        name = self.template_combo.currentText()
        if name and QMessageBox.question(self, "Hapus", f"Hapus '{name}'?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            del self.templates[name]; self._save_to_file(); self._load_templates()

    def _save_current_template(self):
        name = self.template_combo.currentText()
        if name:
            self.templates[name] = {"structure": self.editor_text.toPlainText().split('\n')}
            if self._save_to_file(): QMessageBox.information(self, "Sukses", "Template berhasil disimpan.")

    def _save_to_file(self):
        try:
            os.makedirs(os.path.dirname(REPORT_TEMPLATE_FILE), exist_ok=True)
            with open(REPORT_TEMPLATE_FILE, 'w', encoding='utf-8') as f: json.dump(self.templates, f, indent=4)
            return True
        except Exception as e: logging.error(f"Gagal simpan template: {e}"); return False
# ==========================================
# 3. BSCD MANUAL INPUT DIALOG
# ==========================================
class BSCDManualInputDialog(QDialog):
    def __init__(self, period_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Input Manual - {period_name}")
        layout = QFormLayout(self)
        self.net_sales_input = QLineEdit()
        self.tc_input = QLineEdit()
        self.large_cups_input = QLineEdit()
        self.topping_input = QLineEdit()
        self.ouast_input = QLineEdit()
        
        layout.addRow("Net Sales:", self.net_sales_input)
        layout.addRow("TC:", self.tc_input)
        layout.addRow("Large Cups:", self.large_cups_input)
        layout.addRow("Topping:", self.topping_input)
        layout.addRow("OUAST Sales:", self.ouast_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_data(self):
        def parse(val):
            try: return float(val) if val else 0
            except: return 0
        return {
            'net_sales': parse(self.net_sales_input.text()), 'tc': parse(self.tc_input.text()),
            'large_cups': parse(self.large_cups_input.text()), 'toping': parse(self.topping_input.text()),
            'ouast_sales': parse(self.ouast_input.text())
        }

# ==========================================
# 4. EDSPAYED DIALOGS
# ==========================================
class AddEditPeriodDialog(QDialog):
    def __init__(self, parent=None, period_data=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah/Edit Periode")
        layout = QFormLayout(self)
        self.name_input = QLineEdit()
        self.value_input = QSpinBox(); self.value_input.setRange(1, 999)
        self.unit_input = QComboBox(); self.unit_input.addItems(["Hour", "Day", "Month"])
        layout.addRow("Nama Tampilan:", self.name_input)
        layout.addRow("Nilai:", self.value_input)
        layout.addRow("Satuan:", self.unit_input)
        
        if period_data:
            self.name_input.setText(period_data.get('name', ''))
            self.value_input.setValue(period_data.get('value', 1))
            index = self.unit_input.findText(period_data.get('unit', 'Day'), Qt.MatchFixedString)
            if index >= 0: self.unit_input.setCurrentIndex(index)
            
        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn.accepted.connect(self.accept); btn.rejected.connect(self.reject)
        layout.addWidget(btn)

    def get_data(self):
        return {"name": self.name_input.text(), "value": self.value_input.value(), "unit": self.unit_input.currentText()}

class ManagePeriodsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setWindowTitle("Kelola Daftar Periode")
        self.setMinimumSize(300, 200)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        if hasattr(self.parent_widget, 'periods_config'):
            for p in self.parent_widget.periods_config:
                self.list_widget.addItem(p['name'])
        
        layout.addWidget(self.list_widget)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Tambah"); add_btn.clicked.connect(self.add_period)
        del_btn = QPushButton("Hapus"); del_btn.clicked.connect(self.del_period)
        btn_layout.addWidget(add_btn); btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)
        
    def add_period(self):
        d = AddEditPeriodDialog(self)
        if d.exec_() == QDialog.Accepted:
            new_data = d.get_data(); new_data['items'] = []
            if hasattr(self.parent_widget, 'periods_config'):
                self.parent_widget.periods_config.append(new_data)
                self.parent_widget.save_periods_to_file()
                self.list_widget.addItem(new_data['name'])
            
    def del_period(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            if hasattr(self.parent_widget, 'periods_config'):
                del self.parent_widget.periods_config[row]
                self.parent_widget.save_periods_to_file()
                self.list_widget.takeItem(row)

# ==========================================
# 5. GENERAL & CONFIG DIALOGS
# ==========================================
class AgreementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("License Agreement - Repot.in")
        self.setFixedSize(600, 500)
        self.setStyleSheet("background-color: #1E1F22;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Judul
        title = QLabel("End User License Agreement (EULA)")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #EAEAEA;")
        layout.addWidget(title)

        # 2. Area Teks EULA
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                border: 1px solid #4A4C50;
                border-radius: 4px;
                background-color: #2B2D30;
                padding: 10px;
                font-size: 9pt;
                color: #ECF0F1;
            }
        """)
        # Ganti teks ini dengan EULA asli Anda
        eula_content = """
        <h3>SYARAT DAN KETENTUAN PENGGUNAAN APLIKASI REPOT.IN</h3>
        <p><b>PENTING:</b> Harap baca syarat dan ketentuan ini dengan saksama sebelum menggunakan aplikasi ini.</p>
        
        <ol>
            <li><b>Lisensi Penggunaan:</b> Aplikasi ini diberikan lisensi kepada Anda, bukan dijual. Anda diizinkan menggunakan aplikasi ini untuk keperluan operasional toko sesuai prosedur perusahaan.</li>
            
            <li><b>Privasi & Data:</b> Aplikasi ini memproses data transaksi dan pembayaran (SBD). Pengguna bertanggung jawab penuh atas kerahasiaan data yang diunggah ke dalam aplikasi maupun ke Google Sheet.</li>
            
            <li><b>Batasan Tanggung Jawab:</b> Pengembang tidak bertanggung jawab atas kesalahan input data, kehilangan data, atau kerugian operasional yang timbul akibat penyalahgunaan aplikasi.</li>
            
            <li><b>Pembaruan:</b> Aplikasi dapat diperbarui secara berkala untuk perbaikan bug atau penambahan fitur.</li>
        </ol>
        
        <p>Dengan mengklik tombol "Setuju", Anda menyatakan telah membaca, memahami, dan menyetujui seluruh syarat di atas.</p>
        <hr>
        <p style='font-size:8pt; color:gray'>Repot.in v4.0.6 - Developed by JstEd</p>
        """
        self.text_browser.setHtml(eula_content)
        layout.addWidget(self.text_browser)

        # 3. Checkbox Persetujuan
        self.agree_checkbox = QCheckBox("Saya telah membaca dan menyetujui Syarat & Ketentuan di atas.")
        self.agree_checkbox.setStyleSheet("font-size: 10pt; color: #EAEAEA; margin-top: 5px;")
        self.agree_checkbox.stateChanged.connect(self._toggle_button)
        layout.addWidget(self.agree_checkbox)

        # 4. Tombol Aksi
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = self.button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Lanjutkan")
        self.ok_button.setEnabled(False)  # Matikan tombol OK di awal
        
        # Styling Tombol
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border-radius: 4px; 
                padding: 8px 20px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #b0bec5; color: #eceff1; }
        """)
        
        cancel_btn = self.button_box.button(QDialogButtonBox.Cancel)
        cancel_btn.setText("Keluar")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3f42; color: #EAEAEA; border: 1px solid #4A4C50; 
                border-radius: 4px; padding: 8px 20px;
            }
            QPushButton:hover { background-color: #4A4C50; }
        """)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _toggle_button(self):
        # Tombol OK hanya aktif jika checkbox dicentang
        self.ok_button.setEnabled(self.agree_checkbox.isChecked())

class ConfigDialog(QDialog):
    def __init__(self, config_manager, parent_app):
        super().__init__(parent_app)
        from ui.ui_components import ConfigTab 
        self.setWindowTitle("Konfigurasi")
        self.setMinimumWidth(800)
        self.resize(850, 600)
        layout = QVBoxLayout(self)
        self.tab = ConfigTab(config_manager, parent_app)
        layout.addWidget(self.tab)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.on_save); btns.rejected.connect(self.reject)
        layout.addWidget(btns)
    def on_save(self):
        if self.tab.save_config_action(): self.accept()

class CalculatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kalkulator")
        self.setMinimumSize(250, 350)

        # Variabel untuk menyimpan state kalkulator
        self.current_value = '0'
        self.pending_operation = ''
        self.operand_value = 0
        self.is_waiting_for_operand = True

        # Layout Utama
        main_layout = QVBoxLayout(self)

        # Layar Display
        self.display = QLineEdit('0')
        self.display.setReadOnly(True)
        self.display.setAlignment(Qt.AlignRight)
        self.display.setFont(QFont('Arial', 24))
        self.display.setStyleSheet("border: 1px solid #dcdcdc; padding: 5px;")
        main_layout.addWidget(self.display)
        
        # Grid untuk tombol-tombol
        grid_layout = QGridLayout()
        grid_layout.setSpacing(5)

        # Daftar tombol dan posisinya di grid (baris, kolom, rowspan, colspan)
        buttons = {
            'C': (0, 0, 1, 2),
            '<-': (0, 2, 1, 1),
            '/': (0, 3, 1, 1),
            '7': (1, 0, 1, 1),
            '8': (1, 1, 1, 1),
            '9': (1, 2, 1, 1),
            '*': (1, 3, 1, 1),
            '4': (2, 0, 1, 1),
            '5': (2, 1, 1, 1),
            '6': (2, 2, 1, 1),
            '-': (2, 3, 1, 1),
            '1': (3, 0, 1, 1),
            '2': (3, 1, 1, 1),
            '3': (3, 2, 1, 1),
            '+': (3, 3, 1, 1),
            '+/-': (4, 0, 1, 1),
            '0': (4, 1, 1, 1),
            '.': (4, 2, 1, 1),
            '=': (4, 3, 1, 1),
        }

        for text, pos in buttons.items():
            button = QPushButton(text)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setFont(QFont('Arial', 14))
            button.clicked.connect(self._button_clicked)
            grid_layout.addWidget(button, *pos)
        
        main_layout.addLayout(grid_layout)

    def _button_clicked(self):
        """Handler utama untuk semua klik tombol."""
        button = self.sender()
        key = button.text()

        if key.isdigit():
            self._digit_clicked(key)
        elif key == '.':
            self._decimal_clicked()
        elif key == 'C':
            self._clear_clicked()
        elif key == '<-':
            self._backspace_clicked()
        elif key == '+/-':
            self._sign_change_clicked()
        elif key == '=':
            self._equals_clicked()
        else: # Operator
            self._operator_clicked(key)

    def _digit_clicked(self, digit):
        if self.is_waiting_for_operand:
            self.display.setText(digit)
            self.is_waiting_for_operand = False
        else:
            if self.display.text() == '0':
                self.display.setText(digit)
            else:
                self.display.setText(self.display.text() + digit)
    
    def _decimal_clicked(self):
        if self.is_waiting_for_operand:
            self.display.setText('0.')
            self.is_waiting_for_operand = False
        elif '.' not in self.display.text():
            self.display.setText(self.display.text() + '.')
    
    def _operator_clicked(self, operator):
        display_value = float(self.display.text())
        
        if self.pending_operation and not self.is_waiting_for_operand:
            self._calculate()
            self.display.setText(str(self.operand_value))
        else:
            self.operand_value = display_value
            
        self.pending_operation = operator
        self.is_waiting_for_operand = True
        
    def _calculate(self):
        """Melakukan perhitungan matematika."""
        operand2 = float(self.display.text())
        
        if self.pending_operation == '+':
            self.operand_value += operand2
        elif self.pending_operation == '-':
            self.operand_value -= operand2
        elif self.pending_operation == '*':
            self.operand_value *= operand2
        elif self.pending_operation == '/':
            if operand2 == 0:
                self._clear_clicked()
                self.display.setText("Error")
                return
            self.operand_value /= operand2

    def _equals_clicked(self):
        if self.pending_operation:
            self._calculate()
            self.pending_operation = ''
            self.is_waiting_for_operand = True
            # Tampilkan hasil, hapus .0 jika hasilnya integer
            if self.operand_value == int(self.operand_value):
                self.display.setText(str(int(self.operand_value)))
            else:
                self.display.setText(str(self.operand_value))
    
    def _clear_clicked(self):
        self.display.setText('0')
        self.pending_operation = ''
        self.operand_value = 0
        self.is_waiting_for_operand = True
        
    def _backspace_clicked(self):
        if self.is_waiting_for_operand:
            return
        text = self.display.text()[:-1]
        if not text:
            text = '0'
            self.is_waiting_for_operand = True
        self.display.setText(text)

    def _sign_change_clicked(self):
        value = float(self.display.text())
        if value != 0:
            value = -value
        
        if value == int(value):
            self.display.setText(str(int(value)))
        else:
            self.display.setText(str(value))


class LogDialog(QDialog):
    def __init__(self, log_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Aplikasi")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)
        self.log_file = log_file
        self.load_log_content()
    def load_log_content(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                self.text_edit.setPlainText(f.read())
        else: self.text_edit.setPlainText("File log belum tersedia.")

class PromotionSelectionDialog(QDialog):
    """
    Dialog pemilihan & pengelompokan promosi (Splitter Layout).
    Kiri: Daftar Grup Promo.  Kanan: Konfigurasi grup (nama, metrik, pilih promo).
    Data format: [{"group_name": "...", "promos": [...], "metrics": {...}, "templates": [...]}, ...]
    """
    def __init__(self, promo_names, pre_selected_data=None, current_method='by_item', available_templates=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kelola Grup Promosi")
        self.resize(900, 700)

        # Filter nan from promo names
        self.all_promo_names = sorted([
            p for p in promo_names
            if p and str(p).strip().lower() not in ('nan', 'none', 'null', '', '<na>')
        ])
        
        # group_data: list of dicts
        self.group_data = pre_selected_data if pre_selected_data else []
        self.current_group_idx = -1
        self.current_method = current_method
        self.available_templates = available_templates or []

        self._init_ui()
        self._populate_group_list()
        self._center_on_parent()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # --- LEFT PANEL: GROUP LIST ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)

        left_layout.addWidget(QLabel("<b>Daftar Grup Promo:</b>"))
        self.group_list_widget = QListWidget()
        self.group_list_widget.currentRowChanged.connect(self._on_group_selected)
        left_layout.addWidget(self.group_list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Tambah"); add_btn.clicked.connect(self._add_group)
        del_btn = QPushButton("🗑️ Hapus"); del_btn.clicked.connect(self._delete_group)
        btn_layout.addWidget(add_btn); btn_layout.addWidget(del_btn)
        left_layout.addLayout(btn_layout)

        # --- RIGHT PANEL: GROUP CONFIG ---
        self.right_widget = QWidget()
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # Group Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nama Grup:"))
        self.group_name_input = QLineEdit()
        self.group_name_input.textChanged.connect(self._on_group_name_changed)
        name_layout.addWidget(self.group_name_input)
        right_layout.addLayout(name_layout)

        # Metric Checkboxes
        right_layout.addWidget(QLabel("<b>Metrik yang ditampilkan:</b>"))
        metrics_widget = QWidget()
        metrics_grid = QGridLayout(metrics_widget)
        metrics_grid.setContentsMargins(0, 2, 0, 2)
        metrics_grid.setSpacing(4)

        self.cb_qty_today = QCheckBox("Qty Today"); self.cb_qty_today.stateChanged.connect(self._on_setting_changed)
        self.cb_qty_mtd = QCheckBox("Qty MTD"); self.cb_qty_mtd.stateChanged.connect(self._on_setting_changed)
        self.cb_sales_today = QCheckBox("Sales Today"); self.cb_sales_today.stateChanged.connect(self._on_setting_changed)
        self.cb_sales_mtd = QCheckBox("Sales MTD"); self.cb_sales_mtd.stateChanged.connect(self._on_setting_changed)
        self.cb_contrib = QCheckBox("% Kontribusi"); self.cb_contrib.stateChanged.connect(self._on_setting_changed)

        metrics_grid.addWidget(self.cb_qty_today, 0, 0); metrics_grid.addWidget(self.cb_qty_mtd, 0, 1)
        metrics_grid.addWidget(self.cb_sales_today, 1, 0); metrics_grid.addWidget(self.cb_sales_mtd, 1, 1)
        metrics_grid.addWidget(self.cb_contrib, 2, 0)
        right_layout.addWidget(metrics_widget)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line)

        # ---- TEMPLATE ASSIGNMENT SECTION ----
        right_layout.addWidget(QLabel("<b>🗂️ Tampilkan di Template:</b>"))
        self.template_list_widget = QListWidget()
        self.template_list_widget.setMaximumHeight(90)
        self.template_list_widget.itemChanged.connect(self._on_template_assignment_changed)
        self._repopulate_template_list()
        self.template_info_lbl = QLabel("ℹ️ Jika tidak ada yang dipilih, grup tampil di semua template.")
        self.template_info_lbl.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        right_layout.addWidget(self.template_list_widget)
        right_layout.addWidget(self.template_info_lbl)

        line2 = QFrame(); line2.setFrameShape(QFrame.HLine); line2.setFrameShadow(QFrame.Sunken)
        right_layout.addWidget(line2)

        # Promo Selection for this group
        right_layout.addWidget(QLabel("<b>Pilih Promo untuk Grup Ini:</b>"))
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Cari nama promosi...")
        self.search_box.textChanged.connect(self._repopulate_promo_list)
        search_layout.addWidget(self.search_box)

        self.select_all_cb = QCheckBox("Pilih Semua")
        self.select_all_cb.clicked.connect(self._toggle_select_all)
        search_layout.addWidget(self.select_all_cb)
        right_layout.addLayout(search_layout)

        self.promo_list_widget = QListWidget()
        self.promo_list_widget.setAlternatingRowColors(True)
        self.promo_list_widget.itemChanged.connect(self._on_promo_checked)
        right_layout.addWidget(self.promo_list_widget)

        # Info label
        self.info_label = QLabel("Belum ada promo dipilih.")
        self.info_label.setStyleSheet("color: #5DADE2; font-weight: bold; font-size: 11px;")
        right_layout.addWidget(self.info_label)

        # Metode Kalkulasi per-grup (di right panel agar visible sebagai setting per-grup)
        calc_row = QHBoxLayout()
        calc_row.addWidget(QLabel("Metode Kalkulasi:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(["by_item", "by_receipt"])
        self.method_combo.setCurrentText(self.current_method)
        self.method_combo.setToolTip(
            "by_item : hitung berdasarkan Net Price item yang kena promo\n"
            "by_receipt : hitung berdasarkan total pembayaran struk (ideal untuk promo B1G1 / gratis item)")
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        calc_row.addWidget(self.method_combo)
        calc_row.addStretch()
        right_layout.addLayout(calc_row)

        self.right_widget.setEnabled(False)

        splitter.addWidget(left_widget); splitter.addWidget(self.right_widget)
        splitter.setSizes([280, 600])
        main_layout.addWidget(splitter, 1)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("Simpan & Terapkan")
        self.button_box.button(QDialogButtonBox.Cancel).setText("Batal")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def _center_on_parent(self):
        if self.parent():
            geo = self.frameGeometry()
            geo.moveCenter(self.parent().frameGeometry().center())
            self.move(geo.topLeft())

    # --- GROUP MANAGEMENT ---
    def _populate_group_list(self):
        self.group_list_widget.blockSignals(True)
        self.group_list_widget.clear()
        for idx, grp in enumerate(self.group_data):
            self.group_list_widget.addItem(grp.get("group_name", f"Grup {idx+1}"))
        self.group_list_widget.blockSignals(False)
        if self.group_data:
            self.group_list_widget.setCurrentRow(0)
        else:
            self.right_widget.setEnabled(False)

    def _add_group(self):
        new_group = {
            "group_name": f"Grup Promo {len(self.group_data) + 1}",
            "promos": [],
            "metrics": {"qty_today": True, "qty_mtd": True, "sales_today": True, "sales_mtd": True, "contrib": True},
            "templates": [],
            "calc_method": "by_item",  # default per-grup
        }
        self.group_data.append(new_group)
        self._populate_group_list()
        self.group_list_widget.setCurrentRow(len(self.group_data) - 1)

    def _delete_group(self):
        row = self.group_list_widget.currentRow()
        if row >= 0:
            del self.group_data[row]
            self.current_group_idx = -1
            self._populate_group_list()

    def _on_group_selected(self, row):
        if row < 0 or row >= len(self.group_data):
            self.right_widget.setEnabled(False)
            return
        self.current_group_idx = row
        self.right_widget.setEnabled(True)
        grp = self.group_data[row]

        # Load Name
        self.group_name_input.blockSignals(True)
        self.group_name_input.setText(grp.get("group_name", ""))
        self.group_name_input.blockSignals(False)

        # Load Metrics
        metrics = grp.get("metrics", {})
        for cb, key, default in [
            (self.cb_qty_today, "qty_today", True), (self.cb_qty_mtd, "qty_mtd", True),
            (self.cb_sales_today, "sales_today", True), (self.cb_sales_mtd, "sales_mtd", True),
            (self.cb_contrib, "contrib", True)
        ]:
            cb.blockSignals(True); cb.setChecked(metrics.get(key, default)); cb.blockSignals(False)

        # Load Template Assignments
        assigned_templates = set(grp.get("templates", []))
        self.template_list_widget.blockSignals(True)
        for i in range(self.template_list_widget.count()):
            item = self.template_list_widget.item(i)
            item.setCheckState(Qt.Checked if item.text() in assigned_templates else Qt.Unchecked)
        self.template_list_widget.blockSignals(False)

        # Load Calc Method
        self.method_combo.blockSignals(True)
        self.method_combo.setCurrentText(grp.get("calc_method", "by_item"))
        self.method_combo.blockSignals(False)

        self._repopulate_promo_list()

    def _on_group_name_changed(self, text):
        if self.current_group_idx >= 0:
            self.group_data[self.current_group_idx]["group_name"] = text
            self.group_list_widget.item(self.current_group_idx).setText(text)

    def _on_setting_changed(self):
        if self.current_group_idx >= 0:
            self.group_data[self.current_group_idx]["metrics"] = {
                "qty_today": self.cb_qty_today.isChecked(),
                "qty_mtd": self.cb_qty_mtd.isChecked(),
                "sales_today": self.cb_sales_today.isChecked(),
                "sales_mtd": self.cb_sales_mtd.isChecked(),
                "contrib": self.cb_contrib.isChecked(),
            }

    def _on_method_changed(self, text):
        """Simpan metode kalkulasi ke grup yang sedang aktif."""
        if self.current_group_idx >= 0:
            self.group_data[self.current_group_idx]["calc_method"] = text

    def _repopulate_template_list(self):
        """Mengisi ulang daftar template dari self.available_templates."""
        self.template_list_widget.blockSignals(True)
        self.template_list_widget.clear()
        for tpl_name in self.available_templates:
            item = QListWidgetItem(tpl_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.template_list_widget.addItem(item)
        self.template_list_widget.blockSignals(False)

    def _on_template_assignment_changed(self, item):
        """Simpan daftar template yang dicentang ke grup aktif."""
        if self.current_group_idx >= 0:
            selected_templates = []
            for i in range(self.template_list_widget.count()):
                ti = self.template_list_widget.item(i)
                if ti.checkState() == Qt.Checked:
                    selected_templates.append(ti.text())
            self.group_data[self.current_group_idx]["templates"] = selected_templates

    # --- PROMO LIST FOR CURRENT GROUP ---
    def _repopulate_promo_list(self):
        if self.current_group_idx < 0: return
        self.promo_list_widget.blockSignals(True)
        self.promo_list_widget.clear()

        group_promos = set(self.group_data[self.current_group_idx].get("promos", []))
        search = self.search_box.text().lower()

        visible = 0; checked = 0
        for name in self.all_promo_names:
            if search in name.lower():
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                is_checked = name in group_promos
                item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
                self.promo_list_widget.addItem(item)
                visible += 1
                if is_checked: checked += 1

        # Update Select All state
        self.select_all_cb.blockSignals(True)
        if visible > 0 and visible == checked: self.select_all_cb.setCheckState(Qt.Checked)
        elif checked > 0: self.select_all_cb.setCheckState(Qt.PartiallyChecked)
        else: self.select_all_cb.setCheckState(Qt.Unchecked)
        self.select_all_cb.blockSignals(False)

        self._update_info(len(group_promos))
        self.promo_list_widget.blockSignals(False)

    def _on_promo_checked(self, item):
        if self.current_group_idx < 0: return
        name = item.text()
        current_promos = set(self.group_data[self.current_group_idx].get("promos", []))
        if item.checkState() == Qt.Checked: current_promos.add(name)
        else: current_promos.discard(name)
        self.group_data[self.current_group_idx]["promos"] = list(current_promos)
        self._update_info(len(current_promos))

    def _toggle_select_all(self):
        if self.current_group_idx < 0: return
        should_check = self.select_all_cb.checkState() == Qt.Checked
        current_promos = set(self.group_data[self.current_group_idx].get("promos", []))

        self.promo_list_widget.blockSignals(True)
        for i in range(self.promo_list_widget.count()):
            item = self.promo_list_widget.item(i)
            name = item.text()
            item.setCheckState(Qt.Checked if should_check else Qt.Unchecked)
            if should_check: current_promos.add(name)
            else: current_promos.discard(name)
        self.promo_list_widget.blockSignals(False)

        self.group_data[self.current_group_idx]["promos"] = list(current_promos)
        self._update_info(len(current_promos))

    def _update_info(self, count):
        self.info_label.setText(f"Tertaut ({count}) promo ke grup ini." if count > 0 else "Belum ada promo dipilih.")

    # --- RETURN DATA ---
    def get_selected_data(self):
        # Flatten all selected promos across all groups for backward compat
        all_promos = []
        for grp in self.group_data:
            all_promos.extend(grp.get("promos", []))
        return {
            "promos": list(set(all_promos)),
            "method": self.current_method,  # global default (legacy, per grup ada di calc_method)
            "groups": self.group_data,
        }

class DailyMetricTargetDialog(QDialog):
    def __init__(self, db_manager, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metrik Target Harian")
        self.setMinimumWidth(600)
        self.db_manager = db_manager
        self.config_manager = config_manager
        
        self.current_targets = {}
        self._init_ui()
        self._load_data()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Month Selector
        month_layout = QHBoxLayout()
        month_layout.addWidget(QLabel("Pilih Bulan:"))
        self.month_combo = QComboBox()
        import calendar
        from datetime import datetime
        now = datetime.now()
        for m in range(1, 13):
            self.month_combo.addItem(f"{calendar.month_name[m]} {now.year}", f"{now.year}-{m:02d}")
        self.month_combo.setCurrentIndex(now.month - 1)
        self.month_combo.currentIndexChanged.connect(self._load_data)
        month_layout.addWidget(self.month_combo)
        layout.addLayout(month_layout)
        
        # Grid for display
        grid = QGridLayout()
        self.lbl_target_tm = QLabel("0"); self.lbl_sales_lm = QLabel("0")
        self.lbl_sc_lm = QLabel("0"); self.lbl_tc_lm = QLabel("0")
        self.lbl_target_sc_tm = QLabel("0"); self.lbl_target_tc_tm = QLabel("0")
        
        grid.addWidget(QLabel("<b>Data & Kalkulasi Bulanan</b>"), 0, 0, 1, 4)
        grid.addWidget(QLabel("Target Sales Bulan Ini (TM):"), 1, 0); grid.addWidget(self.lbl_target_tm, 1, 1)
        grid.addWidget(QLabel("Sales Nett Bulan Lalu (LM):"), 1, 2); grid.addWidget(self.lbl_sales_lm, 1, 3)
        grid.addWidget(QLabel("Total SC Bulan Lalu (LM):"), 2, 0); grid.addWidget(self.lbl_sc_lm, 2, 1)
        grid.addWidget(QLabel("Total TC Bulan Lalu (LM):"), 2, 2); grid.addWidget(self.lbl_tc_lm, 2, 3)
        grid.addWidget(QLabel("<b>Target SC Bulan Ini (TM):</b>"), 3, 0); grid.addWidget(self.lbl_target_sc_tm, 3, 1)
        grid.addWidget(QLabel("<b>Target TC Bulan Ini (TM):</b>"), 3, 2); grid.addWidget(self.lbl_target_tc_tm, 3, 3)
        layout.addLayout(grid)
        
        layout.addWidget(QLabel("<hr><b>Target Metrik Harian</b>"))
        self.table = QTableWidget(7, 3) # 7 rows, 3 cols (Metric, Weekday, Weekend)
        self.table.setHorizontalHeaderLabels(["Metrik", "Weekday", "Weekend"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        metrics = ["Target Sales", "Target SC", "Target TC", "Large (70% SC)", "Topping (80% SC)", "Spunbond (70% TC)", "OUAST (35% Sales)"]
        for i, m in enumerate(metrics):
            item = QTableWidgetItem(m)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, item)
        layout.addWidget(self.table)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.save_data)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
    def _load_data(self):
        month_str = self.month_combo.currentData()
        year, month = map(int, month_str.split('-'))
        
        # Calculate LM (Last Month)
        lm_month = month - 1 if month > 1 else 12
        lm_year = year if month > 1 else year - 1
        lm_start = f"{lm_year}-{lm_month:02d}-01"
        import calendar
        lm_end = f"{lm_year}-{lm_month:02d}-{calendar.monthrange(lm_year, lm_month)[1]}"
        
        site_code = self.config_manager.get_config().get('site_code')
        
        # Fetch Target TM
        target_tm = self.config_manager.get_target_for_month(month)
        self.lbl_target_tm.setText(f"{target_tm:,.0f}")
        
        # Fetch LM data from DB
        df_trans = self.db_manager.get_transactions_dataframe(lm_start, lm_end, site_code)
        df_pay = self.db_manager.get_payments_dataframe(lm_start, lm_end, site_code)
        
        from modules.report_processor import ReportProcessor
        processor = ReportProcessor(df_pay, df_trans, target_tm, site_code, self.db_manager)
        
        mtd_other_metrics = processor._calculate_other_sales_metrics(processor.transactions_df, processor.payments_df)
        gross_sales_lm = mtd_other_metrics.get('instore_sales', 0) + mtd_other_metrics.get('ojol_sales', 0) + mtd_other_metrics.get('fnb_order_sales', 0)
        sales_lm = gross_sales_lm / 1.1
        self.lbl_sales_lm.setText(f"{sales_lm:,.0f}")
        
        tc_lm = mtd_other_metrics.get('tc_instore', 0) + mtd_other_metrics.get('tc_ojol', 0) + mtd_other_metrics.get('tc_fnb_order', 0)
        self.lbl_tc_lm.setText(f"{tc_lm}")
        
        qty_metrics = processor._calculate_all_quantity_metrics(processor.transactions_df)
        sc_lm = qty_metrics.get('total_sold_cup', 0)
        self.lbl_sc_lm.setText(f"{sc_lm:,.0f}")
        
        # Calculate monthly metric targets
        target_sc_tm = (sc_lm / sales_lm) * target_tm if sales_lm > 0 else 0
        target_tc_tm = (tc_lm / sales_lm) * target_tm if sales_lm > 0 else 0
        self.lbl_target_sc_tm.setText(f"{target_sc_tm:,.0f}")
        self.lbl_target_tc_tm.setText(f"{target_tc_tm:,.0f}")
        
        # Calculate daily targets
        config = self.config_manager.get_config()
        weekday_w = float(config.get('weekday_weight', 1.0))
        weekend_w = float(config.get('weekend_weight', 1.8604651))
        
        weekdays, weekends = 0, 0
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            from datetime import date
            if date(year, month, day).weekday() < 5: weekdays += 1
            else: weekends += 1
            
        total_w = (weekdays * weekday_w) + (weekends * weekend_w)
        
        val_point_sales = target_tm / total_w if total_w > 0 else 0
        sales_wd = val_point_sales * weekday_w
        sales_we = val_point_sales * weekend_w
        
        sc_wd = target_sc_tm * (sales_wd / target_tm) if target_tm > 0 else 0
        sc_we = target_sc_tm * (sales_we / target_tm) if target_tm > 0 else 0
        
        tc_wd = target_tc_tm * (sales_wd / target_tm) if target_tm > 0 else 0
        tc_we = target_tc_tm * (sales_we / target_tm) if target_tm > 0 else 0
        
        self.current_targets = {
            'sales_wd': float(sales_wd), 'sales_we': float(sales_we),
            'sc_wd': float(sc_wd), 'sc_we': float(sc_we),
            'tc_wd': float(tc_wd), 'tc_we': float(tc_we),
            'large_wd': float(sc_wd * 0.7), 'large_we': float(sc_we * 0.7),
            'topping_wd': float(sc_wd * 0.8), 'topping_we': float(sc_we * 0.8),
            'spunbond_wd': float(tc_wd * 0.7), 'spunbond_we': float(tc_we * 0.7),
            'ouast_wd': float(sales_wd * 0.35), 'ouast_we': float(sales_we * 0.35)
        }
        
        # Populate table
        metrics_order = [
            ('sales_wd', 'sales_we'),
            ('sc_wd', 'sc_we'),
            ('tc_wd', 'tc_we'),
            ('large_wd', 'large_we'),
            ('topping_wd', 'topping_we'),
            ('spunbond_wd', 'spunbond_we'),
            ('ouast_wd', 'ouast_we')
        ]
        
        for i, (wd_key, we_key) in enumerate(metrics_order):
            wd_val = self.current_targets[wd_key]
            we_val = self.current_targets[we_key]
            
            wd_item = QTableWidgetItem(f"{wd_val:,.0f}")
            wd_item.setFlags(wd_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, wd_item)
            
            we_item = QTableWidgetItem(f"{we_val:,.0f}")
            we_item.setFlags(we_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, we_item)
            
    def save_data(self):
        month_str = self.month_combo.currentData()
        self.config_manager.save_monthly_metric_targets(month_str, self.current_targets)
        QMessageBox.information(self, "Tersimpan", f"Target metrik untuk {self.month_combo.currentText()} berhasil disimpan.")
        self.accept()

class BroadcastDialog(QDialog):
    """
    Dialog for displaying remote broadcast messages to the user in a modern dark theme.
    """
    def __init__(self, broadcast_data, parent=None):
        super().__init__(parent)
        # Frameless window, stays on top
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground) # Allow rounded corners on Windows
        self.resize(550, 250)
        self.broadcast_data = broadcast_data
        
        # Determine accent color based on popup_type (Using neon colors for dramatic dark theme)
        b_type = self.broadcast_data.get('popup_type', 'info').lower()
        if b_type == 'danger' or b_type == 'critical':
            self.accent_color = "#ff4757"  # Neon Red
        elif b_type == 'warning':
            self.accent_color = "#ffa502"  # Neon Amber
        elif b_type == 'success':
            self.accent_color = "#2ed573"  # Neon Green
        else: # info
            self.accent_color = "#1e90ff"  # Neon Blue
            
        self._init_ui()
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # Margin for drop shadow effect later
        
        # Inner Frame container with dark theme styling
        self.frame = QFrame(self)
        self.frame.setObjectName("BroadcastFrame")
        self.frame.setStyleSheet(f"""
            #BroadcastFrame {{
                background-color: #1e1e24; /* Dark gray */
                border-radius: 8px;
                border: 1px solid #333333;
                border-top: 4px solid {self.accent_color};
            }}
        """)
        
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(30, 25, 30, 25)
        frame_layout.setSpacing(15)
        
        # --- TITLE ---
        lbl_title = QLabel(self.broadcast_data.get('title', 'Pemberitahuan Sistem'))
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(f"""
            color: #f1f2f6; 
            font-family: 'Segoe UI', Arial, sans-serif; 
            font-weight: 800; 
            font-size: 18px; 
            letter-spacing: 0.5px;
        """)
        frame_layout.addWidget(lbl_title)
        
        # Semantic divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: #2F3542; border: none; min-height: 1px; max-height: 1px;")
        frame_layout.addWidget(divider)
        
        # --- OPTIONAL IMAGE ---
        if 'image_data' in self.broadcast_data:
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap()
            if pixmap.loadFromData(self.broadcast_data['image_data']):
                # Scale it down gracefully if it's too large, but keep aspect ratio
                # Make it fit within the dialog width
                scaled_pixmap = pixmap.scaled(500, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl_img = QLabel()
                lbl_img.setPixmap(scaled_pixmap)
                lbl_img.setAlignment(Qt.AlignCenter)
                lbl_img.setStyleSheet("margin-bottom: 5px; border-radius: 4px;")
                frame_layout.addWidget(lbl_img)
        
        # --- MESSAGE ---
        lbl_msg = QLabel(self.broadcast_data.get('message', ''))
        lbl_msg.setWordWrap(True)
        # Using Markdown format for bold/links support natively
        lbl_msg.setTextFormat(Qt.MarkdownText) 
        lbl_msg.setOpenExternalLinks(True)
        lbl_msg.setStyleSheet("""
            color: #ced6e0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
        """)
        frame_layout.addWidget(lbl_msg)
        
        frame_layout.addStretch()
        
        # --- BUTTON AREA ---
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 5, 0, 0)
        btn_layout.addStretch() # Push button to right
        
        self.btn_ok = QPushButton("FAHHH..")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setMinimumWidth(150)
        self.btn_ok.setMinimumHeight(40)
        
        # Dramatic neon hollow button styling
        self.btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self.accent_color};
                border: 2px solid {self.accent_color};
                border-radius: 6px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: bold;
                font-size: 13px;
                letter-spacing: 1px;
                padding: 5px 15px;
            }}
            QPushButton:hover {{
                background-color: {self.accent_color};
                color: #1e1e24; /* Invert text to dark on hover */
            }}
            QPushButton:pressed {{
                background-color: transparent;
                color: {self.accent_color};
            }}
        """)
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        
        frame_layout.addLayout(btn_layout)
        main_layout.addWidget(self.frame)

# --- CLASS BARU: DIALOG UPLOAD 2 FILE CSV ---


class AuroraSyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sinkronisasi Data Aurora")
        self.setFixedSize(350, 230)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Pilih Rentang Tanggal Laporan:</b>"))
        
        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("Dari:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-1)) # Default kemarin
        form_layout.addWidget(self.start_date_edit)
        
        form_layout.addWidget(QLabel("Sampai:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.end_date_edit.setDate(QDate.currentDate())
        form_layout.addWidget(self.end_date_edit)
        
        layout.addLayout(form_layout)
        
        # --- SHIFT 1 TOGGLE ---
        self.shift1_check = QCheckBox("Tandai sebagai data Shift 1")
        self.shift1_check.setToolTip("Jika dicentang, proses sinkronisasi akan menganggap data ini murni untuk Shift 1\n(untuk keperluan Upselling Table Shift 2 target)")
        self.shift1_check.toggled.connect(self._on_shift1_toggled)
        layout.addWidget(self.shift1_check)
        # ----------------------
        
        layout.addSpacing(10)
        info_lbl = QLabel("<i>Kredensial login akan otomatis menggunakan data\nStore Manager / Asst. Store Manager dari Database.</i>")
        info_lbl.setStyleSheet("color: gray;")
        layout.addWidget(info_lbl)
        
        layout.addStretch()
        
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btn_box.button(QDialogButtonBox.Ok).setText("Mulai Sinkronisasi")
        self.btn_box.accepted.connect(self._validate)
        self.btn_box.rejected.connect(self.reject)
        layout.addWidget(self.btn_box)
        
    def _on_shift1_toggled(self, checked):
        if checked:
            reply = QMessageBox.warning(
                self,
                "⚠ Peringatan: Timpa Data Shift 1",
                "Anda akan menandai data ini sebagai <b>Shift 1</b>.<br><br>"
                "Tindakan ini akan <b>menimpa data Shift 1 yang sudah ada</b> sebelumnya "
                "(jika ada) pada saat proses import dilakukan.<br><br>"
                "Apakah Anda yakin ingin melanjutkan?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                # Batalkan centang jika user memilih No
                self.shift1_check.blockSignals(True)
                self.shift1_check.setChecked(False)
                self.shift1_check.blockSignals(False)
            
    def _validate(self):
        if self.start_date_edit.date() > self.end_date_edit.date():
            QMessageBox.warning(self, "Tanggal Tidak Valid", "Tanggal 'Dari' tidak melebihi tanggal 'Sampai'.")
            return
        self.accept()
        
    def get_dates(self):
        return self.start_date_edit.date().toString("MM/dd/yyyy"), self.end_date_edit.date().toString("MM/dd/yyyy")
        
    def is_shift1(self):
        return self.shift1_check.isChecked()






class DualFileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Data CSV")
        self.setFixedSize(500, 250)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>1. File Transaksi (AH Commodity Report):</b>"))
        self.trans_layout = QHBoxLayout()
        self.trans_path = QLineEdit()
        self.trans_path.setPlaceholderText("Pilih file transaksi...")
        self.trans_btn = QPushButton("Browse")
        self.trans_btn.clicked.connect(lambda: self._browse_file(self.trans_path))
        self.trans_layout.addWidget(self.trans_path)
        self.trans_layout.addWidget(self.trans_btn)
        layout.addLayout(self.trans_layout)
        
        layout.addWidget(QLabel("<b>2. File Pembayaran (MOP Report):</b>"))
        self.pay_layout = QHBoxLayout()
        self.pay_path = QLineEdit()
        self.pay_path.setPlaceholderText("Pilih file pembayaran...")
        self.pay_btn = QPushButton("Browse")
        self.pay_btn.clicked.connect(lambda: self._browse_file(self.pay_path))
        self.pay_layout.addWidget(self.pay_path)
        self.pay_layout.addWidget(self.pay_btn)
        layout.addLayout(self.pay_layout)

        layout.addSpacing(10)
        self.shift1_check = QCheckBox("Tandai sebagai Data Shift 1 (Overhand)")
        self.shift1_check.setToolTip("Centang ini JIKA Anda sedang melakukan overhand dari Shift 1 ke Shift 2.\nData penjualan saat ini akan disimpan sebagai 'Actual Shift 1'.")
        self.shift1_check.setStyleSheet("font-weight: bold; color: #d32f2f;")
        layout.addWidget(self.shift1_check)
        
        layout.addStretch()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _browse_file(self, line_edit):
        f, _ = QFileDialog.getOpenFileName(self, "Pilih File CSV", "", "CSV Files (*.csv);;All Files (*)")
        if f: line_edit.setText(f)

    def _validate_and_accept(self):
        if not self.trans_path.text() or not self.pay_path.text():
            QMessageBox.warning(self, "Data Belum Lengkap", "Harap pilih kedua file (Transaksi dan Pembayaran).")
            return
        
        if self.shift1_check.isChecked():
            confirm = QMessageBox.question(
                self, "Konfirmasi Shift 1",
                "Anda mencentang 'Tandai sebagai Data Shift 1'.\n\n"
                "Data Actual Shift 1 yang lama akan DITIMPA dengan data dari file ini.\n"
                "Apakah Anda yakin?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.No:
                return
            
        self.accept()

    def get_files(self):
        return self.trans_path.text(), self.pay_path.text()
    
    def is_shift1(self):
        return self.shift1_check.isChecked()
