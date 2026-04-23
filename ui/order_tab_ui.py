# ui/order_tab_ui.py
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QCheckBox, QApplication, QFileDialog,
    QComboBox, QLineEdit, QSpacerItem, QSizePolicy, QMessageBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QStyledItemDelegate, QTabWidget,
    QFrame, QGraphicsDropShadowEffect, QStyle
)
from PyQt5.QtCore import Qt, QRect, QRectF, QSize, QSettings
from PyQt5.QtGui import (
    QColor, QDoubleValidator, QIntValidator, QPainter, QBrush, QFont, QPainterPath, QFontMetrics
)

# ==========================================
# 1. CUSTOM DELEGATE (Status Badge)
# ==========================================
class StatusDelegate(QStyledItemDelegate):
    # Map stored data -> displayed text (with emoji prefix)
    _DISPLAY = {
        "OK":    "✓ OK",
        "OVER":  "⚠ Kebanyakan!",
        "ERROR": "✕ INVALID",
    }

    def sizeHint(self, option, index):
        status_text = index.data()
        if not status_text: return super().sizeHint(option, index)
        # Measure the ACTUAL displayed text (with emoji prefix) + generous padding
        display = self._DISPLAY.get(status_text, status_text)
        font = option.font; font.setBold(True); font.setPointSize(8)
        fm = QFontMetrics(font)
        return QSize(fm.horizontalAdvance(display) + 28, 28)

    def paint(self, painter, option, index):
        # Always fill the base background first (inherits table row color)
        bg_base = option.palette.base().color() if (index.row() % 2 == 0) else option.palette.alternateBase().color()
        painter.fillRect(option.rect, bg_base)

        status_text = index.data()
        if not status_text:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        display_text = self._DISPLAY.get(status_text, status_text)

        # Badge colors
        if status_text == "OK":
            bg, text_c = QColor("#28a745"), QColor("#ffffff") # Green
        elif status_text == "OVER":
            bg, text_c = QColor("#ffc107"), QColor("#000000") # Yellow/Amber
        elif status_text == "ERROR":
            bg, text_c = QColor("#dc3545"), QColor("#ffffff") # Red
        else:
            bg, text_c = QColor("#6c757d"), QColor("#ffffff") # Gray

        rect = option.rect.adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 6, 6)
        painter.fillPath(path, QBrush(bg))
        painter.setPen(text_c)
        font = painter.font(); font.setBold(True); font.setPointSize(8)
        painter.setFont(font)
        # Clip to badge rect so text never overflows
        painter.setClipRect(rect)
        painter.drawText(rect, Qt.AlignCenter, display_text)
        painter.restore()



class FloatDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent); editor.setValidator(QDoubleValidator(0.0, 999999.0, 2, parent))
        return editor

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        is_hover    = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        # Row base background
        bg_base = option.palette.base().color() if (index.row() % 2 == 0) else option.palette.alternateBase().color()
        painter.fillRect(option.rect, bg_base)

        # Cell background: bright on hover, selected, or default amber-dark
        if is_selected:
            cell_color = option.palette.highlight().color()
        elif is_hover:
            cell_color = QColor("#fff3cd") if bg_base.lightness() > 128 else QColor("#3d4a14")
        else:
            cell_color = QColor("#fff9e6") if bg_base.lightness() > 128 else QColor("#2a3010")

        cell_rect = option.rect.adjusted(0, 1, 0, -1)
        painter.fillRect(cell_rect, cell_color)

        # Left accent bar — brighter gold on hover
        accent_rect = option.rect.adjusted(0, 2, 0, -2)
        accent_rect.setWidth(3)
        accent_color = QColor("#856404") if bg_base.lightness() > 128 else QColor("#ffd166")
        painter.fillRect(accent_rect, accent_color)

        # Text
        text = index.data() or ""
        if text and text not in ("0", "0.0"):
            text_color = QColor("#856404") if bg_base.lightness() > 128 else QColor("#ffd166")
            font = painter.font(); font.setBold(True); font.setPointSize(9)
        else:
            text_color = QColor("#6c757d") if bg_base.lightness() > 128 else QColor("#4d6040")
            font = painter.font(); font.setBold(False); font.setPointSize(9)

        painter.setFont(font)
        painter.setPen(text_color)
        text_rect = option.rect.adjusted(6, 0, -4, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignCenter, text)
        painter.restore()

