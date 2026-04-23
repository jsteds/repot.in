# ui/waste_conversion_tab.py
import json
import os
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, 
    QFrame, QGraphicsDropShadowEffect, QPushButton, QDialog, 
    QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox, QStyle,
    QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont, QColor
from utils.constants import WASTE_RECIPES_FILE

# --- DIALOG 1: TAMBAH PRODUK BARU (Header Saja) ---
class AddProductDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buat Produk Baru")
        self.setFixedSize(400, 200)
        layout = QFormLayout(self)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Contoh: Milk Tea Base")
        
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Contoh: W000008")
        
        self.uom_input = QLineEdit()
        self.uom_input.setPlaceholderText("G / ML")
        
        layout.addRow("Nama Base", self.name_input)
        layout.addRow("Artikel", self.code_input)
        layout.addRow("Satuan (UOM)", self.uom_input)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Validasi", "Nama produk wajib diisi.")
            return
        self.accept()
        
    def get_data(self):
        return {
            "product_name": self.name_input.text().strip(),
            "product_code": self.code_input.text().strip(),
            "uom": self.uom_input.text().strip().upper() or "UNIT",
            "ingredients": [] # Resep kosong dulu
        }

# --- DIALOG 2: EDITOR RESEP LENGKAP (Header + Bahan) ---
class RecipeEditorDialog(QDialog):
    def __init__(self, recipe_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Kelola Resep & Produk")
        self.resize(700, 550)
        
        # Deep copy data agar aman saat cancel
        self.recipe_data = json.loads(json.dumps(recipe_data))
        self.ingredients = self.recipe_data.get('ingredients', [])
        
        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- BAGIAN 1: EDIT INFO PRODUK UTAMA ---
        info_group = QFrame()
        info_group.setObjectName("wasteInfoGroup")
        info_layout = QFormLayout(info_group)
        
        self.prod_name_edit = QLineEdit(self.recipe_data.get('product_name', ''))
        self.prod_code_edit = QLineEdit(self.recipe_data.get('product_code', ''))
        self.prod_uom_edit = QLineEdit(self.recipe_data.get('uom', ''))
        
        info_layout.addRow("Nama Produk Base", self.prod_name_edit)
        info_layout.addRow("Artikel", self.prod_code_edit)
        info_layout.addRow("UOM", self.prod_uom_edit)
        
        layout.addWidget(QLabel("<b>Info Produk</b>"))
        layout.addWidget(info_group)
        
        # --- BAGIAN 2: INPUT BAHAN BAKU ---
        input_group = QFrame()
        input_group.setObjectName("wasteInputGroup")
        h_layout = QHBoxLayout(input_group)
        
        self.raw_code = QLineEdit(); self.raw_code.setPlaceholderText("Artikel")
        self.raw_name = QLineEdit(); self.raw_name.setPlaceholderText("Nama Raw Material")
        self.raw_factor = QDoubleSpinBox(); self.raw_factor.setRange(0, 999999); self.raw_factor.setDecimals(10); self.raw_factor.setPrefix("")
        self.raw_factor.setMinimumWidth(100) # Pastikan lebarnya cukup
        self.raw_factor.setToolTip("Faktor Pengali")
        self.raw_uom = QLineEdit(); self.raw_uom.setPlaceholderText("UOM"); self.raw_uom.setFixedWidth(60)
        
        add_btn = QPushButton("Tambah Bahan")
        add_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        add_btn.clicked.connect(self._add_ingredient)
        
        h_layout.addWidget(self.raw_code)
        h_layout.addWidget(self.raw_name, 1)
        h_layout.addWidget(self.raw_factor)
        h_layout.addWidget(self.raw_uom)
        h_layout.addWidget(add_btn)
        
        layout.addWidget(QLabel("<b>Komposisi / Bahan Baku:</b>"))
        layout.addWidget(input_group)
        
        # --- TABEL BAHAN ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Kode", "Nama Material", "Faktor", "UOM", "Aksi"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        # --- FOOTER ---
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _populate_table(self):
        self.table.setRowCount(len(self.ingredients))
        for row, item in enumerate(self.ingredients):
            self.table.setItem(row, 0, QTableWidgetItem(item.get('raw_code', '')))
            self.table.setItem(row, 1, QTableWidgetItem(item.get('raw_name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get('factor', 0))))
            self.table.setItem(row, 3, QTableWidgetItem(item.get('uom', '')))
            
            del_btn = QPushButton("Hapus")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("color: #ff6b6b; border: 1px solid #5a2d2d; background-color: #3a1c1d; border-radius: 3px;")
            del_btn.clicked.connect(lambda _, r=row: self._delete_ingredient(r))
            self.table.setCellWidget(row, 4, del_btn)

    def _add_ingredient(self):
        name = self.raw_name.text().strip()
        factor = self.raw_factor.value()
        if not name or factor <= 0:
            QMessageBox.warning(self, "Invalid", "Nama material dan faktor harus valid.")
            return
            
        new_item = {
            "raw_code": self.raw_code.text().strip(),
            "raw_name": name,
            "factor": factor,
            "uom": self.raw_uom.text().strip()
        }
        self.ingredients.append(new_item)
        self.raw_code.clear(); self.raw_name.clear(); self.raw_factor.setValue(0); self.raw_uom.clear()
        self._populate_table()

    def _delete_ingredient(self, row):
        if 0 <= row < len(self.ingredients):
            del self.ingredients[row]
            self._populate_table()

    def _save_and_accept(self):
        # Update data header produk
        self.recipe_data['product_name'] = self.prod_name_edit.text().strip()
        self.recipe_data['product_code'] = self.prod_code_edit.text().strip()
        self.recipe_data['uom'] = self.prod_uom_edit.text().strip()
        self.recipe_data['ingredients'] = self.ingredients
        self.accept()

    def get_updated_recipe(self):
        return self.recipe_data


# --- TAB UTAMA ---
class WasteConversionTab(QWidget):
    def __init__(self, parent_app=None):
        super().__init__()
        self.parent_app = parent_app
        self.recipes_data = [] 
        self.current_recipe = None
        
        self._init_ui()
        self._load_recipes()
        self._refresh_recent_row() # Load recent cards on start

    # --- Tabel Toleransi Waste Budgeting ---
    WASTE_BUDGET_TABLE = [
        (0,          120_000_000, 0.0050),  # 0 – 120 jt  → 0.50%
        (120_000_001, 130_000_000, 0.0030),  # 120 – 130 jt → 0.30%
        (130_000_001, 150_000_000, 0.0025),  # 130 – 150 jt → 0.25%
        (150_000_001, 200_000_000, 0.0020),  # 150 – 200 jt → 0.20%
        (200_000_001, float('inf'), 0.0015),  # > 200 jt     → 0.15%
    ]

    @staticmethod
    def _get_tolerance(sales: float) -> float:
        """Kembalikan persentase toleransi waste berdasarkan sales MTD."""
        for low, high, pct in WasteConversionTab.WASTE_BUDGET_TABLE:
            if low <= sales <= high:
                return pct
        return 0.0050  # fallback

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20); main_layout.setSpacing(30)

        # --- PANEL KIRI: INPUT ---
        input_container = QFrame()
        input_container.setObjectName("wasteInputContainer")
        shadow = QGraphicsDropShadowEffect(); shadow.setBlurRadius(15); shadow.setYOffset(4); shadow.setColor(QColor(0, 0, 0, 30))
        input_container.setGraphicsEffect(shadow)
        
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(20, 30, 20, 30); input_layout.setSpacing(15)

        # --- WASTE BUDGET FRAME (di atas INPUT PRODUCT) ---
        self.budget_frame = QFrame()
        self.budget_frame.setObjectName("wasteBudgetFrame")
        self.budget_frame.setStyleSheet("""
            QFrame#wasteBudgetFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a2a1a, stop:1 #0d1f0d);
                border: 1px solid #2e7d32;
                border-radius: 8px;
            }
        """)
        budget_layout = QVBoxLayout(self.budget_frame)
        budget_layout.setContentsMargins(14, 10, 14, 10)
        budget_layout.setSpacing(4)

        # Judul
        lbl_budget_title = QLabel("BUDGET WASTE")
        lbl_budget_title.setAlignment(Qt.AlignCenter)
        lbl_budget_title.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #81c784; border: none; letter-spacing: 0.5px;"
        )
        budget_layout.addWidget(lbl_budget_title)

        # Separator tipis
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #2e7d32; border: none; max-height: 1px;")
        budget_layout.addWidget(sep)

        # Grid info: 2 kolom
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 4, 0, 0)

        def _mklbl(text, bold=False, align=Qt.AlignLeft):
            l = QLabel(text)
            l.setAlignment(align)
            l.setStyleSheet(f"color: #b0bec5; font-size: 11px; border: none; {'font-weight: bold;' if bold else ''}")
            return l

        grid.addWidget(_mklbl("Sales MTD:"), 0, 0)
        self.lbl_budget_sales = QLabel("– Belum ada data –")
        self.lbl_budget_sales.setStyleSheet("color: #e0e0e0; font-size: 11px; font-weight: bold; border: none;")
        self.lbl_budget_sales.setAlignment(Qt.AlignRight)
        grid.addWidget(self.lbl_budget_sales, 0, 1)

        grid.addWidget(_mklbl("Toleransi Waste:"), 1, 0)
        self.lbl_budget_pct = QLabel("–")
        self.lbl_budget_pct.setStyleSheet("color: #FFD54F; font-size: 11px; font-weight: bold; border: none;")
        self.lbl_budget_pct.setAlignment(Qt.AlignRight)
        grid.addWidget(self.lbl_budget_pct, 1, 1)

        grid.addWidget(_mklbl("Budget Waste:"), 2, 0)
        self.lbl_budget_value = QLabel("–")
        self.lbl_budget_value.setStyleSheet("color: #80deea; font-size: 13px; font-weight: bold; border: none;")
        self.lbl_budget_value.setAlignment(Qt.AlignRight)
        grid.addWidget(self.lbl_budget_value, 2, 1)

        budget_layout.addLayout(grid)
        input_layout.addWidget(self.budget_frame)
        # --------------------------------------------------

        lbl_title_in = QLabel("INPUT PRODUCT")
        lbl_title_in.setAlignment(Qt.AlignCenter)
        lbl_title_in.setStyleSheet("font-weight: bold; font-size: 14px; color: #4CAF50; border: none;")
        input_layout.addWidget(lbl_title_in)

        # --- AREA KONTROL PRODUK (Dropdown + Tombol Add/Del) ---
        
        # --- RECENT PRODUCTS BAR ---
        self.recent_container = QFrame()
        self.recent_container.setObjectName("wasteRecentContainer")
        self.recent_layout = QGridLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 5, 0, 5)
        self.recent_layout.setSpacing(10)
        
        # We'll fill this dynamically in _refresh_recent_row
        
        product_control_layout = QHBoxLayout()
        
        self.product_combo = QComboBox()
        self.product_combo.setEditable(True)
        self.product_combo.setMinimumHeight(35)
        self.product_combo.setPlaceholderText("Cari Produk...")
        self.product_combo.currentIndexChanged.connect(self._on_product_changed)
        
        self.btn_add_prod = QPushButton("+")
        self.btn_add_prod.setToolTip("Input Base/Produk")
        self.btn_add_prod.setFixedSize(35, 35)
        self.btn_add_prod.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #45a049; }")
        self.btn_add_prod.clicked.connect(self._add_new_product)
        
        self.btn_del_prod = QPushButton()
        self.btn_del_prod.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.btn_del_prod.setToolTip("Hapus Produk Terpilih")
        self.btn_del_prod.setFixedSize(35, 35)
        self.btn_del_prod.setStyleSheet("QPushButton { background-color: #ef5350; border-radius: 4px; } QPushButton:hover { background-color: #e53935; }")
        self.btn_del_prod.clicked.connect(self._delete_product)
        self.btn_del_prod.setEnabled(False)
        
        product_control_layout.addWidget(self.product_combo, 1)
        product_control_layout.addWidget(self.btn_add_prod)
        product_control_layout.addWidget(self.btn_del_prod)
        
        input_layout.addWidget(QLabel("Recent Products", objectName="lbl"))
        input_layout.addWidget(self.recent_container)
        input_layout.addLayout(product_control_layout)
        
        # --- TOMBOL EDIT RESEP ---
        self.edit_recipe_btn = QPushButton("✏️ Kelola Detail Produk dan Nilai Konversi")
        self.edit_recipe_btn.setStyleSheet("""
            QPushButton { background-color: #3a2a10; color: #FFB74D; border: 1px solid #5a3a10; border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #4a3a20; }
        """)
        self.edit_recipe_btn.clicked.connect(self._open_recipe_editor)
        self.edit_recipe_btn.setEnabled(False)
        input_layout.addWidget(self.edit_recipe_btn)

        # --- INPUT QTY ---
        input_layout.addWidget(QLabel("Masukkan Qty yang akan diwaste", objectName="lbl"))
        qty_layout = QHBoxLayout()
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setRange(0, 999999)
        self.qty_spin.setDecimals(1) 
        self.qty_spin.setMinimumHeight(45)
        self.qty_spin.setStyleSheet("QDoubleSpinBox { font-size: 18px; font-weight: bold; padding: 5px; border: 1px solid #4A4C50; border-radius: 5px; background-color: #1E1F22; color: #ECF0F1; } QDoubleSpinBox:focus { border: 2px solid #4CAF50; }")
        self.qty_spin.valueChanged.connect(self._calculate)
        
        self.uom_label = QLabel("Unit")
        self.uom_label.setStyleSheet("font-weight: bold; color: #BDC3C7; font-size: 14px; border: none;")
        qty_layout.addWidget(self.qty_spin); qty_layout.addWidget(self.uom_label)
        input_layout.addLayout(qty_layout)
        input_layout.addStretch()
        
        info_lbl = QLabel("💡 <i>Tips: Gunakan tombol + untuk manambahkan produk baru.</i>")
        info_lbl.setWordWrap(True); info_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; border: none;")
        input_layout.addWidget(info_lbl)

        # --- TENGAH ---
        arrow_layout = QVBoxLayout()
        arrow_label = QLabel("➔"); arrow_label.setStyleSheet("font-size: 40px; color: #6c7a89; font-weight: bold;"); arrow_label.setAlignment(Qt.AlignCenter)
        arrow_layout.addStretch(); arrow_layout.addWidget(arrow_label); arrow_layout.addStretch()

        # --- PANEL KANAN: OUTPUT ---
        output_container = QFrame()
        output_container.setObjectName("wasteOutputContainer")
        shadow2 = QGraphicsDropShadowEffect(); shadow2.setBlurRadius(15); shadow2.setYOffset(4); shadow2.setColor(QColor(0, 0, 0, 30))
        output_container.setGraphicsEffect(shadow2)
        
        output_layout = QVBoxLayout(output_container); output_layout.setContentsMargins(0, 0, 0, 0)
        
        header_frame = QFrame()
        header_frame.setObjectName("wasteHeaderFrame")
        header_layout_inner = QVBoxLayout(header_frame)
        lbl_title_out = QLabel("HASIL KONVERSI (Raw Material)")
        lbl_title_out.setAlignment(Qt.AlignCenter)
        lbl_title_out.setStyleSheet("font-weight: bold; font-size: 14px; color: #e65100; border: none; background: transparent;")
        header_layout_inner.addWidget(lbl_title_out)
        output_layout.addWidget(header_frame)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["Kode Artikel", "Nama Raw Material", "Qty", "Uom"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setSelectionMode(QTableWidget.NoSelection)
        self.result_table.setObjectName("wasteResultTable")
        
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        output_layout.addWidget(self.result_table)

        main_layout.addWidget(input_container, 35); main_layout.addLayout(arrow_layout, 5); main_layout.addWidget(output_container, 60)

    def _load_recipes(self):
        if os.path.exists(WASTE_RECIPES_FILE):
            try:
                with open(WASTE_RECIPES_FILE, 'r', encoding='utf-8') as f:
                    self.recipes_data = json.load(f)
                self._refresh_combo()
            except Exception as e:
                logging.error(f"Gagal memuat waste_recipes.json: {e}")
        else:
            self.recipes_data = []
            self._save_recipes_to_file()

    def _refresh_combo(self):
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("- Pilih Produk -")
        
        sorted_recipes = sorted(self.recipes_data, key=lambda x: x['product_name'])
        for recipe in sorted_recipes:
            display_text = f"{recipe['product_name']} ({recipe['product_code']})"
            self.product_combo.addItem(display_text, recipe)
        self.product_combo.blockSignals(False)

    def _save_recipes_to_file(self):
        try:
            os.makedirs(os.path.dirname(WASTE_RECIPES_FILE), exist_ok=True)
            with open(WASTE_RECIPES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.recipes_data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal menyimpan: {e}")

    def _on_product_changed(self, index):
        if index <= 0:
            self.current_recipe = None
            self.uom_label.setText("Unit")
            self.qty_spin.setValue(0); self.qty_spin.setEnabled(False)
            self.edit_recipe_btn.setEnabled(False); self.btn_del_prod.setEnabled(False)
            self.result_table.setRowCount(0)
            return

        self.current_recipe = self.product_combo.itemData(index)
        if self.current_recipe:
            self.uom_label.setText(self.current_recipe.get('uom', 'Unit'))
            self.qty_spin.setEnabled(True)
            self.edit_recipe_btn.setEnabled(True)
            self.btn_del_prod.setEnabled(True)
            self._calculate()
            self._save_recent_product(self.current_recipe) # Update recent list

    def _select_product_by_code(self, code):
        """Helper to select product from combo by its code"""
        for i in range(1, self.product_combo.count()):
            data = self.product_combo.itemData(i)
            if data and data.get('product_code') == code:
                self.product_combo.setCurrentIndex(i)
                break

    def _refresh_recent_row(self):
        """Rebuild the card grid for recent products (Max 2 cards per row)"""
        # Clear existing
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        settings = QSettings("RepotIn", "WasteTab")
        recents_raw = settings.value("recent_products", "[]")
        try:
            recents = json.loads(recents_raw)
        except:
            recents = []
            
        if not recents:
            placeholder = QLabel("<i>Belum ada produk favorit.</i>")
            placeholder.setStyleSheet("color: #7f8c8d; font-size: 11px; border: none;")
            self.recent_layout.addWidget(placeholder, 0, 0)
            return

        for i, item in enumerate(recents):
            name = item.get('name', '???')
            code = item.get('code', '')
            
            btn = QPushButton(name)
            btn.setObjectName("wasteRecentCard")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"Pilih {name} ({code})\nKlik untuk memilih produk ini.")
            btn.setMinimumHeight(40) # Card feel
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _, c=code: self._select_product_by_code(c))
            
            row = i // 2
            col = i % 2
            self.recent_layout.addWidget(btn, row, col)

    def _save_recent_product(self, recipe):
        """Save a product to the top of recent list (limit 5)"""
        if not recipe: return
        name = recipe.get('product_name')
        code = recipe.get('product_code')
        
        settings = QSettings("RepotIn", "WasteTab")
        recents_raw = settings.value("recent_products", "[]")
        try:
            recents = json.loads(recents_raw)
        except:
            recents = []
            
        # Remove if already exists to move to top
        recents = [r for r in recents if r.get('code') != code]
        
        # Insert at start
        recents.insert(0, {'name': name, 'code': code})
        
        # Limit to 6
        recents = recents[:6]
        
        settings.setValue("recent_products", json.dumps(recents))
        self._refresh_recent_row()

    def update_budget_info(self, mtd_sales: float):
        """Dipanggil dari main_app setelah data MTD tersedia.
        Menghitung dan menampilkan budget waste sesuai tabel toleransi."""
        if mtd_sales <= 0:
            self.lbl_budget_sales.setText("– Belum ada data –")
            self.lbl_budget_pct.setText("–")
            self.lbl_budget_value.setText("–")
            return

        pct = self._get_tolerance(mtd_sales)
        budget_rp = mtd_sales * pct

        def fmt_rp(val):
            return "Rp {:,.0f}".format(val).replace(",", ".")

        self.lbl_budget_sales.setText(fmt_rp(mtd_sales))
        self.lbl_budget_pct.setText(f"{pct * 100:.2f}%")
        self.lbl_budget_value.setText(fmt_rp(budget_rp))

        # Warna frame sesuai kisaran (indikator visual)
        if pct <= 0.0015:
            border_color = "#00bcd4"   # teal – penjualan sangat tinggi
            title_color  = "#80deea"
            bg_gradient  = "stop:0 #0a1f2a, stop:1 #051520"
        elif pct <= 0.0020:
            border_color = "#4CAF50"   # hijau
            title_color  = "#81c784"
            bg_gradient  = "stop:0 #1a2a1a, stop:1 #0d1f0d"
        elif pct <= 0.0025:
            border_color = "#8bc34a"   # hijau muda
            title_color  = "#aed581"
            bg_gradient  = "stop:0 #1e2a10, stop:1 #111a08"
        elif pct <= 0.0030:
            border_color = "#FFC107"   # amber
            title_color  = "#FFD54F"
            bg_gradient  = "stop:0 #2a2200, stop:1 #1a1500"
        else:
            border_color = "#FF7043"   # oranye (toleransi tinggi = penjualan rendah)
            title_color  = "#FFAB91"
            bg_gradient  = "stop:0 #2a1200, stop:1 #1a0a00"

        self.budget_frame.setStyleSheet(f"""
            QFrame#wasteBudgetFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    {bg_gradient});
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)
        # Update warna teks judul secara manual (anak pertama dari budget_layout)
        title_lbl = self.budget_frame.findChild(QLabel, "")
        for child in self.budget_frame.findChildren(QLabel):
            if "WASTE BUDGETING" in child.text():
                child.setStyleSheet(
                    f"font-weight: bold; font-size: 11px; color: {title_color}; border: none; letter-spacing: 0.5px;"
                )
                break

    def _calculate(self):
        if not self.current_recipe: return
        input_qty = self.qty_spin.value()
        ingredients = self.current_recipe.get('ingredients', [])
        self.result_table.setRowCount(len(ingredients))
        for row, ing in enumerate(ingredients):
            factor = ing.get('factor', 0)
            result_qty = input_qty * factor
            self.result_table.setItem(row, 0, QTableWidgetItem(ing.get('raw_code', '')))
            self.result_table.setItem(row, 1, QTableWidgetItem(ing.get('raw_name', '')))
            qty_item = QTableWidgetItem(f"{result_qty:,.3f}") 
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            qty_item.setFont(QFont("Arial", 10, QFont.Bold))
            self.result_table.setItem(row, 2, qty_item)
            self.result_table.setItem(row, 3, QTableWidgetItem(ing.get('uom', '')))

    def _add_new_product(self):
        dialog = AddProductDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            # Cek duplikat kode
            if any(p['product_code'] == new_data['product_code'] for p in self.recipes_data if new_data['product_code']):
                QMessageBox.warning(self, "Gagal", f"Kode Produk '{new_data['product_code']}' sudah ada.")
                return
                
            self.recipes_data.append(new_data)
            self._save_recipes_to_file()
            self._refresh_combo()
            
            # Auto select
            new_idx = self.product_combo.findText(f"{new_data['product_name']} ({new_data['product_code']})")
            if new_idx >= 0: self.product_combo.setCurrentIndex(new_idx)
            
            QMessageBox.information(self, "Info", "Produk berhasil dibuat. Silakan tambahkan bahan bakunya.")
            self._open_recipe_editor() # Langsung buka editor

    def _delete_product(self):
        if not self.current_recipe: return
        name = self.current_recipe.get('product_name')
        if QMessageBox.question(self, "Konfirmasi", f"Hapus produk '{name}' beserta resepnya?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            # Hapus dari list
            self.recipes_data = [r for r in self.recipes_data if r != self.current_recipe]
            self._save_recipes_to_file()
            self._refresh_combo()
            self.qty_spin.setValue(0)

    def _open_recipe_editor(self):
        if not self.current_recipe: return
        dialog = RecipeEditorDialog(self.current_recipe, self)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_updated_recipe()
            
            # Update di list utama (cari index berdasarkan referensi lama atau kode)
            for i, r in enumerate(self.recipes_data):
                if r['product_code'] == self.current_recipe['product_code']: # Asumsi kode unik, atau gunakan ID jika ada
                    self.recipes_data[i] = updated_data
                    break
            
            self._save_recipes_to_file()
            self._refresh_combo()
            
            # Restore selection
            new_text = f"{updated_data['product_name']} ({updated_data['product_code']})"
            idx = self.product_combo.findText(new_text)
            if idx >= 0: self.product_combo.setCurrentIndex(idx)