import logging
import pandas as pd
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTextEdit, QFrame, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QPushButton,
    QRadioButton, QDateEdit, QApplication, QStyle, QLineEdit
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QEvent

# ============================================================================
# 1. CUSTOM TEXT EDIT (Clickable)
# ============================================================================
class ClickableTextEdit(QTextEdit):
    clicked = pyqtSignal()
    def focusInEvent(self, event):
        self.clicked.emit()
        super().focusInEvent(event)
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

# ============================================================================
# 2. WIDGET LAPORAN (DENGAN TOMBOL SALIN & PRINT)
# ============================================================================
class ReportSectionWidget(QWidget):
    section_clicked = pyqtSignal(object) 
    print_requested = pyqtSignal(str) 
    copy_requested = pyqtSignal(object) # Sinyal baru untuk trigger logika salin

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4) 

        header_layout = QHBoxLayout()
        self.label = QLabel(title)
        self.label.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.view_combo = QComboBox()
        self.view_combo.setStyleSheet("font-size: 11px;")
        self.view_combo.setVisible(False)

        self.template_combo = QComboBox()
        self.template_combo.setStyleSheet("font-size: 11px;")
        
        # Tombol Salin
        self.copy_btn = QPushButton("Salin Teks")
        self.copy_btn.setStyleSheet("QPushButton { background-color: #3498db; color: white; border: none; border-radius: 3px; padding: 2px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #2980b9; }")
        self.copy_btn.setVisible(False)
        # Hubungkan klik ke sinyal, BUKAN langsung copy
        self.copy_btn.clicked.connect(lambda: self.copy_requested.emit(self))

        # Tombol Print
        self.print_btn = QPushButton("Print")
        self.print_btn.setStyleSheet("QPushButton { background-color: #27ae60; color: white; border: none; border-radius: 3px; padding: 2px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #2ecc71; }")
        self.print_btn.setVisible(False)
        self.print_btn.clicked.connect(lambda: self.print_requested.emit(self.text_edit.toPlainText()))

        header_layout.addWidget(self.label)
        header_layout.addWidget(self.copy_btn)
        header_layout.addWidget(self.print_btn)
        header_layout.addStretch()
        header_layout.addWidget(self.view_combo)
        header_layout.addWidget(self.template_combo)
        self.layout.addLayout(header_layout)

        # Text Area
        self.text_edit = ClickableTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setStyleSheet(self._get_default_style())
        self.text_edit.clicked.connect(self._on_clicked)
        self.layout.addWidget(self.text_edit)

    def get_text(self):
        """Mengembalikan isi teks dari QTextEdit widget ini."""
        return self.text_edit.toPlainText()

    def _get_default_style(self):
        return "QTextEdit { font-family: Consolas, 'Courier New', monospace; font-size: 12px; padding: 6px; }"

    def _on_clicked(self):
        self.section_clicked.emit(self)

    def set_selected(self, is_selected):
        if is_selected:
            self.text_edit.setProperty("selected", "true")
            self.text_edit.style().unpolish(self.text_edit)
            self.text_edit.style().polish(self.text_edit)
            self.copy_btn.setVisible(True)
            self.print_btn.setVisible(True) 
        else:
            self.text_edit.setProperty("selected", "false")
            self.text_edit.style().unpolish(self.text_edit)
            self.text_edit.style().polish(self.text_edit)
            self.copy_btn.setVisible(False)
            self.print_btn.setVisible(False) 

    # Fungsi ini akan dipanggil oleh main_app.py setelah teks berhasil disalin
    def show_copied_feedback(self):
        self.copy_btn.setText("Tersalin!")
        self.copy_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; border-radius: 3px; padding: 2px 8px; font-size: 10px;")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self._reset_copy_btn("Salin Teks"))

    def _reset_copy_btn(self, text):
        self.copy_btn.setText(text)
        self.copy_btn.setStyleSheet("QPushButton { background-color: #3498db; color: white; border: none; border-radius: 3px; padding: 2px 8px; font-size: 10px; font-weight: bold; } QPushButton:hover { background-color: #2980b9; }")

    def mousePressEvent(self, event):
        self._on_clicked()
        super().mousePressEvent(event)

# ============================================================================
# NUMERIC SORT ITEM — QTableWidgetItem yang sort berdasarkan nilai numerik
# ============================================================================
class _NumericSortItem(QTableWidgetItem):
    """Item yang sort berdasarkan nilai float, bukan teks string."""
    def __init__(self, text: str, sort_value: float):
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, _NumericSortItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)

