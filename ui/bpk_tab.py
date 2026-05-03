import os
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QFrame, QButtonGroup,
    QRadioButton, QGroupBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSlot
from PyQt5.QtGui import QColor, QFont

from modules.database_manager import DatabaseManager
from modules.config_manager import ConfigManager
from ui.bpk_dialog import BPKDialog


class SettingsPanel(QFrame):
    """Panel pengaturan yang bisa ditampilkan/disembunyikan."""
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("bpk_settings_panel")
        self._init_ui()
        self.setVisible(False)
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        
        title = QLabel("⚙️  Pengaturan BPK")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(title)
        
        # --- Name Format Group ---
        name_group = QGroupBox("Format Nama pada Cetak BPK")
        name_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        name_layout = QHBoxLayout(name_group)
        name_layout.setSpacing(20)
        
        self.rb_full = QRadioButton("Nama Lengkap")
        self.rb_first = QRadioButton("Nama Depan Saja")
        
        btn_group = QButtonGroup(self)
        btn_group.addButton(self.rb_full)
        btn_group.addButton(self.rb_first)
        
        name_layout.addWidget(self.rb_full)
        name_layout.addWidget(self.rb_first)
        name_layout.addStretch()
        
        # Example label
        self.lbl_example = QLabel()
        self.lbl_example.setStyleSheet("font-style: italic; font-size: 11px;")
        name_layout.addWidget(self.lbl_example)
        
        layout.addWidget(name_group)
        
        # --- Paper Mode & Offset Group ---
        paper_group = QGroupBox("Pengaturan Kertas & Cetak")
        paper_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        paper_layout = QVBoxLayout(paper_group)
        
        # Mode Kertas
        mode_layout = QHBoxLayout()
        self.rb_a4 = QRadioButton("A4 HVS (Lengkap Garis & Logo)")
        self.rb_continuous = QRadioButton("2-Ply Pre-Printed (Hanya Data)")
        
        paper_btn_group = QButtonGroup(self)
        paper_btn_group.addButton(self.rb_a4)
        paper_btn_group.addButton(self.rb_continuous)
        
        mode_layout.addWidget(self.rb_a4)
        mode_layout.addWidget(self.rb_continuous)
        mode_layout.addStretch()
        paper_layout.addLayout(mode_layout)
        
        # Offsets
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("Geser Kanan (X):"))
        from PyQt5.QtWidgets import QDoubleSpinBox
        self.spin_offset_x = QDoubleSpinBox()
        self.spin_offset_x.setRange(-50.0, 50.0)
        self.spin_offset_x.setSuffix(" mm")
        self.spin_offset_x.setSingleStep(1.0)
        offset_layout.addWidget(self.spin_offset_x)
        
        offset_layout.addWidget(QLabel("  Geser Bawah (Y):"))
        self.spin_offset_y = QDoubleSpinBox()
        self.spin_offset_y.setRange(-50.0, 50.0)
        self.spin_offset_y.setSuffix(" mm")
        self.spin_offset_y.setSingleStep(1.0)
        offset_layout.addWidget(self.spin_offset_y)
        offset_layout.addStretch()
        
        paper_layout.addLayout(offset_layout)
        layout.addWidget(paper_group)
        
        # Load current setting
        config_data = self.config_manager.get_config()
        mode = config_data.get('bpk_name_mode', 'full')
        if mode == 'first':
            self.rb_first.setChecked(True)
        else:
            self.rb_full.setChecked(True)
        self._update_example()
        
        paper_mode = config_data.get('bpk_paper_mode', 'a4')
        if paper_mode == 'continuous':
            self.rb_continuous.setChecked(True)
        else:
            self.rb_a4.setChecked(True)
            
        self.spin_offset_x.setValue(float(config_data.get('bpk_offset_x', 0.0)))
        self.spin_offset_y.setValue(float(config_data.get('bpk_offset_y', 0.0)))
        
        self.rb_full.toggled.connect(self._on_mode_changed)
        self.rb_first.toggled.connect(self._on_mode_changed)
        self.rb_a4.toggled.connect(self._on_paper_changed)
        self.rb_continuous.toggled.connect(self._on_paper_changed)
        self.spin_offset_x.valueChanged.connect(self._on_offset_changed)
        self.spin_offset_y.valueChanged.connect(self._on_offset_changed)
        
    def _update_example(self):
        is_first = self.rb_first.isChecked()
        if is_first:
            self.lbl_example.setText("Contoh: 147251/KEVIN")
        else:
            self.lbl_example.setText("Contoh: 147251/KEVIN CRIST ADRIAN")
            
    def _on_mode_changed(self):
        self._update_example()
        mode = 'first' if self.rb_first.isChecked() else 'full'
        self.config_manager.set_value('bpk_name_mode', mode)

    def _on_paper_changed(self):
        paper_mode = 'continuous' if self.rb_continuous.isChecked() else 'a4'
        self.config_manager.set_value('bpk_paper_mode', paper_mode)
        
    def _on_offset_changed(self):
        self.config_manager.set_value('bpk_offset_x', self.spin_offset_x.value())
        self.config_manager.set_value('bpk_offset_y', self.spin_offset_y.value())