# ==========================================
# 2. SITE SUMMARY WIDGET (Perbaikan Warna Tombol)
# ==========================================
class SiteSummaryWidget(QWidget):
    _SETTINGS_KEY = "order_summary/batch"

    def __init__(self, site_code, summary_df, parent=None):
        super().__init__(parent)
        self.site_code = site_code
        self.summary_df = summary_df
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10)
        
        self.summary_table = QTableWidget()
        self.summary_table.setObjectName("siteSummaryTable")
        self.summary_table.setColumnCount(4)
        self.summary_table.setHorizontalHeaderLabels(["Status", "Article", "Article Description", "Total Order Qty"])
        header = self.summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.populate_table()
        layout.addWidget(self.summary_table)
        
        # --- Bottom bar ---
        bottom = QHBoxLayout()

        # Load saved batch value (default 20)
        settings = QSettings("RepotIn", "OrderTab")
        saved_batch = settings.value(self._SETTINGS_KEY, 20, type=int)
        self.batch_spin = QSpinBox()
        self.batch_spin.setPrefix("Batch: ")
        self.batch_spin.setRange(1, 999)
        self.batch_spin.setValue(saved_batch)
        self.batch_spin.valueChanged.connect(self._save_batch)
        self.batch_spin.setToolTip("Jumlah baris yang disalin per klik. Nilai disimpan otomatis.")

        reset_btn = QPushButton("🔄 Reset Status")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setToolTip("Hapus tanda 'Tersalin' agar semua baris bisa disalin ulang")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d; color: white;
                border-radius: 4px; padding: 7px 12px; font-weight: bold; font-size: 9pt;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        reset_btn.clicked.connect(self.reset_status)

        copy_btn = QPushButton(f"📋 Salin {self.site_code} ke SAP")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff; color: white;
                border: 1px solid #007bff; border-radius: 4px;
                padding: 8px 16px; font-weight: bold; font-size: 10pt;
            }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #004085; }
        """)
        copy_btn.clicked.connect(self.copy_summary_to_clipboard)

        bottom.addStretch()
        bottom.addWidget(self.batch_spin)
        bottom.addWidget(reset_btn)
        bottom.addWidget(copy_btn)
        layout.addLayout(bottom)

    def _save_batch(self, value):
        QSettings("RepotIn", "OrderTab").setValue(self._SETTINGS_KEY, value)

    def populate_table(self):
        self.summary_table.setRowCount(len(self.summary_df))
        for i, row in self.summary_df.iterrows():
            st = QTableWidgetItem(""); st.setFlags(Qt.ItemIsEnabled)
            self.summary_table.setItem(i, 0, st)
            self.summary_table.setItem(i, 1, QTableWidgetItem(str(row['artikel'])))
            self.summary_table.setItem(i, 2, QTableWidgetItem(str(row['deskripsi'])))
            self.summary_table.setItem(i, 3, QTableWidgetItem(f"{row['jumlah']:.2f}".rstrip('0').rstrip('.')))

    def reset_status(self):
        """Clear all 'Tersalin' marks so rows can be re-copied."""
        for r in range(self.summary_table.rowCount()):
            item = self.summary_table.item(r, 0)
            if item and item.text() == "Tersalin":
                blank = QTableWidgetItem("")
                blank.setFlags(Qt.ItemIsEnabled)
                self.summary_table.setItem(r, 0, blank)
        QMessageBox.information(self, "Reset", "Status berhasil direset. Semua baris siap disalin ulang.")

    def copy_summary_to_clipboard(self):
        batch = self.batch_spin.value(); copied_indices = []
        for r in range(self.summary_table.rowCount()):
            item = self.summary_table.item(r, 0)
            if not item or item.text() != "Tersalin":
                copied_indices.append(r)
                if len(copied_indices) >= batch: break
        
        if not copied_indices:
            QMessageBox.information(self, "Selesai", "Semua data sudah disalin. Klik 'Reset Status' untuk menyalin ulang.")
            return

        text = ""
        for r in copied_indices:
            art = self.summary_table.item(r, 1).text()
            desc = self.summary_table.item(r, 2).text()
            qty = self.summary_table.item(r, 3).text()
            text += f"{art}\t{desc}\t{qty}\n"

        QApplication.clipboard().setText(text)
        
        for r in copied_indices:
            item = QTableWidgetItem("Tersalin"); item.setFlags(Qt.ItemIsEnabled)
            item.setBackground(QColor("#d4edda")); item.setForeground(QColor("#155724"))
            item.setTextAlignment(Qt.AlignCenter)
            self.summary_table.setItem(r, 0, item)
            
        remaining = sum(1 for r in range(self.summary_table.rowCount()) 
                        if self.summary_table.item(r, 0) and self.summary_table.item(r, 0).text() != "Tersalin")
        msg = f"{len(copied_indices)} baris disalin."
        if remaining > 0:
            msg += f" Sisa {remaining} baris belum disalin."
        else:
            msg += " Semua selesai!"
        QMessageBox.information(self, "Sukses", msg)


class OrderSummaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ringkasan Order per Site")
        self.setMinimumSize(800, 500)
        self.setObjectName("orderSummaryDialog")
        
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("orderSummaryTabWidget")
        layout.addWidget(self.tab_widget)
        
        close_btn = QPushButton("Tutup")
        close_btn.setStyleSheet("""
            QPushButton { background-color: #6c757d; color: white; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #5a6268; }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

    def add_summary_tab(self, site, df):
        self.tab_widget.addTab(SiteSummaryWidget(site, df, self), site)

# ==========================================
# 3. CLASS UTAMA & FORM (Perbaikan Warna Tombol)
# ==========================================
class ItemFormDialog(QDialog):
    def __init__(self, parent=None, item_data=None, db_manager=None):
        super().__init__(parent)
        self.is_edit = (item_data is not None)
        self.setWindowTitle("Edit Barang" if self.is_edit else "Tambah Barang")
        self.setMinimumWidth(440)
        self.setObjectName("itemFormDialog")

        # --- Live dropdown options from DB (fallback to hardcoded) ---
        sites_opts    = db_manager.get_all_sites()    if db_manager else ["F001","F008","FC05"]
        specs_opts    = db_manager.get_all_specs()    if db_manager else ["CHATIME","NON MERCH"]
        packages_opts = db_manager.get_all_packages() if db_manager else ["ROL","BTL","PACK","EA"]
        uom_opts      = db_manager.get_all_units()    if db_manager else ["EA","G","ML"]

        def make_combo(options, current=""):
            cb = QComboBox()
            cb.setEditable(True)
            cb.setInsertPolicy(QComboBox.NoInsert)
            cb.addItems(options)
            cb.setCurrentText(current)
            return cb

        self.ac_input   = QLineEdit()
        self.site_input = make_combo(sites_opts)
        self.spec_input = make_combo(specs_opts)
        self.desc_input = QLineEdit()
        self.pkg_input  = make_combo(packages_opts)
        self.cnt_input  = QLineEdit("0"); self.cnt_input.setValidator(QIntValidator())
        self.uom_input  = make_combo(uom_opts)
        self.max_input  = QLineEdit("0"); self.max_input.setValidator(QIntValidator())

        # Build form
        form = QFormLayout()
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Article Code:", self.ac_input)
        form.addRow("Sites:",        self.site_input)
        form.addRow("Spec:",         self.spec_input)
        form.addRow("Description:",  self.desc_input)
        form.addRow("Packages:",     self.pkg_input)
        form.addRow("Contain:",      self.cnt_input)
        form.addRow("UOM:",          self.uom_input)
        form.addRow("Max Order:",    self.max_input)

        if self.is_edit:
            self.ac_input.setText(item_data.get('article_code','')); self.ac_input.setReadOnly(True)
            self.ac_input.setProperty("readOnlyField", True)
            self.site_input.setCurrentText(item_data.get('sites',''))
            self.spec_input.setCurrentText(item_data.get('spec',''))
            self.desc_input.setText(item_data.get('article_description',''))
            self.pkg_input.setCurrentText(item_data.get('packages',''))
            self.cnt_input.setText(str(item_data.get('contain', 0)))
            self.uom_input.setCurrentText(item_data.get('uom',''))
            self.max_input.setText(str(item_data.get('max_order', 0)))

        # Button bar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("💾 Simpan")
        btns.button(QDialogButtonBox.Cancel).setText("Batal")
        btns.button(QDialogButtonBox.Ok).setStyleSheet("background-color: #28a745; color: white;")
        btns.button(QDialogButtonBox.Cancel).setStyleSheet("background-color: #6c757d; color: white;")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # Main layout: form + buttons stacked
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 14)
        main_layout.setSpacing(14)
        main_layout.addLayout(form)
        main_layout.addWidget(btns)

    def get_data(self):
        return {
            'article_code': self.ac_input.text().strip(),
            'sites': self.site_input.currentText().strip().upper(),
            'spec': self.spec_input.currentText().strip().upper(),
            'article_description': self.desc_input.text().strip(),
            'packages': self.pkg_input.currentText().strip(),
            'contain': int(self.cnt_input.text() or 0),
            'uom': self.uom_input.currentText().strip(),
            'max_order': int(self.max_input.text() or 0),
            'is_orderable': 1
        }

