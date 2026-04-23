# ui_components.py
import logging
import pandas as pd
import json
import numpy as np
import calendar
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel,
    QFileDialog, QTableWidget, QTableWidgetItem, QHBoxLayout, QHeaderView,
    QRadioButton, QDateEdit, QGridLayout, QLineEdit, QFrame, QSpacerItem, QSizePolicy, QMessageBox,
    QSplitter, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QFormLayout, QSpinBox, QComboBox, QCalendarWidget, QGroupBox, QCheckBox, QApplication, QScrollArea,
    QProgressBar, QStyle, QStackedWidget, QGraphicsDropShadowEffect, QSplashScreen
)
from PyQt5.QtCore import QDate, Qt, QRegExp, pyqtSignal
from PyQt5.QtGui import QRegExpValidator, QFont, QIcon, QTextCharFormat, QColor, QIntValidator, QDoubleValidator, QPixmap, QMovie

# --- Force Pyinstaller to detect PyQtWebEngine ---
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtCore import QUrl
except ImportError:
    pass

from utils.constants import (
    BASE_DIR, COL_ARTICLE_NAME, COL_NET_PRICE, COL_QUANTITY, COL_PROMOTION_NAME,
    REPORT_TEMPLATE_FILE, EDSPAYED_DATA_FILE, # <--- Penting: Path Konfigurasi
    APP_ICON_PATH, DEFAULT_MARQUEE_TEXT
)
from utils.app_utils import calculate_ac, calculate_growth, format_article_name_short
from utils.employee_utils import EmployeeDB
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# --- Konstanta untuk Edspayed ---
VIEW_ICO = os.path.join(BASE_DIR, "assets", "images", "view_icon.png")
CALENDAR_ICO = os.path.join(BASE_DIR, "assets", "images", "calendar_icon.png")

# --- KELAS UNTUK FITUR EDSPAYED SEKARANG ADA DI SINI ---

class AddEditPeriodDialog(QDialog):
    def __init__(self, parent=None, period_data=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah/Edit Periode Kedaluwarsa")
        layout = QFormLayout(self)
        self.name_input = QLineEdit()
        self.value_input = QSpinBox(); self.value_input.setRange(1, 999)
        self.unit_input = QComboBox(); self.unit_input.addItems(["Hour", "Day", "Month"])
        layout.addRow("Nama Tampilan (e.g., '2 Minggu'):", self.name_input)
        layout.addRow("Nilai Periode:", self.value_input)
        layout.addRow("Satuan:", self.unit_input)
        if period_data:
            self.name_input.setText(period_data.get('name', ''))
            self.value_input.setValue(period_data.get('value', 1))
            index = self.unit_input.findText(period_data.get('unit', 'Day'), Qt.MatchFixedString)
            if index >= 0: self.unit_input.setCurrentIndex(index)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def validate_and_accept(self):
        if not self.name_input.text().strip() or self.value_input.value() <= 0:
            QMessageBox.warning(self, "Input Tidak Valid", "Nama Tampilan dan Nilai Periode tidak boleh kosong.")
            return
        self.accept()

    def get_data(self):
        return {"name": self.name_input.text().strip().title(), "value": self.value_input.value(), "unit": self.unit_input.currentText()}

class EditItemDialog(QDialog):
    def __init__(self, current_name, current_temp, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Item")
        layout = QFormLayout(self)
        self.name_input = QLineEdit(current_name)
        self.temp_combo = QComboBox()
        self.temp_combo.addItems(["Suhu Ruang", "Suhu Chiller", "Suhu Freezer"])
        idx = self.temp_combo.findText(current_temp)
        if idx >= 0: self.temp_combo.setCurrentIndex(idx)
        layout.addRow("Nama Item:", self.name_input)
        layout.addRow("Penyimpanan:", self.temp_combo)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
    def get_data(self):
        return self.name_input.text().strip().title(), self.temp_combo.currentText()

class ManagePeriodsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setWindowTitle("Kelola Daftar Periode Kedaluwarsa")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout(self)
        self.period_list_widget = QListWidget()
        self.populate_list()
        layout.addWidget(self.period_list_widget)
        button_layout = QHBoxLayout()
        add_btn, edit_btn, delete_btn = QPushButton("Tambah Baru..."), QPushButton("Edit Terpilih..."), QPushButton("Hapus Terpilih")
        button_layout.addWidget(add_btn); button_layout.addWidget(edit_btn); button_layout.addWidget(delete_btn)
        layout.addLayout(button_layout)
        close_button = QDialogButtonBox(QDialogButtonBox.Close)
        close_button.rejected.connect(self.accept)
        layout.addWidget(close_button)
        add_btn.clicked.connect(self.add_period)
        edit_btn.clicked.connect(self.edit_period)
        delete_btn.clicked.connect(self.delete_period)
    
    def populate_list(self):
        self.period_list_widget.clear()
        for period in self.parent_widget.periods_config: self.period_list_widget.addItem(period['name'])
            
    def add_period(self):
        dialog = AddEditPeriodDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data(); new_data['items'] = []
            self.parent_widget.periods_config.append(new_data)
            self.parent_widget.save_periods_to_file(); self.populate_list()

    def edit_period(self):
        current_item = self.period_list_widget.currentItem()
        if not current_item: QMessageBox.warning(self, "Peringatan", "Pilih periode yang ingin diedit."); return
        current_index = self.period_list_widget.row(current_item)
        period_data = self.parent_widget.periods_config[current_index]
        dialog = AddEditPeriodDialog(self, period_data=period_data)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_data()
            self.parent_widget.periods_config[current_index].update(updated_data)
            self.parent_widget.save_periods_to_file(); self.populate_list()

    def delete_period(self):
        current_item = self.period_list_widget.currentItem()
        if not current_item: QMessageBox.warning(self, "Peringatan", "Pilih periode yang ingin dihapus."); return
        reply = QMessageBox.question(self, "Konfirmasi", f"Anda yakin ingin menghapus periode '{current_item.text()}'?", QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            current_index = self.period_list_widget.row(current_item)
            del self.parent_widget.periods_config[current_index]
            self.parent_widget.save_periods_to_file(); self.populate_list()

class EdspayedWidget(QWidget):
    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        self.periods_config = []
        self.current_start_date = datetime.now()
        self.is_custom_date = False
        self._init_ui()
        self.load_periods_from_file()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel); left_layout.setContentsMargins(0,0,0,0)
        
        self.period_table = QTableWidget()
        self.period_table.setObjectName("edspayedPeriodTable")
        self.period_table.setColumnCount(3); self.period_table.setHorizontalHeaderLabels(["EXPIRATION PERIOD", "FROM", "EXP DATE"])
        header = self.period_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.period_table.setSelectionBehavior(QTableWidget.SelectRows); self.period_table.setSelectionMode(QTableWidget.SingleSelection)
        self.period_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.period_table.setAlternatingRowColors(True)
        
        self.period_table.itemSelectionChanged.connect(self.on_period_selected)
        left_layout.addWidget(self.period_table)

        calendar_button_layout = QHBoxLayout() 
        self.date_picker_button = QPushButton()
        calendar_icon = QIcon(CALENDAR_ICO)
        if calendar_icon.isNull(): self.date_picker_button.setText("Pilih Tanggal Mulai")
        else: self.date_picker_button.setIcon(calendar_icon)
        self.date_picker_button.setToolTip("Pilih tanggal mulai untuk perhitungan kedaluwarsa")
        self.date_picker_button.clicked.connect(self.open_date_picker)
        calendar_button_layout.addStretch(); calendar_button_layout.addWidget(self.date_picker_button); calendar_button_layout.addStretch()
        left_layout.addLayout(calendar_button_layout)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.items_title_label = QLabel("Item Tertaut (Pilih Periode)"); font = self.items_title_label.font(); font.setBold(True); self.items_title_label.setFont(font)
        
        # Ganti dengan tabel untuk kolom suhu
        self.linked_items_table = QTableWidget()
        self.linked_items_table.setObjectName("edspayedItemTable")
        self.linked_items_table.setColumnCount(2)
        self.linked_items_table.setHorizontalHeaderLabels(["Nama Item", "Penyimpanan"])
        header_items = self.linked_items_table.horizontalHeader()
        header_items.setSectionResizeMode(0, QHeaderView.Stretch)
        header_items.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.linked_items_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.linked_items_table.setSelectionMode(QTableWidget.SingleSelection)
        self.linked_items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.linked_items_table.setAlternatingRowColors(True)

        # Kontrol input baru
        self.add_item_input = QLineEdit(); self.add_item_input.setPlaceholderText("Ketik nama item baru..."); self.add_item_input.setFixedHeight(32)
        self.item_temp_combo = QComboBox()
        self.item_temp_combo.addItems(["Suhu Ruang", "Suhu Chiller", "Suhu Freezer"]); self.item_temp_combo.setFixedHeight(32)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.add_item_input, stretch=2)
        input_layout.addWidget(self.item_temp_combo, stretch=1)
        
        self.add_item_btn = QPushButton("Tambah"); self.add_item_btn.setFixedHeight(32); self.add_item_btn.setObjectName("edspayedAddBtn")
        self.edit_item_btn = QPushButton("Edit Terpilih"); self.edit_item_btn.setFixedHeight(32); self.edit_item_btn.setObjectName("edspayedEditBtn")
        self.delete_item_btn = QPushButton("Hapus Terpilih"); self.delete_item_btn.setFixedHeight(32); self.delete_item_btn.setObjectName("edspayedDeleteBtn")
        
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.add_item_btn)
        action_layout.addWidget(self.edit_item_btn)
        action_layout.addWidget(self.delete_item_btn)
        
        right_layout.addWidget(self.items_title_label); right_layout.addWidget(self.linked_items_table)
        right_layout.addLayout(input_layout); right_layout.addLayout(action_layout)
        
        self.add_item_btn.clicked.connect(self.add_linked_item)
        self.edit_item_btn.clicked.connect(self.edit_linked_item)
        self.delete_item_btn.clicked.connect(self.delete_linked_item)

        splitter.addWidget(left_panel); splitter.addWidget(right_panel); splitter.setSizes([450, 250])
        main_layout.addWidget(splitter)
        
        bottom_button_layout = QHBoxLayout()
        self.manage_periods_button = QPushButton("Kelola Daftar Periode"); self.manage_periods_button.setObjectName("edspayedManageBtn")
        self.save_all_button = QPushButton("Simpan Perubahan Item"); self.save_all_button.setObjectName("edspayedSaveBtn")
        # Note: Dialog ManagePeriodsDialog harus diimport dari ui.dialogs atau didefinisikan jika ingin lokal
        self.manage_periods_button.clicked.connect(self.open_manage_periods_dialog)
        self.save_all_button.clicked.connect(self.save_all_changes)
        bottom_button_layout.addStretch(); bottom_button_layout.addWidget(self.manage_periods_button); bottom_button_layout.addWidget(self.save_all_button)
        main_layout.addLayout(bottom_button_layout)

    def load_periods_from_file(self):
        try:
            # --- PERBAIKAN: Gunakan konstanta path dari utils.constants ---
            with open(EDSPAYED_DATA_FILE, 'r', encoding='utf-8') as f: self.periods_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.periods_config = [{"name": "6 Month", "value": 6, "unit": "Month", "items": []}, {"name": "90 Days", "value": 90, "unit": "Day", "items": []}]
            self.save_periods_to_file()
        self.populate_period_table()

    def save_periods_to_file(self):
        try:
            # --- PERBAIKAN: Gunakan konstanta path dari utils.constants ---
            with open(EDSPAYED_DATA_FILE, 'w', encoding='utf-8') as f: json.dump(self.periods_config, f, indent=4)
            return True
        except IOError as e: QMessageBox.critical(self, "Error", f"Gagal menyimpan data periode: {e}"); return False

    def populate_period_table(self):
        if not self.is_custom_date:
            self.current_start_date = datetime.now()
            
        def get_sort_key(period_dict):
            value = period_dict.get('value', 0)
            unit = period_dict.get('unit', 'Day')
            if unit == 'Month': return value * 30 
            return value

        self.periods_config.sort(key=get_sort_key)
        self.period_table.setRowCount(0)
        from_date_str = self.current_start_date.strftime("%d-%m-%Y")

        for period_data in self.periods_config:
            row_pos = self.period_table.rowCount()
            self.period_table.insertRow(row_pos)
            
            value, unit = period_data.get('value', 0), period_data.get('unit', 'Day')
            if unit == "Month":
                exp_date = self.current_start_date + relativedelta(months=value)
                exp_date_str = exp_date.strftime("%d-%m-%Y")
                from_date_fmt = from_date_str
            elif unit == "Hour":
                exp_date = self.current_start_date + relativedelta(hours=value)
                exp_date_str = exp_date.strftime("%H.%M.%d")
                from_date_fmt = self.current_start_date.strftime("%H.%M.%d")
            else: # Day
                exp_date = self.current_start_date + relativedelta(days=value)
                exp_date_str = exp_date.strftime("%d-%m-%Y")
                from_date_fmt = from_date_str
            
            self.period_table.setItem(row_pos, 0, QTableWidgetItem(period_data.get('name', '')))
            self.period_table.setItem(row_pos, 1, QTableWidgetItem(from_date_fmt))
            self.period_table.setItem(row_pos, 2, QTableWidgetItem(exp_date_str))
        
        self.linked_items_table.setRowCount(0); self.items_title_label.setText("Item Tertaut (Pilih Periode)")

    def refresh_times_only(self):
        if self.is_custom_date:
            return
            
        self.current_start_date = datetime.now()
        from_date_str = self.current_start_date.strftime("%d-%m-%Y")

        for row_pos in range(self.period_table.rowCount()):
            # Fallback in case period_table and periods_config length mismatch during edit
            if row_pos >= len(self.periods_config):
                break
                
            period_data = self.periods_config[row_pos]
            value = period_data.get('value', 0)
            unit = period_data.get('unit', 'Day')
            
            if unit == "Month":
                exp_date = self.current_start_date + relativedelta(months=value)
                exp_date_str = exp_date.strftime("%d-%m-%Y")
                from_date_fmt = from_date_str
            elif unit == "Hour":
                exp_date = self.current_start_date + relativedelta(hours=value)
                exp_date_str = exp_date.strftime("%H.%M.%d")
                from_date_fmt = self.current_start_date.strftime("%H.%M.%d")
            else: # Day
                exp_date = self.current_start_date + relativedelta(days=value)
                exp_date_str = exp_date.strftime("%d-%m-%Y")
                from_date_fmt = from_date_str
            
            # Hanya update text-nya saja tanpa mengubah selection atau focus
            from_item = self.period_table.item(row_pos, 1)
            if from_item:
                from_item.setText(from_date_fmt)
            exp_item = self.period_table.item(row_pos, 2)
            if exp_item:
                exp_item.setText(exp_date_str)

    def on_period_selected(self):
        selected_rows = self.period_table.selectionModel().selectedRows()
        if not selected_rows: self.linked_items_table.setRowCount(0); self.items_title_label.setText("Item Tertaut (Pilih Periode)"); return
        period_data = self.periods_config[selected_rows[0].row()]
        self.items_title_label.setText(f"Item untuk: {period_data.get('name', '')}")
        self.linked_items_table.setRowCount(0)
        
        items = period_data.get('items', [])
        for item in items:
            row_pos = self.linked_items_table.rowCount()
            self.linked_items_table.insertRow(row_pos)
            if isinstance(item, dict):
                name = item.get("name", "")
                temp = item.get("temp", "-")
            else:
                # Legacy compatibility (string)
                name = str(item)
                temp = "-"
                
            self.linked_items_table.setItem(row_pos, 0, QTableWidgetItem(name))
            self.linked_items_table.setItem(row_pos, 1, QTableWidgetItem(temp))

    def add_linked_item(self):
        if not self.period_table.selectionModel().selectedRows(): QMessageBox.warning(self, "Peringatan", "Pilih dulu periode di tabel kiri."); return
        item_text = self.add_item_input.text().strip().title()
        item_temp = self.item_temp_combo.currentText()
        
        if item_text:
             row_pos = self.linked_items_table.rowCount()
             self.linked_items_table.insertRow(row_pos)
             self.linked_items_table.setItem(row_pos, 0, QTableWidgetItem(item_text))
             self.linked_items_table.setItem(row_pos, 1, QTableWidgetItem(item_temp))
             self.add_item_input.clear()
        else: QMessageBox.warning(self, "Input Kosong", "Nama item tidak boleh kosong.")

    def edit_linked_item(self):
        selected_rows = self.linked_items_table.selectionModel().selectedRows()
        if not selected_rows: 
            QMessageBox.warning(self, "Peringatan", "Pilih item di daftar yang ingin diedit.")
            return
            
        row = selected_rows[0].row()
        current_name = self.linked_items_table.item(row, 0).text() if self.linked_items_table.item(row, 0) else ""
        current_temp = self.linked_items_table.item(row, 1).text() if self.linked_items_table.item(row, 1) else "-"
        
        dialog = EditItemDialog(current_name, current_temp, self)
        if dialog.exec_() == QDialog.Accepted:
            new_name, new_temp = dialog.get_data()
            if new_name:
                self.linked_items_table.setItem(row, 0, QTableWidgetItem(new_name))
                self.linked_items_table.setItem(row, 1, QTableWidgetItem(new_temp))
            else:
                QMessageBox.warning(self, "Input Kosong", "Nama item tidak boleh kosong.")

    def delete_linked_item(self):
        selected_rows = self.linked_items_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "Peringatan", "Pilih item di daftar yang ingin dihapus."); return
        for index in sorted(selected_rows, reverse=True):
             self.linked_items_table.removeRow(index.row())

    def save_all_changes(self):
        selected_rows = self.period_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "Peringatan", "Tidak ada periode yang dipilih untuk disimpan itemnya."); return
        
        updated_items = []
        for row in range(self.linked_items_table.rowCount()):
            name_item = self.linked_items_table.item(row, 0)
            temp_item = self.linked_items_table.item(row, 1)
            updated_items.append({
                "name": name_item.text() if name_item else "",
                "temp": temp_item.text() if temp_item else "-"
            })
            
        self.periods_config[selected_rows[0].row()]['items'] = updated_items
        if self.save_periods_to_file():
            QMessageBox.information(self, "Sukses", "Perubahan item berhasil disimpan.")
            self.populate_period_table()

    def open_manage_periods_dialog(self):
        # Dialog ini diimport dari ui.dialogs untuk menghindari circular dependency
        from ui.dialogs import ManagePeriodsDialog 
        dialog = ManagePeriodsDialog(self); dialog.exec_()
        self.load_periods_from_file()

    def open_date_picker(self):
        dialog = QDialog(self); dialog.setWindowTitle("Pilih Tanggal Mulai Perhitungan"); dialog.setGeometry(200, 200, 350, 280)
        layout = QVBoxLayout(dialog); calendar_widget = QCalendarWidget(); calendar_widget.setGridVisible(True)
        calendar_widget.setSelectedDate(QDate(self.current_start_date.year, self.current_start_date.month, self.current_start_date.day))
        layout.addWidget(calendar_widget); select_button = QPushButton("Pilih Tanggal Ini"); select_button.setFixedHeight(30)
        layout.addWidget(select_button, alignment=Qt.AlignCenter)
        def on_select_date():
            q_date = calendar_widget.selectedDate(); self.current_start_date = datetime(q_date.year(), q_date.month(), q_date.day())
            self.is_custom_date = True
            self.populate_period_table(); dialog.accept()
        select_button.clicked.connect(on_select_date); dialog.exec_()

class EdspayedTab(QWidget): 
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10,10,10,10) # Beri sedikit margin
        self.edspayed_content_widget = EdspayedWidget(parent_app)
        layout.addWidget(self.edspayed_content_widget)
        self.setLayout(layout)