class BPKTab(QWidget):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        
        # Determine store_code
        self.store_code = ""
        try:
            site = self.config_manager.site_list[self.config_manager.get_current_site_index()]
            self.store_code = site.split(" - ")[0]
        except:
            pass
            
        self._init_ui()
        self.refresh_data()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 1. Summary Cards Layout
        cards_layout = QHBoxLayout()
        
        self.lbl_total_store = self._create_summary_card("Total BPK (Store)", "Rp 0")
        self.lbl_total_ho = self._create_summary_card("Total BPK (HO / Claimed)", "Rp 0")
        self.lbl_total_all = self._create_summary_card("Total BPK Keseluruhan", "Rp 0")
        self.lbl_total_done = self._create_summary_card("Sudah Cair / Selesai", "Rp 0")
        
        cards_layout.addWidget(self.lbl_total_store)
        cards_layout.addWidget(self.lbl_total_ho)
        cards_layout.addWidget(self.lbl_total_all)
        cards_layout.addWidget(self.lbl_total_done)
        
        layout.addLayout(cards_layout)
        
        # 2. Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.btn_new = QPushButton("Buat BPK Baru")
        self.btn_new.clicked.connect(self._generate_new_bpk)
        
        self.btn_open = QPushButton(" Buka File")
        self.btn_open.clicked.connect(self._open_file)
        self.btn_open.setEnabled(False)
        
        self.btn_print = QPushButton("Print Ulang")
        self.btn_print.clicked.connect(self._print_file)
        self.btn_print.setEnabled(False)
        
        self.btn_claim = QPushButton("Tandai Claimed/HO")
        self.btn_claim.clicked.connect(self._mark_claimed)
        self.btn_claim.setEnabled(False)
        
        self.btn_done = QPushButton("Tandai Selesai/Cair")
        self.btn_done.clicked.connect(self._mark_done)
        self.btn_done.setEnabled(False)
        self.btn_done.setToolTip("Tandai BPK sebagai sudah dibayarkan/cair. Nominal akan dikeluarkan dari total.")
        
        self.btn_delete = QPushButton("Hapus Histori")
        self.btn_delete.clicked.connect(self._delete_history)
        self.btn_delete.setEnabled(False)
        
        # Gear button (settings toggle)
        self.btn_gear = QPushButton("⚙️")
        self.btn_gear.setToolTip("Pengaturan BPK")
        self.btn_gear.setCheckable(True)
        self.btn_gear.setFixedWidth(38)
        self.btn_gear.setStyleSheet("""
            QPushButton { border-radius: 4px; padding: 4px; font-size: 16px; }
            QPushButton:checked { background-color: #2980b9; color: white; }
        """)
        self.btn_gear.toggled.connect(self._toggle_settings)
        
        toolbar_layout.addWidget(self.btn_new)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_open)
        toolbar_layout.addWidget(self.btn_print)
        toolbar_layout.addWidget(self.btn_claim)
        toolbar_layout.addWidget(self.btn_done)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_gear)
        
        layout.addLayout(toolbar_layout)
        
        # 3. Settings Panel (hidden by default)
        self.settings_panel = SettingsPanel(self.config_manager, self)
        layout.addWidget(self.settings_panel)
        
        # 4. Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Tanggal", "No. Cek", "Rek Lawan", "Uraian", "Nominal", "Status"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Tanggal
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # No. Cek
        header.setSectionResizeMode(3, QHeaderView.Stretch)           # Rek Lawan
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # Uraian
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Nominal
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Status
        
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Hidden column to store pdf_path
        self.table.setColumnCount(8)
        self.table.hideColumn(7)
        
        layout.addWidget(self.table)
        
    def _create_summary_card(self, title, value_text):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFrameShadow(QFrame.Raised)
        # No hardcoded colors — inherit from theme
        card.setProperty("class", "bpk_summary_card")
        
        card_layout = QVBoxLayout(card)
        
        lbl_title = QLabel(title)
        lbl_title.setObjectName("bpk_card_title")
        
        lbl_val = QLabel(value_text)
        lbl_val.setObjectName("bpk_card_value")
        lbl_val.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_val.setAlignment(Qt.AlignLeft)
        
        card_layout.addWidget(lbl_title)
        card_layout.addWidget(lbl_val)
        
        card.value_label = lbl_val
        return card
        
    def _update_summary(self, history_data):
        # Only 'Store' and 'Claimed' count toward outstanding totals
        total_store = sum(d['nominal'] for d in history_data if d['status'] == 'Store')
        total_ho    = sum(d['nominal'] for d in history_data if d['status'] == 'Claimed')
        total_done  = sum(d['nominal'] for d in history_data if d['status'] == 'Done')
        # Total keseluruhan = outstanding only (Done sudah keluar)
        total_all = total_store + total_ho
        
        def format_rp(val):
            return f"Rp {val:,.0f}".replace(",", ".")
            
        self.lbl_total_store.value_label.setText(format_rp(total_store))
        self.lbl_total_ho.value_label.setText(format_rp(total_ho))
        self.lbl_total_all.value_label.setText(format_rp(total_all))
        self.lbl_total_done.value_label.setText(format_rp(total_done))

    @pyqtSlot(bool)
    def _toggle_settings(self, checked: bool):
        self.settings_panel.setVisible(checked)

    def refresh_data(self):
        db = DatabaseManager()
        history = db.get_bpk_history(self.store_code)
        
        self.table.setRowCount(0)
        for row_data in history:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            
            nominal_str = f"Rp {row_data['nominal']:,.0f}".replace(",", ".")
            
            id_item = QTableWidgetItem(str(row_data['id']))
            date_item = QTableWidgetItem(row_data['tanggal'])
            cek_item = QTableWidgetItem(row_data['dokumen_no'])
            rek_item = QTableWidgetItem(row_data['rek_lawan'])
            desc_item = QTableWidgetItem(row_data['uraian'].upper())
            nom_item = QTableWidgetItem(nominal_str)
            status_item = QTableWidgetItem(row_data['status'])
            path_item = QTableWidgetItem(row_data['pdf_path'])
            
            # Styling per status
            status = row_data['status']
            if status == 'Claimed':
                bg_color = QColor("#e8f5e9")  # light green
                for item in [id_item, date_item, cek_item, rek_item, desc_item, nom_item, status_item]:
                    item.setBackground(bg_color)
            elif status == 'Done':
                bg_color = QColor("#bdbdbd")  # abu-abu — sudah selesai/cair
                fg_color = QColor("#616161")
                for item in [id_item, date_item, cek_item, rek_item, desc_item, nom_item, status_item]:
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)
            
            id_item.setTextAlignment(Qt.AlignCenter)
            nom_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_item.setTextAlignment(Qt.AlignCenter)
            
            self.table.setItem(row_idx, 0, id_item)
            self.table.setItem(row_idx, 1, date_item)
            self.table.setItem(row_idx, 2, cek_item)
            self.table.setItem(row_idx, 3, rek_item)
            self.table.setItem(row_idx, 4, desc_item)
            self.table.setItem(row_idx, 5, nom_item)
            self.table.setItem(row_idx, 6, status_item)
            self.table.setItem(row_idx, 7, path_item)
            
        self._update_summary(history)
        self._on_selection_changed()

    def _on_selection_changed(self):
        selected_rows = self.table.selectedItems()
        has_selection = len(selected_rows) > 0
        
        self.btn_open.setEnabled(has_selection)
        self.btn_print.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        
        if has_selection:
            row = self.table.currentRow()
            status = self.table.item(row, 6).text()
            # Claim: only from Store
            self.btn_claim.setEnabled(status == 'Store')
            # Done: hanya dari Claimed (Store harus Claimed dulu)
            self.btn_done.setEnabled(status == 'Claimed')
        else:
            self.btn_claim.setEnabled(False)
            self.btn_done.setEnabled(False)

    def _get_selected_data(self):
        row = self.table.currentRow()
        if row < 0: return None
        return {
            'id': int(self.table.item(row, 0).text()),
            'pdf_path': self.table.item(row, 7).text(),
            'status': self.table.item(row, 6).text()
        }

    def _generate_new_bpk(self):
        dialog = BPKDialog(self.config_manager, self)
        dialog.bpk_generated.connect(self.refresh_data)
        dialog.exec_()

    def _open_file(self):
        data = self._get_selected_data()
        if not data: return
        path = data['pdf_path']
        if os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                logging.error(f"Failed to open PDF: {e}")
                QMessageBox.warning(self, "Error", f"Gagal membuka file:\n{e}")
        else:
            QMessageBox.warning(self, "Tidak Ditemukan", "File PDF tidak ditemukan. Mungkin telah dipindahkan atau dihapus.")

    def _print_file(self):
        data = self._get_selected_data()
        if not data: return
        path = data['pdf_path']
        if not os.path.exists(path):
            QMessageBox.warning(self, "Tidak Ditemukan", "File PDF tidak ditemukan.")
            return

        try:
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from modules.bpk_generator import BPKGenerator

            printer = QPrinter()
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle("Pilih Printer untuk BPK")
            if dialog.exec_() == QPrintDialog.Accepted:
                printer_name = printer.printerName()
                gen = BPKGenerator(self.config_manager)
                gen.print_pdf(path, printer_name=printer_name, parent=self)
        except Exception as e:
            logging.error(f"Failed to open print dialog: {e}")
            # Fallback: gunakan print_pdf langsung tanpa dialog
            try:
                from modules.bpk_generator import BPKGenerator
                gen = BPKGenerator(self.config_manager)
                gen.print_pdf(path, printer_name="", parent=self)
            except Exception as e2:
                QMessageBox.warning(self, "Error", f"Gagal mencetak:\n{e2}")

    def _mark_claimed(self):
        data = self._get_selected_data()
        if not data: return
        reply = QMessageBox.question(
            self, "Konfirmasi",
            "Tandai BPK ini sebagai 'Claimed/HO'?\n\nBPK yang sudah di-claim akan masuk ke kategori HO.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            db = DatabaseManager()
            if db.update_bpk_status(data['id'], 'Claimed'):
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "Gagal mengupdate status di database.")

    def _mark_done(self):
        data = self._get_selected_data()
        if not data: return
        reply = QMessageBox.question(
            self, "Konfirmasi — Tandai Selesai/Cair",
            "Tandai BPK ini sebagai sudah dibayarkan / cair?\n\n"
            "Nominal BPK ini akan dikeluarkan dari Total BPK yang masih berjalan.\n"
            "Status ini tidak dapat dibatalkan.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            db = DatabaseManager()
            if db.update_bpk_status(data['id'], 'Done'):
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "Gagal mengupdate status di database.")

    def _delete_history(self):
        data = self._get_selected_data()
        if not data: return
        reply = QMessageBox.question(
            self, "Hapus Histori",
            "Apakah Anda yakin ingin menghapus histori BPK ini?\n\n(Catatan: File PDF asli tidak akan dihapus dari komputer Anda).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            db = DatabaseManager()
            if db.delete_bpk_history(data['id']):
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "Gagal menghapus histori dari database.")
