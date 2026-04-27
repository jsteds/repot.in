import os
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDoubleSpinBox, QDateEdit, QPushButton, QMessageBox, 
    QFormLayout
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl

from modules.bpk_generator import BPKGenerator, BPKEntry
from modules.config_manager import ConfigManager
from utils.employee_utils import EmployeeDB
from modules.database_manager import DatabaseManager

class BPKDialog(QDialog):
    bpk_generated = pyqtSignal()
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Bukti Pengeluaran Kas (BPK)")
        self.resize(450, 300)
        self.config_manager = config_manager
        
        self.generator = BPKGenerator(self.config_manager)
        self.generated_pdf_path = None
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Info Store
        info_layout = QHBoxLayout()
        info_label = QLabel(f"<b>Toko:</b> {self.generator.store_code} - {self.generator.store_name}")
        info_layout.addWidget(info_label)
        layout.addLayout(info_layout)
        
        # Form Input
        form_layout = QFormLayout()
        
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setDisplayFormat("dd/MM/yyyy")
        form_layout.addRow("Tanggal:", self.date_input)
        
        self.rek_input = QLineEdit()
        self.rek_input.setPlaceholderText("Nama/No. Rekening Lawan")
        form_layout.addRow("No. Rek Lawan:", self.rek_input)
        
        self.cek_input = QLineEdit()
        self.cek_input.setPlaceholderText("Nomor Cek / BG (Opsional)")
        form_layout.addRow("No. Cek / BG:", self.cek_input)
        
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setRange(0, 9999999999.99)
        self.amount_input.setDecimals(0)
        self.amount_input.setGroupSeparatorShown(True)
        self.amount_input.setPrefix("Rp ")
        form_layout.addRow("Jumlah:", self.amount_input)
        
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Uraian pengeluaran (maks. 50 karakter)")
        self.desc_input.setMaxLength(50)
        form_layout.addRow("Uraian:", self.desc_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("📄 Generate && Simpan PDF")
        self.generate_btn.clicked.connect(self._generate_pdf)
        self.generate_btn.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; border: none; border-radius: 4px; padding: 8px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #218838; }
        """)
        btn_layout.addWidget(self.generate_btn)
        
        self.print_btn = QPushButton("🖨️ Print")
        self.print_btn.clicked.connect(self._print_pdf)
        self.print_btn.setEnabled(False) # Enable after generation
        self.print_btn.setStyleSheet("""
            QPushButton { background-color: #17a2b8; color: white; border: none; border-radius: 4px; padding: 8px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #138496; }
            QPushButton:disabled { background-color: #a8d5db; color: #f0f0f0; }
        """)
        btn_layout.addWidget(self.print_btn)
        
        self.close_btn = QPushButton("Tutup")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setStyleSheet("""
            QPushButton { background-color: #6c757d; color: white; border: none; border-radius: 4px; padding: 8px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6268; }
        """)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
    def _get_entry_data(self) -> BPKEntry:
        diajukan_info = ""
        disetujui_info = ""
        diberikan_info = ""
        diterima_info = ""
        
        # Read name mode setting from config
        config_data = self.config_manager.get_config()
        use_first_name_only = config_data.get('bpk_name_mode', 'full') == 'first'
        
        def fmt_name(nama: str) -> str:
            """Return first word only if setting is 'first', else full name. Already uppercase."""
            nama = nama.upper()
            return nama.split()[0] if use_first_name_only and nama.split() else nama
        
        def fmt_emp(emp) -> str:
            return f"{emp['nik']}/{fmt_name(emp['nama_lengkap'])}"
        
        try:
            db = EmployeeDB()
            employees = db.get_all_employees()
            
            def has_role(emp, role_name):
                return emp['jabatan'] == role_name or emp['role_aplikasi'] == role_name
                
            sm = next((e for e in employees if has_role(e, 'Store Manager')), None)
            
            if sm:
                disetujui_info = fmt_emp(sm)
                
                asms = [e for e in employees if has_role(e, 'Asst. Store Manager')]
                staffs = [e for e in employees if has_role(e, 'Staff')]
                
                if len(asms) >= 2:
                    diajukan_info = fmt_emp(asms[0])
                    diterima_info = diajukan_info
                    diberikan_info = fmt_emp(asms[1])
                elif len(asms) == 1:
                    diberikan_info = fmt_emp(asms[0])
                    if len(staffs) >= 1:
                        diajukan_info = fmt_emp(staffs[0])
                        diterima_info = diajukan_info
                    
        except Exception as e:
            logging.error(f"Failed to fetch employee info for BPK: {e}")
            
        return BPKEntry(
            counterparty_account=self.rek_input.text().strip(),
            description=self.desc_input.text().strip(),
            amount=self.amount_input.value(),
            check_number=self.cek_input.text().strip() or "-",
            date=self.date_input.date().toString("dd/MM/yyyy"),
            diajukan_info=diajukan_info,
            disetujui_info=disetujui_info,
            diberikan_info=diberikan_info,
            diterima_info=diterima_info
        )
        
    def _validate_inputs(self) -> bool:
        if not self.rek_input.text().strip():
            QMessageBox.warning(self, "Peringatan", "No. Rek Lawan tidak boleh kosong.")
            self.rek_input.setFocus()
            return False
        if not self.desc_input.text().strip():
            QMessageBox.warning(self, "Peringatan", "Uraian tidak boleh kosong.")
            self.desc_input.setFocus()
            return False
        if self.amount_input.value() <= 0:
            QMessageBox.warning(self, "Peringatan", "Jumlah pengeluaran harus lebih dari 0.")
            self.amount_input.setFocus()
            return False
        return True
        
    def _generate_pdf(self):
        if not self._validate_inputs():
            return
            
        try:
            entry = self._get_entry_data()
            self.generated_pdf_path = self.generator.generate_pdf(entry)
            
            # Save to history database
            db = DatabaseManager()
            # Store 'dokumen_no' as the Check Number from entry
            saved = db.save_bpk_history(
                store_code=self.generator.store_code,
                tanggal=entry.date,
                dokumen_no=entry.check_number,
                rek_lawan=entry.counterparty_account,
                uraian=entry.description,
                nominal=entry.amount,
                pdf_path=self.generated_pdf_path
            )
            
            if saved:
                self.bpk_generated.emit()
                QMessageBox.information(self, "Sukses", f"PDF berhasil dibuat dan histori disimpan!\nDisimpan di:\n{self.generated_pdf_path}")
                self.accept()  # Close the dialog on success
            else:
                QMessageBox.warning(self, "Peringatan", "PDF berhasil dibuat, tetapi gagal menyimpan histori ke database.")
            
        except Exception as e:
            logging.error(f"Gagal generate BPK PDF: {e}")
            QMessageBox.critical(self, "Error", f"Terjadi kesalahan saat generate PDF:\n{str(e)}")

    def _print_pdf(self):
        if not self.generated_pdf_path or not os.path.exists(self.generated_pdf_path):
            QMessageBox.warning(self, "Peringatan", "PDF belum digenerate atau file tidak ditemukan.")
            return
            
        self.generator.print_pdf(self.generated_pdf_path, parent=self)