# ============================================================================
# 3. DYNAMIC TABLE WIDGET (UPDATED: DOUBLE CLICK & RECEIPT VIEW)
# ============================================================================
class DynamicTableWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.label_title = QLabel("<b>Detail Table</b>")
        header_layout.addWidget(self.label_title)
        
        self.view_selector = QComboBox()
        self.view_selector.addItems(["Sales by Payment", "Menu Summary", "Sales Per-Hour (Global)", "Sales Per-Hour (Ouast)", "Sales Per-Hour (Non-Ouast)"])
        self.view_selector.currentIndexChanged.connect(self._on_view_mode_changed)
        header_layout.addWidget(self.view_selector)

        self.period_selector = QComboBox()
        self.period_selector.addItems(["Today", "MTD"])
        self.period_selector.setFixedWidth(80)
        self.period_selector.currentIndexChanged.connect(self._update_table_view)
        header_layout.addWidget(self.period_selector)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari No. Receipt / Menu...")
        self.search_input.textChanged.connect(self._handle_search)
        header_layout.addWidget(self.search_input)

        # Tombol Back (Hanya muncul saat mode Struk)
        self.btn_back = QPushButton("Kembali")
        self.btn_back.setStyleSheet("background-color: #95a5a6; color: white; border: none; padding: 4px 8px; border-radius: 3px;")
        self.btn_back.clicked.connect(self._reset_view)
        self.btn_back.setVisible(False)
        header_layout.addWidget(self.btn_back)

        self.layout.addLayout(header_layout)

        # --- TABLE ---
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # ── Kolom: Interactive resize (drag) + header klik = sort ──
        _hdr = self.table.horizontalHeader()
        _hdr.setSectionResizeMode(QHeaderView.Interactive)
        _hdr.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        
        # [FITUR BARU] Double Click Event
        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        
        self.layout.addWidget(self.table)

        # Data Containers
        self.payment_df = pd.DataFrame()
        self.menu_today_df = pd.DataFrame()
        self.menu_mtd_df = pd.DataFrame()
        self.raw_transactions_df = pd.DataFrame()
        self.raw_payments_df = pd.DataFrame()
        self._hourly_receipts_map = {}  # { hour: [receipt_no, ...] } — untuk drill-down klik Jam

    def set_data(self, payment_df, menu_today_df, menu_mtd_df, raw_trx_df=None, raw_pay_df=None):
        self.payment_df = payment_df if payment_df is not None else pd.DataFrame()
        self.menu_today_df = menu_today_df if menu_today_df is not None else pd.DataFrame()
        self.menu_mtd_df = menu_mtd_df if menu_mtd_df is not None else pd.DataFrame()
        self.raw_transactions_df = raw_trx_df if raw_trx_df is not None else pd.DataFrame()
        self.raw_payments_df = raw_pay_df if raw_pay_df is not None else pd.DataFrame()
        
        # Reset view
        self._update_table_view()

    def _reset_view(self):
        self.search_input.clear()
        self._update_table_view()

    def _on_table_double_click(self, row, col):
        """Handle Double Click pada tabel."""
        header_item = self.table.horizontalHeaderItem(col)
        if not header_item: return

        col_name = header_item.text()
        cell_item = self.table.item(row, col)
        if not cell_item: return
        cell_val = cell_item.text()

        # ── MODE SALES PER-HOUR: klik kolom Jam → drill-down receipt list ──
        if self.view_selector.currentText().startswith("Sales Per-Hour") and col == 0:
            # Ambil jam dari sel (strip emoji dan spasi)
            import re
            m = re.search(r'(\d{2}):', cell_val)
            if m and int(m.group(1)) in self._hourly_receipts_map:
                self._show_hourly_receipt_list(int(m.group(1)))
            return

        # ── MODE NORMAL: klik Receipt No → detail struk ────────────────────
        if "Receipt No" in col_name and cell_val:
            self.search_input.setText(cell_val)

    def _handle_search(self, text):
        search_text = text.strip()
        
        if not search_text:
            self.btn_back.setVisible(False)
            self._update_table_view()
            return

        # LOGIKA PINTAR: Cek apakah text ada di Raw Transactions (sebagai Receipt No)
        # Kita cari exact match atau contains yang sangat spesifik
        found_receipt = None
        
        if not self.raw_transactions_df.empty and 'Receipt No' in self.raw_transactions_df.columns:
            # Cek exact match dulu (prioritas tertinggi - biasanya dari double click)
            exact_match = self.raw_transactions_df[self.raw_transactions_df['Receipt No'] == search_text]
            
            # Cek contains (untuk pencarian manual)
            contains_match = pd.DataFrame()
            if exact_match.empty and len(search_text) > 5: # Minimal ketik 5 huruf baru cari detail
                contains_match = self.raw_transactions_df[
                    self.raw_transactions_df['Receipt No'].astype(str).str.contains(search_text, case=False)
                ]
            
            if not exact_match.empty:
                found_receipt = exact_match.iloc[0]['Receipt No']
            elif not contains_match.empty:
                 # Jika hasil unik (cuma 1 struk), langsung tampilkan detail
                 unique_receipts = contains_match['Receipt No'].unique()
                 if len(unique_receipts) == 1:
                     found_receipt = unique_receipts[0]

        if found_receipt:
            # MODE 1: Tampilkan Detail Struk
            self._show_receipt_detail(found_receipt)
        else:
            # MODE 2: Filter Tabel Biasa
            if self.view_selector.isEnabled(): # Hanya refresh jika belum mode struk
                if self.table.columnCount() < 2 or "RECEIPT:" in self.table.item(0,0).text() if self.table.item(0,0) else False:
                    self._update_table_view() # Balik ke tabel normal dulu
            
            self._filter_table_rows(text)

    def _show_receipt_detail(self, receipt_no):
        """Render tabel mirip struk dengan Info Diskon dan Harga Asli yang rapi."""
        self.btn_back.setVisible(True)
        self.label_title.setText(f"<b>Receipt: {receipt_no}</b>")

        trx = self.raw_transactions_df[self.raw_transactions_df['Receipt No'] == receipt_no]
        pay = pd.DataFrame()
        if not self.raw_payments_df.empty: pay = self.raw_payments_df[self.raw_payments_df['Receipt No'] == receipt_no]
        if pay.empty and not self.payment_df.empty: pay = self.payment_df[self.payment_df['Receipt No'] == receipt_no]

        if trx.empty: return

        date_str = str(trx.iloc[0]['Created Date']) if 'Created Date' in trx.columns else str(trx.iloc[0].get('Tanggal', '-'))
        # created_time tidak di-rename oleh database_manager, coba berbagai nama kolom
        time_str = (
            str(trx.iloc[0]['Created Time']) if 'Created Time' in trx.columns
            else str(trx.iloc[0]['created_time']) if 'created_time' in trx.columns
            else "-"
        )
        # Bersihkan format waktu: buang detik jika format HH:MM:SS
        if time_str and time_str != '-' and len(time_str) >= 5:
            time_str = time_str[:5]  # Ambil HH:MM saja
        order_no = str(trx.iloc[0]['Order No']) if 'Order No' in trx.columns else "-"

        self.table.clear()
        self.table.setColumnCount(5) # Harus 5 Kolom
        self.table.setHorizontalHeaderLabels(["Item / Promo", "Qty", "Harga Asli", "Diskon", "Subtotal"])
        
        rows = []
        rows.append([f"TGL: {date_str} {time_str}", "", "", "", ""])
        rows.append([f"ORD: {order_no}", "", "", "", ""])
        rows.append(["-"*30, "-", "-", "-", "-"])

        total_trx = 0
        total_discount = 0

        # --- LOOP ITEMS ---
        for _, row in trx.iterrows():
            name = str(row.get('Article Name', 'Item'))
            qty = int(row.get('Quantity', 0))
            
            # Harga Setelah Diskon (Net Price)
            net_price = float(row.get('Net Price', 0))
            
            # Harga Sebelum Diskon (Original Price) — coba PascalCase lalu lowercase
            orig_price = float(
                row.get('Original Price',
                        row.get('original_price', net_price))
            )
            if orig_price == 0 and net_price > 0: orig_price = net_price  # Fallback
            
            # Nama Promo
            promo_name = str(row.get('Promotion Name', ''))
            if promo_name.lower() in ['nan', 'none', 'null', '']: promo_name = ""

            # Perhitungan
            unit_price = orig_price / qty if qty != 0 else 0
            discount = orig_price - net_price

            # Format Angka (Titik Ribuan)
            def fmt(num): return f"{num:,.0f}".replace(",", ".")

            # 1. Baris Item Utama
            rows.append([name, str(qty), fmt(unit_price), fmt(discount), fmt(net_price)])
            
            # 2. Baris Promo (Jika ada diskon)
            if promo_name and discount > 0:
                rows.append([f"  ↳ Promo: {promo_name}", "", "", "", ""])

            total_trx += net_price
            total_discount += discount

        rows.append(["-"*30, "-", "-", "-", "-"])
        rows.append(["<b>Amount</b>", "", "", f"<b>{fmt(total_discount)}</b>", f"<b>{fmt(total_trx)}</b>"])

        # --- PAYMENTS ---
        total_pay = 0
        for _, p_row in pay.iterrows():
            mop = str(p_row.get('MOP Name', 'Payment'))
            amt = float(p_row.get('Amount', 0))
            rows.append([f"MOP: {mop}", "", "", "", fmt(amt)])
            total_pay += amt

        if total_pay > total_trx:
            rows.append(["Kembali (Change)", "", "", "", fmt(total_pay - total_trx)])

        # Render ke Tabel
        self.table.setSortingEnabled(False)   # nonaktif sementara agar insert tidak ter-sort
        self.table.setRowCount(len(rows))
        for r, row_data in enumerate(rows):
            for c, text in enumerate(row_data):
                item = QTableWidgetItem(str(text))
                
                # Rata Kanan untuk Angka (Mulai dari kolom ke-3 / index 2)
                if c >= 2 and any(char.isdigit() for char in str(text)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                # Bold untuk Total
                if "<b>" in str(text):
                    clean_text = text.replace("<b>", "").replace("</b>", "")
                    item.setText(clean_text)
                    font = item.font(); font.setBold(True); item.setFont(font)

                self.table.setItem(r, c, item)
        
        # Merapikan lebar kolom agar tidak berantakan
        # Kolom interaktif: auto-fit lalu izinkan resize & sort
        self.table.resizeColumnsToContents()
        _h = self.table.horizontalHeader()
        _h.setSectionResizeMode(QHeaderView.Interactive)
        _h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)

    def _show_hourly_receipt_list(self, hour: int):
        """Drill-down: tampilkan daftar receipt pada jam tertentu (Sales Per-Hour)."""
        from PyQt5.QtGui import QColor, QFont

        receipts = self._hourly_receipts_map.get(hour, [])
        if not receipts:
            return

        self.btn_back.setVisible(True)
        self.label_title.setText(f"<b>Jam {hour:02d}:00 – {hour:02d}:59 — {len(receipts)} Receipt</b>")

        trx_df = self.raw_transactions_df
        pay_df = self.raw_payments_df

        # Helper kolom
        def _find_col(df, *names):
            norm = {c.lower().replace(' ', '_'): c for c in df.columns}
            for n in names:
                if n in df.columns: return n
                if n.lower().replace(' ', '_') in norm: return norm[n.lower().replace(' ', '_')]
            return None

        rcp_col_trx  = _find_col(trx_df, 'Receipt No', 'receipt_no')
        dept_col     = _find_col(trx_df, 'Department Name', 'department_name')
        qty_col      = _find_col(trx_df, 'Quantity', 'quantity')
        rcp_col_pay  = _find_col(pay_df, 'Receipt No', 'receipt_no')
        amt_col      = _find_col(pay_df, 'Amount', 'amount')

        CHATIME_KWORDS = r'Large|Regular|Small|Pop Can|Extra Large|Gede|Butterfly'

        rows = []
        for rcp in receipts:
            # Filter transaksi receipt ini
            if rcp_col_trx and not trx_df.empty:
                t = trx_df[trx_df[rcp_col_trx] == rcp]
            else:
                t = pd.DataFrame()

            # Sold Cup = hanya Chatime drinks
            sc = 0
            if not t.empty and dept_col and qty_col:
                mask_dept = t[dept_col].astype(str).str.contains('Chatime', case=False, na=False)
                mask_name = True
                art_col = _find_col(t, 'Article Name', 'article_name')
                merch_col = _find_col(t, 'Merchandise Name', 'merchandise_name')
                size_col  = merch_col or art_col
                if size_col:
                    mask_name = t[size_col].astype(str).str.contains(CHATIME_KWORDS, case=False, na=False)
                sc = int(t.loc[mask_dept & mask_name, qty_col].sum()) if isinstance(mask_name, pd.Series) else int(t.loc[mask_dept, qty_col].sum())
            elif not t.empty and qty_col:
                sc = int(t[qty_col].sum())

            # Net Sales dari payment
            net = 0.0
            if rcp_col_pay and amt_col and not pay_df.empty:
                p = pay_df[pay_df[rcp_col_pay] == rcp]
                net = float(p[amt_col].sum()) / 1.1 if not p.empty else 0.0

            def fmt_rp(v): return "{:,.0f}".format(v).replace(",", ".")

            rows.append((str(rcp), sc, fmt_rp(net)))

        # Render tabel
        COLS = ["Receipt No", "SC", "Net Sales (Rp)"]
        self.table.clear()
        self.table.setColumnCount(len(COLS))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(COLS)

        font_bold = QFont(); font_bold.setBold(True)

        self.table.setSortingEnabled(False)   # nonaktif selama insert
        for r, (rcp, sc, net_str) in enumerate(rows):
            data = [(rcp, Qt.AlignLeft), (str(sc), Qt.AlignRight), (net_str, Qt.AlignRight)]
            for c, (text, align) in enumerate(data):
                it = QTableWidgetItem(text)
                it.setTextAlignment(align | Qt.AlignVCenter)
                self.table.setItem(r, c, it)

        # Total row
        total_sc  = sum(r[1] for r in rows)
        def fmt_rp(v): return "{:,.0f}".format(v).replace(",", ".")
        total_net_raw = 0.0
        for rcp in receipts:
            if rcp_col_pay and amt_col and not pay_df.empty:
                p = pay_df[pay_df[rcp_col_pay] == rcp]
                total_net_raw += float(p[amt_col].sum()) / 1.1 if not p.empty else 0.0

        self.table.setRowCount(len(rows) + 1)
        total_data = [("TOTAL", Qt.AlignLeft), (str(total_sc), Qt.AlignRight),
                      (fmt_rp(total_net_raw), Qt.AlignRight)]
        for c, (text, align) in enumerate(total_data):
            it = QTableWidgetItem(text)
            it.setTextAlignment(align | Qt.AlignVCenter)
            it.setFont(font_bold)
            it.setBackground(QColor("#1a2744"))
            it.setForeground(QColor("#90caf9"))
            self.table.setItem(len(rows), c, it)

        self.table.resizeColumnsToContents()
        _h = self.table.horizontalHeader()
        _h.setSectionResizeMode(QHeaderView.Interactive)
        _h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)

        # Klik Receipt No → buka detail struk
        self._pending_hourly_view_hour = hour  # simpan agar tombol Back bisa kembali ke jam ini
        # Reconnect cellDoubleClicked ke handler drill-down receipt khusus mode ini
        try:
            self.table.cellDoubleClicked.disconnect()
        except TypeError:
            pass  # Sudah tidak ada koneksi, abaikan
        def _on_rcp_click(row, col):
            if col == 0:
                rcp_item = self.table.item(row, 0)
                if rcp_item and rcp_item.text() != "TOTAL":
                    self._show_receipt_detail(rcp_item.text())
        self.table.cellDoubleClicked.connect(_on_rcp_click)

    def _on_view_mode_changed(self):
        """Kontrol visibilitas period_selector lalu refresh tabel."""
        mode = self.view_selector.currentText()
        # Mode Sales Per-Hour: period selector disembunyikan
        self.period_selector.setVisible(not mode.startswith("Sales Per-Hour"))
        self._update_table_view()

    def _update_table_view(self):
        # Reset UI elements ke mode normal
        self.btn_back.setVisible(False)
        self.label_title.setText("<b>Detail Table</b>")

        # PENTING: Selalu reconnect cellDoubleClicked ke handler utama saat view di-refresh.
        # Ini memastikan handler drill-down dari _show_hourly_receipt_list tidak "stuck"
        # dan tabel bisa dirender ulang dengan benar saat dropdown Today/MTD diubah.
        try:
            self.table.cellDoubleClicked.disconnect()
        except TypeError:
            pass  # Belum ada koneksi, abaikan
        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        
        view_mode = self.view_selector.currentText()
        period_mode = self.period_selector.currentText()

        # ── MODE: SALES PER-HOUR ──────────────────────────────────────────
        if view_mode.startswith("Sales Per-Hour"):
            category = "Global"
            if "Ouast" in view_mode and "Non" not in view_mode:
                category = "Ouast"
            elif "Non-Ouast" in view_mode:
                category = "Non-Ouast"
            self._build_hourly_view(category=category)
            return
        # ─────────────────────────────────────────────────────────────────
        
        df = pd.DataFrame()
        if view_mode == "Sales by Payment":
            df = self.payment_df.copy()
            if not df.empty and 'Tanggal' in df.columns:
                df['Tanggal'] = pd.to_datetime(df['Tanggal'])
                if period_mode == "Today":
                    max_date = df['Tanggal'].max()
                    df = df[df['Tanggal'] == max_date]
        else:
            if period_mode == "Today": df = self.menu_today_df.copy()
            else: df = self.menu_mtd_df.copy()

        self.table.clear()
        if df.empty:
            self.table.setRowCount(0); self.table.setColumnCount(1); self.table.setHorizontalHeaderLabels(["No Data Available"])
            return
        
        self.table.setSortingEnabled(False)   # nonaktif selama insert
        self.table.setRowCount(len(df)); self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(df.columns.astype(str).tolist())
        
        for r in range(len(df)):
            for c in range(len(df.columns)):
                col_name = str(df.columns[c])
                val = df.iloc[r, c]
                text = str(val)
                align = Qt.AlignLeft
                sort_val = None   # jika diisi, pakai _NumericSortItem
                if isinstance(val, (int, float)):
                    align = Qt.AlignRight
                    sort_val = float(val)
                    if "%" in col_name:
                        text = f"{val:.3f}"
                    elif any(x in col_name for x in ["Amount", "Sales", "Net", "Price"]):
                        text = f"{val:,.0f}".replace(",", ".")
                    elif "Qty" in col_name or "Quantity" in col_name:
                        text = str(int(val))

                if sort_val is not None:
                    item = _NumericSortItem(text, sort_val)
                else:
                    item = QTableWidgetItem(text)
                item.setTextAlignment(align | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        
        # Auto-fit lebar kolom setelah data masuk, lalu izinkan resize & sort
        self.table.resizeColumnsToContents()
        _h = self.table.horizontalHeader()
        _h.setSectionResizeMode(QHeaderView.Interactive)
        _h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)

        # Apply filter jika search box tidak kosong
        txt = self.search_input.text()
        if txt and not "E7" in txt: 
             self._filter_table_rows(txt)

    def _build_hourly_view(self, category="Global"):
        """Render tabel Sales Per-Hour.
        - Jam   : dari raw_transactions_df (Created Time / Created Date)
        - TC    : unique Receipt No per jam (dari raw_payments_df) — sesuai laporan
        - Qty   : sum Quantity per jam (dari raw_transactions_df)
        - Net   : sum Amount / 1.1 per jam (dari raw_payments_df) — sesuai laporan
        - Avc   : Net / TC
        - Baris TOTAL di bawah. Warna peak-hour otomatis.
        """
        from PyQt5.QtGui import QColor, QFont

        self.table.clear()
        trx_df = self.raw_transactions_df
        pay_df = self.raw_payments_df

        # ── VALIDASI DATA ──────────────────────────────────────────────────────
        if (trx_df is None or trx_df.empty):
            self.table.setRowCount(0)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(["Tidak ada data transaksi"])
            return

        # ── HELPER: Pencarian kolom case-insensitive ──────────────────────────
        def _find_col(df, *candidates):
            """Return nama kolom pertama yang cocok (case & space insensitive)."""
            cols_norm = {c.lower().replace(' ', '_'): c for c in df.columns}
            for name in candidates:
                if name in df.columns:           # exact match dulu
                    return name
                key = name.lower().replace(' ', '_')
                if key in cols_norm:
                    return cols_norm[key]
            return None

        # ── EKSTRAK JAM DARI TRANSACTIONS ──────────────────────────────────────
        hour_series = None
        if trx_df is not None and not trx_df.empty:
            time_col = _find_col(trx_df, 'Created Time', 'created_time')
            date_col = _find_col(trx_df, 'Created Date', 'created_date')

            # Strategi 1: Gabungkan Date + Time sebagai full datetime string
            if date_col and time_col:
                try:
                    combined = (trx_df[date_col].astype(str).str.strip()
                                + ' '
                                + trx_df[time_col].astype(str).str.strip())
                    parsed = pd.to_datetime(combined, errors='coerce')
                    if not parsed.isna().all():
                        hour_series = parsed.dt.hour
                except Exception:
                    pass

            # Strategi 2: Prefix dummy date
            if (hour_series is None or hour_series.isna().all()) and time_col:
                try:
                    time_str = trx_df[time_col].astype(str).str.strip()
                    parsed = pd.to_datetime('2000-01-01 ' + time_str, errors='coerce')
                    if not parsed.isna().all():
                        hour_series = parsed.dt.hour
                except Exception:
                    pass

            # Strategi 3: Parse date_col sebagai full datetime
            if (hour_series is None or hour_series.isna().all()) and date_col:
                try:
                    parsed = pd.to_datetime(trx_df[date_col].astype(str), errors='coerce')
                    candidate = parsed.dt.hour
                    if not candidate.isna().all() and candidate.max() > 0:
                        hour_series = candidate
                except Exception:
                    pass

        if hour_series is None or hour_series.isna().all():
            self.table.setRowCount(1)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(["Info"])
            self.table.setItem(0, 0, QTableWidgetItem(
                "Kolom waktu tidak dapat dideteksi. "
                "Pastikan kolom 'Created Time' / 'created_time' tersedia di data transaksi."
            ))
            return

        # ── BUAT RECEIPT→HOUR MAP dari transactions ────────────────────────────
        rcp_col_trx = _find_col(trx_df, 'Receipt No', 'receipt_no', 'Order No', 'order_no')
        qty_col     = _find_col(trx_df, 'Quantity', 'quantity', 'Qty')
        dept_col    = _find_col(trx_df, 'Department Name', 'department_name')
        merch_col   = _find_col(trx_df, 'Merchandise Name', 'merchandise_name')
        art_col     = _find_col(trx_df, 'Article Name', 'article_name')
        pgn_col     = _find_col(trx_df, 'Product Group Name', 'product_group_name')
        cat_col     = _find_col(trx_df, 'Category Name', 'category_name')
        size_col    = merch_col or art_col          

        CHATIME_KWORDS = r'Large|Regular|Small|Pop Can|Extra Large|Gede|Butterfly'

        work_trx = trx_df.copy()
        work_trx['_hour'] = hour_series
        work_trx = work_trx.dropna(subset=['_hour'])
        work_trx['_hour'] = work_trx['_hour'].astype(int)

        # ── FILTER BERDASARKAN KATEGORI (Ouast / Non-Ouast) ────────────────────
        if category != "Global" and (pgn_col or cat_col):
            # Cek apakah item adalah Ouast
            ouast_mask = pd.Series([False] * len(work_trx), index=work_trx.index)
            if pgn_col:
                ouast_mask = ouast_mask | work_trx[pgn_col].astype(str).str.contains(r'Ouast|K-Food|Korean Street Food', case=False, na=False)
            if cat_col:
                ouast_mask = ouast_mask | work_trx[cat_col].astype(str).str.contains(r'Ouast|K-Food|Korean Street Food', case=False, na=False)
                
            if category == "Ouast":
                work_trx = work_trx[ouast_mask]
            elif category == "Non-Ouast":
                work_trx = work_trx[~ouast_mask]

        if work_trx.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels([f"Tidak ada data transaksi untuk kategori {category}"])
            return

        # ── SOLD CUP per jam ───────────────────────────────────────────────────
        sc_per_hour = {}
        if qty_col:
            work_trx[qty_col] = pd.to_numeric(work_trx[qty_col], errors='coerce').fillna(0)
            
            if category == "Global" and dept_col:
                # Global: Sold Cup = Chatime drinks
                mask_dept = work_trx[dept_col].astype(str).str.contains('Chatime', case=False, na=False)
                if size_col:
                    mask_size = work_trx[size_col].astype(str).str.contains(CHATIME_KWORDS, case=False, na=False)
                    sc_mask   = mask_dept & mask_size
                else:
                    sc_mask   = mask_dept
                sc_per_hour = work_trx.loc[sc_mask].groupby('_hour')[qty_col].sum().to_dict()
            else:
                # Ouast/Non-Ouast: Qty = total item pada kategori tsb
                sc_per_hour = work_trx.groupby('_hour')[qty_col].sum().to_dict()

        # Mapping receipt_no → jam (ambil jam pertama jika ada duplikasi)
        if rcp_col_trx:
            receipt_hour_map = (
                work_trx.drop_duplicates(subset=[rcp_col_trx])
                        .set_index(rcp_col_trx)['_hour']
                        .to_dict()
            )
        else:
            receipt_hour_map = {}

        # ── AGGREGATE DARI PAYMENTS / TRANSACTIONS ─────────────────────────────
        rcp_col_pay = _find_col(pay_df, 'Receipt No', 'receipt_no', 'Order No', 'order_no') if (pay_df is not None and not pay_df.empty) else None
        amt_col_pay = _find_col(pay_df, 'Amount', 'amount')                                  if (pay_df is not None and not pay_df.empty) else None

        agg = {}  # { hour: {'tc': int, 'sc': int, 'gross': float} }

        # Jika mode spesifik (Ouast/Non-Ouast), KITA WAJIB PAKAI TRANSACTIONS
        # Karena 1 payment/struk bisa berisi Ouast & Non-Ouast.
        use_payment = (category == "Global") and (pay_df is not None and not pay_df.empty and rcp_col_pay and receipt_hour_map)

        if use_payment:
            work_pay = pay_df.copy()
            if amt_col_pay:
                work_pay[amt_col_pay] = pd.to_numeric(work_pay[amt_col_pay], errors='coerce').fillna(0)

            # Tambahkan kolom jam ke payments via mapping receipt
            work_pay['_hour'] = work_pay[rcp_col_pay].map(receipt_hour_map)
            work_pay = work_pay.dropna(subset=['_hour'])
            work_pay['_hour'] = work_pay['_hour'].astype(int)

            # TC = nunique Receipt per jam
            for h, grp in work_pay.groupby('_hour'):
                tc    = grp[rcp_col_pay].nunique()
                gross = grp.groupby(rcp_col_pay)[amt_col_pay].sum().sum() if amt_col_pay else 0.0
                sc    = int(sc_per_hour.get(h, 0))
                agg[h] = {'tc': tc, 'sc': sc, 'gross': float(gross)}
        else:
            # Fallback / Specific Category: pakai transactions
            net_col_trx = _find_col(work_trx, 'Net Price', 'net_price', 'Net_Price')
            if net_col_trx:
                work_trx[net_col_trx] = pd.to_numeric(work_trx[net_col_trx], errors='coerce').fillna(0)
            for h, grp in work_trx.groupby('_hour'):
                tc    = grp[rcp_col_trx].nunique() if rcp_col_trx else len(grp)
                sc    = int(sc_per_hour.get(h, 0))
                gross = float(grp[net_col_trx].sum() * 1.1) if net_col_trx else 0.0
                agg[h] = {'tc': tc, 'sc': sc, 'gross': gross}

        if not agg:
            self.table.setRowCount(0)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(["Tidak ada data jam"])
            return

        # Simpan receipt list per jam untuk drill-down double-click
        if rcp_col_trx:
            self._hourly_receipts_map = {
                h: work_trx.loc[work_trx['_hour'] == h, rcp_col_trx].unique().tolist()
                for h in agg.keys()
            }
        else:
            self._hourly_receipts_map = {}

        # Net Sales =  Gross / 1.1  (konsisten dengan report_processor)
        total_gross = sum(v['gross'] for v in agg.values())
        total_net   = total_gross / 1.1

        peak_hour   = max(agg, key=lambda h: agg[h]['gross']) if total_gross > 0 else list(agg.keys())[0]
        avg_gross   = total_gross / len(agg) if agg else 0

        hours_sorted = sorted(agg.keys())
        data_rows = []
        for h in hours_sorted:
            v   = agg[h]
            net = v['gross'] / 1.1
            pct = (v['gross'] / total_gross * 100) if total_gross > 0 else 0.0
            avc = (net / v['tc']) if v['tc'] > 0 else 0.0
            data_rows.append((h, v['tc'], v['sc'], net, avc, pct))

        # ── RENDER ────────────────────────────────────────────────────────────
        qty_header = "SC" if category == "Global" else "Qty"
        COLS = ["Jam", "TC", qty_header, "Net Sales (Rp)", "Avc", "% Sales"]
        self.table.setRowCount(len(data_rows) + 1)
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)

        def fmt_rp(v): return "{:,.0f}".format(v).replace(",", ".")

        COLOR_PEAK     = QColor("#1b5e20")   # Hijau gelap – peak hour
        COLOR_HIGH     = QColor("#1a2f1a")   # Hijau tua – di atas rata-rata
        COLOR_NORMAL   = QColor()            # Default (transparan)
        COLOR_TOTAL_BG = QColor("#1a2744")   # Biru gelap – baris TOTAL

        # Warna teks sesuai background
        FG_PEAK   = QColor("#a5d6a7")        # Hijau cerah – peak
        FG_HIGH   = QColor("#d4edda")        # Putih kehijauan – above avg
        FG_NORMAL = QColor()                 # Default (inherit dari stylesheet)

        font_bold = QFont(); font_bold.setBold(True)

        self.table.setSortingEnabled(False)   # nonaktif selama insert
        for r, (h, tc, sc, net, avc, pct) in enumerate(data_rows):
            gross_h = agg[h]['gross']
            if h == peak_hour:
                bg, fg, is_peak = COLOR_PEAK, FG_PEAK, True
            elif gross_h >= avg_gross:
                bg, fg, is_peak = COLOR_HIGH, FG_HIGH, False
            else:
                bg, fg, is_peak = COLOR_NORMAL, FG_NORMAL, False

            jam_text = f"{h:02d}:00 – {h:02d}:59"
            if h == peak_hour: jam_text = f"🔥 {jam_text}"

            cells = [
                (jam_text,        h * 1.0,  Qt.AlignLeft),
                (str(tc),         tc * 1.0, Qt.AlignRight),
                (str(sc),         sc * 1.0, Qt.AlignRight),
                (fmt_rp(net),     net,      Qt.AlignRight),
                (fmt_rp(avc),     avc,      Qt.AlignRight),
                (f"{pct:.1f}%",   pct,      Qt.AlignRight),
            ]
            for c, (text, sort_v, align) in enumerate(cells):
                it = _NumericSortItem(text, sort_v)
                it.setTextAlignment(align | Qt.AlignVCenter)
                if is_peak:
                    it.setFont(font_bold)
                if bg != COLOR_NORMAL:
                    it.setBackground(bg)
                if fg != FG_NORMAL:
                    it.setForeground(fg)
                self.table.setItem(r, c, it)

        # Baris TOTAL — pakai sort_value = float('inf') agar selalu di paling bawah
        total_tc  = sum(v['tc']  for v in agg.values())
        total_sc  = sum(v['sc']  for v in agg.values())
        total_avc = (total_net / total_tc) if total_tc > 0 else 0.0
        total_cells = [
            ("TOTAL",           float('inf'), Qt.AlignLeft),
            (str(total_tc),     float('inf'), Qt.AlignRight),
            (str(total_sc),     float('inf'), Qt.AlignRight),
            (fmt_rp(total_net), float('inf'), Qt.AlignRight),
            (fmt_rp(total_avc), float('inf'), Qt.AlignRight),
            ("100.0%",          float('inf'), Qt.AlignRight),
        ]
        for c, (text, sort_v, align) in enumerate(total_cells):
            it = _NumericSortItem(text, sort_v)
            it.setTextAlignment(align | Qt.AlignVCenter)
            it.setBackground(COLOR_TOTAL_BG)
            it.setForeground(QColor("#90caf9"))
            it.setFont(font_bold)
            self.table.setItem(len(data_rows), c, it)

        self.table.resizeColumnsToContents()
        _h = self.table.horizontalHeader()
        _h.setSectionResizeMode(QHeaderView.Interactive)
        _h.setStretchLastSection(True)
        self.table.setSortingEnabled(True)

        # Re-connect signal agar kembali ke handler utama setelah drill-down
        try:
            self.table.cellDoubleClicked.disconnect()
        except Exception:
            pass
        self.table.cellDoubleClicked.connect(self._on_table_double_click)

    def _filter_table_rows(self, text):
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True; break
            self.table.setRowHidden(row, not match)
                       