class OrderTab(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.db_manager = self.parent_app.order_db_manager 
        self.order_qty_cache = {} 
        self._init_ui()
        self._refresh_spec_filter()
        self.load_data_to_table()

    def _init_ui(self):
        main = QVBoxLayout(self); main.setContentsMargins(20,20,20,20); main.setSpacing(15)
        
        # Filter Card
        card = QFrame()
        card.setObjectName("orderFilterCard")
        card.setGraphicsEffect(QGraphicsDropShadowEffect(blurRadius=8, xOffset=0, yOffset=2, color=QColor(0,0,0,20)))
        fl = QVBoxLayout(card); fl.setContentsMargins(15,15,15,15)
        
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Filter Spec:")); 
        self.spec_combo = QComboBox()
        self.spec_combo.setObjectName("orderSpecCombo")
        self.spec_combo.setMinimumWidth(150)
        self.spec_combo.currentTextChanged.connect(self.load_data_to_table)
        r1.addWidget(self.spec_combo); r1.addSpacing(20)
        
        r1.addWidget(QLabel("Cari:")); 
        self.search = QLineEdit()
        self.search.setObjectName("orderSearchInput")
        self.search.setPlaceholderText("Artikel / Deskripsi...")
        self.search.textChanged.connect(self.filter_table_view)
        r1.addWidget(self.search, 1)
        fl.addLayout(r1)
        
        r2 = QHBoxLayout()
        self.show_disabled = QCheckBox("Tampilkan Non-Aktif"); self.show_disabled.stateChanged.connect(self.load_data_to_table)
        r2.addWidget(self.show_disabled); r2.addStretch()
        
        # --- Tombol Aksi ---
        self.btn_add = QPushButton("➕ Tambah"); self.btn_add.clicked.connect(self.add_new_master_item)
        self.btn_edit = QPushButton("✏️ Edit"); self.btn_edit.clicked.connect(self.edit_master_item)
        self.btn_del = QPushButton("🗑️ Hapus"); self.btn_del.clicked.connect(self.delete_master_item)
        self.btn_imp = QPushButton("📂 Impor"); self.btn_imp.clicked.connect(self.import_from_file)
        self.btn_reverse = QPushButton("🔄 Balik Status")
        self.btn_reverse.clicked.connect(self.reverse_all_statuses)
        for b in [self.btn_add, self.btn_edit, self.btn_del, self.btn_imp, self.btn_reverse]: 
            b.setCursor(Qt.PointingHandCursor)
            r2.addWidget(b)
        fl.addLayout(r2)
        main.addWidget(card)

        # ─── Compact Info / Stats Bar ─────────────────────────────────────────
        self.info_bar = QFrame()
        self.info_bar.setObjectName("orderInfoBar")
        self.info_bar.setFixedHeight(38)
        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(14, 0, 14, 0)
        info_layout.setSpacing(8)

        self.lbl_total     = self._make_chip("📦 Total: —",  "#3d5a80", "#c8e0f4")
        self.lbl_aktif     = self._make_chip("✅ Aktif: —",  "#1b4332", "#95d5b2")
        self.lbl_nonaktif  = self._make_chip("🔒 Non-Aktif: —", "#4a1942", "#f4a8d4")
        for lbl in [self.lbl_total, self.lbl_aktif, self.lbl_nonaktif]:
            info_layout.addWidget(lbl)

        # Separator
        sep = QLabel("│"); sep.setStyleSheet("color: #4a6070; font-size: 16px;")
        info_layout.addWidget(sep)

        self.info_site_labels = {}   # site_code -> QLabel, dynamic
        self.info_site_container = QHBoxLayout()
        self.info_site_container.setSpacing(6)
        info_layout.addLayout(self.info_site_container)
        info_layout.addStretch()

        main.addWidget(self.info_bar)

        # Table
        self.table = QTableWidget(); self.table.setColumnCount(11)
        self.table.setObjectName("orderTable")
        self.table.setHorizontalHeaderLabels(["Sites","Spec","Article","Description","Lock","Pkg","Cont","UOM","Max","🛒 Order","Status"])
        self.table.verticalHeader().setVisible(False); self.table.setAlternatingRowColors(True)
        self.table.setItemDelegateForColumn(9, FloatDelegate(self.table))
        self.table.setItemDelegateForColumn(10, StatusDelegate(self.table))
        h = self.table.horizontalHeader(); h.setSectionResizeMode(3, QHeaderView.Stretch)
        for i in [0,1,2,4,5,6,7,8,9,10]: h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        # Enable mouse tracking so hover state fires to custom delegates
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        # Double-click any row to open edit dialog
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        self.table.itemChanged.connect(self.on_qty_change)
        main.addWidget(self.table, 1)

        # Footer Buttons
        bf = QHBoxLayout()
        self.btn_clear = QPushButton("Bersihkan Input"); self.btn_clear.clicked.connect(self.clear_qtys)
        # Tombol Merah (Clear)
        self.btn_clear.setObjectName("clear_btn")
        
        self.btn_proc = QPushButton("Proses Order"); self.btn_proc.clicked.connect(self.process)
        # Tombol Hijau (Proses)
        self.btn_proc.setObjectName("orderProcessBtn")
        bf.addWidget(self.btn_clear); bf.addStretch(); bf.addWidget(self.btn_proc)
        main.addLayout(bf)

    def _make_chip(self, text, bg, fg):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 8pt;
                font-weight: bold;
            }}
        """)
        lbl.setFixedHeight(22)
        return lbl

    def _refresh_info_bar(self):
        stats = self.db_manager.get_summary_stats()
        if not stats: return
        self.lbl_total.setText(f"📦 Total: {stats.get('total', 0)}")
        self.lbl_aktif.setText(f"✅ Aktif: {stats.get('aktif', 0)}")
        self.lbl_nonaktif.setText(f"🔒 Non-Aktif: {stats.get('non_aktif', 0)}")

        # Clear old site chips & rebuild dynamically
        while self.info_site_container.count():
            item = self.info_site_container.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.info_site_labels.clear()

        site_colors = ['#2d4a6e','#2d5a3d','#5a3d2d','#4a2d5a','#2d4a5a','#5a4a2d']
        for i, (site, count) in enumerate(stats.get('per_site', {}).items()):
            if not site: continue
            color = site_colors[i % len(site_colors)]
            chip = self._make_chip(f"🏪 {site}: {count}", color, "#cce0f5")
            self.info_site_container.addWidget(chip)
            self.info_site_labels[site] = chip

    def _refresh_spec_filter(self):
        self.spec_combo.blockSignals(True); curr = self.spec_combo.currentText()
        self.spec_combo.clear(); self.spec_combo.addItems(["ALL"] + self.db_manager.get_all_specs())
        if self.spec_combo.findText(curr) != -1: self.spec_combo.setCurrentText(curr)
        self.spec_combo.blockSignals(False)

    def _save_cache(self):
        for r in range(self.table.rowCount()):
            try:
                ac = self.table.item(r, 2).text(); qty_item = self.table.item(r, 9)
                if ac and qty_item and qty_item.text():
                    val = float(qty_item.text().replace(',', '.'))
                    if val > 0: self.order_qty_cache[ac] = val
                    elif ac in self.order_qty_cache: del self.order_qty_cache[ac]
            except: pass

    def load_data_to_table(self):
        self._save_cache(); spec = self.spec_combo.currentText(); inc_dis = self.show_disabled.isChecked()
        items = self.db_manager.get_master_barang(spec, inc_dis)
        self.table.setSortingEnabled(False); self.table.blockSignals(True); self.table.setRowCount(len(items))
        
        for r, d in enumerate(items):
            ac = d.get("article_code")
            self.table.setItem(r, 0, QTableWidgetItem(d.get("site_code", "")))
            self.table.setItem(r, 1, QTableWidgetItem(d.get("spec", "")))
            self.table.setItem(r, 2, QTableWidgetItem(ac or ""))
            self.table.setItem(r, 3, QTableWidgetItem(d.get("nama_barang", "")))
            
            is_open = d.get("status", "Aktif") == "Aktif"
            cb = QCheckBox(); cb.setChecked(is_open); cb.setProperty("ac", ac); cb.stateChanged.connect(self.on_lock)
            cw = QWidget(); cl = QHBoxLayout(cw); cl.addWidget(cb); cl.setAlignment(Qt.AlignCenter); cl.setContentsMargins(0,0,0,0)
            self.table.setCellWidget(r, 4, cw)
            
            self.table.setItem(r, 5, QTableWidgetItem(d.get("kemasan", "")))
            self.table.setItem(r, 6, QTableWidgetItem(str(d.get("isi", 0))))
            self.table.setItem(r, 7, QTableWidgetItem(d.get("satuan", "")))
            self.table.setItem(r, 8, QTableWidgetItem(str(d.get("max_order", 0))))
            
            cached = self.order_qty_cache.get(ac, 0)
            qty_it = QTableWidgetItem(str(cached) if cached else "")
            qty_it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 9, qty_it)
            
            st_it = QTableWidgetItem(""); self.table.setItem(r, 10, st_it)
            self._upd_status(r, cached, float(d.get("isi", 0)), float(d.get("max_order", 0)))
            self._upd_lock_ui(r, is_open)
            
        self.table.blockSignals(False); self.table.setSortingEnabled(True); self.filter_table_view()
        self._refresh_info_bar()

    def on_lock(self):
        cb = self.sender(); ac = cb.property("ac")
        for r in range(self.table.rowCount()):
            if self.table.item(r, 2).text() == ac: self._upd_lock_ui(r, cb.isChecked()); break

    def _upd_lock_ui(self, r, is_open):
        ac_it = self.table.item(r, 2); 
        if not ac_it: return
        self.db_manager.update_item_order_status(ac_it.text(), is_open)
        qi = self.table.item(r, 9)
        if qi:
            if is_open: 
                qi.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            else: 
                qi.setFlags(Qt.ItemIsEnabled)
                qi.setText("0")

    def _upd_status(self, r, qty, cont, max_o):
        si = self.table.item(r, 10)
        if not si: return
        if qty <= 0: si.setData(Qt.DisplayRole, ""); return
        total = qty * cont
        si.setData(Qt.DisplayRole, "OVER" if total > max_o else "OK")

    def on_qty_change(self, item):
        if item.column() != 9: return
        r = item.row(); ac = self.table.item(r, 2).text()
        try:
            val = float(item.text().replace(',', '.'))
            if val > 0: self.order_qty_cache[ac] = val
            elif ac in self.order_qty_cache: del self.order_qty_cache[ac]
            cont = float(self.table.item(r, 6).text()); max_o = float(self.table.item(r, 8).text())
            self._upd_status(r, val, cont, max_o)
        except:
            if ac in self.order_qty_cache: del self.order_qty_cache[ac]
            self.table.item(r, 10).setData(Qt.DisplayRole, "ERROR")

    def filter_table_view(self):
        txt = self.search.text().lower()
        for r in range(self.table.rowCount()):
            ac = self.table.item(r, 2).text().lower(); ad = self.table.item(r, 3).text().lower()
            self.table.setRowHidden(r, not (txt in ac or txt in ad))

    def process(self):
        data = []; self._save_cache()
        for r in range(self.table.rowCount()):
            cw = self.table.cellWidget(r, 4)
            if not (cw and cw.findChild(QCheckBox).isChecked()): continue
            try:
                qty = float(self.table.item(r, 9).text().replace(',', '.'))
                if qty > 0:
                    mx = float(self.table.item(r, 8).text()); cn = float(self.table.item(r, 6).text())
                    tot = qty * cn
                    if tot > mx:
                        nm = self.table.item(r, 3).text()
                        QMessageBox.warning(self, "Limit Exceeded", f"Item: <b>{nm}</b><br>Total ({tot}) melebihi Max ({mx})!"); return
                    data.append({'artikel': self.table.item(r, 2).text(), 'deskripsi': self.table.item(r, 3).text(), 'jumlah': tot, 'sites': self.table.item(r, 0).text()})
            except: continue
        
        if not data: QMessageBox.information(self, "Info", "Tidak ada order valid."); return
        df = pd.DataFrame(data); dlg = OrderSummaryDialog(self)
        for s in df['sites'].unique(): dlg.add_summary_tab(s, df[df['sites']==s].reset_index(drop=True))
        dlg.exec_()

    def clear_qtys(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()): self.table.item(r, 9).setText("0"); self.table.item(r, 10).setData(Qt.DisplayRole, "")
        self.table.blockSignals(False); self.order_qty_cache.clear()
        QMessageBox.information(self, "Selesai", "Input dibersihkan.")

    def import_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Impor Master Barang", "", "Excel/CSV (*.xlsx *.csv)")
        if not path: return
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success, msg = self.db_manager.import_master_from_excel(path)
            QApplication.restoreOverrideCursor()
            if success:
                QMessageBox.information(self, "Berhasil", msg)
                self._refresh_spec_filter()
                self.load_data_to_table()
            else:
                QMessageBox.warning(self, "Peringatan", msg)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error", str(e))

    def reverse_all_statuses(self):
        reply = QMessageBox.question(
            self, "Konfirmasi Balik Status",
            "Semua item Aktif \u2192 Non-Aktif dan Non-Aktif \u2192 Aktif.\nLanjutkan?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes: return
        ok, msg = self.db_manager.reverse_all_statuses()
        if ok:
            QMessageBox.information(self, "Berhasil", msg)
            self.load_data_to_table()
        else:
            QMessageBox.critical(self, "Error", msg)

    def add_new_master_item(self): self._open_form()

    def _on_cell_double_click(self, row, col):
        """Open edit dialog when any cell in a row is double-clicked."""
        try:
            d = {
                'article_code': self.table.item(row,2).text(),
                'sites': self.table.item(row,0).text(),
                'spec': self.table.item(row,1).text(),
                'article_description': self.table.item(row,3).text(),
                'packages': self.table.item(row,5).text(),
                'contain': int(self.table.item(row,6).text() or 0),
                'uom': self.table.item(row,7).text(),
                'max_order': int(self.table.item(row,8).text() or 0)
            }
            self._open_form(d)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Gagal membuka form edit: {e}")

    def edit_master_item(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.warning(self, "Perhatian", "Pilih item yang ingin diedit terlebih dahulu.")
            return
        self._on_cell_double_click(sel[0].row(), 2)
        
    def _open_form(self, data=None):
        dlg = ItemFormDialog(self, data, db_manager=self.db_manager)
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.get_data()
            if self.db_manager.add_or_update_master_item(nd): self._refresh_spec_filter(); self.load_data_to_table()
    
    def delete_master_item(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.warning(self, "Perhatian", "Pilih item yang ingin dihapus terlebih dahulu.")
            return
        item_name = self.table.item(sel[0].row(), 3).text() or self.table.item(sel[0].row(), 2).text()
        reply = QMessageBox.question(self, "Konfirmasi Hapus", f"Yakin ingin menghapus:\n<b>{item_name}</b>?", QMessageBox.Yes|QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.db_manager.delete_master_item(self.table.item(sel[0].row(), 2).text()):
                self.load_data_to_table()
            else:
                QMessageBox.critical(self, "Error", "Gagal menghapus item.")