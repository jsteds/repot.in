# utils/employee_utils.py
import sqlite3
import hashlib
import os
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox, 
    QMessageBox, QTableWidget, QTableWidgetItem, QPushButton, 
    QHBoxLayout, QHeaderView, QComboBox, QLabel, QWidget, QDateEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from utils.constants import BASE_DIR

# Konstanta Role untuk Login Aplikasi
ROLE_ADMIN = "Administrator"
ROLE_USER = "User"

# Lokasi Database Karyawan
DB_NAME = os.path.join(BASE_DIR, 'data', 'karyawan.db')

class EmployeeDB:
    def __init__(self):
        self.init_db()

    def init_db(self):
        """Membuat tabel karyawan jika belum ada dan update skema jika perlu."""
        os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Buat Tabel Dasar (Jika belum ada)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nik TEXT UNIQUE NOT NULL,
                nama_lengkap TEXT NOT NULL,
                jabatan TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role_aplikasi TEXT NOT NULL,
                join_date TEXT  -- Kolom baru (YYYY-MM-DD)
            )
        ''')
        
        # 2. Skema Migrasi: Cek apakah kolom join_date sudah ada (untuk database lama)
        cursor.execute("PRAGMA table_info(employees)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'join_date' not in columns:
            logging.info("Mengupdate skema database: Menambahkan kolom join_date")
            try:
                cursor.execute("ALTER TABLE employees ADD COLUMN join_date TEXT")
                # Set default date ke hari ini untuk data lama
                today = datetime.now().strftime("%Y-%m-%d")
                cursor.execute("UPDATE employees SET join_date = ?", (today,))
            except Exception as e:
                logging.error(f"Gagal migrasi database: {e}")

        # Tabel kredensial (untuk fitur Credential Manager)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                description TEXT
            )
        ''')
        
        # Cek admin default
        cursor.execute("SELECT count(*) FROM employees")
        if cursor.fetchone()[0] == 0:
            pass_hash = hashlib.sha256("admin".encode()).hexdigest()
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("INSERT INTO employees (nik, nama_lengkap, jabatan, password_hash, role_aplikasi, join_date) VALUES (?, ?, ?, ?, ?, ?)",
                           ("admin", "Administrator", "System Admin", pass_hash, ROLE_ADMIN, today))
            logging.info("Admin default dibuat (NIK: admin, Pass: admin)")
            
        conn.commit()
        conn.close()

    def get_all_employees(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Ambil join_date juga
        cursor.execute("SELECT id, nik, nama_lengkap, jabatan, role_aplikasi, join_date FROM employees")
        rows = cursor.fetchall()
        conn.close()
        employees = []
        for r in rows:
            # Handle jika join_date None (data sangat lama)
            j_date = r[5] if r[5] else datetime.now().strftime("%Y-%m-%d")
            employees.append({
                'id': r[0], 'nik': r[1], 'nama_lengkap': r[2], 
                'jabatan': r[3], 'role_aplikasi': r[4], 'join_date': j_date
            })
        return employees

    def add_employee(self, nik, nama, jabatan, password, role, join_date):
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            pass_hash = hashlib.sha256(password.encode()).hexdigest()
            cursor.execute("INSERT INTO employees (nik, nama_lengkap, jabatan, password_hash, role_aplikasi, join_date) VALUES (?, ?, ?, ?, ?, ?)",
                           (nik, nama, jabatan, pass_hash, role, join_date))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False 
        finally:
            conn.close()

    def update_employee(self, emp_id, nik, nama, jabatan, role, join_date, new_password=None):
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            if new_password:
                pass_hash = hashlib.sha256(new_password.encode()).hexdigest()
                cursor.execute("UPDATE employees SET nik=?, nama_lengkap=?, jabatan=?, role_aplikasi=?, join_date=?, password_hash=? WHERE id=?",
                               (nik, nama, jabatan, role, join_date, pass_hash, emp_id))
            else:
                cursor.execute("UPDATE employees SET nik=?, nama_lengkap=?, jabatan=?, role_aplikasi=?, join_date=? WHERE id=?",
                               (nik, nama, jabatan, role, join_date, emp_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def delete_employee(self, emp_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employees WHERE id=?", (emp_id,))
        conn.commit()
        conn.close()
        return True

    def check_login(self, nik, password):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        pass_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("SELECT role_aplikasi, nama_lengkap FROM employees WHERE nik=? AND password_hash=?", (nik, pass_hash))
        result = cursor.fetchone()
        conn.close()
        return result 

    # --- Methods untuk Credentials ---
    def get_all_credentials(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, platform, username, password, description FROM credentials")
        rows = cursor.fetchall()
        conn.close()
        creds = []
        for r in rows:
            creds.append({'id': r[0], 'platform': r[1], 'username': r[2], 'password': r[3], 'description': r[4]})
        return creds

    def add_credential(self, platform, username, password, description):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO credentials (platform, username, password, description) VALUES (?, ?, ?, ?)",
                       (platform, username, password, description))
        conn.commit()
        conn.close()

    def delete_credential(self, cred_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM credentials WHERE id=?", (cred_id,))
        conn.commit()
        conn.close()

    def get_aurora_credentials(self):
        """Mengambil kredensial Aurora dari database berdasarkan SM/ASM NIK dan kredensial platform."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Cari NIK Store Manager / Asst. Store Manager
        cursor.execute("SELECT nik FROM employees WHERE jabatan IN ('Store Manager', 'Asst. Store Manager') LIMIT 1")
        emp_row = cursor.fetchone()
        nik = emp_row[0] if emp_row else None
        
        # 2. Cari Password Aurora di Kredensial Manager
        cursor.execute("SELECT username, password FROM credentials WHERE platform LIKE '%Aurora%' COLLATE NOCASE LIMIT 1")
        cred_row = cursor.fetchone()
        
        conn.close()
        
        username = nik
        password = None
        
        if cred_row:
            if cred_row[0]: # Jika username secara eksplisit diset di kredensial, prioritaskan ini
                username = cred_row[0]
            password = cred_row[1]
            
        return username, password

# --- DIALOGS ---

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login Karyawan")
        self.setFixedSize(300, 150)
        self.db = EmployeeDB()
        self.logged_in_role = None
        self.logged_in_name = None
        
        layout = QFormLayout(self)
        self.nik_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        
        layout.addRow("NIK / ID:", self.nik_input)
        layout.addRow("Password:", self.pass_input)
        
        self.role_combo = QComboBox()
        self.role_combo.addItems([ROLE_USER, ROLE_ADMIN])
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.check_login)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        if parent: self._center_on_parent()

    def _center_on_parent(self):
        if self.parent():
            geo = self.frameGeometry()
            geo.moveCenter(self.parent().frameGeometry().center())
            self.move(geo.topLeft())

    def check_login(self):
        nik = self.nik_input.text()
        password = self.pass_input.text()
        
        result = self.db.check_login(nik, password)
        if result:
            role, nama = result
            self.logged_in_role = role
            self.logged_in_name = nama
            self.accept()
        else:
            QMessageBox.warning(self, "Login Gagal", "NIK atau Password salah.")

class AddEmployeeDialog(QDialog):
    def __init__(self, parent=None, employee_data=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Karyawan" if not employee_data else "Edit Karyawan")
        self.setFixedSize(400, 300) # Sedikit lebih tinggi untuk tanggal
        layout = QFormLayout(self)
        
        self.nik_input = QLineEdit()
        self.nama_input = QLineEdit()
        
        # --- PERUBAHAN 1: Jabatan menggunakan QComboBox ---
        self.jabatan_input = QComboBox()
        jabatan_list = ["Area Manager", "Store Manager", "Asst. Store Manager", "Staff", "Partimer"]
        self.jabatan_input.addItems(jabatan_list)
        
        # --- PERUBAHAN 3: Input Tanggal Bergabung ---
        self.join_date_input = QDateEdit()
        self.join_date_input.setCalendarPopup(True)
        self.join_date_input.setDisplayFormat("dd MMMM yyyy")
        self.join_date_input.setDate(QDate.currentDate()) # Default hari ini
        # --------------------------------------------
        
        self.role_input = QComboBox()
        self.role_input.addItems([ROLE_USER, ROLE_ADMIN])
        
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setPlaceholderText("Kosongkan jika tidak ubah password (Edit Mode)")
        
        layout.addRow("NIK:", self.nik_input)
        layout.addRow("Nama Lengkap:", self.nama_input)
        layout.addRow("Jabatan:", self.jabatan_input)
        layout.addRow("Tanggal Bergabung:", self.join_date_input) # Tambahkan ke layout
        layout.addRow("Role Aplikasi:", self.role_input)
        layout.addRow("Password:", self.pass_input)
        
        if employee_data:
            self.nik_input.setText(employee_data['nik'])
            self.nama_input.setText(employee_data['nama_lengkap'])
            
            index = self.jabatan_input.findText(employee_data['jabatan'], Qt.MatchFixedString)
            if index >= 0: self.jabatan_input.setCurrentIndex(index)
            
            # Set Tanggal dari data
            date_str = employee_data.get('join_date')
            if date_str:
                self.join_date_input.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
                
            self.role_input.setCurrentText(employee_data['role_aplikasi'])
            self.nik_input.setReadOnly(True) 
            
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_data(self):
        # Convert QDate to string YYYY-MM-DD for database
        join_date_str = self.join_date_input.date().toString("yyyy-MM-dd")
        
        return {
            'nik': self.nik_input.text(),
            'nama': self.nama_input.text(),
            'jabatan': self.jabatan_input.currentText(),
            'role': self.role_input.currentText(),
            'join_date': join_date_str,
            'password': self.pass_input.text()
        }

class EmployeeManagementDialog(QDialog):
    def __init__(self, current_role, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manajemen Data Karyawan")
        self.resize(900, 500) # Sedikit lebih lebar untuk kolom tanggal
        self.db = EmployeeDB()
        self.current_role = current_role
        self._init_ui()
        self.load_data()
        self._center_on_parent()

    def _center_on_parent(self):
        if self.parent():
            geo = self.frameGeometry()
            geo.moveCenter(self.parent().frameGeometry().center())
            self.move(geo.topLeft())

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Tambah Karyawan")
        self.edit_btn = QPushButton("Edit Karyawan")
        self.del_btn = QPushButton("Hapus Karyawan")
        
        self.add_btn.clicked.connect(self.add_employee)
        self.edit_btn.clicked.connect(self.edit_employee)
        self.del_btn.clicked.connect(self.delete_employee)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.table = QTableWidget()
        # --- PERUBAHAN 4: Tambah kolom Tanggal Gabung ---
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "NIK", "Nama Lengkap", "Jabatan", "Tgl Gabung", "Role App"])
        # ------------------------------------------------
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnHidden(0, True) 
        layout.addWidget(self.table)
        
        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

    def load_data(self):
        employees = self.db.get_all_employees()
        self.table.setRowCount(0)
        for emp in employees:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(emp['id'])))
            self.table.setItem(row, 1, QTableWidgetItem(emp['nik']))
            self.table.setItem(row, 2, QTableWidgetItem(emp['nama_lengkap']))
            self.table.setItem(row, 3, QTableWidgetItem(emp['jabatan']))
            # Format tanggal untuk tampilan tabel (dd-mm-yyyy)
            try:
                date_obj = datetime.strptime(emp['join_date'], "%Y-%m-%d")
                date_display = date_obj.strftime("%d-%m-%Y")
            except:
                date_display = emp['join_date']
            self.table.setItem(row, 4, QTableWidgetItem(date_display))
            self.table.setItem(row, 5, QTableWidgetItem(emp['role_aplikasi']))

    def add_employee(self):
        if self.current_role != ROLE_ADMIN:
            QMessageBox.warning(self, "Akses Ditolak", "Hanya Administrator yang bisa menambah karyawan.")
            return
            
        dialog = AddEmployeeDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if not data['nik'] or not data['password']:
                QMessageBox.warning(self, "Gagal", "NIK dan Password wajib diisi.")
                return
                
            # Panggil fungsi DB yang baru (dengan join_date)
            if self.db.add_employee(data['nik'], data['nama'], data['jabatan'], data['password'], data['role'], data['join_date']):
                QMessageBox.information(self, "Sukses", "Karyawan berhasil ditambahkan.")
                self.load_data()
            else:
                QMessageBox.critical(self, "Error", "Gagal menambah karyawan (NIK mungkin sudah ada).")

    def edit_employee(self):
        if self.current_role != ROLE_ADMIN:
            QMessageBox.warning(self, "Akses Ditolak", "Hanya Administrator yang bisa mengedit.")
            return
            
        selected = self.table.currentRow()
        if selected < 0: return
        
        # Ambil data dari database berdasarkan ID (lebih aman)
        emp_id = int(self.table.item(selected, 0).text())
        # Kita cari data lengkap dari list yang dimuat di memori atau query ulang
        # Untuk simpelnya, kita ambil dari tabel, tapi tanggal harus dikonversi balik
        
        # Query single employee data untuk memastikan format tanggal benar
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT nik, nama_lengkap, jabatan, role_aplikasi, join_date FROM employees WHERE id=?", (emp_id,))
        res = c.fetchone()
        conn.close()
        
        if not res: return

        emp_data = {
            'nik': res[0],
            'nama_lengkap': res[1],
            'jabatan': res[2],
            'role_aplikasi': res[3],
            'join_date': res[4] # Format YYYY-MM-DD dari DB
        }
        
        dialog = AddEmployeeDialog(self, emp_data)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if self.db.update_employee(emp_id, data['nik'], data['nama'], data['jabatan'], data['role'], data['join_date'], data['password']):
                QMessageBox.information(self, "Sukses", "Data karyawan diperbarui.")
                self.load_data()
            else:
                QMessageBox.critical(self, "Error", "Gagal memperbarui data.")

    def delete_employee(self):
        if self.current_role != ROLE_ADMIN: return
        selected = self.table.currentRow()
        if selected < 0: return
        
        emp_id = int(self.table.item(selected, 0).text())
        nama = self.table.item(selected, 2).text()
        
        if QMessageBox.question(self, "Konfirmasi", f"Hapus karyawan {nama}?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_employee(emp_id)
            self.load_data()

class CredentialManagementDialog(QDialog):
    def __init__(self, current_role, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manajemen Kredensial Aplikasi")
        self.resize(600, 400)
        self.db = EmployeeDB()
        self.current_role = current_role
        
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Platform", "Username", "Password", "Ket."])
        self.table.setColumnHidden(0, True)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Tambah")
        del_btn = QPushButton("Hapus")
        add_btn.clicked.connect(self.add_cred)
        del_btn.clicked.connect(self.del_cred)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)
        
        self.load_data()
        if parent:
            geo = self.frameGeometry()
            geo.moveCenter(parent.frameGeometry().center())
            self.move(geo.topLeft())

    def load_data(self):
        creds = self.db.get_all_credentials()
        self.table.setRowCount(0)
        for c in creds:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(c['id'])))
            self.table.setItem(r, 1, QTableWidgetItem(c['platform']))
            self.table.setItem(r, 2, QTableWidgetItem(c['username']))
            self.table.setItem(r, 3, QTableWidgetItem(c['password']))
            self.table.setItem(r, 4, QTableWidgetItem(c['description']))

    def add_cred(self):
        d = QDialog(self)
        l = QFormLayout(d)
        p = QLineEdit(); u = QLineEdit(); pw = QLineEdit(); desc = QLineEdit()
        l.addRow("Platform:", p); l.addRow("Username:", u); l.addRow("Password:", pw); l.addRow("Ket:", desc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        l.addWidget(bb)
        if d.exec_() == QDialog.Accepted:
            self.db.add_credential(p.text(), u.text(), pw.text(), desc.text())
            self.load_data()

    def del_cred(self):
        row = self.table.currentRow()
        if row >= 0:
            cid = int(self.table.item(row, 0).text())
            self.db.delete_credential(cid)
            self.load_data()