# ============================================================================
# 4. SALES REPORT TAB (MAIN) - Tidak Berubah Banyak, hanya import
# ============================================================================
class SalesReportTab(QWidget):
    copy_action_requested = pyqtSignal(object)

    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- TOOLBAR ---
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("toolbar_frame")
        toolbar_frame.setFixedHeight(50)
        btns_layout = QHBoxLayout(toolbar_frame)
        btns_layout.setContentsMargins(10, 5, 10, 5)
        btns_layout.setSpacing(10)
        self.toolbar_layout = btns_layout  # expose so main_app can inject upload button

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(self.style().standardIcon(self.style().SP_BrowserReload))
        self.refresh_button.setObjectName("refresh_btn")
        
        self.select_articles_button = QPushButton("Filter Artikel")
        self.select_promos_button = QPushButton("Filter Promo")

        btns_layout.addWidget(self.refresh_button)
        btns_layout.addWidget(self.select_articles_button)
        btns_layout.addWidget(self.select_promos_button)

        line = QFrame(); line.setFrameShape(QFrame.VLine); line.setFrameShadow(QFrame.Sunken); btns_layout.addWidget(line)

        self.all_dates_radio = QRadioButton("Semua"); self.all_dates_radio.setChecked(True)
        self.date_range_radio = QRadioButton("Periode:")
        self.start_date_edit = QDateEdit(QDate.currentDate()); self.start_date_edit.setCalendarPopup(True); self.start_date_edit.setEnabled(False); self.start_date_edit.setFixedWidth(100)
        self.end_date_edit = QDateEdit(QDate.currentDate()); self.end_date_edit.setCalendarPopup(True); self.end_date_edit.setEnabled(False); self.end_date_edit.setFixedWidth(100)
        self.date_range_radio.toggled.connect(self._toggle_date_range_widgets)

        btns_layout.addWidget(self.all_dates_radio); btns_layout.addWidget(self.date_range_radio)
        btns_layout.addWidget(self.start_date_edit); btns_layout.addWidget(QLabel("-")); btns_layout.addWidget(self.end_date_edit)
        btns_layout.addStretch()

        self.clear_ui_button = QPushButton("Clear")
        self.clear_ui_button.setObjectName("clear_btn")
        btns_layout.addWidget(self.clear_ui_button)

        main_layout.addWidget(toolbar_frame)


        # --- SPLITTER ---
        main_splitter = QSplitter(Qt.Horizontal); main_splitter.setHandleWidth(6)
        
        # Kiri
        self.main_report_section = ReportSectionWidget("Sales Report")
        self.result_text_main = self.main_report_section.text_edit
        main_splitter.addWidget(self.main_report_section)

        # Kanan
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel); right_layout.setContentsMargins(0,0,0,0); right_layout.setSpacing(8)
        right_v_split = QSplitter(Qt.Vertical); right_v_split.setHandleWidth(6)
        top_h_split = QSplitter(Qt.Horizontal); top_h_split.setHandleWidth(6)

        self.today_mop_section = ReportSectionWidget("Sales By Date (MOP)")
        self.today_mop_section.view_combo.setVisible(True); self.today_mop_section.view_combo.addItems(["Today", "MTD"])
        self.today_mop_section.template_combo.setVisible(False)

        contrib_cont = QWidget(); contrib_lay = QVBoxLayout(contrib_cont); contrib_lay.setContentsMargins(0,0,0,0); contrib_lay.setSpacing(4)
        contrib_lay.addWidget(QLabel("<b>Kontribusi New Series</b>"))
        self.contrib_table = QTableWidget(); self.contrib_table.setColumnCount(5); self.contrib_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.contrib_table.verticalHeader().setVisible(False); self.contrib_table.setAlternatingRowColors(True); self.contrib_table.setStyleSheet("font-size: 11px;")
        self.contrib_table.setHorizontalHeaderLabels(["Artikel", "Qty Today", "% Today", "Qty MTD", "% MTD"])
        contrib_lay.addWidget(self.contrib_table)

        top_h_split.addWidget(self.today_mop_section); top_h_split.addWidget(contrib_cont); top_h_split.setSizes([300, 300])

        self.dynamic_table_widget = DynamicTableWidget() # New Table

        right_v_split.addWidget(top_h_split); right_v_split.addWidget(self.dynamic_table_widget); right_v_split.setSizes([350, 250])
        right_layout.addWidget(right_v_split)
        main_splitter.addWidget(right_panel); main_splitter.setSizes([350, 750]); main_splitter.setCollapsible(0, False)
        
        main_layout.addWidget(main_splitter)
        self._main_splitter = main_splitter

        main_layout.addWidget(main_splitter)
        self._main_splitter = main_splitter

        # Signals
        self.main_report_section.section_clicked.connect(self._handle_section_click)
        self.today_mop_section.section_clicked.connect(self._handle_section_click)
        self._active_report_widget = self.main_report_section
        self.main_report_section.print_requested.connect(self._handle_print_request)
        self.today_mop_section.print_requested.connect(self._handle_print_request)
        self.main_report_section.copy_requested.connect(self._handle_copy_request)
        self.today_mop_section.copy_requested.connect(self._handle_copy_request)

    # Helpers
    def _handle_section_click(self, w):
        self.main_report_section.set_selected(False); self.today_mop_section.set_selected(False)
        w.set_selected(True); self._active_report_widget = w
        if hasattr(self.main_app, "set_active_print_widget"): self.main_app.set_active_print_widget(w)

    def _toggle_date_range_widgets(self, c): self.start_date_edit.setEnabled(c); self.end_date_edit.setEnabled(c)
    def get_date_filter_settings(self): return {'all_dates': self.all_dates_radio.isChecked(), 'start_date': self.start_date_edit.date(), 'end_date': self.end_date_edit.date()}
    def update_main_report_text(self, t): self.main_report_section.text_edit.setText(t)
    def update_today_mop_text(self, t, d): self.today_mop_section.text_edit.setText(t)
    def update_contribution_table(self, mtd, day, day_net=0.0, mtd_net=0.0, new_series_prefs=None):
        if new_series_prefs is None: new_series_prefs = []
        self.contrib_table.setRowCount(0)

        from utils.app_utils import format_article_name_short
        from PyQt5.QtGui import QColor, QFont

        # ── helper: cari qty & sales 1 artikel dari DataFrame ─────────────
        def _lookup(df, article):
            if df is None or df.empty:
                return 0, 0.0
            m = df[df.iloc[:, 0].astype(str) == article]
            if m.empty:
                return 0, 0.0
            row = m.iloc[0]
            qty  = int(float(row.get("Quantity",  row.get("qty_today",  row.get("qty_mtd",  0)))))
            sale = float(row.get("Net_Price", row.get("sales_today", row.get("sales_mtd", 0.0))))
            return qty, sale

        # ── helper: tambahkan 1 baris ke tabel ────────────────────────────
        def _add_row(label, qt, pct_t, qm, pct_m, is_header=False):
            r = self.contrib_table.rowCount()
            self.contrib_table.insertRow(r)
            items = [
                QTableWidgetItem(label),
                QTableWidgetItem(str(qt)),
                QTableWidgetItem(f"{pct_t:.1f}%"),
                QTableWidgetItem(str(qm)),
                QTableWidgetItem(f"{pct_m:.1f}%"),
            ]
            for col, it in enumerate(items):
                if is_header:
                    font = QFont(); font.setBold(True); it.setFont(font)
                    it.setBackground(QColor("#1a3a5c"))
                    it.setForeground(QColor("#ffffff"))
                    it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                else:
                    it.setTextAlignment(
                        (Qt.AlignLeft if col == 0 else Qt.AlignRight) | Qt.AlignVCenter
                    )
                self.contrib_table.setItem(r, col, it)

        # ── KASUS 1: format baru (list of dict dengan group_name & articles) ─
        is_new_format = (
            new_series_prefs
            and isinstance(new_series_prefs, list)
            and isinstance(new_series_prefs[0], dict)
        )

        if is_new_format:
            for grp in new_series_prefs:
                grp_name     = grp.get("group_name", "Grup")
                grp_articles = grp.get("articles", [])
                grp_format   = grp.get("format", "Grouped")  # "Grouped" | "Detailed"

                if not grp_articles:
                    continue

                # Hitung total grup untuk semua kasus
                tot_qt = tot_st = tot_qm = tot_sm = 0
                for art in grp_articles:
                    qt, st = _lookup(day, art)
                    qm, sm = _lookup(mtd, art)
                    tot_qt += qt; tot_st += st
                    tot_qm += qm; tot_sm += sm

                pct_t = (tot_st / day_net  * 100) if day_net  > 0 else 0.0
                pct_m = (tot_sm / mtd_net * 100) if mtd_net > 0 else 0.0

                if grp_format == "Grouped":
                    # GROUPED: 1 baris bold (total grup)
                    _add_row(grp_name, tot_qt, pct_t, tot_qm, pct_m, is_header=True)

                else:
                    # DETAILED: baris header grup + baris per artikel
                    _add_row(f"\u25b8 {grp_name}", tot_qt, pct_t, tot_qm, pct_m, is_header=True)
                    for art in grp_articles:           # urutan dari definisi grup
                        qt, st = _lookup(day, art)
                        qm, sm = _lookup(mtd, art)
                        pt = (st / day_net  * 100) if day_net  > 0 else 0.0
                        pm = (sm / mtd_net * 100) if mtd_net > 0 else 0.0
                        _add_row(f"  {format_article_name_short(art)}", qt, pt, qm, pm)

        # ── KASUS 2: fallback (list of string, format lama) ──────────────────
        else:
            # Pertahankan urutan; hindari set() agar tidak acak
            seen = set()
            articles_ordered = []
            for a in (new_series_prefs if new_series_prefs else []):
                if a not in seen:
                    articles_ordered.append(a); seen.add(a)

            # Jika preferensi kosong, ambil dari DataFrame (urutan stabil)
            if not articles_ordered:
                for df in (mtd, day):
                    if df is not None and not df.empty:
                        for a in df.iloc[:, 0].astype(str).tolist():
                            if a not in seen:
                                articles_ordered.append(a); seen.add(a)

            for art in articles_ordered:
                qt, st = _lookup(day, art)
                qm, sm = _lookup(mtd, art)
                pt = (st / day_net  * 100) if day_net  > 0 else 0.0
                pm = (sm / mtd_net * 100) if mtd_net > 0 else 0.0
                _add_row(format_article_name_short(art), qt, pt, qm, pm)
    def clear_all_dynamic_content(self):
        self.main_report_section.text_edit.clear(); self.today_mop_section.text_edit.clear(); self.contrib_table.setRowCount(0)
        self.dynamic_table_widget.set_data(None, None, None)

    def _handle_copy_request(self, widget):
        # The signal emits the widget itself
        if widget and hasattr(widget, 'get_text'):
            text = widget.get_text()
            QApplication.clipboard().setText(text)
            
            warning_msg = ""
            if widget == getattr(self, 'main_report_section', None):
                min_date = 'N/A'
                # report_results_data adalah dict hasil dari processor.process()
                if hasattr(self, 'main_app') and hasattr(self.main_app, 'report_results_data'):
                    res = self.main_app.report_results_data or {}
                    min_date = res.get('min_date_str', 'N/A')
                
                import logging
                logging.info(f"Salin Teks ditekan. min_date_str dari report_results_data: {min_date}")
                
                if min_date not in ('N/A', '') and not min_date.startswith('01-'):
                    day_val = min_date.split('-')[0]  # Ambil DD dari DD-MM-YYYY
                    warning_msg = (
                        f"\n\n⚠️ PERINGATAN:\n"
                        f"Data yang diproses dimulai dari tanggal {day_val} (Bukan tanggal 1).\n"
                        f"Nilai MTD yang disalin mungkin hanya mewakili sebagian hari "
                        f"dan TIDAK sesuai dengan pencapaian aktual bulan berjalan."
                    )
            
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Berhasil", f"Teks berhasil disalin ke Setempel (Clipboard).{warning_msg}")
        
    def _handle_print_request(self, text_to_print):
        if hasattr(self.main_app, "print_report_from_text"):
            # If printing the MOP tab, inject the Print Date into the header
            sender = self.sender()
            if sender == self.today_mop_section:
                from datetime import datetime
                print_date_str = datetime.now().strftime('%d %b %Y %H:%M:%S')
                
                # The text already has:
                # Site       : F413 - CHATIME
                # Sales Date : 01 Mar 2026
                # ---
                
                # We need to inject "Print date : {print_date_str}\n" after the Site line
                lines = text_to_print.split('\n')
                if len(lines) > 0 and lines[0].startswith("Site"):
                    # Insert print date and add the TITLE
                    lines.insert(0, "             SALES BY DATE              \n")
                    lines.insert(2, f"Print date : {print_date_str}")
                    text_to_print = '\n'.join(lines)
            
            self.main_app.print_report_from_text(text_to_print)
        elif hasattr(self.main_app, "print_report"):
            self.main_app.print_report() # Fallback untuk fungsi print versi lama