class MainDashboardUI(QWidget):
    # Sinyal untuk berkomunikasi dengan window utama
    open_file_requested = pyqtSignal()
    sync_aurora_requested = pyqtSignal() # Add signal for Aurora sync
    db_analysis_requested = pyqtSignal()
    nav_index_requested = pyqtSignal(QPushButton) # Add signal
    recent_file_selected = pyqtSignal(str)
    quick_access_triggered = pyqtSignal(str)

    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- SIDEBAR ---
        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebar_widget")
        self.sidebar_widget.setFixedWidth(220)
        # Akan distyling lewat QSS nanti, tapi kasih default di sini
        self.sidebar_widget.setStyleSheet("""
            QWidget#sidebar_widget {
                background-color: #2b3e50;
                border-right: 1px solid #1a252f;
            }
            QPushButton.sidebar_btn {
                background-color: transparent;
                color: #ecf0f1;
                text-align: left;
                padding: 12px 15px;
                border: none;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                margin: 2px 10px;
            }
            QPushButton.sidebar_btn:hover {
                background-color: #34495e;
            }
            QPushButton.sidebar_btn:checked {
                background-color: #eef1f7;
                color: #1a4f8a;
                border-top-left-radius: 20px;
                border-bottom-left-radius: 20px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                margin: 5px 0px 5px 15px;
            }
            QLabel.sidebar_title {
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: 20px 10px;
                text-align: center;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #1a252f;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #34495e;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        sidebar_main_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_main_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_main_layout.setSpacing(0)

        # Header Sidebar (Toggle + Logo)
        sidebar_header = QHBoxLayout()
        sidebar_header.setContentsMargins(10, 15, 10, 15)
        
        self.toggle_btn = QPushButton("☰")
        self.toggle_btn.setFixedSize(40, 40)
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                font-size: 20px;
                border: none;
            }
            QPushButton:hover {
                background-color: #34495e;
                border-radius: 5px;
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle_sidebar)
        
        self.logo_label = QLabel("Repot.in")
        self.logo_label.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.logo_label.setAlignment(Qt.AlignCenter)
        
        sidebar_header.addWidget(self.toggle_btn)
        sidebar_header.addWidget(self.logo_label, 1)
        
        # Container for Header so we can add Marquee below it
        sidebar_header_container = QVBoxLayout()
        sidebar_header_container.addLayout(sidebar_header)
        
        # Tambahkan Marquee text di bawah Logo pada Sidebar
        self.marquee_label = QLabel(DEFAULT_MARQUEE_TEXT)
        self.marquee_label.setObjectName("marquee_label")
        self.marquee_label.setAlignment(Qt.AlignCenter)
        # Style marquee disesuaikan dengan warna sidebar agar menyatu indah
        self.marquee_label.setStyleSheet("color: #ecf0f1; font-size: 10px; font-style: italic; padding-bottom: 5px; background: transparent;")
        self.marquee_label.setWordWrap(False)
        
        sidebar_header_container.addWidget(self.marquee_label)
        sidebar_main_layout.addLayout(sidebar_header_container)
        
        # Scroll Area for Buttons
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        sidebar_layout = QVBoxLayout(scroll_content)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(5)

        # Sidebar Buttons
        self.all_nav_buttons = [] # Track all button instances
        self.btn_dashboard = self._create_nav_button("Dashboard", "★", checked=True)
        self.btn_sales_report = self._create_nav_button("Sales Report", "📊")
        self.btn_bscd = self._create_nav_button("BSCD", "📋")
        self.btn_kas = self._create_nav_button("Kas & Tips", "💰")
        self.btn_order = self._create_nav_button("Order Barang", "📦")
        self.btn_inuse = self._create_nav_button("In-Use", "🏷")
        self.btn_waste = self._create_nav_button("Konversi Waste", "♻")
        self.btn_edspayed = self._create_nav_button("Edspayed", "🕒")
        self.btn_minum = self._create_nav_button("Minum", "💧")
        
        self.btn_import = self._create_nav_button("Import CSV", "📁")
        self.btn_sync_aurora = self._create_nav_button("Sync Aurora", "☁")
        self.btn_db = self._create_nav_button("Database", "🗄")
        #self.btn_tools = self._create_nav_button("Tools", "🔧")
        self.btn_todo = self._create_nav_button("Todo List", "✅")
        self.btn_notes = self._create_nav_button("Notes", "📝")

        # Grouping buttons visually
        lbl_menu = QLabel(" MAIN MENU")
        lbl_menu.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold; margin-left: 10px; background: transparent;")
        sidebar_layout.addWidget(lbl_menu)
        sidebar_layout.addWidget(self.btn_dashboard)
        
        sidebar_layout.addSpacing(10)
        lbl_reports = QLabel(" REPORTS & DATA")
        lbl_reports.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold; margin-left: 10px; background: transparent;")
        sidebar_layout.addWidget(lbl_reports)
        sidebar_layout.addWidget(self.btn_sales_report)
        sidebar_layout.addWidget(self.btn_bscd)
        sidebar_layout.addWidget(self.btn_kas)
        sidebar_layout.addWidget(self.btn_order)
        sidebar_layout.addWidget(self.btn_inuse)
        sidebar_layout.addWidget(self.btn_waste)
        sidebar_layout.addWidget(self.btn_edspayed)
        sidebar_layout.addWidget(self.btn_minum)
        
        sidebar_layout.addSpacing(10)
        lbl_system = QLabel(" SYSTEM")
        lbl_system.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold; margin-left: 10px; background: transparent;")
        sidebar_layout.addWidget(lbl_system)
        sidebar_layout.addWidget(self.btn_import)
        sidebar_layout.addWidget(self.btn_sync_aurora)
        sidebar_layout.addWidget(self.btn_db)
        #sidebar_layout.addWidget(self.btn_tools)
        sidebar_layout.addWidget(self.btn_todo)
        sidebar_layout.addWidget(self.btn_notes)
        
        sidebar_layout.addStretch()
        
        self.scroll_area.setWidget(scroll_content)
        sidebar_main_layout.addWidget(self.scroll_area, 1)

        # Bottom stats/info in sidebar (optional based on reference)
        self.version_label = QLabel(f"v{getattr(self.parent_app, 'app_version', 'N/A')}")
        self.version_label.setStyleSheet("color: #7f8c8d; padding: 10px; font-size: 10px; background: transparent;")
        self.version_label.setAlignment(Qt.AlignCenter)
        sidebar_main_layout.addWidget(self.version_label)

        # Simpan referensi ke label kategori agar mudah disembunyikan
        self.category_labels = [lbl_menu, lbl_reports, lbl_system]

        # --- MAIN CONTENT AREA ---
        content_wrapper = QWidget()
        content_wrapper.setObjectName("content_wrapper")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(20, 12, 20, 20)

        # Header of Main Content
        header_layout = QHBoxLayout()
        self.welcome_label = QLabel("Welcome, Store")
        self.welcome_label.setObjectName("welcome_label")
        
        self.datetime_label = QLabel("...")
        self.datetime_label.setObjectName("datetime_label")
        
        header_layout.addWidget(self.welcome_label)
        header_layout.addStretch()
        header_layout.addWidget(self.datetime_label)

        content_layout.addLayout(header_layout)
        content_layout.addSpacing(8)

        # The actual content placeholder using QStackedWidget
        self.main_stack = QStackedWidget()
        
        # Load Dashboard Tab as index 0
        from ui.dashboard_tab import DashboardTab
        self.dashboard_content = DashboardTab(self.parent_app)
        self.main_stack.addWidget(self.dashboard_content)
        
        # Frame for styling
        card_frame = QFrame()
        card_frame.setObjectName("main_card_frame")
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.addWidget(self.main_stack)

        content_layout.addWidget(card_frame)

        # Assemble Main Layout
        main_layout.addWidget(self.sidebar_widget)
        main_layout.addWidget(content_wrapper, 1) # content takes remaining space

        # Connect internal buttons to signals that main_app will catch
        self.btn_import.clicked.connect(self.open_file_requested.emit)
        self.btn_sync_aurora.clicked.connect(self.sync_aurora_requested.emit)
        self.btn_db.clicked.connect(self.db_analysis_requested.emit)
        
        # Kita simpan button report dalam dictionary/list agar mudah dikontrol enabled/disabled state-nya
        self.report_buttons = [
            self.btn_sales_report, self.btn_bscd, self.btn_kas, 
            self.btn_order, self.btn_inuse, self.btn_waste, self.btn_edspayed,
            self.btn_minum
        ]

    def _create_nav_button(self, text, icon_str, checked=False):
        btn = QPushButton(f" {icon_str}   {text}")
        btn.setObjectName(f"nav_btn_{text.lower().replace(' ', '_')}")
        btn.setProperty("class", "sidebar_btn")
        btn.setProperty("icon_str", f" {icon_str} ")
        btn.setProperty("full_text", f" {icon_str}   {text}")
        btn.setCheckable(True)
        if checked:
            btn.setChecked(True)
            
        if hasattr(self, 'all_nav_buttons'):
            self.all_nav_buttons.append(btn)
        
        # Connect to uncheck others (naive radio behavior)
        btn.toggled.connect(lambda is_checked: self._on_nav_toggled(btn, is_checked))
        return btn

    def _toggle_sidebar(self):
        current_width = self.sidebar_widget.width()
        is_expanded = current_width > 100
        
        if is_expanded:
            # Collapse Sidebar
            new_width = 60
            self.logo_label.hide()
            self.marquee_label.hide()
            self.version_label.hide()
            for lbl in self.category_labels:
                lbl.hide()
            for btn in self.all_nav_buttons:
                btn.setText(btn.property("icon_str"))
                btn.setStyleSheet("text-align: center; margin: 2px 5px;")
                btn.setToolTip(btn.property("full_text").strip())
        else:
            # Expand Sidebar
            new_width = 220
            self.logo_label.show()
            self.marquee_label.show()
            self.version_label.show()
            for lbl in self.category_labels:
                lbl.show()
            for btn in self.all_nav_buttons:
                btn.setText(btn.property("full_text"))
                # Restore original stylesheet from class rather than hardcoding here
                btn.setStyleSheet("")
                btn.setToolTip("")
                
        self.sidebar_widget.setFixedWidth(new_width)

    def _on_nav_toggled(self, clicked_btn, is_checked):
        if not is_checked: return # Ignore when becoming unchecked
        # Uncheck other sidebar buttons
        all_btns = [self.btn_dashboard, self.btn_import, self.btn_sync_aurora, self.btn_db] + self.report_buttons
        for btn in all_btns:
            if btn != clicked_btn:
                btn.blockSignals(True) # Mencegah recurse
                btn.setChecked(False)
                btn.blockSignals(False)
                
        # Emit signal to main window
        self.nav_index_requested.emit(clicked_btn)

    def refresh_data(self):
        # Dipanggil saat init atau sinkronisasi data; paksa update greeting
        self._last_greeting = None  
        self.update_time()
        
    def update_time(self): 
        now = datetime.now()
        hari_indo = {"Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu", "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"}
        bulan_indo = {"January": "Januari", "February": "Februari", "March": "Maret", "April": "April", "May": "Mei", "June": "Juni", "July": "Juli", "August": "Agustus", "September": "September", "October": "Oktober", "November": "November", "December": "Desember"}
        hari = hari_indo.get(now.strftime("%A"), now.strftime("%A"))
        bulan = bulan_indo.get(now.strftime("%B"), now.strftime("%B"))
        formatted_time = f"{hari}, {now.strftime('%d')} {bulan} {now.strftime('%Y - %H:%M:%S')}"
        self.datetime_label.setText(formatted_time)

        # Update greeting otomatis (Sore/Malam/dll) setiap jam berubah
        current_hour = now.hour
        if 5 <= current_hour < 12: greeting = "Pagi"
        elif 12 <= current_hour < 15: greeting = "Siang"
        elif 15 <= current_hour < 18: greeting = "Sore"
        else: greeting = "Malam"
        
        # Cek apakah greeting berubah untuk menghindari update GUI berlebihan setiap detik
        if not hasattr(self, '_last_greeting') or self._last_greeting != greeting:
            self._last_greeting = greeting
            config = self.parent_app.config_manager.get_config()
            site_code = config.get('site_code')
            store_name = self.parent_app.config_manager.get_store_name(site_code) if site_code else "Store"
            self.welcome_label.setText(f"Selamat {greeting}, {store_name}!")

class SalesReportTab(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self._init_ui()
        self._populate_template_combobox()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.date_filter_layout = QHBoxLayout()
        self.all_dates_radio = QRadioButton("Proses semua tanggal"); self.all_dates_radio.setChecked(True)
        self.date_filter_layout.addWidget(self.all_dates_radio)
        self.date_range_radio = QRadioButton("Proses tanggal terpilih"); self.date_filter_layout.addWidget(self.date_range_radio)
        self.start_date_edit = QDateEdit(); self.start_date_edit.setCalendarPopup(True); self.start_date_edit.setDate(QDate.currentDate()); self.start_date_edit.setEnabled(False)
        self.date_filter_layout.addWidget(QLabel("Dari:")); self.date_filter_layout.addWidget(self.start_date_edit)
        self.end_date_edit = QDateEdit(); self.end_date_edit.setCalendarPopup(True); self.end_date_edit.setDate(QDate.currentDate()); self.end_date_edit.setEnabled(False)
        self.date_filter_layout.addWidget(QLabel("Sampai:")); self.date_filter_layout.addWidget(self.end_date_edit)
        layout.addLayout(self.date_filter_layout)
        self.date_range_radio.toggled.connect(self._toggle_date_range_widgets)
        separator1 = QFrame(); separator1.setFrameShape(QFrame.HLine); separator1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator1)
        
        grid_layout = QGridLayout()
        self.main_report_section = ReportSectionWidget("Sales Report", self.parent_app, is_main_report=True)
        grid_layout.addWidget(self.main_report_section, 0, 0, 2, 1)
        self.today_mop_section = ReportSectionWidget("Sales By Date", self.parent_app, is_switchable=True)
        grid_layout.addWidget(self.today_mop_section, 0, 1)
        contribution_widget = QWidget(); contrib_vbox = QVBoxLayout(contribution_widget); contrib_vbox.setContentsMargins(0, 0, 0, 0)
        contrib_vbox.addWidget(QLabel("Kontribusi New Series"))
        self.contribution_table = QTableWidget(); self.contribution_table.setColumnCount(5)
        self.contribution_table.setHorizontalHeaderLabels(["Selected Article", "Qty Today", "Sales Today", "Qty MTD", "Sales MTD"])
        self._setup_table_properties(self.contribution_table)
        contrib_vbox.addWidget(self.contribution_table)
        grid_layout.addWidget(contribution_widget, 0, 2)
        self.dynamic_table_widget = DynamicTableWidget()
        grid_layout.addWidget(self.dynamic_table_widget, 1, 1, 1, 2)
        grid_layout.setRowStretch(0, 2); grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1); grid_layout.setColumnStretch(1, 1); grid_layout.setColumnStretch(2, 1)
        layout.addLayout(grid_layout)
        self.today_mop_section.view_combo.currentTextChanged.connect(self._on_mop_view_changed)
        
        self.buttons_layout = QHBoxLayout()
        self.open_sbd_button = QPushButton("Buka File"); self.print_button = QPushButton("Print"); self.clear_ui_button = QPushButton("Hapus Tampilan"); self.refresh_button = QPushButton("Refresh Data"); self.select_articles_button = QPushButton("Pilih Artikel New Series"); self.select_promos_button = QPushButton("Pilih Promosi")
        self.print_button.clicked.connect(lambda: self.parent_app.print_selected_report())
        for btn in [self.open_sbd_button, self.clear_ui_button, self.print_button, self.refresh_button, self.select_articles_button, self.select_promos_button]:
            btn.setFixedHeight(30); self.buttons_layout.addWidget(btn)
        layout.addLayout(self.buttons_layout)
    
    def _setup_table_properties(self, table_widget):
        table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        table_widget.setStyleSheet("font-size: 9pt;") 
        table_widget.setAlternatingRowColors(True)

    def update_contribution_table(self, contribution_mtd_df, contribution_today_df):
        self.contribution_table.setRowCount(0)
        df_mtd = pd.DataFrame(columns=[COL_ARTICLE_NAME, 'qty_mtd', 'sales_mtd'])
        if contribution_mtd_df is not None and not contribution_mtd_df.empty: df_mtd = contribution_mtd_df.rename(columns={'Quantity': 'qty_mtd', 'Net_Price': 'sales_mtd'}, errors='ignore')
        df_today = pd.DataFrame(columns=[COL_ARTICLE_NAME, 'qty_today', 'sales_today'])
        if contribution_today_df is not None and not contribution_today_df.empty: df_today = contribution_today_df.rename(columns={'Quantity': 'qty_today', 'Net_Price': 'sales_today'}, errors='ignore')
        if df_mtd.empty and df_today.empty: return
        if not df_mtd.empty and not df_today.empty: merged_df = pd.merge(df_mtd[[COL_ARTICLE_NAME, 'qty_mtd', 'sales_mtd']], df_today[[COL_ARTICLE_NAME, 'qty_today', 'sales_today']], on=COL_ARTICLE_NAME, how='outer').fillna(0)
        elif not df_mtd.empty: merged_df = df_mtd.copy(); merged_df['qty_today'] = 0; merged_df['sales_today'] = 0
        else: merged_df = df_today.copy(); merged_df['qty_mtd'] = 0; merged_df['sales_mtd'] = 0
        self.contribution_table.setRowCount(len(merged_df))
        for row_idx, row_data in merged_df.iterrows():
            full_name = str(row_data.get(COL_ARTICLE_NAME,'')); short_name = format_article_name_short(full_name)
            self.contribution_table.setItem(row_idx, 0, QTableWidgetItem(short_name))
            self.contribution_table.setItem(row_idx, 1, QTableWidgetItem(f"{int(row_data.get('qty_today', 0)):,}"))
            self.contribution_table.setItem(row_idx, 2, QTableWidgetItem(f"{int(row_data.get('sales_today', 0)):,}"))
            self.contribution_table.setItem(row_idx, 3, QTableWidgetItem(f"{int(row_data.get('qty_mtd', 0)):,}"))
            self.contribution_table.setItem(row_idx, 4, QTableWidgetItem(f"{int(row_data.get('sales_mtd', 0)):,}"))
            
    def _populate_template_combobox(self):
        try:
            # --- PERBAIKAN: Gunakan REPORT_TEMPLATE_FILE ---
            with open(REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                templates = json.load(f)
                template_names = list(templates.keys())
                self.main_report_section.template_combo.addItems(template_names)
        except Exception as e:
            logging.error(f"Gagal memuat template ke combobox: {e}")
            self.main_report_section.template_combo.addItem("Default Template")
            
    def _on_mop_view_changed(self, selected_view):
        results = self.parent_app.report_results_data
        if not results: return
        if selected_view == "Today":
            text = results.get('mop_today_text', ''); date_str = results.get('daily_used_date_str', 'N/A')
            self.today_mop_section.set_title(f"Sales By Date ({date_str})"); self.today_mop_section.text_edit.setPlainText(text)
        elif selected_view == "MTD":
            text = results.get('mop_mtd_text', ''); self.today_mop_section.set_title("Sales By Date"); self.today_mop_section.text_edit.setPlainText(text)
            
    def update_today_mop_text(self, text, report_date_str):
        self.today_mop_section.set_title(f"Sales By Date ({report_date_str})"); self.today_mop_section.text_edit.setPlainText(text)
    def _toggle_date_range_widgets(self, checked): self.start_date_edit.setEnabled(checked); self.end_date_edit.setEnabled(checked)
    def get_date_filter_settings(self): return {'all_dates': self.all_dates_radio.isChecked(), 'start_date': self.start_date_edit.date(), 'end_date': self.end_date_edit.date()}
    def update_main_report_text(self, text): self.main_report_section.text_edit.setPlainText(text)
    def append_main_report_text(self, text): self.main_report_section.text_edit.append(text)
    def get_main_report_text(self): return self.main_report_section.text_edit.toPlainText()
    def clear_all_dynamic_content(self):
        self.main_report_section.text_edit.clear(); self.today_mop_section.text_edit.clear(); self.dynamic_table_widget.table.clear()
        if hasattr(self, 'contribution_table'): self.contribution_table.setRowCount(0)
        self.all_dates_radio.setChecked(True); self.start_date_edit.setDate(QDate.currentDate()); self.end_date_edit.setDate(QDate.currentDate())
        self.dynamic_table_widget.table.setRowCount(0)

class ConfigTab(QWidget):
    def __init__(self, config_manager, parent_app):
        super().__init__()
        self.config_manager = config_manager
        self.parent_app = parent_app 
        self._init_ui()
        self.load_initial_config()

    def _init_ui(self):
        top_layout = QVBoxLayout(self); top_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget(); layout = QVBoxLayout(content_widget)

        general_group = QGroupBox("Pengaturan Umum"); general_layout = QFormLayout(general_group)
        self.site_code_input = QLineEdit(); self.store_name_label = QLabel("(Nama toko akan muncul di sini)"); self.store_name_label.setStyleSheet("font-style: italic; color: #888;")
        site_layout = QHBoxLayout(); site_layout.addWidget(self.site_code_input); site_layout.addWidget(self.store_name_label, 1)
        general_layout.addRow("Site Code:", site_layout)
        self.running_text_input = QLineEdit(); general_layout.addRow("Running Text:", self.running_text_input)
        self.template_combo = QComboBox(); general_layout.addRow("Template Laporan Default:", self.template_combo)
        layout.addWidget(general_group)
        self.g_sheet_id_input = QLineEdit(); self.g_sheet_id_input.setPlaceholderText("Masukkan ID dari URL Google Sheet Anda...")
        general_layout.addRow("Google Sheet ID:", self.g_sheet_id_input)
        self.chat_it_link_input = QLineEdit()
        self.chat_it_link_input.setPlaceholderText("Masukkan URL link chat WA/Telegram IT atau 'cerberus.klgsys.com/sso' ...")
        self.btn_fetch_chat_token = QPushButton("🔄 Ambil Token")
        self.btn_fetch_chat_token.setToolTip("Otomatis mengambil token dari cerberus.klgsys.com/sso (Membutuhkan kredensial Aurora)")
        self.btn_fetch_chat_token.clicked.connect(self._fetch_chat_token)
        
        chat_link_layout = QHBoxLayout()
        chat_link_layout.addWidget(self.chat_it_link_input)
        chat_link_layout.addWidget(self.btn_fetch_chat_token)
        general_layout.addRow("Link Chat with IT:", chat_link_layout)
        self.auto_update_checkbox = QCheckBox("Perbarui Apliakasi Otomatis di Latar Belakang (Seamless Auto-Update)")
        general_layout.addWidget(self.auto_update_checkbox)
        
        targets_group = QGroupBox("Pengaturan Target"); targets_layout = QVBoxLayout(targets_group)
        weight_layout = QGridLayout()
        self.weekday_weight_input = QLineEdit("1.0"); self.weekend_weight_input = QLineEdit("1.86")
        weight_layout.addWidget(QLabel("Bobot Weekday:"), 0, 0); weight_layout.addWidget(self.weekday_weight_input, 0, 1)
        weight_layout.addWidget(QLabel("Bobot Weekend:"), 0, 2); weight_layout.addWidget(self.weekend_weight_input, 0, 3)
        targets_layout.addLayout(weight_layout)
        self.targets_table = QTableWidget(12, 2); self.targets_table.setHorizontalHeaderLabels(["Bulan", "Target (Rp)"])
        self.targets_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.targets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        for i, month in enumerate(months):
            month_item = QTableWidgetItem(month); month_item.setFlags(month_item.flags() & ~Qt.ItemIsEditable); self.targets_table.setItem(i, 0, month_item)
        self.targets_table.setFixedHeight(300); targets_layout.addWidget(self.targets_table)
        button_layout = QHBoxLayout()
        self.btn_metric_target = QPushButton("🎯 Metrik Target Harian")
        self.import_btn = QPushButton("Impor Target..."); self.export_btn = QPushButton("Ekspor Template...")
        button_layout.addWidget(self.btn_metric_target); button_layout.addStretch(); button_layout.addWidget(self.import_btn); button_layout.addWidget(self.export_btn)
        targets_layout.addLayout(button_layout)
        breakdown_group = QGroupBox("Hasil Breakdown Target Harian (berdasarkan bulan saat ini)")
        breakdown_layout = QFormLayout(breakdown_group)
        self.target_weekday_output = QLineEdit(); self.target_weekday_output.setReadOnly(True)
        self.target_weekend_output = QLineEdit(); self.target_weekend_output.setReadOnly(True)
        breakdown_layout.addRow("Target Weekday:", self.target_weekday_output); breakdown_layout.addRow("Target Weekend:", self.target_weekend_output)
        breakdown_group.setMaximumWidth(450); targets_layout.addWidget(breakdown_group, 0, Qt.AlignCenter)
        layout.addWidget(targets_group); layout.addStretch()
        scroll_area.setWidget(content_widget); top_layout.addWidget(scroll_area)
        self.site_code_input.textChanged.connect(self.update_store_name_display)
        self.targets_table.itemChanged.connect(self.calculate_daily_targets)
        self.weekday_weight_input.textChanged.connect(self.calculate_daily_targets)
        self.weekend_weight_input.textChanged.connect(self.calculate_daily_targets)
        self.import_btn.clicked.connect(self._import_targets); self.export_btn.clicked.connect(self._export_targets)
        self.btn_metric_target.clicked.connect(self._open_metric_target_dialog)

    def _open_metric_target_dialog(self):
        from ui.dialogs import DailyMetricTargetDialog
        dialog = DailyMetricTargetDialog(self.parent_app.db_manager, self.config_manager, self)
        dialog.exec_()

    def _fetch_chat_token(self):
        url_input = self.chat_it_link_input.text().strip()
        if "cerberus.klgsys.com/sso" not in url_input:
            QMessageBox.information(self, "Info", "Input harus berisi alamat portal login SSO (misal: cerberus.klgsys.com/sso) untuk mengambil token secara otomatis.")
            return

        # Ambil kredensial
        from utils.employee_utils import EmployeeDB
        db = EmployeeDB()
        username, password = db.get_aurora_credentials()
        if not username or not password:
            QMessageBox.warning(self, "Kredensial Belum Diatur", "Harap atur kredensial Aurora pada tab Database terlebih dahulu.")
            return
            
        from PyQt5.QtWidgets import QProgressDialog
        self.fetch_progress = QProgressDialog("Memulai pencarian token...", "Batal", 0, 0, self)
        self.fetch_progress.setWindowTitle("Mendapatkan Token Chat")
        self.fetch_progress.setWindowModality(Qt.WindowModal)
        self.fetch_progress.setCancelButton(None)
        self.fetch_progress.show()

        from modules.chat_it_fetcher import ChatTokenFetcher
        self.token_fetcher = ChatTokenFetcher(username, password)
        self.token_fetcher.progress.connect(self.fetch_progress.setLabelText)
        self.token_fetcher.finished.connect(self._on_token_fetch_finished)
        self.token_fetcher.start()

    def _on_token_fetch_finished(self, success, message, token_url):
        if hasattr(self, 'fetch_progress') and self.fetch_progress:
            self.fetch_progress.close()
            self.fetch_progress = None
            
        if success and token_url:
            self.chat_it_link_input.setText(token_url)
            self.parent_app.notification_manager.show('SUCCESS', 'Token Ditemukan', 'Link lengkap telah disisipkan. Silakan simpan pengaturan.')
        else:
            QMessageBox.warning(self, "Gagal Mengambil Token", message)

    def _format_target_display(self, value_str):
        try: num_val = int(float(str(value_str).replace(",", ""))); return f"{num_val:,}"
        except (ValueError, TypeError): return str(value_str) 
    def _parse_input_text(self, text, default_val=0.0, to_type=float):
        try: return to_type(text.replace(',', ''))
        except (ValueError, TypeError): return default_val
    def _format_target_on_edit(self, text):
        if not text: return
        self.target_input.textChanged.disconnect(self._format_target_on_edit)
        original_pos = self.target_input.cursorPosition(); text_no_comma = text.replace(",", "")
        try:
            num = int(text_no_comma); formatted_text = f"{num:,}"; self.target_input.setText(formatted_text)
            diff = len(formatted_text) - len(text); new_pos = original_pos + diff
            if new_pos < 0: new_pos = 0
            if new_pos > len(formatted_text) : new_pos = len(formatted_text)
            self.target_input.setCursorPosition(new_pos)
        except ValueError: pass 
        self.target_input.textChanged.connect(self._format_target_on_edit)
    def _parse_target_from_input(self, text_value): return float(text_value.replace(",", "")) if text_value else 0.0

    def load_initial_config(self):
        self._load_templates_to_combo()
        self.reload_ui_from_config()
        config = self.config_manager.get_config()
        self.site_code_input.setText(config.get('site_code', ''))
        self.g_sheet_id_input.setText(config.get('google_sheet_id', ''))
        self.chat_it_link_input.setText(config.get('chat_it_link', ''))
        self.running_text_input.setText(config.get('running_text', ''))
        self.auto_update_checkbox.setChecked(config.get('auto_update', False))
        saved_template = config.get('default_template', "Default Template")
        index = self.template_combo.findText(saved_template, Qt.MatchFixedString)
        if index >= 0: self.template_combo.setCurrentIndex(index)
        config = self.config_manager.config
        self.weekday_weight_input.setText(config.get('DEFAULT', 'weekday_weight', fallback='1.0'))
        self.weekend_weight_input.setText(config.get('DEFAULT', 'weekend_weight', fallback='1.8604651'))
        self.targets_table.blockSignals(True)
        monthly_targets = self.config_manager.get_monthly_targets()
        for month_num in range(1, 13):
            target_value = monthly_targets.get(month_num, 0)
            item = QTableWidgetItem(f"{target_value:,.0f}")
            self.targets_table.setItem(month_num - 1, 1, item)
        self.targets_table.blockSignals(False)    
        self.update_store_name_display()
        self.calculate_daily_targets()
    
    def _load_templates_to_combo(self):
        self.template_combo.clear()
        try:
            # --- PERBAIKAN: Gunakan REPORT_TEMPLATE_FILE ---
            with open(REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                templates = json.load(f)
                template_names = list(templates.keys())
                self.template_combo.addItems(template_names)
        except Exception as e:
            logging.error(f"Gagal memuat template laporan: {e}")
            self.template_combo.addItem("Default Template")
    
    def update_store_name_display(self):
        site_code = self.site_code_input.text().strip().upper()
        store_name = self.config_manager.get_store_name(site_code)
        if store_name: self.store_name_label.setText(f"{store_name}"); self.store_name_label.setStyleSheet("font-style: bold; color: green;")
        else: self.store_name_label.setText("(Nama toko tidak ditemukan)"); self.store_name_label.setStyleSheet("font-style: italic; color: red;")
    
    def calculate_daily_targets(self):
        try:
            month_now = datetime.now().month
            target_item = self.targets_table.item(month_now - 1, 1)
            target_bulanan = float((target_item.text() or "0").replace(',', '')) if target_item else 0
            weekday_weight = float(self.weekday_weight_input.text() or "1.0"); weekend_weight = float(self.weekend_weight_input.text() or "1.86")
            now = datetime.now(); days_in_month = calendar.monthrange(now.year, now.month)[1]
            weekdays, weekends = 0, 0
            for day in range(1, days_in_month + 1):
                d = date(now.year, now.month, day)
                if d.weekday() < 5: weekdays += 1
                else: weekends += 1
            total_weight_points = (weekdays * weekday_weight) + (weekends * weekend_weight)
            value_per_point = target_bulanan / total_weight_points if total_weight_points > 0 else 0
            target_weekday = value_per_point * weekday_weight; target_weekend = value_per_point * weekend_weight
            self.target_weekday_output.setText(f"Rp {target_weekday:,.0f}"); self.target_weekend_output.setText(f"Rp {target_weekend:,.0f}")
        except (ValueError, TypeError) as e:
            self.target_weekday_output.setText("Input tidak valid"); self.target_weekend_output.setText("Input tidak valid"); logging.warning(f"Error saat kalkulasi target harian: {e}")
    
    def reload_ui_from_config(self):
        logging.info("Reloading ConfigTab UI with current settings...")
        config = self.config_manager.get_config()
        self.site_code_input.blockSignals(True); self.g_sheet_id_input.blockSignals(True); self.running_text_input.blockSignals(True); self.auto_update_checkbox.blockSignals(True)
        self.site_code_input.setText(config.get('site_code', '')); self.g_sheet_id_input.setText(config.get('google_sheet_id', '')); self.running_text_input.setText(config.get('running_text', '')); self.auto_update_checkbox.setChecked(config.get('auto_update', False))
        self.site_code_input.blockSignals(False); self.g_sheet_id_input.blockSignals(False); self.running_text_input.blockSignals(False); self.auto_update_checkbox.blockSignals(False)
        saved_template = config.get('default_template', "Default Template")
        index = self.template_combo.findText(saved_template, Qt.MatchFixedString)
        if index >= 0: self.template_combo.setCurrentIndex(index)
        self.update_store_name_display(); self.calculate_daily_targets()
    
    def save_config_action(self):
        try:
            site_code = self.site_code_input.text().strip().upper()
            running_text = self.running_text_input.text().strip()
            default_template = self.template_combo.currentText()
            weekday_weight = float(self.weekday_weight_input.text() or "1.0")
            weekend_weight = float(self.weekend_weight_input.text() or "1.8604651")
            g_sheet_id = self.g_sheet_id_input.text().strip()
            chat_it_link = self.chat_it_link_input.text().strip()
            auto_update = self.auto_update_checkbox.isChecked()

            if not site_code: QMessageBox.warning(self, "Peringatan", "Site Code tidak boleh kosong."); return False
            general_save_success = self.config_manager.update_general_config(site_code, running_text, default_template, weekday_weight, weekend_weight, g_sheet_id, chat_it_link, auto_update)
            targets_to_save = {}
            for i in range(12):
                item = self.targets_table.item(i, 1)
                value_str = item.text().replace(",", "") if item and item.text() else "0"
                targets_to_save[str(i + 1)] = int(value_str)
            targets_save_success = self.config_manager.save_monthly_targets(targets_to_save)
            return general_save_success and targets_save_success
        except Exception as e:
            logging.error(f"Error saat save_config_action: {e}"); QMessageBox.critical(self, "Error", f"Gagal memproses penyimpanan: {e}"); return False
            
    def _import_targets(self): QMessageBox.information(self, "Info", "Fungsi impor akan segera tersedia.")
    def _export_targets(self): QMessageBox.information(self, "Info", "Fungsi ekspor akan segera tersedia.")        
class EdspayedTab(QWidget): 
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        try:
            self.edspayed_content_widget = EdspayedWidget(parent_app)
            layout.addWidget(self.edspayed_content_widget)
        except NameError: 
             error_label = QLabel("Komponen Edspayed (edspayed_logic.py) tidak ditemukan atau gagal dimuat.")
             error_label.setAlignment(Qt.AlignCenter)
             layout.addWidget(error_label)
             logging.error("EdspayedWidget tidak terdefinisi. Pastikan edspayed_logic.py ada dan benar.")
        self.setLayout(layout)

# ... (Pastikan import tetap ada di bagian atas file) ...
# from utils.constants import BASE_DIR, COL_ARTICLE_NAME, COL_QUANTITY

# --- UPDATE CLASS BSCD TAB (HEADER PROPER & DARK MODE FIX) ---
class BSCDTab(QWidget):
    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        self.labels = {}
        self.bscd_data_cache = {}
        self._all_bscd_widgets = []  # Track all styled widgets for deferred polish
        
        self.targets_file = os.path.join(BASE_DIR, 'config', 'bscd_targets.json')
        
        self._init_ui()
        self.clear_view()
        self.load_targets()
        # Polishing harus dilakukan setelah stylesheet utama terpasang ke main window
        # QTimer.singleShot(0) memastikan polish delay sampai setelah event loop startup pertama
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._polish_all_bscd_labels)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Main Content Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # Bikin background scroll area agak abu sedikit (subtle gray) biar card putihnya pop up
        scroll.setObjectName("bscdScrollArea")
        
        content_container = QWidget()
        content_container.setObjectName("scroll_content")
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(10, 5, 10, 15) # Kurangi margin agar lebih padat
        content_layout.setSpacing(15) # Jarak antar card dikurangi dari 25 ke 15
        
        # ==========================================================
        # CARD 1: BALANCE SCORE CARD DAILY (ATAS)
        # ==========================================================
        card1 = QFrame()
        card1.setObjectName("bscdCard1")
        # Jika QT versi baru support shadow, sebaiknya pakai QGraphicsDropShadowEffect, 
        # tapi untuk kesederhanaan, border abu muda dipadu background beda udah cukup modern.
        effect1 = QGraphicsDropShadowEffect()
        effect1.setBlurRadius(15)
        effect1.setColor(QColor(0, 0, 0, 15))
        effect1.setOffset(0, 2)
        card1.setGraphicsEffect(effect1)
        
        card1_layout = QVBoxLayout(card1)
        card1_layout.setContentsMargins(15, 15, 15, 15) # Lebih compact
        card1_layout.setSpacing(10)

        title_label = QLabel("BALANCE SCORE CARD DAILY")
        title_label.setObjectName("bscdTitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        card1_layout.addWidget(title_label)

        # Kontainer Grid (bungkus pake widget untuk border tabel internal)
        grid_container = QWidget()
        grid_container.setObjectName("bscdGridContainer")
        
        grid = QGridLayout(grid_container)
        grid.setSpacing(0)
        card1_layout.addWidget(grid_container)
        
        # Header Statis
        grid.addWidget(self._create_static_header("TARGET", align=Qt.AlignLeft), 0, 0)
        grid.addWidget(self._create_static_header("BSCD BU", align=Qt.AlignLeft), 1, 0)
        
        # Comparison row: static subheaders for all columns
        single_row_headers = {"Comparison": 0, "TW": 1, "LW": 2, "LM": 3}
        for text, c in single_row_headers.items():
            grid.addWidget(self._create_static_header(text, is_subheader=True), 2, c, 1, 1)

        merged_headers = {"% LW": 4, "% LM": 5, "MTD": 6}
        for text, c in merged_headers.items():
            grid.addWidget(self._create_static_header(text, is_subheader=True), 2, c, 3, 1)

        grid.addWidget(self._create_static_header("DATE", align=Qt.AlignLeft), 3, 0)
        grid.addWidget(self._create_static_header("DAY", align=Qt.AlignLeft), 4, 0)

        # --- TW DatePicker on DATE row (editable/backdate) ---
        self.tw_date_edit = QDateEdit()
        self.tw_date_edit.setDisplayFormat("dd.MMM.yyyy")
        self.tw_date_edit.setCalendarPopup(True)
        self.tw_date_edit.setProperty("bscd_cell", True)
        self.tw_date_edit.setAlignment(Qt.AlignCenter)
        self.tw_date_edit.setDate(QDate.currentDate())
        self.tw_date_edit.dateChanged.connect(self._on_tw_date_changed)
        self._all_bscd_widgets.append(self.tw_date_edit)  # Track for deferred polish
        grid.addWidget(self.tw_date_edit, 3, 1, 1, 1)

        row_headers_text = ["NET SALES", "TC", "AC", "LARGE", "TOPING", "OUAST"]
        for r, text in enumerate(row_headers_text):
            grid.addWidget(self._create_static_header(text, align=Qt.AlignLeft), r + 5, 0)

        # Labels Data (date_tw is now replaced by tw_date_edit above)
        self.labels = {}
        key_positions = {
            'target_sales': (0, 1, 1, 3), 'target_other': (0, 4, 1, 3), 
            'bscd_bu_value': (1, 1, 1, 6),
            'date_lw': (3, 2), 'date_lm': (3, 3),
            'day_tw': (4, 1), 'day_lw': (4, 2), 'day_lm': (4, 3),
        }
        start_row = 5
        for i, metric in enumerate(['netsales', 'tc', 'ac', 'large', 'topping', 'ouast_sales']):
            for j, period in enumerate(['_tw', '_lw', '_lm', '_lw_growth', '_lm_growth', '_mtd']):
                key = f"{metric}{period}"; key_positions[key] = (start_row + i, j + 1)
        
        for key, pos in key_positions.items():
            label = QLabel(); label.setProperty("bscd_cell", True)
            if 'growth' in key: label.setAlignment(Qt.AlignCenter)
            else: label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.labels[key] = label
            grid.addWidget(label, *pos)
        
        # Tombol Manual Input
        self.lw_manual_button = QPushButton("Input Manual"); self.lw_manual_button.setVisible(False)
        self.lm_manual_button = QPushButton("Input Manual"); self.lm_manual_button.setVisible(False)
        self.lw_manual_button.clicked.connect(lambda: self.on_manual_input_clicked('lw'))
        self.lm_manual_button.clicked.connect(lambda: self.on_manual_input_clicked('lm'))
        
        last_metric_row = start_row + len(['netsales', 'tc', 'ac', 'large', 'toping', 'ouast'])
        grid.addWidget(self.lw_manual_button, last_metric_row, 2, Qt.AlignTop)
        grid.addWidget(self.lm_manual_button, last_metric_row, 3, Qt.AlignTop)
        
        self.labels['bscd_bu_value'].setAlignment(Qt.AlignCenter)
        for key in ['date_tw', 'date_lw', 'date_lm', 'day_tw', 'day_lw', 'day_lm']:
            if key in self.labels: self.labels[key].setAlignment(Qt.AlignCenter)

        # Masukkan Card 1 ke layout utama
        content_layout.addWidget(card1)

        # ==========================================================
        # CARD 2: UPSELLING & PROMO TRACKING (BAWAH)
        # ==========================================================
        card2 = QFrame()
        card2.setObjectName("bscdCard2")
        effect2 = QGraphicsDropShadowEffect()
        effect2.setBlurRadius(15)
        effect2.setColor(QColor(0, 0, 0, 15))
        effect2.setOffset(0, 2)
        card2.setGraphicsEffect(effect2)
        
        card2_layout = QVBoxLayout(card2)
        card2_layout.setContentsMargins(15, 15, 15, 15) # Compact
        card2_layout.setSpacing(10)

        lbl_bottom = QLabel("UPSELLING & PROMO TRACKING")
        lbl_bottom.setObjectName("bscdUpsellingLabel")
        card2_layout.addWidget(lbl_bottom)

        # Container Split Horizontal (50:50)
        split_container = QWidget()
        split_container.setStyleSheet("border: none;") # Hilangkan border warisan dari card
        split_layout = QHBoxLayout(split_container)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(20) 
        
        # --- PERBAIKAN HEADER TEKS ---
        # 1. Tabel Input Target
        self.promo_table = QTableWidget()
        self.promo_table.setColumnCount(6)
        self.promo_table.setHorizontalHeaderLabels([
            "Item / Promo Name", 
            "Target\n(Opening)", "Target\n(Closing)", 
            "Actual\n(Opening)", "Actual\n(Closing)",
            "" # Kolom tombol hapus (kosong judulnya)
        ])
        
        # --- STYLING TABLE (WRAP HEADER & COMPACT) ---
        self.promo_table.verticalHeader().setVisible(False)
        self.promo_table.verticalHeader().setDefaultSectionSize(32) # Tinggi baris direndahkan lagi
        
        self.promo_table.setFrameShape(QFrame.NoFrame)
        self.promo_table.setShowGrid(True)
        self.promo_table.setObjectName("bscdPromoTable")
        
        self.promo_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        # --- PENGATURAN KOLOM ---
        header = self.promo_table.horizontalHeader()
        
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setFixedHeight(50)  # Cukup tinggi untuk 2-baris teks header
        
        # Atur Lebar Kolom
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Kolom Nama: Stretch
        for i in range(1, 5):
            header.setSectionResizeMode(i, QHeaderView.Fixed)  # Kolom Angka: Fixed
            self.promo_table.setColumnWidth(i, 70)  # Sedikit lebih kecil agar tidak penuh
            
        # Kolom Hapus: narrow biar proporsional
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.promo_table.setColumnWidth(5, 36)
            
        self.promo_table.setRowCount(10)
        
        # Init Tombol Hapus untuk baris awal
        self._add_delete_buttons_to_all_rows()
        
        self.promo_table.itemChanged.connect(self._on_promo_item_changed)
        
        split_layout.addWidget(self.promo_table, 1)

        tips_container = QGroupBox("💡 Tips ")
        tips_container.setObjectName("bscdTipsContainer")
        tips_layout = QVBoxLayout(tips_container)
        tips_layout.setContentsMargins(15, 20, 15, 15)
        
        tips_text = QLabel(
            "<span style='color:#BDC3C7;'>"
            "• Gunakan <b>keyword</b> untuk mengisi data otomatis, cth:<br>"
            "&nbsp;&nbsp;&nbsp;- <b>large</b> / <b>regular</b> / <b>small</b><br>"
            "&nbsp;&nbsp;&nbsp;- <b>topping</b> / <b>toping</b><br>"
            "&nbsp;&nbsp;&nbsp;- <b>TC</b> / <b>Food</b> / <b>Merch</b><br><br>"
            "• Kata apapun yang dicari <b>tidak <i>case sensitive</i></b>.<br><br>"
            "• Gunakan tombol <b><span style='color:#ef4444;'>×</span></b> untuk menghapus baris."
            "</span>"
        )
        tips_text.setWordWrap(True)
        tips_text.setStyleSheet("font-size: 10pt; line-height: 1.5;")
        tips_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        tips_layout.addWidget(tips_text)
        tips_layout.addStretch() # Dorong teks ke atas
        
        split_layout.addWidget(tips_container, 1) # Tips (50%)
        
        # --- BSCD AI BUSINESS REVIEW CARD ---
        self.business_review_card = QFrame()
        self.business_review_card.setObjectName("bscdBusinessReviewCard")
        effect_br = QGraphicsDropShadowEffect()
        effect_br.setBlurRadius(15)
        effect_br.setColor(QColor(0, 0, 0, 15))
        effect_br.setOffset(0, 2)
        self.business_review_card.setGraphicsEffect(effect_br)
        
        br_layout = QVBoxLayout(self.business_review_card)
        br_layout.setContentsMargins(15, 15, 15, 15)
        br_layout.setSpacing(10)

        lbl_br_title = QLabel("BUSINESS REVIEW")
        lbl_br_title.setObjectName("bscdBusinessReviewTitle")
        br_layout.addWidget(lbl_br_title)

        self.business_review_text = QTextEdit()
        self.business_review_text.setReadOnly(True)
        self.business_review_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.business_review_text.setObjectName("bscdBusinessReviewText")
        self.business_review_text.setMinimumHeight(100)
        br_layout.addWidget(self.business_review_text)
        
        # Tambahkan Card 2 dan Business Review Card ke Content Layout
        card2_layout.addWidget(split_container)
        content_layout.addWidget(card2)
        content_layout.addWidget(self.business_review_card)
        content_layout.addStretch() # Padding bawah ekstra
        
        scroll.setWidget(content_container)
        main_layout.addWidget(scroll)
        
    def save_shift1_actuals(self, report_results_data):
        """
        Otomatis mengisi kolom 'Actual Shift 1' berdasarkan data report saat ini.
        Dipanggil jika user mencentang 'Tandai Shift 1' saat upload.
        """
        day_trx = report_results_data.get('day_trx')
        if day_trx is None or day_trx.empty:
            logging.warning("Gagal simpan Shift 1: Data transaksi kosong.")
            return

        special_keywords = {
            'topping': 'day_qty_topping', 'toping': 'day_qty_topping',
            'large': 'day_qty_large', 'regular': 'day_qty_regular',
            'small': 'day_qty_small', 'tc': 'day_tc',
            'food': 'day_qty_foods', 'foods': 'day_qty_foods',
            'merch': 'day_qty_merch'
        }

        # Iterasi setiap baris di tabel promo
        self.promo_table.blockSignals(True) # Matikan sinyal agar tidak loop recalculate
        try:
            for row in range(self.promo_table.rowCount()):
                name_item = self.promo_table.item(row, 0)
                if not name_item or not name_item.text().strip():
                    continue

                item_name = name_item.text().strip().lower()
                calculated_qty = 0

                # 1. Hitung Qty berdasarkan nama item
                if item_name in special_keywords:
                    key_data = special_keywords[item_name]
                    calculated_qty = report_results_data.get(key_data, 0)
                else:
                    col_name = COL_ARTICLE_NAME # Pastikan konstanta ini ada/diimport
                    matches = day_trx[day_trx[col_name].str.lower().str.contains(item_name, na=False)]
                    if not matches.empty:
                        calculated_qty = matches[COL_QUANTITY].sum()

                # 1b. Ambil Target Dynamic
                target_map = {
                    'large': 'target_large', 'topping': 'target_topping', 'toping': 'target_topping',
                    'tc': 'target_tc', 'spunbond': 'target_spunbond', 'food': 'target_ouast', 'foods': 'target_ouast',
                    'ouast': 'target_ouast', 'sc': 'target_sc'
                }
                target_qty = 0
                if item_name in target_map:
                    target_key = target_map[item_name]
                    target_qty = report_results_data.get(target_key, 0)
                
                split_items = ['large', 'topping', 'toping', 'spunbond']
                is_permanent = item_name in split_items
                current_t_open = self.promo_table.item(row, 1)
                
                if is_permanent or (target_qty > 0 and (not current_t_open or not current_t_open.text().strip())):
                    if is_permanent:
                        t_open_val = int(target_qty * 0.4)
                        t_close_val = int(target_qty * 0.6)
                    else:
                        t_open_val = int(target_qty)
                        t_close_val = int(target_qty)
                        
                    t_open_item = QTableWidgetItem(f"{t_open_val:,}")
                    t_close_item = QTableWidgetItem(f"{t_close_val:,}")
                    
                    if is_permanent:
                        t_open_item.setFlags(t_open_item.flags() & ~Qt.ItemIsEditable)
                        t_close_item.setFlags(t_close_item.flags() & ~Qt.ItemIsEditable)
                        
                    self.promo_table.setItem(row, 1, t_open_item)
                    self.promo_table.setItem(row, 2, t_close_item)


                # 2. Masukkan ke Kolom Actual Shift 1 (Index 3)
                qty_str = f"{int(calculated_qty):,}"
                cell_item_shift1 = QTableWidgetItem(qty_str)
                cell_item_shift1.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
                
                font = QFont(); font.setBold(True)
                cell_item_shift1.setFont(font); cell_item_shift1.setTextAlignment(Qt.AlignCenter)
                cell_item_shift1.setBackground(QColor("#e8f5e9")) 
                cell_item_shift1.setForeground(QColor("#1b5e20")) 
                
                self.promo_table.setItem(row, 3, cell_item_shift1)
                
                # 3. Hitung ulang Shift 2 (karena Shift 1 berubah, dan Shift 2 = Total - Shift 1)
                # Saat ini Total = Shift 1 (karena file yg diupload adalah file shift 1)
                # Jadi Shift 2 akan jadi 0, yang mana LOGIS saat overhand.
                cell_item_shift2 = QTableWidgetItem("0")
                cell_item_shift2.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
                cell_item_shift2.setFont(font); cell_item_shift2.setTextAlignment(Qt.AlignCenter)
                cell_item_shift2.setBackground(QColor("#e8f5e9")) 
                cell_item_shift2.setForeground(QColor("#1b5e20")) 
                
                self.promo_table.setItem(row, 4, cell_item_shift2) 

            # 4. Simpan ke JSON
            self.save_targets()
            
        except Exception as e:
            logging.error(f"Error saving Shift 1 actuals: {e}")
        finally:
            self.promo_table.blockSignals(False)

    def _create_static_header(self, text, is_subheader=False, align=Qt.AlignCenter):
        label = QLabel(text)
        label.setProperty("bscd_cell", True)  # Keep property for QSS border/padding
        if is_subheader:
            label.setProperty("bscd_subheader", True)
            # Direct inline style so colors appear on first load regardless of QSS timing
            label.setStyleSheet(
                "background-color: #34688f; color: #ffffff; font-weight: bold;"
                "border: 1px solid #2b5a7c; padding: 5px 8px; font-size: 9pt;"
            )
        else:
            label.setProperty("bscd_header", True)
            label.setStyleSheet(
                "background-color: #2b3e50; color: #ffffff; font-weight: bold;"
                "border: 1px solid #1e2d3d; padding: 5px 8px; font-size: 9pt;"
            )
        label.setAlignment(align)
        self._all_bscd_widgets.append(label)
        return label
    def _polish_all_bscd_labels(self):
        """Polish semua widget BSCD setelah stylesheet utama terpasang.
        
        Widget yang dibuat sebelum setStyleSheet() main window tidak otomatis
        mendapatkan style dari property-based QSS (bscd_header, bscd_cell, dll.)
        Polishing eksplisit memaksa Qt me-re-evaluate dan menerapkan style.
        """
        # Polish header/cell labels (statis) yang dibuat di _init_ui
        for widget in self._all_bscd_widgets:
            try:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
            except Exception:
                pass
        
        # Polish juga semua data cell labels
        for label in self.labels.values():
            try:
                label.style().unpolish(label)
                label.style().polish(label)
                label.update()
            except Exception:
                pass

    def apply_bscd_theme(self, is_dark=False):
        """Update inline styles pada header labels saat tema berubah.
        Diperlukan karena inline setStyleSheet() tidak di-override oleh QSS.
        """
        if is_dark:
            header_style = (
                "background-color: #1e2d3d; color: #e0e8f0; font-weight: bold;"
                "border: 1px solid #0d1b26; padding: 5px 8px; font-size: 9pt;"
            )
            subheader_style = (
                "background-color: #1a4a6b; color: #e0f0ff; font-weight: bold;"
                "border: 1px solid #133d5a; padding: 5px 8px; font-size: 9pt;"
            )
        else:
            header_style = (
                "background-color: #2b3e50; color: #ffffff; font-weight: bold;"
                "border: 1px solid #1e2d3d; padding: 5px 8px; font-size: 9pt;"
            )
            subheader_style = (
                "background-color: #34688f; color: #ffffff; font-weight: bold;"
                "border: 1px solid #2b5a7c; padding: 5px 8px; font-size: 9pt;"
            )

        for widget in self._all_bscd_widgets:
            try:
                prop = widget.property("bscd_subheader")
                if prop is True or prop == "true":
                    widget.setStyleSheet(subheader_style)
                elif widget.property("bscd_header") is True or widget.property("bscd_header") == "true":
                    widget.setStyleSheet(header_style)
                widget.update()
            except Exception:
                pass
        # Re-polish growth labels so QSS positive/negative colors also re-apply
        for label in self.labels.values():
            try:
                label.style().unpolish(label)
                label.style().polish(label)
                label.update()
            except Exception:
                pass

    # --- FITUR TOMBOL HAPUS ---
    def _add_delete_buttons_to_all_rows(self):
        """Menambahkan tombol hapus di kolom terakhir untuk semua baris."""
        permanent_items = ["Large", "Topping", "Spunbond"]
        
        self.promo_table.blockSignals(True)
        for row in range(self.promo_table.rowCount()):
            if row < 3:
                name_item = QTableWidgetItem(permanent_items[row])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                font = QFont(); font.setBold(True); name_item.setFont(font)
                self.promo_table.setItem(row, 0, name_item)
                container = QWidget()
                self.promo_table.setCellWidget(row, 5, container)
            else:
                self._add_delete_button(row)
        self.promo_table.blockSignals(False)

    def _add_delete_button(self, row):
        """Menambahkan tombol hapus (X) ke baris tertentu."""
        if self.promo_table.cellWidget(row, 5): return

        del_btn = QPushButton("×")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #c0392b;
                border-radius: 10px;
                font-weight: bold;
                font-size: 9pt;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #c0392b;
                color: #ffffff;
            }
        """)
        del_btn.setToolTip("Hapus Baris Ini")
        
        del_btn.clicked.connect(self._delete_row)
        
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(del_btn)
        
        self.promo_table.setCellWidget(row, 5, container)

    def _delete_row(self):
        """Menghapus baris saat tombol X diklik."""
        sender_btn = self.sender()
        if not sender_btn: return
        
        # Cari posisi tombol di tabel
        # Tombol ada di dalam container, jadi parent().parent() adalah cell widget?
        # Cara paling aman: iterasi semua cell widget
        row_to_delete = -1
        for r in range(self.promo_table.rowCount()):
            container = self.promo_table.cellWidget(r, 5)
            if container:
                # Cari tombol di dalam layout container
                btn = container.findChild(QPushButton)
                if btn == sender_btn:
                    row_to_delete = r
                    break
        
        if row_to_delete != -1:
            if row_to_delete < 3: return # Prevent deleting permanent row
            # Konfirmasi hapus hanya jika baris ada isinya
            item = self.promo_table.item(row_to_delete, 0)
            if item and item.text().strip():
                reply = QMessageBox.question(self, "Hapus", "Hapus baris ini?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No: return

            self.promo_table.removeRow(row_to_delete)
            self.save_targets() # Simpan perubahan
            
            # Jika tabel jadi kosong atau terlalu sedikit, tambah baris kosong di bawah
            if self.promo_table.rowCount() < 5:
                self.promo_table.insertRow(self.promo_table.rowCount())
                self._add_delete_button(self.promo_table.rowCount() - 1)

    # --- FITUR SIMPAN & MUAT ---
    def load_targets(self):
        if not os.path.exists(self.targets_file): return
        try:
            with open(self.targets_file, 'r') as f: data = json.load(f)
            
            data_map = {}
            for item in data:
                name_key = item.get("name", "").strip().lower()
                if name_key == 'toping': name_key = 'topping'
                if name_key: data_map[name_key] = item
                
            permanent_items = ["Large", "Topping", "Spunbond"]
            permanent_names = [p.lower() for p in permanent_items]
            other_data = [item for item in data if item.get("name", "").lower() not in permanent_names and item.get("name", "").lower() != 'toping']
            
            total_rows_needed = 3 + len(other_data) + 2
            if total_rows_needed > self.promo_table.rowCount(): 
                self.promo_table.setRowCount(total_rows_needed)
                
            self.promo_table.blockSignals(True) 
            
            for row, p_name in enumerate(permanent_items):
                name_item = QTableWidgetItem(p_name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable) 
                font = QFont(); font.setBold(True); name_item.setFont(font)
                self.promo_table.setItem(row, 0, name_item)
                
                existing = data_map.get(p_name.lower(), {})
                self.promo_table.setItem(row, 1, QTableWidgetItem(existing.get("target_open", "")))
                self.promo_table.setItem(row, 2, QTableWidgetItem(existing.get("target_close", "")))
                
                actual_open_val = existing.get("actual_open", "")
                if actual_open_val:
                    cell_item = QTableWidgetItem(actual_open_val)
                    cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
                    font = QFont(); font.setBold(True); cell_item.setFont(font); cell_item.setTextAlignment(Qt.AlignCenter)
                    cell_item.setBackground(QColor("#e8f5e9")); cell_item.setForeground(QColor("#1b5e20")) 
                    self.promo_table.setItem(row, 3, cell_item)
                
            current_row = 3
            for item in other_data:
                self.promo_table.setItem(current_row, 0, QTableWidgetItem(item.get("name", "")))
                self.promo_table.setItem(current_row, 1, QTableWidgetItem(item.get("target_open", "")))
                self.promo_table.setItem(current_row, 2, QTableWidgetItem(item.get("target_close", "")))
                
                actual_open_val = item.get("actual_open", "")
                if actual_open_val:
                    cell_item = QTableWidgetItem(actual_open_val)
                    cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
                    font = QFont(); font.setBold(True); cell_item.setFont(font); cell_item.setTextAlignment(Qt.AlignCenter)
                    cell_item.setBackground(QColor("#e8f5e9")); cell_item.setForeground(QColor("#1b5e20")) 
                    self.promo_table.setItem(current_row, 3, cell_item)
                current_row += 1
                
            for r in range(self.promo_table.rowCount()):
                if r < 3:
                     container = QWidget()
                     self.promo_table.setCellWidget(r, 5, container)
                else:
                     self._add_delete_button(r)

            self.promo_table.blockSignals(False)
        except Exception as e: logging.error(f"Gagal memuat BSCD targets: {e}")

    def save_targets(self):
        data = []
        for row in range(self.promo_table.rowCount()):
            name_item = self.promo_table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            if name: 
                t_open_item = self.promo_table.item(row, 1)
                t_close_item = self.promo_table.item(row, 2)
                a_open_item = self.promo_table.item(row, 3)
                data.append({
                    "name": name,
                    "target_open": t_open_item.text().strip() if t_open_item else "",
                    "target_close": t_close_item.text().strip() if t_close_item else "",
                    "actual_open": a_open_item.text().strip() if a_open_item else ""
                })
        try:
            os.makedirs(os.path.dirname(self.targets_file), exist_ok=True)
            with open(self.targets_file, 'w') as f: json.dump(data, f, indent=4)
        except Exception as e: logging.error(f"Gagal menyimpan BSCD targets: {e}")

    def _on_promo_item_changed(self, item):
        self.promo_table.blockSignals(True)
        try:
            row = item.row(); col = item.column()
            if col == 0:
                item_name = item.text().strip().lower()
                actual_qty = 0
                
                special_keywords = {'topping': 'day_qty_topping', 'toping': 'day_qty_topping', 'large': 'day_qty_large', 'regular': 'day_qty_regular', 'small': 'day_qty_small', 'tc': 'day_tc', 'food': 'day_qty_foods', 'foods': 'day_qty_foods', 'merch': 'day_qty_merch'}

                if self.parent_app and hasattr(self.parent_app, 'report_results_data'):
                    report_data = self.parent_app.report_results_data
                    if item_name in special_keywords:
                        key_data = special_keywords[item_name]
                        actual_qty = report_data.get(key_data, 0)
                    else:
                        day_trx = report_data.get('day_trx')
                        if day_trx is not None and not day_trx.empty:
                            col_name = COL_ARTICLE_NAME
                            matches = day_trx[day_trx[col_name].str.lower().str.contains(item_name, na=False)]
                            if not matches.empty: actual_qty = matches[COL_QUANTITY].sum()
                
                # --- AUTO-FILL DYNAMIC TARGETS ---
                target_qty = 0
                if self.parent_app and hasattr(self.parent_app, 'report_results_data'):
                    report_data = self.parent_app.report_results_data
                    target_map = {
                        'large': 'target_large', 'topping': 'target_topping', 'toping': 'target_topping',
                        'tc': 'target_tc', 'spunbond': 'target_spunbond', 'food': 'target_ouast', 'foods': 'target_ouast',
                        'ouast': 'target_ouast', 'sc': 'target_sc'
                    }
                    if item_name in target_map:
                        target_key = target_map[item_name]
                        target_qty = report_data.get(target_key, 0)
                
                split_items = ['large', 'topping', 'toping', 'spunbond']
                is_permanent = item_name in split_items
                current_t_open = self.promo_table.item(row, 1)
                
                if is_permanent or (target_qty > 0 and (not current_t_open or not current_t_open.text().strip())):
                    if is_permanent:
                        t_open_val = int(target_qty * 0.4)
                        t_close_val = int(target_qty * 0.6)
                    else:
                        t_open_val = int(target_qty)
                        t_close_val = int(target_qty)
                        
                    t_open_item = QTableWidgetItem(f"{t_open_val:,}")
                    t_close_item = QTableWidgetItem(f"{t_close_val:,}")
                    
                    if is_permanent:
                        t_open_item.setFlags(t_open_item.flags() & ~Qt.ItemIsEditable)
                        t_close_item.setFlags(t_close_item.flags() & ~Qt.ItemIsEditable)
                        
                    self.promo_table.setItem(row, 1, t_open_item)
                    self.promo_table.setItem(row, 2, t_close_item)

                qty_str = f"{int(actual_qty):,}"
                
                # Baca Actual Opening (Shift 1) dari kolom 3
                shift1_item = self.promo_table.item(row, 3)
                shift1_qty = 0
                if shift1_item and shift1_item.text().strip():
                    try:
                        shift1_qty = int(shift1_item.text().replace(',', ''))
                    except ValueError:
                        pass
                
                # Shift 2 (Closing) = Total Harian (actual_qty) - Shift 1 (Opening)
                shift2_qty = actual_qty - shift1_qty
                if shift2_qty < 0:
                     shift2_qty = 0
                     
                shift2_qty_str = f"{int(shift2_qty):,}"
                
                # Update UI: Actual Closing (Shift 2) di Kolom 4
                # (Kolom 3 tidak di-overwrite agar Shift 1 dipertahankan)
                cell_item = QTableWidgetItem(shift2_qty_str)
                cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
                
                font = QFont(); font.setBold(True)
                cell_item.setFont(font); cell_item.setTextAlignment(Qt.AlignCenter)
                
                # Beri warna background Hijau Muda yang spesifik
                cell_item.setBackground(QColor("#e8f5e9")) 
                # Paksa warna teks Hitam agar kontras dengan hijau muda
                cell_item.setForeground(QColor("#1b5e20")) 
                
                self.promo_table.setItem(row, 4, cell_item)
            
            if col in [0, 1, 2, 3]: self.save_targets()
                
        except Exception as e: logging.error(f"Error updating promo table: {e}")
        finally: self.promo_table.blockSignals(False)

    def on_manual_input_clicked(self, period_key):
        from ui.dialogs import BSCDManualInputDialog
        period_name = "Minggu Lalu (LW)" if period_key == 'lw' else "Bulan Lalu (LM)"
        dialog = BSCDManualInputDialog(period_name, self)
        if dialog.exec_() == QDialog.Accepted:
            manual_data = dialog.get_data()
            self.bscd_data_cache[f'data_{period_key}'] = manual_data
            self._populate_and_recalculate_view()

    def _on_tw_date_changed(self, new_date):
        """Handle when the user changes the TW backdate"""
        # --- Update dates in UI immediately for better feedback ---
        py_date = new_date.toPyDate()
        date_lw = py_date - timedelta(days=7)
        date_lm = py_date - timedelta(days=28)
        
        indonesian_days = {
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        }
        
        self.labels['day_tw'].setText(indonesian_days.get(py_date.strftime('%A'), py_date.strftime('%A')))
        self.labels['date_lw'].setText(date_lw.strftime('%d.%b.%Y'))
        self.labels['day_lw'].setText(indonesian_days.get(date_lw.strftime('%A'), date_lw.strftime('%A')))
        self.labels['date_lm'].setText(date_lm.strftime('%d.%b.%Y'))
        self.labels['day_lm'].setText(indonesian_days.get(date_lm.strftime('%A'), date_lm.strftime('%A')))
        
        # --- Trigger backend recalculation ---
        self.setProperty("tw_backdate", new_date.toString("yyyy-MM-dd"))
        if hasattr(self, 'parent_app') and self.parent_app:
            try:
                self.parent_app.bscd_tw_custom_date = py_date
                if hasattr(self.parent_app, '_recalculate_bscd_only'):
                    self.parent_app._recalculate_bscd_only()
            except Exception as e:
                logging.error(f"Failed to recalculate BSCD for new TW date: {e}")

    def update_view(self, data):
        if not data: self.clear_view(); return
        self.bscd_data_cache = data
        self._populate_and_recalculate_view()
        
        self.promo_table.blockSignals(True)
        for row in range(self.promo_table.rowCount()):
            item_name_widget = self.promo_table.item(row, 0)
            if item_name_widget and item_name_widget.text().strip():
                self.promo_table.blockSignals(False)
                self._on_promo_item_changed(item_name_widget)
                self.promo_table.blockSignals(True)
        self.promo_table.blockSignals(False)

    def update_data(self, data):
        """Called by main_app when a new calculation happens so promo tracking also updates."""
        if not data: return
        self.promo_table.blockSignals(True)
        try:
            for row in range(self.promo_table.rowCount()):
                item_name_widget = self.promo_table.item(row, 0)
                if item_name_widget and item_name_widget.text().strip():
                    self._on_promo_item_changed(item_name_widget)
                    
            # --- Update AI Business Review Text ---
            if hasattr(self, 'business_review_text'):
                analysis_text = data.get('auto_analysis_text', '')
                if analysis_text:
                    self.business_review_text.setPlainText(analysis_text)
                else:
                    self.business_review_text.setPlainText("Belum ada analisa otomatis untuk data ini.")
                    
        except Exception as e:
            logging.error(f"Error in BSCDTab update_data: {e}")
        finally:
            self.promo_table.blockSignals(False)

    def _populate_and_recalculate_view(self):
        data = self.bscd_data_cache
        if not data: return
        data_tw_raw, data_lw_raw, data_lm_raw = data.get('data_tw'), data.get('data_lw'), data.get('data_lm')
        mtd_metrics, targets = data.get('mtd_metrics', {}), data.get('targets', {})
        self.lw_manual_button.setVisible(data_lw_raw is None); self.lm_manual_button.setVisible(data_lm_raw is None)
            
        def process_period_data(source_data):
            if source_data is None: return {m: 0 for m in ['net_sales','tc','large_cups','toping','ouast_sales','ac']}
            p = {}; 
            for k, v in source_data.items():
                try: p[k] = float(v)
                except (ValueError, TypeError): p[k] = v
            p['ac'] = calculate_ac(p.get('net_sales',0), p.get('tc',0)); return p
        tw, lw, lm = process_period_data(data_tw_raw), process_period_data(data_lw_raw), process_period_data(data_lm_raw)
        def calculate_growth_metrics(c, p):
            g = {}; metrics = ['net_sales','tc','ac','large_cups','toping','ouast_sales']
            for m in metrics: g[m] = calculate_growth(c.get(m, 0), p.get(m, 0))
            return g
        lw_growth, lm_growth = calculate_growth_metrics(tw, lw), calculate_growth_metrics(tw, lm)
        
        def format_int(v):
            if isinstance(v, (int, float, np.integer, np.floating)): return f"{int(v):,}"
            try: return f"{int(float(v)):,}"
            except: return "N/A"
        def format_pct(v): return f"{v:.0%}" if v is not None else "N/A"
        
        site_code = data.get('site_code', 'N/A'); store_name = data.get('store_name', 'Toko Tidak Ditemukan')
        self.labels['target_sales'].setText(format_int(targets.get('sales'))); self.labels['target_other'].setText(format_int(targets.get('other'))); self.labels['bscd_bu_value'].setText(f"{site_code} - {store_name}")
        indonesian_days = {
            'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
            'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
        }
        # Set dates: TW goes to date picker, LW/LM go to labels
        date_tw_val = data.get('date_tw')
        if date_tw_val:
            self.tw_date_edit.blockSignals(True)
            self.tw_date_edit.setDate(QDate(date_tw_val.year, date_tw_val.month, date_tw_val.day))
            self.tw_date_edit.blockSignals(False)
            self.labels['day_tw'].setText(indonesian_days.get(date_tw_val.strftime('%A'), date_tw_val.strftime('%A')))
        else:
            self.labels['day_tw'].setText('N/A')
        for p in ['lw', 'lm']:
            d = data.get(f'date_{p}')
            self.labels[f'date_{p}'].setText(d.strftime('%d.%b.%Y') if d else 'N/A')
            self.labels[f'day_{p}'].setText(indonesian_days.get(d.strftime('%A'), d.strftime('%A')) if d else 'N/A')
        
        metrics_map = {'netsales':'net_sales','tc':'tc','ac':'ac','large':'large_cups','topping':'toping','ouast_sales':'ouast_sales'}
        for ui_k, data_k in metrics_map.items():
            self.labels[f'{ui_k}_tw'].setText(format_int(tw.get(data_k,0))); self.labels[f'{ui_k}_lw'].setText(format_int(lw.get(data_k,0))); self.labels[f'{ui_k}_lm'].setText(format_int(lm.get(data_k,0)))
            self.labels[f'{ui_k}_lw_growth'].setText(format_pct(lw_growth.get(data_k))); self.labels[f'{ui_k}_lm_growth'].setText(format_pct(lm_growth.get(data_k)))
            
            mtd_value = 0 
            if ui_k == 'topping': mtd_value = mtd_metrics.get('toping_mtd', 0)
            elif ui_k == 'ouast_sales': mtd_value = mtd_metrics.get('ouast_mtd', 0)
            else: mtd_value = mtd_metrics.get(f'{ui_k}_mtd', 0)
            self.labels[f'{ui_k}_mtd'].setText(format_int(mtd_value))
               
            for p_key, g_data in [('_lw_growth',lw_growth),('_lm_growth',lm_growth)]:
                g_val, lbl_w = g_data.get(data_k), self.labels[f'{ui_k}{p_key}']
                lbl_w.setProperty("bscd_growth","none");
                if isinstance(g_val,(int,float)): lbl_w.setProperty("bscd_growth","positive" if g_val>0 else "negative")
                lbl_w.style().unpolish(lbl_w); lbl_w.style().polish(lbl_w)
                        
    def clear_view(self):
        if hasattr(self, 'lw_manual_button'): self.lw_manual_button.setVisible(False)
        if hasattr(self, 'lm_manual_button'): self.lm_manual_button.setVisible(False)
        for key, label in self.labels.items():
            if key in ['target_sales', 'target_other', 'bscd_bu_value']: label.setText("...")
            else: label.setText("")
            label.setProperty("bscd_growth", "none"); label.style().unpolish(label); label.style().polish(label)

class KasDanTipsTab(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.db_manager = self.parent_app.db_manager
        self.config_manager = self.parent_app.config_manager
        self.employee_db = EmployeeDB()
        self._init_ui()
        self.load_initial_data()

    def _init_ui(self):
        self.setStyleSheet("font-family: 'Segoe UI', Arial, sans-serif;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # =============================================
        # LEFT PANEL — Fixed width form
        # =============================================
        left_panel = QWidget()
        left_panel.setFixedWidth(300)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # --- SUMMARY CARDS ---
        self.saldo_akhir_kas_label = QLabel("Rp 0")
        self.saldo_akhir_tips_label = QLabel("Rp 0")

        def make_card(icon, label_text, value_widget, grad_a, grad_b):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {grad_a}, stop:1 {grad_b});
                    border-radius: 12px;
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(4)
            QLabel(icon).setParent(card)

            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("background: transparent; font-size: 20px;")

            name_lbl = QLabel(label_text)
            name_lbl.setStyleSheet("background: transparent; color: rgba(255,255,255,0.9); font-size: 10px; font-weight: 700; letter-spacing: 1.5px;")

            value_widget.setStyleSheet("background: transparent; color: white; font-size: 18px; font-weight: bold;")

            cl.addWidget(icon_lbl)
            cl.addWidget(name_lbl)
            cl.addWidget(value_widget)
            return card

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        cards_row.addWidget(make_card("🏦", "SALDO KAS", self.saldo_akhir_kas_label, "#4f9cf9", "#1a73e8"))
        cards_row.addWidget(make_card("💰", "SALDO TIPS", self.saldo_akhir_tips_label, "#2ec4b6", "#0c9e90"))
        left_layout.addLayout(cards_row)

        # --- INPUT CARD ---
        form_card = QFrame()
        form_card.setStyleSheet("""
            QFrame {
                border-radius: 10px;
                border: 1px solid gray;
            }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.setSpacing(6)

        title_row = QHBoxLayout()
        form_icon = QLabel("✦")
        form_icon.setStyleSheet("color: #5DADE2; font-size: 12px;")
        form_title = QLabel("Input Transaksi Baru")
        form_title.setStyleSheet("color: #5DADE2; font-size: 12px; font-weight: bold;")
        title_row.addWidget(form_icon)
        title_row.addWidget(form_title)
        title_row.addStretch()
        form_layout.addLayout(title_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("border: none; background-color: gray; max-height: 1px;")
        form_layout.addWidget(divider)

        # Shared styles
        LABEL_STYLE = "font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
        INPUT_STYLE = """
            QLineEdit, QComboBox, QDateEdit {
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { border: none; }
        """

        def form_row(layout, label, widget):
            group = QVBoxLayout()
            group.setSpacing(1)
            lbl = QLabel(label)
            lbl.setStyleSheet(LABEL_STYLE)
            widget.setStyleSheet(INPUT_STYLE)
            group.addWidget(lbl)
            group.addWidget(widget)
            layout.addLayout(group)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd MMMM yyyy")
        self.date_edit.setReadOnly(True)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("cth: Saldo awal kas, Pembelian galon...")

        self.amount_input = QLineEdit()
        self.amount_input.setValidator(QIntValidator())
        self.amount_input.setPlaceholderText("Masukkan nominal...")

        self.type_trans_combo = QComboBox()
        self.type_trans_combo.addItems(["Pemasukan", "Pengeluaran"])

        self.type_dana_combo = QComboBox()
        self.type_dana_combo.addItems(["Kas", "Tips"])

        self.diinput_oleh_combo = QComboBox()

        form_row(form_layout, "📅  TANGGAL", self.date_edit)
        form_row(form_layout, "📝  DESKRIPSI", self.desc_input)
        form_row(form_layout, "💵  JUMLAH (Rp)", self.amount_input)
        form_row(form_layout, "↕  TIPE TRANSAKSI", self.type_trans_combo)
        form_row(form_layout, "🗂  TIPE DANA", self.type_dana_combo)
        form_row(form_layout, "👤  DIINPUT OLEH", self.diinput_oleh_combo)

        self.add_trans_button = QPushButton("＋  Tambah Transaksi")
        self.add_trans_button.setCursor(Qt.PointingHandCursor)
        self.add_trans_button.setFixedHeight(34)
        self.add_trans_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f9cf9, stop:1 #1a73e8);
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 10px;
                border: none;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a73e8, stop:1 #1557b0);
            }
            QPushButton:pressed { background: #1557b0; }
            QPushButton:disabled {
                background: #e0e0e0;
                color: #9e9e9e;
            }
        """)
        form_layout.addSpacing(4)
        form_layout.addWidget(self.add_trans_button)
        left_layout.addWidget(form_card)
        left_layout.addStretch()

        # =============================================
        # RIGHT PANEL — History Table
        # =============================================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Top bar: title + delete
        top_bar = QHBoxLayout()
        tbl_title = QLabel("Riwayat Semua Transaksi")
        tbl_title.setStyleSheet("font-size: 14px; font-weight: bold;")

        delete_button = QPushButton("🗑  Hapus Terpilih")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.setFixedHeight(34)
        delete_button.setStyleSheet("""
            QPushButton {
                color: #ff6b6b;
                border: 1.5px solid #ff6b6b;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
                color: white;
            }
        """)
        top_bar.addWidget(tbl_title)
        top_bar.addStretch()
        top_bar.addWidget(delete_button)
        right_layout.addLayout(top_bar)

        # Table card wrapper
        table_card = QFrame()
        table_card.setStyleSheet("""
            QFrame {
                border-radius: 12px;
                border: 1px solid gray;
            }
        """)
        tcard_layout = QVBoxLayout(table_card)
        tcard_layout.setContentsMargins(0, 0, 0, 0)

        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(7)
        self.transactions_table.setHorizontalHeaderLabels(["ID", "Tanggal", "Deskripsi", "Jenis", "Dana", "Jumlah", "Diinput oleh"])
        self.transactions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.transactions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.transactions_table.setAlternatingRowColors(True)
        self.transactions_table.setColumnHidden(0, True)
        self.transactions_table.setShowGrid(False)
        self.transactions_table.verticalHeader().setVisible(False)
        self.transactions_table.setStyleSheet("""
            QTableWidget {
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTableWidget::item {
                padding: 9px 8px;
                border: none;
                border-bottom: 1px solid gray;
            }
            QTableWidget::item:selected {
                background-color: #3A78D0;
                color: #FFFFFF;
            }
            QHeaderView::section {
                font-weight: 700;
                font-size: 11px;
                padding: 9px 8px;
                border: none;
                border-bottom: 2px solid gray;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)

        header = self.transactions_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        tcard_layout.addWidget(self.transactions_table)
        right_layout.addWidget(table_card)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

        # Wire up signals
        self.add_trans_button.clicked.connect(self.add_transaction)
        delete_button.clicked.connect(self.delete_transaction)

    def load_initial_data(self):
        self.populate_employee_combos()
        self.load_all_transactions()
    
    def load_all_transactions(self):
        """Memuat semua transaksi dari database dan memperbarui UI."""
        site_code = self.config_manager.get_config().get('site_code')
        if not site_code:
            if self.isVisible(): QMessageBox.warning(self, "Konfigurasi Dibutuhkan", "Harap atur Site Code di menu File > Konfigurasi.")
            self.add_trans_button.setEnabled(False)
            return
            
        self.add_trans_button.setEnabled(True)
        transactions = self.db_manager.get_all_kas_tips_transactions(site_code)
        
        self.transactions_table.setRowCount(0)
        if not transactions:
            self.recalculate_summary()
            return

        self.transactions_table.setRowCount(len(transactions))
        for row, trans in enumerate(transactions):
            self.transactions_table.setItem(row, 0, QTableWidgetItem(str(trans['id'])))
            
            tanggal_obj = trans['tanggal']
            tanggal_str = datetime.strptime(tanggal_obj, '%Y-%m-%d').strftime("%d-%m-%Y") if isinstance(tanggal_obj, str) else tanggal_obj.strftime("%d-%m-%Y")
            self.transactions_table.setItem(row, 1, QTableWidgetItem(tanggal_str))
            
            self.transactions_table.setItem(row, 2, QTableWidgetItem(trans.get('keterangan', '')))
            self.transactions_table.setItem(row, 3, QTableWidgetItem(trans.get('jenis', '')))
            self.transactions_table.setItem(row, 4, QTableWidgetItem(trans.get('kategori', '')))
            self.transactions_table.setItem(row, 5, QTableWidgetItem(f"{float(trans.get('nominal', 0)):,.0f}"))
            self.transactions_table.setItem(row, 6, QTableWidgetItem(trans.get('input_by', 'N/A')))
            
        self.recalculate_summary()
        
 
    def populate_employee_combos(self):
        try:
            karyawan = self.employee_db.get_all_employees()
            current_diinput = self.diinput_oleh_combo.currentData()
            self.diinput_oleh_combo.clear()
            self.diinput_oleh_combo.addItem("- Pilih -", None)
            for k in karyawan: self.diinput_oleh_combo.addItem(k.get('nik', 'N/A'), k.get('nik'))
            if current_diinput:
                index = self.diinput_oleh_combo.findData(current_diinput)
                if index != -1: self.diinput_oleh_combo.setCurrentIndex(index)
        except Exception as e:
            logging.error(f"Gagal memuat daftar karyawan: {e}")

    def load_transactions_for_selected_date(self):
        target_date = self.date_edit.date().toPyDate()
        site_code = self.config_manager.get_config().get('site_code')
        transactions = self.db_manager.get_transactions_for_date(target_date, site_code)
        
        all_employees = self.employee_db.get_all_employees()
        employee_map = {emp['nik']: emp['nama_lengkap'] for emp in all_employees}

        self.transactions_table.setRowCount(0)
        if not transactions:
            self.recalculate_summary()
            return

        # Pastikan kolom tabel diatur ke 7
        self.transactions_table.setColumnCount(7)
        self.transactions_table.setHorizontalHeaderLabels(["Tanggal", "Deskripsi", "Jenis", "Dana", "Jumlah", "Diinput oleh", "ID"])
        self.transactions_table.setColumnHidden(6, True) # Sembunyikan kolom ID di indeks 6

        self.transactions_table.setRowCount(len(transactions))
        
        for row, trans in enumerate(transactions):
            tanggal_obj = trans['tanggal']
            tanggal_str = datetime.strptime(tanggal_obj, '%Y-%m-%d').strftime("%d-%m-%Y") if isinstance(tanggal_obj, str) else tanggal_obj.strftime("%d-%m-%Y")
            
            # Isi kolom dengan benar
            self.transactions_table.setItem(row, 0, QTableWidgetItem(tanggal_str))
            self.transactions_table.setItem(row, 1, QTableWidgetItem(trans['deskripsi']))
            self.transactions_table.setItem(row, 2, QTableWidgetItem(trans['tipe_transaksi']))
            self.transactions_table.setItem(row, 3, QTableWidgetItem(trans['tipe_dana']))
            
            jumlah = float(trans['jumlah'])
            jumlah_item = QTableWidgetItem(f"{jumlah:,.0f}")
            self.transactions_table.setItem(row, 4, jumlah_item)
            
            nama_penginput = employee_map.get(trans.get('diinput_oleh'), 'N/A')
            self.transactions_table.setItem(row, 5, QTableWidgetItem(nama_penginput))
            
            id_item = QTableWidgetItem(str(trans['id']))
            self.transactions_table.setItem(row, 6, id_item) # ID sekarang di kolom 6
        
        self.recalculate_summary()

    def recalculate_summary(self):
        total_kas, total_tips = 0, 0
        for row in range(self.transactions_table.rowCount()):
            try:
                # --- PERBAIKAN: Sesuaikan indeks kolom dengan struktur yang benar ---
                jumlah = float(self.transactions_table.item(row, 5).text().replace(',', '')) # Kolom 5: Jumlah
                tipe_transaksi = self.transactions_table.item(row, 3).text() # Kolom 3: Jenis
                tipe_dana = self.transactions_table.item(row, 4).text() # Kolom 4: Dana
                # -------------------------------------------------------------------
                multiplier = 1 if tipe_transaksi == "Pemasukan" else -1
                if tipe_dana == "Kas": total_kas += (jumlah * multiplier)
                elif tipe_dana == "Tips": total_tips += (jumlah * multiplier)
            except (ValueError, AttributeError): continue
        self.saldo_akhir_kas_label.setText(f"Rp {total_kas:,.0f}")
        self.saldo_akhir_tips_label.setText(f"Rp {total_tips:,.0f}")
        
    def add_transaction(self):
        """Menyimpan data dari form sebagai transaksi baru."""
        deskripsi = self.desc_input.text().strip()
        jumlah_str = self.amount_input.text().strip()
        
        if not deskripsi or not jumlah_str: QMessageBox.warning(self, "Input Tidak Lengkap", "Deskripsi dan Jumlah tidak boleh kosong."); return
        if self.diinput_oleh_combo.currentIndex() <= 0: QMessageBox.warning(self, "Input Tidak Lengkap", "Pilih siapa yang menginput."); return
        
        try: jumlah = float(jumlah_str)
        except ValueError: QMessageBox.warning(self, "Input Salah", "Jumlah harus berupa angka."); return
            
        trans_data = {
            'tanggal': self.date_edit.date().toPyDate(),
            'site_code': self.config_manager.get_config().get('site_code'),
            'deskripsi': deskripsi, 'jumlah': jumlah,
            'tipe_transaksi': self.type_trans_combo.currentText(),
            'tipe_dana': self.type_dana_combo.currentText(),
            'diinput_oleh': self.diinput_oleh_combo.currentData()
        }
        
        if self.db_manager.add_kas_tips_transaction(trans_data):
            self.load_all_transactions()
            self.desc_input.clear(); self.amount_input.clear()
            self.desc_input.setFocus()
        else:
            QMessageBox.critical(self, "Error", "Gagal menyimpan transaksi ke database.")

    def delete_transaction(self):
        """Menghapus baris transaksi yang dipilih dari tabel dan database."""
        selected_rows = self.transactions_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Peringatan", "Pilih transaksi yang ingin dihapus.")
            return
            
        row_to_delete = selected_rows[0].row()
        
        # --- PERBAIKAN: Ambil ID dan Deskripsi dari kolom yang benar ---
        id_item = self.transactions_table.item(row_to_delete, 0) # ID di kolom 0
        deskripsi_item = self.transactions_table.item(row_to_delete, 2) # Deskripsi di kolom 2
        # -------------------------------------------------------------

        if not id_item or not deskripsi_item:
            logging.error("Gagal menghapus: Kolom ID atau Deskripsi tidak ditemukan.")
            return

        reply = QMessageBox.question(self, "Konfirmasi Hapus", f"Anda yakin ingin menghapus transaksi '{deskripsi}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if self.db_manager.delete_kas_tips_transaction(transaction_id):
                self.load_all_transactions() # Refresh dengan metode utama
            else:
                QMessageBox.critical(self, "Error", "Gagal menghapus transaksi dari database.")


class ArticleSelectionDialogInUse(QDialog):
    def __init__(self, all_articles, previously_selected_codes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Artikel untuk In-Use")
        self.setGeometry(150, 150, 950, 500)
        
        self.all_articles = all_articles
        self.previously_selected_codes = set(previously_selected_codes)
        self.selected_articles = []
        if parent and hasattr(parent, 'db_manager'):
            self.db_manager = parent.db_manager
        else:
            self.db_manager = None
            
        self.unique_groups = sorted(list(set(art.get('custom_group', 'Semua') for art in self.all_articles)))
        if "Semua" not in self.unique_groups:
            self.unique_groups.insert(0, "Semua")
        
        main_layout = QVBoxLayout(self)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Cari:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Ketik kode atau deskripsi...")
        self.search_input.textChanged.connect(self.filter_table)
        filter_layout.addWidget(self.search_input)
        
        filter_layout.addWidget(QLabel("Grup:"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(self.unique_groups)
        self.group_combo.currentTextChanged.connect(self.filter_table)
        filter_layout.addWidget(self.group_combo)
        
        self.show_hidden_cb = QCheckBox("Tampilkan yg Disembunyikan")
        self.show_hidden_cb.stateChanged.connect(self.filter_table)
        filter_layout.addWidget(self.show_hidden_cb)
        
        # Add Select All checkbox
        self.select_all_cb = QCheckBox("Pilih Semua (Terlihat)")
        self.select_all_cb.stateChanged.connect(self.toggle_select_all)
        filter_layout.addWidget(self.select_all_cb)
        
        main_layout.addLayout(filter_layout)
        
        self.article_table = QTableWidget()
        self.article_table.setColumnCount(6)
        self.article_table.setHorizontalHeaderLabels(["Pilih", "Article", "Article Description", "GL Account", "Grup", "Disembunyikan"])
        self.article_table.setSelectionMode(QTableWidget.NoSelection)
        self.article_table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.article_table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        self.populate_table(self.all_articles)
        self.filter_table() # apply initial filter
        
        main_layout.addWidget(self.article_table)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_selection)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
    def populate_table(self, articles):
        self.article_table.setRowCount(len(articles))
        for row, article in enumerate(articles):
            checkbox = QCheckBox()
            if article.get('article_code') in self.previously_selected_codes:
                checkbox.setChecked(True)
            cell_widget = QWidget()
            layout = QHBoxLayout(cell_widget); layout.addWidget(checkbox); layout.setAlignment(Qt.AlignCenter); layout.setContentsMargins(0,0,0,0)
            
            self.article_table.setCellWidget(row, 0, cell_widget)
            self.article_table.setItem(row, 1, QTableWidgetItem(article.get('article_code', '')))
            self.article_table.setItem(row, 2, QTableWidgetItem(article.get('article_description', '')))
            self.article_table.setItem(row, 3, QTableWidgetItem(article.get('gl_account', '')))
            
            # Setup Group cell to be editable (we use a tool button or line edit or double click later)
            # For simplicity, let's use a QLineEdit in the table cell
            group_edit = QLineEdit(article.get('custom_group', 'Semua'))
            # We connect editing finished to an update function
            group_edit.editingFinished.connect(lambda r=row, le=group_edit: self.update_group(r, le.text()))
            self.article_table.setCellWidget(row, 4, group_edit)
            
            hide_cb = QCheckBox()
            is_hid = article.get('is_hidden', 0)
            hide_cb.setChecked(bool(is_hid))
            hide_cb.clicked.connect(lambda checked, r=row: self.toggle_hidden(r, checked))
            hide_widget = QWidget()
            h_layout = QHBoxLayout(hide_widget); h_layout.addWidget(hide_cb); h_layout.setAlignment(Qt.AlignCenter); h_layout.setContentsMargins(0,0,0,0)
            self.article_table.setCellWidget(row, 5, hide_widget)

    def toggle_hidden(self, row, is_checked):
        article_code = self.article_table.item(row, 1).text()
        if self.db_manager:
            self.db_manager.toggle_inuse_article_hidden(article_code, int(is_checked))
            for art in self.all_articles:
                if art['article_code'] == article_code:
                    art['is_hidden'] = int(is_checked)
                    break
        self.filter_table()
        
    def update_group(self, row, new_group):
        article_code = self.article_table.item(row, 1).text()
        if not new_group.strip():
            new_group = "Semua" # default fallback
        
        if self.db_manager:
            self.db_manager.update_inuse_article_group(article_code, new_group)
            for art in self.all_articles:
                if art['article_code'] == article_code:
                    art['custom_group'] = new_group
                    break
        
        # update unique groups dropdown if it's new
        if new_group not in self.unique_groups:
            self.unique_groups.append(new_group)
            self.unique_groups.sort()
            
            # recreate combo box items while retaining selection
            current_sel = self.group_combo.currentText()
            self.group_combo.blockSignals(True)
            self.group_combo.clear()
            self.group_combo.addItems(self.unique_groups)
            self.group_combo.setCurrentText(current_sel)
            self.group_combo.blockSignals(False)
            
    def filter_table(self):
        filter_text = self.search_input.text().lower()
        selected_group = self.group_combo.currentText()
        show_hidden = self.show_hidden_cb.isChecked()
        
        for row in range(self.article_table.rowCount()):
            code_item, desc_item = self.article_table.item(row, 1), self.article_table.item(row, 2)
            code_text = code_item.text().lower() if code_item else ""
            desc_text = desc_item.text().lower() if desc_item else ""
            
            is_match_search = (filter_text in code_text) or (filter_text in desc_text)
            
            # Check group
            group_widget = self.article_table.cellWidget(row, 4)
            current_art_group = "Semua"
            if group_widget:
                current_art_group = group_widget.text()
                
            matches_group = (selected_group == "Semua") or (current_art_group == selected_group)
                
            is_hidden = False
            hide_widget = self.article_table.cellWidget(row, 5) # Column 5 has the hide toggle
            if hide_widget:
                cb = hide_widget.findChild(QCheckBox)
                if cb: is_hidden = cb.isChecked()
            
            is_match_hidden = True
            if not show_hidden and is_hidden:
                is_match_hidden = False
                
            self.article_table.setRowHidden(row, not (is_match_search and matches_group and is_match_hidden))
            
    def toggle_select_all(self, state):
        is_checked = (state == Qt.Checked)
        for row in range(self.article_table.rowCount()):
            if not self.article_table.isRowHidden(row):
                widget = self.article_table.cellWidget(row, 0)
                if widget:
                    cb = widget.findChild(QCheckBox)
                    if cb:
                        cb.setChecked(is_checked)
            
    def accept_selection(self):
        for row in range(self.article_table.rowCount()):
            if not self.article_table.isRowHidden(row):
                checkbox = self.article_table.cellWidget(row, 0).findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    article_code = self.article_table.item(row, 1).text()
                    original_article = next((item for item in self.all_articles if item['article_code'] == article_code), None)
                    if original_article: self.selected_articles.append(original_article)
        self.accept()

    def get_selected_articles(self):
        return self.selected_articles

class ManageGroupDialogInUse(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kelola Grup In-Use")
        self.setMinimumSize(800, 500)
        self.db_manager = db_manager
        
        self.all_articles = self.db_manager.get_all_inuse_articles()
        self.unique_groups = sorted(list(set(art.get('custom_group', 'Semua') for art in self.all_articles)))
        if "Semua" not in self.unique_groups:
            self.unique_groups.insert(0, "Semua")
        
        # UI Layout
        main_layout = QHBoxLayout(self)
        
        # KIRI: List Grup
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Daftar Grup:"))
        self.group_list = QListWidget()
        self.group_list.addItems(self.unique_groups)
        self.group_list.currentRowChanged.connect(self.on_group_selected)
        left_layout.addWidget(self.group_list)
        
        btn_layout_left = QHBoxLayout()
        self.btn_add_group = QPushButton("➕ Tambah")
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_del_group = QPushButton("🗑️ Hapus")
        self.btn_del_group.clicked.connect(self.delete_group)
        self.btn_del_group.setStyleSheet("QPushButton { background-color: #1976D2; color: white; border: none; padding: 6px; border-radius:4px; font-weight:bold; } QPushButton:hover{background-color: #1565C0;}")
        self.btn_add_group.setStyleSheet("QPushButton { background-color: #1976D2; color: white; border: none; padding: 6px; border-radius:4px; font-weight:bold; } QPushButton:hover{background-color: #1565C0;}")
        
        btn_layout_left.addWidget(self.btn_add_group)
        btn_layout_left.addWidget(self.btn_del_group)
        left_layout.addLayout(btn_layout_left)
        
        # KANAN: Detail Grup & Artikel
        right_layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        self.group_name_input = QLineEdit()
        self.group_name_input.textChanged.connect(self.on_group_name_changed)
        form_layout.addRow("Nama Grup:", self.group_name_input)
        right_layout.addLayout(form_layout)
        
        right_layout.addWidget(QLabel("Pilih Artikel untuk Grup Ini:"))
        
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Cari nama artikel...")
        self.search_input.textChanged.connect(self.filter_articles)
        search_layout.addWidget(self.search_input)
        right_layout.addLayout(search_layout)
        
        self.article_list_widget = QListWidget()
        self.populate_articles()
        right_layout.addWidget(self.article_list_widget)
        
        self.linked_count_label = QLabel("Terkait (0) artikel ke grup ini.")
        self.linked_count_label.setStyleSheet("color: #1976D2; font-weight: bold;")
        right_layout.addWidget(self.linked_count_label)
        
        btn_layout_right = QHBoxLayout()
        btn_layout_right.addStretch()
        self.btn_save = QPushButton("Simpan Terapkan")
        self.btn_save.clicked.connect(self.save_group)
        self.btn_save.setStyleSheet("background-color: #1976D2; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet("background-color: #1976D2; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        
        btn_layout_right.addWidget(self.btn_save)
        btn_layout_right.addWidget(self.btn_cancel)
        right_layout.addLayout(btn_layout_right)
        
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        
        if self.group_list.count() > 0:
            self.group_list.setCurrentRow(0)

    def populate_articles(self):
        self.article_list_widget.clear()
        for art in self.all_articles:
            item = QListWidgetItem(f"{art['article_code']} - {art['article_description']}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, art['article_code'])
            self.article_list_widget.addItem(item)

    def on_group_selected(self, row):
        if row < 0: return
        group_name = self.group_list.item(row).text()
        self.group_name_input.setText(group_name)
        
        if group_name == "Semua":
            self.group_name_input.setReadOnly(True)
            self.btn_del_group.setEnabled(False)
        else:
            self.group_name_input.setReadOnly(False)
            self.btn_del_group.setEnabled(True)
            
        linked_count = 0
        for i in range(self.article_list_widget.count()):
            item = self.article_list_widget.item(i)
            article_code = item.data(Qt.UserRole)
            art = next((a for a in self.all_articles if a['article_code'] == article_code), None)
            
            # Default uncheck
            item.setCheckState(Qt.Unchecked)
            
            if art and art.get('custom_group', 'Semua') == group_name:
                item.setCheckState(Qt.Checked)
                linked_count += 1
                
        self.linked_count_label.setText(f"Terkait ({linked_count}) artikel ke grup ini.")

    def on_group_name_changed(self, text):
        row = self.group_list.currentRow()
        if row >= 0 and self.group_list.item(row).text() != "Semua":
            self.group_list.item(row).setText(text)

    def filter_articles(self):
        search_text = self.search_input.text().lower()
        for i in range(self.article_list_widget.count()):
            item = self.article_list_widget.item(i)
            item.setHidden(search_text not in item.text().lower())

    def add_group(self):
        new_name = f"Grup Baru {self.group_list.count()}"
        self.group_list.addItem(new_name)
        self.group_list.setCurrentRow(self.group_list.count() - 1)

    def delete_group(self):
        row = self.group_list.currentRow()
        if row >= 0:
            group_name = self.group_list.item(row).text()
            if group_name == "Semua": return
            
            reply = QMessageBox.question(self, "Hapus Grup", f"Yakin menghapus grup '{group_name}'?\nArtikel di dalamnya akan dikembalikan ke grup 'Semua'.", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.group_list.takeItem(row)
                for art in self.all_articles:
                    if art.get('custom_group') == group_name:
                        art['custom_group'] = 'Semua'
                        self.db_manager.update_inuse_article_group(art['article_code'], 'Semua')
                self.accept()

    def save_group(self):
        row = self.group_list.currentRow()
        if row < 0: return
        group_name = self.group_name_input.text().strip()
        if not group_name:
            QMessageBox.warning(self, "Error", "Nama grup tidak boleh kosong!")
            return
            
        # Update checked items to this group
        for i in range(self.article_list_widget.count()):
            item = self.article_list_widget.item(i)
            article_code = item.data(Qt.UserRole)
            
            if item.checkState() == Qt.Checked:
                # Move to this group
                for art in self.all_articles:
                    if art['article_code'] == article_code:
                        art['custom_group'] = group_name
                        self.db_manager.update_inuse_article_group(article_code, group_name)
                        break
            elif item.checkState() == Qt.Unchecked:
                 # If it was in this group and now unchecked, move back to "Semua" ONLY IF the current group isn't "Semua"
                 if group_name != "Semua":
                     for art in self.all_articles:
                         if art['article_code'] == article_code and art.get('custom_group') == group_name:
                             art['custom_group'] = 'Semua'
                             self.db_manager.update_inuse_article_group(article_code, 'Semua')
                             break
                             
        QMessageBox.information(self, "Sukses", "Data grup berhasil disimpan.")
        self.accept()

# --- DIALOG BARU: INPUT MANUAL IN-USE ---
class ManualInUseItemDialog(QDialog):
    def __init__(self, parent=None, item_data=None):
        super().__init__(parent)
        self.setWindowTitle("Input Item Manual")
        self.setFixedSize(400, 250)
        layout = QFormLayout(self)
        
        self.code_input = QLineEdit()
        self.desc_input = QLineEdit()
        self.uom_input = QLineEdit()
        self.gl_input = QLineEdit()
        
        layout.addRow("Kode Artikel:", self.code_input)
        layout.addRow("Deskripsi:", self.desc_input)
        layout.addRow("UOM (Satuan):", self.uom_input)
        layout.addRow("GL Account:", self.gl_input)
        
        # Isi data jika mode edit
        if item_data:
            self.code_input.setText(item_data.get('article_code', ''))
            self.desc_input.setText(item_data.get('article_description', ''))
            self.uom_input.setText(item_data.get('uom', ''))
            self.gl_input.setText(item_data.get('gl_account', ''))
            
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
    def get_data(self):
        return {
            'article_code': self.code_input.text().strip(),
            'article_description': self.desc_input.text().strip(),
            'uom': self.uom_input.text().strip().upper(),
            'gl_account': self.gl_input.text().strip()
        }
        
class InUseTab(QWidget):
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.db_manager = self.parent_app.db_manager
        self.config_manager = self.parent_app.config_manager

        self.sap_headers = [
            "No", "Article Description", "Article", "Qty", "E", "Sloc", "Cost Ctr", "GL Acc", "Batch", "Val", 
            "Mvt", "D", "Stock Typ", "Site", "", "", "", "", "", "", "", "", 
            "", "", "", "", "", "", "", "", "Text"
        ]
        self.col_map = {name: i for i, name in enumerate(self.sap_headers) if name}

        self._init_ui()
        self.load_initial_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- BAGIAN 1: KONFIGURASI HEADER ---
        config_group = QGroupBox("Konfigurasi Header & Data")
        config_layout = QGridLayout(config_group)
        
        # 1. Nama
        self.input_nama = QLineEdit()
        self.input_nama.setPlaceholderText("Nama Penginput")
        if hasattr(self.parent_app, 'logged_in_user_name') and self.parent_app.logged_in_user_name:
             self.input_nama.setText(self.parent_app.logged_in_user_name.upper())

        # 2. Kategori
        self.combo_kategori = QComboBox()
        self.combo_kategori.addItems(["[REG]", "[MKT]", "[TESTER]", "[CLOSING]", "[MAINTENANCE]"])
        
        # 3. Tanggal
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        
        # 4. Remark
        self.input_remark = QLineEdit()
        self.input_remark.setPlaceholderText("INUSED W2 NOVEMBER 25")
        
        # 5. Preview Text SAP (Format Panjang)
        self.header_preview = QLineEdit()
        self.header_preview.setReadOnly(True)
        self.header_preview.setStyleSheet("background-color: #e0f7fa; font-weight: bold; color: #006064;")
        self.header_preview.setPlaceholderText("Format: [KATEGORI]-NAMA/TGL/REMARK")

        # 6. Header Text Short (BARU: NAMA/TGL)
        self.header_text_short = QLineEdit()
        self.header_text_short.setReadOnly(True)
        self.header_text_short.setStyleSheet("background-color: #fff3e0; font-weight: bold; color: #e65100;")
        self.header_text_short.setPlaceholderText("Format: NAMA/TGL")
        
        # Tombol Salin Short Text (BARU)
        self.btn_copy_short = QPushButton()
        self.btn_copy_short.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton)) # Atau icon copy jika ada asset
        self.btn_copy_short.setToolTip("Salin Header")
        self.btn_copy_short.setFixedSize(30, 25)
        self.btn_copy_short.clicked.connect(self._copy_short_text)

        # --- Layout Konfigurasi (Grid) ---
        # Baris 0
        config_layout.addWidget(QLabel("Nama User"), 0, 0)
        config_layout.addWidget(self.input_nama, 0, 1)
        config_layout.addWidget(QLabel("Kategori"), 0, 2)
        config_layout.addWidget(self.combo_kategori, 0, 3)
        
        # Baris 1
        config_layout.addWidget(QLabel("Tanggal"), 1, 0)
        config_layout.addWidget(self.date_edit, 1, 1)
        config_layout.addWidget(QLabel("Remark"), 1, 2)
        config_layout.addWidget(self.input_remark, 1, 3)
        
        # Baris 2: Header Text Short (BARU)
        config_layout.addWidget(QLabel("Header Text"), 2, 0)
        
        # Container untuk Textbox + Tombol Copy
        short_text_container = QWidget()
        short_h_layout = QHBoxLayout(short_text_container)
        short_h_layout.setContentsMargins(0,0,0,0)
        short_h_layout.addWidget(self.header_text_short)
        short_h_layout.addWidget(self.btn_copy_short)
        
        config_layout.addWidget(short_text_container, 2, 1)
        
        # Baris 2 Lanjutan: Preview SAP (Digeser ke kanan atau baris baru)
        # Kita taruh Preview SAP di sebelah kanannya agar efisien
        config_layout.addWidget(QLabel("Preview Text SAP:"), 2, 2)
        config_layout.addWidget(self.header_preview, 2, 3)
        
        # Baris 3 (Tombol Import & Keterangan)
        self.article_count_label = QLabel("Master Data: 0 Artikel")
        self.article_count_label.setStyleSheet("color: gray; font-style: italic;")
        
        self.import_button = QPushButton("📥 Import")
        self.import_button.setFixedSize(120, 25)
        self.import_button.setToolTip("Import Update Master Artikel dari Excel")
        self.import_button.setStyleSheet("""
            QPushButton {
                background-color: #f1f3f4; color: #5f6368;
                border: 1px solid #dadce0; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #e8eaed; color: #202124; }
        """)
        self.import_button.clicked.connect(self.import_master_data)
        
        bottom_config_layout = QHBoxLayout()
        bottom_config_layout.addWidget(self.article_count_label)
        bottom_config_layout.addStretch()
        bottom_config_layout.addWidget(self.import_button)
        
        config_layout.addLayout(bottom_config_layout, 3, 0, 1, 4)

        main_layout.addWidget(config_group)

        # --- BAGIAN 2: TOMBOL AKSI CRUD ---
        selection_layout = QHBoxLayout()
        
        self.list_artikel_button = QPushButton("➕ Pilih Artikel dari Daftar")
        # --- PERBAIKAN DI SINI: Menambahkan warna teks (color: #0d47a1) agar kontras ---
        self.list_artikel_button.setStyleSheet("""
            QPushButton {
                font-weight: bold; 
                background-color: #e3f2fd; 
                color: #0d47a1; 
                border: 1px solid #90caf9; 
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #bbdefb;
            }
        """)
        self.list_artikel_button.clicked.connect(self.open_article_selection)
        
        self.manage_group_button = QPushButton("Kelola Grup")
        self.manage_group_button.setStyleSheet("""
            QPushButton {
                font-weight: bold; 
                background-color: #e3f2fd; 
                color: #0d47a1; 
                border: 1px solid #90caf9; 
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #bbdefb;
            }
        """)
        self.manage_group_button.clicked.connect(self.open_manage_group)
        
        # Style umum tombol biru solid
        btn_style_blue = """
            QPushButton { background-color: #1976D2; color: white; border-radius: 4px; padding: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #1565C0; }
        """
        
        # Tombol CRUD Manual
        self.btn_add_manual = QPushButton("Tambah Manual")
        self.btn_add_manual.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_add_manual.clicked.connect(self.add_manual_item)
        
        self.btn_edit = QPushButton("Edit Item")
        self.btn_edit.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.btn_edit.clicked.connect(self.edit_selected_item)
        
        self.btn_del = QPushButton("Hapus Item")
        self.btn_del.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_del.setStyleSheet("color: red;")
        self.btn_del.clicked.connect(self.delete_selected_item)
        
        selection_layout.addWidget(self.list_artikel_button)
        selection_layout.addWidget(self.manage_group_button)
        selection_layout.addSpacing(10)
        selection_layout.addWidget(self.btn_add_manual)
        selection_layout.addWidget(self.btn_edit)
        selection_layout.addWidget(self.btn_del)
        selection_layout.addStretch()
        
        main_layout.addLayout(selection_layout)



        # --- BAGIAN 3: TABEL UTAMA ---
        self.inuse_table = QTableWidget()
        self.sap_headers_display = ["Status"] + self.sap_headers
        self.inuse_table.setColumnCount(len(self.sap_headers_display))
        self.inuse_table.setHorizontalHeaderLabels(self.sap_headers_display)
        
        header = self.inuse_table.horizontalHeader()
        visible_headers = ["Status", "Article Description", "Article", "Qty", "Sloc", "Cost Ctr", "GL Acc", "Text"]
        for i, h in enumerate(self.sap_headers_display):
            if h not in visible_headers:
                self.inuse_table.setColumnHidden(i, True)
            if h == "Article Description": header.setSectionResizeMode(i, QHeaderView.Stretch)
            elif h == "Qty": self.inuse_table.setColumnWidth(i, 80)
            elif h == "Status": self.inuse_table.setColumnWidth(i, 80)
            elif h: header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            
        main_layout.addWidget(self.inuse_table)

        # --- BAGIAN 4: EKSEKUSI ---
        bottom_button_layout = QHBoxLayout()
        self.clear_table_button = QPushButton("Bersihkan Tabel")
        self.clear_table_button.clicked.connect(lambda: self.inuse_table.setRowCount(0))
        
        self.batch_size_spinbox = QSpinBox()
        self.batch_size_spinbox.setPrefix("Batch Size: ")
        self.batch_size_spinbox.setRange(1, 100)
        self.batch_size_spinbox.setValue(20)
        
        self.copy_button = QPushButton("📋 Salin ke SAP")
        self.copy_button.setFont(QFont("Arial", 10, QFont.Bold))
        self.copy_button.setMinimumHeight(40)
        self.copy_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.copy_button.clicked.connect(self._copy_next_batch)
        
        bottom_button_layout.addWidget(self.clear_table_button)
        bottom_button_layout.addStretch()
        bottom_button_layout.addWidget(self.batch_size_spinbox)
        bottom_button_layout.addWidget(self.copy_button)
        main_layout.addLayout(bottom_button_layout)

        # Koneksi Sinyal
        self.input_nama.textChanged.connect(self._update_header_preview)
        self.combo_kategori.currentTextChanged.connect(self._update_header_preview)
        self.date_edit.dateChanged.connect(self._update_header_preview)
        self.input_remark.textChanged.connect(self._update_header_preview) # Koneksi Remark
        
        # Trigger update pertama kali
        self._update_header_preview()
    
    def _update_header_preview(self):
        """Update kedua format header (SAP Long dan Short)."""
        nama = self.input_nama.text().strip().upper()
        kategori = self.combo_kategori.currentText()
        tanggal = self.date_edit.date().toString("dd.MM.yyyy")
        remark = self.input_remark.text().strip().upper()
        
        # 1. Format SAP (Panjang)
        final_text = f"{kategori}-{nama}/{tanggal}"
        if remark:
            final_text += f"/{remark}"
            
        # Validasi Karakter SAP
        char_count = len(final_text)
        max_chars = 50
        tooltip_text = f"Jumlah Karakter: {char_count} / {max_chars}"
        
        if char_count > max_chars:
            tooltip_text += f" (Kelebihan {char_count - max_chars} karakter!)"
            self.header_preview.setStyleSheet("background-color: #ffcdd2; font-weight: bold; color: #c62828;")
        else:
            self.header_preview.setStyleSheet("background-color: #e0f7fa; font-weight: bold; color: #006064;")
            
        self.header_preview.setText(final_text)
        self.header_preview.setToolTip(tooltip_text)
        
        # 2. Format Pendek (NAMA/TGL)
        short_text = f"{nama}/{tanggal}"
        self.header_text_short.setText(short_text)

        # Update tabel dengan format SAP (Panjang)
        self._update_table_text_column(final_text)



    def open_manage_group(self):
        dialog = ManageGroupDialogInUse(self.db_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_initial_data() # Refresh in case labels changed atau ada barang baru di tabel

    def _copy_short_text(self):
        """Menyalin teks header pendek ke clipboard."""
        text = self.header_text_short.text()
        if text:
            QApplication.clipboard().setText(text)
            if hasattr(self.parent_app, 'notification_manager'):
                self.parent_app.notification_manager.show('SUCCESS', 'Disalin', f"'{text}' disalin ke clipboard.")
        else:
            QMessageBox.warning(self, "Kosong", "Teks header pendek kosong.")

    def _update_table_text_column(self, new_text):
        if not hasattr(self, 'inuse_table'): return
        col_idx = self.col_map["Text"] + 1 
        for row in range(self.inuse_table.rowCount()):
            status_item = self.inuse_table.item(row, 0)
            if not status_item or status_item.text() != "Tersalin":
                item = QTableWidgetItem(new_text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.inuse_table.setItem(row, col_idx, item)

    def load_initial_data(self):
        try:
            all_articles = self.db_manager.get_all_inuse_articles()
            count = len(all_articles) if all_articles else 0
            self.article_count_label.setText(f"Master Data: {count} Artikel, pastikan artikel dan GL Account yang digunakan selalu update!")
        except Exception as e:
            logging.error(f"Gagal memuat jumlah artikel In-Use: {e}")

    # --- IMPLEMENTASI CRUD MANUAL ---
    def add_manual_item(self):
        dialog = ManualInUseItemDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data['article_description']:
                QMessageBox.warning(self, "Validasi", "Deskripsi artikel wajib diisi.")
                return
            self.add_single_article_to_table(data)

    def edit_selected_item(self):
        row = self.inuse_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Pilih Item", "Silakan pilih baris yang ingin diedit.")
            return
            
        # Ambil data dari tabel
        def get_val(col_name):
            return self.inuse_table.item(row, self.col_map[col_name] + 1).text()
            
        current_data = {
            'article_code': get_val("Article"),
            'article_description': get_val("Article Description"),
            'uom': get_val("E"),
            'gl_account': get_val("GL Acc")
        }
        
        dialog = ManualInUseItemDialog(self, current_data)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            # Update tabel
            self.inuse_table.item(row, self.col_map["Article"] + 1).setText(new_data['article_code'])
            self.inuse_table.item(row, self.col_map["Article Description"] + 1).setText(new_data['article_description'])
            self.inuse_table.item(row, self.col_map["E"] + 1).setText(new_data['uom'])
            self.inuse_table.item(row, self.col_map["GL Acc"] + 1).setText(new_data['gl_account'])

    def delete_selected_item(self):
        row = self.inuse_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Pilih Item", "Silakan pilih baris yang ingin dihapus.")
            return
        
        desc = self.inuse_table.item(row, self.col_map["Article Description"] + 1).text()
        if QMessageBox.question(self, "Hapus", f"Hapus item '{desc}'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.inuse_table.removeRow(row)

    def _copy_next_batch(self):
        if not self.input_nama.text().strip():
            QMessageBox.warning(self, "Data Kurang", "Harap isi Nama User terlebih dahulu.")
            self.input_nama.setFocus(); return

        batch_size = self.batch_size_spinbox.value()
        rows_to_copy_indices = []
        
        for row in range(self.inuse_table.rowCount()):
            status_item = self.inuse_table.item(row, 0)
            if not status_item or status_item.text() != "Tersalin":
                qty_item = self.inuse_table.item(row, self.col_map["Qty"] + 1)
                try:
                    qty_val = float(qty_item.text())
                    if qty_val <= 0: raise ValueError
                except: continue
                rows_to_copy_indices.append(row)
                if len(rows_to_copy_indices) >= batch_size: break
        
        if not rows_to_copy_indices:
            QMessageBox.information(self, "Selesai", "Tidak ada data siap salin (Cek Qty atau Status).")
            return

        def get_text(r, col_name):
            col_idx = self.col_map.get(col_name)
            if col_idx is None: return ""
            item = self.inuse_table.item(r, col_idx + 1)
            return item.text().strip() if item else ""
        
        lines_to_copy = []
        for row in rows_to_copy_indices:
            sap_row_data = [""] * 31
            sap_row_data[0] = get_text(row, "Article")
            sap_row_data[1] = get_text(row, "Qty")
            sap_row_data[2] = get_text(row, "E")
            sap_row_data[3] = get_text(row, "Sloc")
            sap_row_data[4] = get_text(row, "Cost Ctr")
            sap_row_data[5] = get_text(row, "GL Acc")
            sap_row_data[8] = get_text(row, "Mvt")
            sap_row_data[11] = get_text(row, "Site")
            sap_row_data[30] = get_text(row, "Text")
            lines_to_copy.append("\t".join(sap_row_data))
        
        final_text = "\n".join(lines_to_copy)
        QApplication.clipboard().setText(final_text)
        
        for row in rows_to_copy_indices:
            status_item = QTableWidgetItem("Tersalin")
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setBackground(QColor(200, 230, 201)) 
            self.inuse_table.setItem(row, 0, status_item)

        if hasattr(self.parent_app, 'notification_manager'):
            self.parent_app.notification_manager.show('SUCCESS', 'Tersalin', f"{len(rows_to_copy_indices)} baris disalin. Paste (Ctrl+V) di SAP sekarang.")

    def import_master_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Impor Master Artikel In-Use", "",
            "Excel Files (*.xlsx *.xls);;Excel 97-2003 (*.xls);;Excel (*.xlsx);;CSV Files (*.csv)"
        )
        if not path: return
        try:
            ext = path.lower().rsplit('.', 1)[-1]
            if ext == 'xlsx':
                df = pd.read_excel(path, engine='openpyxl')
            elif ext == 'xls':
                df = pd.read_excel(path, engine='xlrd')
            else:
                df = pd.read_csv(path)
            df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]
            required_cols = ['article', 'article_description', 'gl_account']
            if not all(col in df.columns for col in required_cols):
                QMessageBox.critical(self, "Error", f"File harus memiliki kolom: {', '.join(required_cols)}")
                return
            df.rename(columns={'article': 'article_code'}, inplace=True)
            for col in ['uom', 'sloc', 'cost_ctr']:
                if col not in df.columns: df[col] = ''
            items_to_import = df.to_dict('records')
            success, message = self.db_manager.batch_import_inuse(items_to_import, overwrite=True)
            if success:
                QMessageBox.information(self, "Sukses", message)
                self.article_count_label.setText(f"Master Data: {len(items_to_import)} Artikel")
            else: QMessageBox.critical(self, "Gagal Impor", f"Terjadi kesalahan: {message}")
        except Exception as e: QMessageBox.critical(self, "Error Baca File", f"Gagal membaca file impor: {e}")

    def open_article_selection(self):
        all_articles = self.db_manager.get_all_inuse_articles()
        if not all_articles:
            QMessageBox.warning(self, "Data Kosong", "Master data artikel kosong. Import Excel dulu.")
            return
        current_codes = set()
        for row in range(self.inuse_table.rowCount()):
            item = self.inuse_table.item(row, 2 + 1) 
            if item: current_codes.add(item.text())
        dialog = ArticleSelectionDialogInUse(all_articles, current_codes, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_articles = dialog.get_selected_articles()
            self.update_main_table_with_selection(selected_articles)
            
    def update_main_table_with_selection(self, new_selection_list):
        new_selection_dict = {item['article_code']: item for item in new_selection_list}
        for row in range(self.inuse_table.rowCount() - 1, -1, -1):
            item = self.inuse_table.item(row, self.col_map["Article"] + 1)
            # Jangan hapus jika item tersebut ditambahkan manual (tidak ada di master list)
            # Logika sederhana: jika ada di table tapi tidak di seleksi master, hapus
            # TAPI, ini bisa menghapus item manual. Sebaiknya hanya hapus jika item tersebut ADA di all_articles master.
            # Untuk simplifikasi, kita asumsikan sinkronisasi penuh hanya untuk barang master.
            if item and item.text() in [a['article_code'] for a in self.db_manager.get_all_inuse_articles()]:
                 if item.text() not in new_selection_dict:
                    self.inuse_table.removeRow(row)

        current_codes_in_table = set()
        for r in range(self.inuse_table.rowCount()):
            item = self.inuse_table.item(r, self.col_map["Article"] + 1)
            if item: current_codes_in_table.add(item.text())
        for article_code, article_data in new_selection_dict.items():
            if article_code not in current_codes_in_table:
                self.add_single_article_to_table(article_data)

    def add_single_article_to_table(self, article):
        row_pos = self.inuse_table.rowCount()
        self.inuse_table.insertRow(row_pos)
        site_code = self.config_manager.get_config().get('site_code', 'F???')
        current_header_text = self.header_preview.text()
        cost_center = f"{site_code}2801"
        def make_read_only(text=""):
            item = QTableWidgetItem(str(text))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            return item
        
        self.inuse_table.setItem(row_pos, 0, make_read_only("Pending"))
        col_offset = 1 
        self.inuse_table.setItem(row_pos, self.col_map["No"] + col_offset, make_read_only(row_pos + 1))
        self.inuse_table.setItem(row_pos, self.col_map["Article Description"] + col_offset, make_read_only(article.get('article_description', '')))
        self.inuse_table.setItem(row_pos, self.col_map["Article"] + col_offset, make_read_only(article.get('article_code', '')))
        qty_item = QTableWidgetItem("0")
        qty_item.setBackground(QColor(255, 243, 224)) 
        self.inuse_table.setItem(row_pos, self.col_map["Qty"] + col_offset, qty_item)
        self.inuse_table.setItem(row_pos, self.col_map["E"] + col_offset, make_read_only(article.get('uom', '')))
        self.inuse_table.setItem(row_pos, self.col_map["Sloc"] + col_offset, make_read_only("1000"))
        self.inuse_table.setItem(row_pos, self.col_map["Cost Ctr"] + col_offset, make_read_only(cost_center))
        self.inuse_table.setItem(row_pos, self.col_map["GL Acc"] + col_offset, make_read_only(article.get('gl_account', '')))
        self.inuse_table.setItem(row_pos, self.col_map["Mvt"] + col_offset, make_read_only("201"))
        self.inuse_table.setItem(row_pos, self.col_map["Site"] + col_offset, make_read_only(site_code))
        self.inuse_table.setItem(row_pos, self.col_map["Text"] + col_offset, make_read_only(current_header_text))
        for i in range(len(self.sap_headers)):
            if self.inuse_table.item(row_pos, i + col_offset) is None:
                self.inuse_table.setItem(row_pos, i + col_offset, make_read_only(""))
class ReportSectionWidget(QWidget):
    """Widget kontainer untuk setiap area laporan (QTextEdit + Tombol Salin/Template)."""
    def __init__(self, title, parent_app, is_main_report=False, is_switchable=False):
        super().__init__()
        self.parent_app = parent_app
        self.is_main_report = is_main_report
        self.is_switchable = is_switchable
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        top_bar_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #BDC3C7;")
        top_bar_layout.addWidget(self.title_label)
        top_bar_layout.addStretch()
        
        # --- PENAMBAHAN: Dropdown untuk mengganti view (Today/MTD) ---
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Today", "MTD"])
        self.view_combo.setMinimumWidth(100)
        self.view_combo.hide() # Sembunyikan secara default
        top_bar_layout.addWidget(self.view_combo)

        # Tampilkan dropdown HANYA jika widget ini switchable
        if self.is_switchable:
            self.view_combo.show()
            
        # --- ComboBox untuk Template ---
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(180)
        self.template_combo.hide()
        # Sinyal akan dihubungkan di main_app.py
        top_bar_layout.addWidget(self.template_combo)
        
        self.copy_button = QPushButton("📋")
        self.copy_button.setFixedSize(60, 22)
        self.copy_button.hide() # Sembunyikan secara default
        self.copy_button.clicked.connect(self._on_copy_clicked)
        top_bar_layout.addWidget(self.copy_button)
        
        layout.addLayout(top_bar_layout)

        # Area teks
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setObjectName("reportTextEdit") # Beri nama objek untuk styling
        # Saat area teks diklik, ia akan memberitahu parent (SalesReportTab -> ReportingApp)
        self.text_edit.mousePressEvent = lambda event: self.parent_app.column_clicked(self)
        layout.addWidget(self.text_edit)

    def _on_copy_clicked(self):
        """Panggil metode penyalinan di aplikasi utama."""
        self.parent_app.copy_selected_column_content()

    def set_selected(self, is_selected):
        if is_selected:
            self.copy_button.show()
            # Tampilkan dropdown HANYA jika ini adalah laporan utama
            if self.is_main_report:
                self.template_combo.show()
            self.text_edit.setProperty("selected", True)
        else:
            self.copy_button.hide()
            self.template_combo.hide()
            self.text_edit.setProperty("selected", False)
        
        self.text_edit.style().unpolish(self.text_edit); self.text_edit.style().polish(self.text_edit)
        
    def set_title(self, new_title):
        self.title_label.setText(new_title)
        
class DynamicTableWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sales_by_payment_data = pd.DataFrame()
        self.menu_summary_data = pd.DataFrame()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Kontrol (Judul, Pencarian, dan Dropdown)
        control_layout = QHBoxLayout()
        self.title_label = QLabel("Kolom Dinamis")
        self.title_label.setStyleSheet("font-weight: bold; color: #BDC3C7;")
        
        # --- PENAMBAHAN: Kotak Pencarian ---
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cari di tabel...")
        self.search_box.textChanged.connect(self._on_search_changed)
        
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Sales by Payment", "Menu Summary"])
        
        control_layout.addWidget(self.title_label)
        control_layout.addStretch()
        control_layout.addWidget(self.search_box) # Tambahkan kotak pencarian ke layout
        control_layout.addWidget(self.view_combo)
        layout.addLayout(control_layout)

        # Tabel untuk menampilkan data
        self.table = QTableWidget()
        # --- PENAMBAHAN: Mengaktifkan sorting pada tabel ---
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        
        self.view_combo.currentTextChanged.connect(self.update_display)

    def set_data(self, payment_data, menu_data):
        """Menerima dan menyimpan data dari main_app."""
        self.sales_by_payment_data = payment_data if payment_data is not None else pd.DataFrame()
        self.menu_summary_data = menu_data if menu_data is not None else pd.DataFrame()
        self.update_display()

    def update_display(self):
        """Mengupdate header dan isi tabel sesuai pilihan dropdown."""
        # Hentikan sorting sementara untuk mencegah error saat mengisi ulang data
        self.table.setSortingEnabled(False)
        
        current_view = self.view_combo.currentText()
        self.title_label.setText(current_view)
        
        # Bersihkan pencarian saat view berubah
        self.search_box.clear()

    def _on_search_changed(self, text):
        """Menyembunyikan baris yang tidak cocok dengan teks pencarian."""
        search_text = text.lower()
        for i in range(self.table.rowCount()):
            row_is_match = False
            for j in range(self.table.columnCount()):
                item = self.table.item(i, j)
                if item and search_text in item.text().lower():
                    row_is_match = True
                    break # Cukup temukan satu kecocokan per baris
            self.table.setRowHidden(i, not row_is_match)

        if current_view == "Sales by Payment":
            self.setup_table(
                headers=['Amount', 'Order No', 'Receipt No', 'MOP Code', 'MOP Name'],
                data_df=self.sales_by_payment_data,
                formats={'Amount': '{:,.0f}'}
            )
        elif current_view == "Menu Summary":
            self.setup_table(
                headers=['Article Name', 'Qty', '%', 'Sales'],
                data_df=self.menu_summary_data,
                formats={'Qty': '{:,}', '%': '{:.2f}%', 'Sales': '{:,.0f}'}
            )
            
        # Aktifkan kembali sorting setelah data terisi
        self.table.setSortingEnabled(True)

    def setup_table(self, headers, data_df, formats=None):
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(data_df))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        for row_idx, row_data in data_df.iterrows():
            for col_idx, col_name in enumerate(headers):
                value = row_data.get(col_name, "")
                
                # Buat item tabel
                item = QTableWidgetItem()

                # Atur data untuk sorting (angka vs teks) dan tampilan
                if isinstance(value, (int, float, np.number)):
                    item.setData(Qt.DisplayRole, formats.get(col_name, '{}').format(value))
                    item.setData(Qt.UserRole, value) # Simpan nilai asli untuk sorting
                else:
                    item.setData(Qt.DisplayRole, str(value))
                
                self.table.setItem(row_idx, col_idx, item)
        
        self.table.resizeColumnsToContents()
        if headers:
            # Atur kolom pertama agar memanjang, sisanya sesuai konten
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            for i in range(1, len(headers)):
                 self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)

    # --- PENAMBAHAN: Metode untuk menangani pencarian ---
    def _on_search_changed(self, text):
        """Menyembunyikan baris yang tidak cocok dengan teks pencarian."""
        search_text = text.lower()
        for i in range(self.table.rowCount()):
            row_is_match = False
            for j in range(self.table.columnCount()):
                item = self.table.item(i, j)
                if item and search_text in item.text().lower():
                    row_is_match = True
                    break # Cukup temukan satu kecocokan per baris
            self.table.setRowHidden(i, not row_is_match)
# ---------------------------------------------------

class KPICardWidget(QGroupBox):
    """Widget kartu custom yang lebih modern dan visual."""
    def __init__(self, title, icon_char, parent=None):
        super().__init__("", parent) # Judul akan kita buat sendiri
        
        main_layout = QHBoxLayout(self)
        
        # Ikon di sisi kiri
        self.icon_label = QLabel(icon_char)
        icon_font = QFont(); icon_font.setPointSize(100)
        self.icon_label.setFont(icon_font)
        self.icon_label.setFixedWidth(80)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setProperty("class", "cardIcon")
        self.icon_label.setScaledContents(True)
        
        # Konten di sisi kanan
        content_layout = QVBoxLayout()
        self.title_label = QLabel(title)
        title_font = QFont(); title_font.setBold(True); title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        
        self.main_value_label = QLabel("N/A")
        main_font = QFont(); main_font.setPointSize(22); main_font.setBold(True)
        self.main_value_label.setFont(main_font)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False) # Sembunyi secara default

        self.sub_value_layout = QHBoxLayout()
        
        content_layout.addWidget(self.title_label)
        content_layout.addWidget(self.main_value_label)
        content_layout.addWidget(self.progress_bar)
        content_layout.addLayout(self.sub_value_layout)
        
        main_layout.addWidget(self.icon_label)
        main_layout.addLayout(content_layout)
        
        self.setMinimumHeight(140)

    def _create_sub_value_widget(self, text, value):
        """Membuat widget untuk sub-nilai dengan indikator."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)
        
        indicator_label = QLabel()
        text_label = QLabel(text)
        
        if value > 0:
            indicator_label.setText("▲")
            indicator_label.setStyleSheet("color: #2E7D32;") # Hijau
        elif value < 0:
            indicator_label.setText("▼")
            indicator_label.setStyleSheet("color: #C62828;") # Merah
        else:
            indicator_label.setText("●")
            indicator_label.setStyleSheet("color: #757575;") # Abu-abu

        layout.addWidget(indicator_label)
        layout.addWidget(text_label)
        layout.addStretch()
        return widget

    def set_data(self, main_value, sub_values=None, progress_value=None):
        """Mengisi data ke kartu. sub_values adalah list of tuple (teks, nilai)."""
        self.main_value_label.setText(main_value)
        
        # Hapus sub-nilai lama
        for i in reversed(range(self.sub_value_layout.count())): 
            widget_to_remove = self.sub_value_layout.itemAt(i).widget()
            if widget_to_remove is not None:
                widget_to_remove.deleteLater()
            
        # Tambahkan sub-nilai baru
        if sub_values:
            # --- FIX: Add a check to prevent unpacking errors ---
            for item in sub_values:
                # Ensure the item is a list/tuple with exactly 2 elements
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    text, value = item
                    self.sub_value_layout.addWidget(self._create_sub_value_widget(text, value))
                else:
                    # Log a warning if the data is malformed, but don't crash
                    logging.warning(f"Malformed sub_value item found in KPICardWidget: {item}")

        # Tampilkan atau sembunyikan progress bar
        if progress_value is not None:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(int(progress_value))
        else:
            self.progress_bar.setVisible(False)

class ExecutiveDashboardTab(QWidget):
    """Tab baru untuk menampilkan Dasbor Eksekutif."""
    def __init__(self, parent_app):
         super().__init__()
         self.parent_app = parent_app
         self.fig_composition, self.ax_composition = plt.subplots()
         self.canvas_composition = FigureCanvas(self.fig_composition)
         self._init_ui()

    def _init_ui(self):
        layout = QGridLayout(self)
        
        # Buat instance kartu KPI seperti biasa
        self.card_target = KPICardWidget("Pencapaian Target Bulanan", "🎯")
        self.card_daily = KPICardWidget("Performa Harian", "📅")
        self.card_quantity = KPICardWidget("Performa Kuantitas MTD", "🥤")
        
        # --- PENAMBAHAN: Beri nama objek unik untuk styling ---
        self.card_target.setObjectName("cardTarget")
        self.card_daily.setObjectName("cardDaily")
        self.card_quantity.setObjectName("cardQuantity")
        
        # --- PERBAIKAN: Buat QGroupBox terpisah untuk Pie Chart ---
        composition_group = QGroupBox("Komposisi Sales MTD")
        font = composition_group.font()
        font.setPointSize(11)
        font.setBold(True)
        composition_group.setFont(font)
        
        # Buat layout untuk grup ini
        composition_layout = QVBoxLayout(composition_group)
        
        # Buat figure dan canvas untuk pie chart di sini
        self.fig_composition = Figure(figsize=(5, 3), dpi=100)
        self.canvas_composition = FigureCanvas(self.fig_composition)
        composition_layout.addWidget(self.canvas_composition)
        # ----------------------------------------------------
        
        # Atur tata letak kartu dan grup chart
        layout.addWidget(self.card_target, 0, 0)
        layout.addWidget(self.card_daily, 0, 1)
        layout.addWidget(self.card_quantity, 1, 0)
        layout.addWidget(composition_group, 1, 1)

    def update_dashboard(self, data):
        """Menerima data yang sudah diolah dan mengisi setiap kartu."""
        if not data: return

        # --- PERBAIKAN: Gunakan pemanggilan metode set_data yang benar ---
        
        # Isi Kartu 1: Target
        self.card_target.set_data(
            main_value=f"{data.get('mtd_nett_sales', 0) / 1e6:.1f} Jt",
            progress_value=data.get('ach', 0),
            sub_values=[
                (f"{data.get('ach', 0):.1f}% dari Target", data.get('ach', 0)),
                (f"{data.get('ssg_mtd', 0):.1%} vs LY MTD", data.get('ssg_mtd', 0))
            ]
        )
        
        # Isi Kartu 2: Harian
        self.card_daily.set_data(
            main_value=f"{data.get('day_net', 0):,.0f}",
            sub_values=[
                (f"{data.get('growth_lw_pct', 0):.1%} vs LW", data.get('growth_lw_pct', 0)),
                (f"{data.get('ssg', 0):.1%} vs LY", data.get('ssg', 0))
            ]
        )
        
        # Isi Kartu 3: Kuantitas
        self.card_quantity.set_data(
            main_value=f"{data.get('mtd_total_sc', 0):,} Cups",
            sub_values=[
                (f"{data.get('mtd_pct_large', 0):.1f}% Large", 1), # Nilai 1 agar panah hijau
                (f"{data.get('mtd_pct_topping', 0):.1f}% Topping/TC", 1) # Nilai 1 agar panah hijau
            ]
        )
        
        # --- Update Pie Chart ---
        # Kosongkan figure sebelum menggambar ulang
        self.fig_composition.clear()
        ax_composition = self.fig_composition.add_subplot(111)
        
        labels = ['Instore', 'Ojol', 'FNB Order']
        sizes = [
            data.get('mtd_sales_instore', 0),
            data.get('mtd_sales_ojol', 0),
            data.get('mtd_fnb_order_sales', 0)
        ]
        
        if sum(sizes) > 0:
            ax_composition.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90,
                               colors=['#66BB6A', '#FFA726', '#42A5F5'])
        else:
            ax_composition.text(0.5, 0.5, 'Tidak ada data', ha='center', va='center', color='gray')
            
        ax_composition.axis('equal')
class ChatWebWindow(QDialog):
    """Frameless dialog to show a web page internally using PyQtWebEngine and persist state."""
    def __init__(self, url_string, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chat with IT")
        self.resize(380, 600)  # Make it look more like a mobile/chat window profile
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        
        # Main layout with 1px border
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)
        self.setStyleSheet("""
            ChatWebWindow {
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 8px;
            }
        """)
        
        # --- Custom Title Bar ---
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(45)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: #006b38;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #008744;
                border-radius: 4px;
            }
        """)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        lbl_title = QLabel("💬 Chat with IT")
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()
        
        btn_minimize = QPushButton("—")
        btn_minimize.setFixedSize(30, 30)
        btn_minimize.clicked.connect(self.showMinimized)
        title_layout.addWidget(btn_minimize)
        
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(self.hide) # Only hide on close
        title_layout.addWidget(btn_close)
        
        main_layout.addWidget(self.title_bar)
        
        # --- Content Area ---
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        try:
            self.web_view = QWebEngineView()
            self.web_view.setUrl(QUrl(url_string))
            content_layout.addWidget(self.web_view)
        except ImportError:
            fallback_label = QLabel("Komponen WebBrowser internal (PyQtWebEngine) tidak tersedia.\nPastikan Anda sudah me-restart aplikasi.\n\nAtau buka link di browser eksternal:")
            fallback_label.setAlignment(Qt.AlignCenter)
            content_layout.addWidget(fallback_label)
            
            btn_open = QPushButton("Buka di Browser Eksternal")
            btn_open.setStyleSheet("""
                QPushButton {
                    background-color: #006b38; color: white; border-radius: 5px; padding: 10px; font-weight: bold;
                }
                QPushButton:hover { background-color: #008744; }
            """)
            btn_open.clicked.connect(lambda: self._open_external(url_string))
            content_layout.addWidget(btn_open, alignment=Qt.AlignCenter)
            
        main_layout.addWidget(content_widget)
        
        # Dragging state for title bar
        self._is_dragging = False
        self._drag_pos = None

    def _open_external(self, url_string):
        import webbrowser
        webbrowser.open(url_string)
        self.hide()
        
    def closeEvent(self, event):
        # Override so it just hides and doesn't get destroyed
        event.ignore()
        self.hide()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.title_bar.geometry().contains(event.pos()):
            self._is_dragging = True
            self._drag_pos = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False

class ChatITWidget(QPushButton):
    """Floating draggable button that sticks to the right side of the main window."""
    def __init__(self, parent=None, link=""):
        super().__init__("💬 Chat with IT", parent)
        self.link = link
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #006b38; 
                color: white; 
                border-radius: 15px; 
                padding: 6px 14px; 
                font-weight: bold; 
                font-size: 13px;
                border: 2px solid white;
            }
            QPushButton:hover {
                background-color: #008744;
            }
            QPushButton:pressed {
                background-color: #00502a;
            }
        """)
        self.adjustSize()
        self.setVisible(bool(self.link))
        
        # State for dragging
        self._is_dragging = False
        self._mouse_press_pos = None
        self._mouse_move_pos = None

        # State for dialog instance
        self.chat_window = None

    def set_link(self, link):
        self.link = link
        self.setVisible(bool(link))
        # Clear existing window if link changes
        if self.chat_window:
            self.chat_window.deleteLater()
            self.chat_window = None
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._mouse_press_pos = event.globalPos()
            self._mouse_move_pos = event.globalPos()
            self._is_dragging = False
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            global_pos = event.globalPos()
            diff = global_pos - self._mouse_move_pos
            
            # Initiate drag if moved far enough
            if not self._is_dragging and (global_pos - self._mouse_press_pos).manhattanLength() > 3:
                self._is_dragging = True
                
            if self._is_dragging and self.parent():
                new_pos = self.pos() + diff
                parent_rect = self.parent().rect()
                
                # Stick to right edge (margin of 15px)
                x = parent_rect.width() - self.width() - 15
                
                # Constrain vertically
                y = min(max(new_pos.y(), 10), parent_rect.height() - self.height() - 10)
                
                self.move(x, y)
                self._mouse_move_pos = global_pos
                event.accept()
                return # Don't pass event up while dragging
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._is_dragging and self.link:
                # Initialize window once so state is retained internally
                if self.chat_window is None:
                    self.chat_window = ChatWebWindow(self.link, self.window())
                
                # Calculate new position relative to this button
                try:
                    # Get button position relative to window
                    btn_pos = self.mapTo(self.window(), self.rect().topLeft())
                    
                    # Position above the button, aligned to right edge
                    # Window height is 600, width is 380 (defined in ChatWebWindow)
                    window_x = btn_pos.x() + self.width() - 380
                    window_y = btn_pos.y() - 600 - 10
                    
                    # Safety check if it goes above screen
                    if window_y < 10:
                        window_y = btn_pos.y() + self.height() + 10 # Place below if not enough room
                        
                    self.chat_window.move(window_x, window_y)
                except Exception as e:
                    logging.warning(f"Error repositioning chat window: {e}")
                    pass
                
                # Show, raise to front, and activate
                self.chat_window.showNormal()
                self.chat_window.raise_()
                self.chat_window.activateWindow()
                
        self._is_dragging = False
        self._mouse_press_pos = None
        super().mouseReleaseEvent(event)
        
    def reposition_to_edge(self):
        """Called automatically by main window resizeEvent to keep it on the right edge"""
        if self.parent():
            parent_rect = self.parent().rect()
            x = parent_rect.width() - self.width() - 15
            current_y = self.pos().y()
            # If widget is at initial position (top), move it to bottom-right
            if current_y <= 10:
                y = parent_rect.height() - self.height() - 25
            else:
                y = min(max(current_y, 10), parent_rect.height() - self.height() - 10)
            self.move(x, y)

class AnimatedSplashScreen(QWidget):
    def __init__(self, movie_path):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        self.gif_label = QLabel(self)
        self.movie = QMovie(movie_path)
        if self.movie.isValid():
            self.gif_label.setMovie(self.movie)
            self.movie.start()
            self.setFixedSize(self.movie.frameRect().size())
        else:
            self.gif_label.setText("Gagal memuat animasi...")
            self.setFixedSize(400, 200)
        self.message_label = QLabel(self.gif_label)
        self.message_label.setAlignment(Qt.AlignBottom | Qt.AlignCenter)
        self.message_label.setStyleSheet("color: white; font-weight: bold; background-color: rgba(0, 0, 0, 180); padding: 10px; border-radius: 3px;")
        layout.addWidget(self.gif_label)

    def showMessage(self, text, alignment=Qt.AlignBottom | Qt.AlignCenter, color=Qt.white):
        self.message_label.setText(text)
        self.message_label.adjustSize()
        self.message_label.move(
            int((self.width() - self.message_label.width()) / 2),
            int(self.height() - self.message_label.height() - 10)
        )


