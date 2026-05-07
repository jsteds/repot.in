import logging
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QDateEdit, QTimeEdit, QGroupBox, QFrame, QApplication, QGridLayout,
    QPushButton, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialogButtonBox, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate, QTime, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect


class CelebrationBanner(QFrame):
    """Banner perayaan inline yang muncul di antara KPI cards dan chart saat target tercapai."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f9c800, stop:0.4 #ffe066, stop:1 #f9c800);
                border-radius: 8px;
                border: none;
            }
        """)
        # Left gold accent line
        accent = QFrame(self)
        accent.setFixedSize(6, 52)
        accent.setStyleSheet("background-color: #b8860b; border-radius: 3px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 16, 0)
        layout.setSpacing(0)
        layout.addWidget(accent)
        layout.addSpacing(12)

        icon = QLabel("🏆")
        icon.setStyleSheet("font-size: 22px; background: transparent; border: none;")
        icon.setAlignment(Qt.AlignVCenter)

        self.title_lbl = QLabel("TARGET TERCAPAI!")
        self.title_lbl.setStyleSheet(
            "color: #1a1a1a; font-size: 14px; font-weight: bold; background: transparent; border: none;"
        )
        self.title_lbl.setAlignment(Qt.AlignVCenter)

        self.sub_lbl = QLabel()
        self.sub_lbl.setStyleSheet(
            "color: #3d3000; font-size: 12px; background: transparent; border: none;"
        )
        self.sub_lbl.setAlignment(Qt.AlignVCenter)

        layout.addWidget(icon)
        layout.addSpacing(8)
        layout.addWidget(self.title_lbl)
        layout.addSpacing(10)
        layout.addWidget(self.sub_lbl)
        layout.addStretch()

        dismiss_lbl = QLabel("✕")
        dismiss_lbl.setStyleSheet(
            "color: #5a4400; font-size: 16px; cursor: pointer; background: transparent; border: none;"
        )
        dismiss_lbl.setAlignment(Qt.AlignVCenter)
        dismiss_lbl.mousePressEvent = lambda _: self.hide()
        layout.addWidget(dismiss_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_banner(self, message="", auto_hide_ms=8000):
        self.sub_lbl.setText(message)
        self.show()
        self._timer.start(auto_hide_ms)

    def hide_banner(self):
        self._timer.stop()
        self.hide()


# Mengatur style matplotlib agar lebih modern dan segar
plt.style.use('seaborn-v0_8-white')
plt.rcParams.update({
    'font.size': 9, 
    'font.family': 'Segoe UI', 
    'axes.spines.top': False, 
    'axes.spines.right': False,
    'axes.edgecolor': '#e0e0e0',
    'axes.titlesize': 10,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white'
})

class DashboardTab(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.db = parent_app.db_manager
        
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(10)
        
        # --- 1. FILTER SECTION ---
        filter_layout = QHBoxLayout()
        
        self.date_range_combo = QComboBox()
        self.date_range_combo.addItems([
            "Hari Ini", "Kemarin", "7 Hari Terakhir", 
            "Bulan Ini", "Bulan Lalu", "Kustom"
        ])
        self.date_range_combo.currentIndexChanged.connect(self.update_date_range_auto)
        
        self.start_date = QDateEdit(QDate.currentDate())
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd/MM/yyyy")
        
        # Auto-load saat tanggal berubah
        self.start_date.dateChanged.connect(self.load_data)
        self.end_date.dateChanged.connect(self.load_data)
        self.start_date.dateChanged.connect(lambda: self.date_range_combo.setCurrentText("Kustom"))
        self.end_date.dateChanged.connect(lambda: self.date_range_combo.setCurrentText("Kustom"))
        
        filter_layout.addWidget(QLabel("Periode:"))
        filter_layout.addWidget(self.date_range_combo)
        filter_layout.addSpacing(20)
        filter_layout.addWidget(QLabel("Dari:"))
        filter_layout.addWidget(self.start_date)
        filter_layout.addWidget(QLabel("Sampai:"))
        filter_layout.addWidget(self.end_date)
        filter_layout.addStretch()
        
        # Badge: tersembunyi, muncul saat target tercapai
        self.achievement_badge = QLabel("🏆 Target Achieved!")
        self.achievement_badge.setStyleSheet("""
            QLabel {
                background-color: #FFD700;
                color: #1a1a1a;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 12px;
                border: none;
            }
        """)
        self.achievement_badge.setVisible(False)
        filter_layout.addWidget(self.achievement_badge)
        
        self.btn_prakiraan_bonus = QPushButton("Prakiraan Bonus")
        self.btn_prakiraan_bonus.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover {
                background-color: #219653;
            }
        """)
        self.btn_prakiraan_bonus.setVisible(False)
        self.btn_prakiraan_bonus.clicked.connect(self._show_prakiraan_bonus)
        filter_layout.addWidget(self.btn_prakiraan_bonus)

        # Tombol Komparasi Per Jam
        self.btn_comp_hour = QPushButton("📊 Komparasi Per Jam")
        self.btn_comp_hour.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover { background-color: #7d3c98; }
            QPushButton:pressed { background-color: #6c3483; }
        """)
        self.btn_comp_hour.clicked.connect(self._open_hourly_comparison_dialog)
        filter_layout.addWidget(self.btn_comp_hour)
        
        main_layout.addLayout(filter_layout)
        
        # --- 2. KPI CARDS (Top Row -> 1 Baris agar lebih efisien space) ---
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(8)
        
        self.kpi_sales_today = self._create_kpi_card("Sales Today", "Rp 0")
        self.kpi_sales_mtd = self._create_kpi_card("Sales MTD", "Rp 0")
        self.kpi_to_achieve = self._create_kpi_card("To Achieve", "Rp 0\n(0%)")
        self.kpi_sales_sly = self._create_kpi_card("SLY (YoY)", "Rp 0\n(0%)")
        self.kpi_forecast = self._create_kpi_card("Forecast", "Rp 0")
        self.kpi_qty_large = self._create_kpi_card("Large", "0\n(0%)")
        self.kpi_qty_topping = self._create_kpi_card("Topping", "0\n(0%)")
        self.kpi_productivity = self._create_kpi_card("Productivity", "Rp 0\n(-)")
        
        kpi_layout.addWidget(self.kpi_sales_today)
        kpi_layout.addWidget(self.kpi_sales_mtd)
        kpi_layout.addWidget(self.kpi_to_achieve)
        kpi_layout.addWidget(self.kpi_sales_sly)
        kpi_layout.addWidget(self.kpi_forecast)
        kpi_layout.addWidget(self.kpi_qty_large)
        kpi_layout.addWidget(self.kpi_qty_topping)
        kpi_layout.addWidget(self.kpi_productivity)
        
        main_layout.addLayout(kpi_layout)
        
        # --- 2.5 CELEBRATION BANNER (tersembunyi, muncul di antara KPI & chart saat target tercapai) ---
        self._banner = CelebrationBanner()
        main_layout.addWidget(self._banner)
        
        # ── Middle Row: Peak Hour │ Ojol vs Instore │ Top Menus ──────────────
        middle_chart_layout = QHBoxLayout()

        # Peak Hour Chart
        self.chart_peak_group = QGroupBox("Analisa Peak Hour")
        peak_layout = QVBoxLayout(self.chart_peak_group)
        self.fig_peak = Figure(figsize=(5, 3), dpi=100)
        self.chart_peak = FigureCanvas(self.fig_peak)
        peak_layout.addWidget(self.chart_peak)

        # Ojol vs Instore Chart (NEW)
        self.chart_channel_group = QGroupBox("Ojol vs Instore")
        channel_layout = QVBoxLayout(self.chart_channel_group)
        self.fig_channel = Figure(figsize=(3, 3), dpi=100)
        self.chart_channel = FigureCanvas(self.fig_channel)
        channel_layout.addWidget(self.chart_channel)

        # Top Menus Chart
        self.chart_top_group = QGroupBox("Top Menu")
        top_layout = QVBoxLayout(self.chart_top_group)
        self.fig_top = Figure(figsize=(5, 3), dpi=100)
        self.chart_top = FigureCanvas(self.fig_top)
        top_layout.addWidget(self.chart_top)

        middle_chart_layout.addWidget(self.chart_peak_group, 5)
        middle_chart_layout.addWidget(self.chart_channel_group, 3)
        middle_chart_layout.addWidget(self.chart_top_group, 5)

        main_layout.addLayout(middle_chart_layout)
        
        # Bottom Row: Dynamic Chart & Comparation Chart
        bottom_chart_layout = QHBoxLayout()
        
        self.chart_dyn_group = QGroupBox("Grafik Dinamis")
        dyn_layout = QVBoxLayout(self.chart_dyn_group)
        
        # Dynamic Chart Controls
        dyn_controls = QHBoxLayout()
        self.dyn_x_combo = QComboBox()
        self.dyn_x_combo.addItems(["Tanggal", "Jam", "Kategori", "Group Produk", "MOP"])
        self.dyn_y_combo = QComboBox()
        self.dyn_y_combo.addItems(["Net Sales (Rp)", "Quantity (Qty)", "Transaction Count (TC)"])
        self.dyn_type_combo = QComboBox()
        self.dyn_type_combo.addItems(["Bar", "Line", "Donut"])
        
        self.dyn_x_combo.currentIndexChanged.connect(self._update_dynamic_chart)
        self.dyn_y_combo.currentIndexChanged.connect(self._update_dynamic_chart)
        self.dyn_type_combo.currentIndexChanged.connect(self._update_dynamic_chart)
        
        dyn_controls.addWidget(QLabel("Sumbu X:"))
        dyn_controls.addWidget(self.dyn_x_combo)
        dyn_controls.addWidget(QLabel("Sumbu Y:"))
        dyn_controls.addWidget(self.dyn_y_combo)
        dyn_controls.addWidget(QLabel("Tipe Grafik:"))
        dyn_controls.addWidget(self.dyn_type_combo)
        dyn_controls.addStretch()
        dyn_layout.addLayout(dyn_controls)
        
        # Dynamic Chart Canvas
        self.fig_dyn = Figure(figsize=(6, 3), dpi=100)
        self.chart_dyn = FigureCanvas(self.fig_dyn)
        dyn_layout.addWidget(self.chart_dyn)
        
        bottom_chart_layout.addWidget(self.chart_dyn_group, 6)
        
        # Comparation Chart (Today vs LM)
        self.chart_comp_group = QGroupBox("Komparasi Sales")
        comp_layout = QVBoxLayout(self.chart_comp_group)
        
        self.comp_type_combo = QComboBox()
        self.comp_type_combo.addItems([
            "Today vs Last Month",
            "Today vs Last Week",
            "MTD vs Last Month"
        ])
        self.comp_type_combo.currentIndexChanged.connect(self._update_comparation_chart)
        comp_layout.addWidget(self.comp_type_combo)
        
        self.fig_comp = Figure(figsize=(4, 3), dpi=100)
        self.chart_comp = FigureCanvas(self.fig_comp)
        comp_layout.addWidget(self.chart_comp)
        
        bottom_chart_layout.addWidget(self.chart_comp_group, 4)
        
        main_layout.addLayout(bottom_chart_layout)
        
        # Panggil inisialisasi tanggal pertama kali
        self.set_initial_date_range()

    def set_initial_date_range(self):
        """Set tanggal awal ke Bulan Ini (MTD) berdasarkan data terakhir di DB."""
        site_code = self.parent_app.config_manager.get_config().get('site_code')
        min_date_str, max_date_str = self.db.get_available_date_range(site_code)
        
        self.start_date.blockSignals(True)
        self.end_date.blockSignals(True)
        
        if max_date_str:
            # Gunakan bulan dari data terbaru
            from datetime import datetime
            max_dt = datetime.strptime(max_date_str, "%Y-%m-%d")
            first_day = QDate(max_dt.year, max_dt.month, 1)
            last_day = QDate(max_dt.year, max_dt.month, max_dt.day)
            
            self.start_date.setDate(first_day)
            self.end_date.setDate(last_day)
            
            # Cek apakah itu bulan ini
            today = QDate.currentDate()
            if max_dt.year == today.year() and max_dt.month == today.month():
                self.date_range_combo.setCurrentText("Bulan Ini")
            else:
                self.date_range_combo.setCurrentText("Kustom")
        else:
            # Fallback ke bulan ini dari kalender PC
            today = QDate.currentDate()
            self.start_date.setDate(QDate(today.year(), today.month(), 1))
            self.end_date.setDate(today)
            self.date_range_combo.setCurrentText("Bulan Ini")
            
        self.start_date.blockSignals(False)
        self.end_date.blockSignals(False)
        
        # Langsung load data
        self.load_data()

    def _create_kpi_card(self, title, initial_value):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold; border: none;")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setWordWrap(True)
        
        lbl_value = QLabel(initial_value)
        lbl_value.setStyleSheet("color: #2c3e50; font-size: 14px; font-weight: bold; border: none;")
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setWordWrap(True)
        
        # Menyimpan referensi label ke object frame agar mudah diupdate nanti
        frame.title_label = lbl_title
        frame.value_label = lbl_value 
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)
        return frame

    def update_date_range_auto(self):
        selection = self.date_range_combo.currentText()
        today = QDate.currentDate()
        
        self.start_date.blockSignals(True)
        self.end_date.blockSignals(True)
        
        if selection == "Hari Ini":
            self.start_date.setDate(today)
            self.end_date.setDate(today)
        elif selection == "Kemarin":
            self.start_date.setDate(today.addDays(-1))
            self.end_date.setDate(today.addDays(-1))
        elif selection == "7 Hari Terakhir":
            self.start_date.setDate(today.addDays(-6))
            self.end_date.setDate(today)
        elif selection == "Bulan Ini":
            self.start_date.setDate(QDate(today.year(), today.month(), 1))
            self.end_date.setDate(today)
        elif selection == "Bulan Lalu":
            first_day_prev = QDate(today.year(), today.month(), 1).addMonths(-1)
            last_day_prev = QDate(today.year(), today.month(), 1).addDays(-1)
            self.start_date.setDate(first_day_prev)
            self.end_date.setDate(last_day_prev)
            
        self.start_date.blockSignals(False)
        self.end_date.blockSignals(False)
        
        lbl_period = "(MTD)" if selection == "Bulan Ini" else "(Period)"
        self.kpi_sales_mtd.title_label.setText(f"Sales {lbl_period.replace('(', '').replace(')', '')}")
        self.kpi_to_achieve.title_label.setText(f"To Achieve")
        self.kpi_sales_sly.title_label.setText(f"SLY (YoY)")
        self.kpi_qty_large.title_label.setText(f"Large")
        self.kpi_qty_topping.title_label.setText(f"Topping")
        self.kpi_productivity.title_label.setText(f"Productivity")
        
        self.load_data()

    def load_data(self):
        s_date = self.start_date.date().toPyDate()
        e_date = self.end_date.date().toPyDate()
        site_code = self.parent_app.config_manager.get_config().get('site_code')
        
        # Load data asynchronus
        QTimer.singleShot(10, lambda: self._process_dashboard_metrics(s_date, e_date, site_code))

    def _format_currency(self, value):
        return f"Rp {value:,.0f}".replace(",", ".")

    def _show_achievement_effects(self, over_rp=0, over_pct=0):
        """Menampilkan semua efek perayaan ketika target tercapai."""
        # --- Opsi 1: Update teks pada Card "To Achieve" ---
        self.kpi_to_achieve.title_label.setText("🎉 Target Achieved!")
        self.kpi_to_achieve.value_label.setTextFormat(Qt.RichText)
        
        extra_info = ""
        if over_rp > 0:
            extra_info = f"<br><span style='color:#27ae60; font-size:12px; font-weight:bold;'>+{self._format_currency(over_rp)} (+{over_pct:.1f}%)</span>"
            
        self.kpi_to_achieve.value_label.setText(
            f"<div style='text-align:center;'><span style='color:#27ae60; font-size:15px; font-weight:bold;'>🏆 TARGET TERCAPAI!</span>{extra_info}</div>"
        )

        # --- Opsi 4: Glow border emas pada Card "To Achieve" ---
        self.kpi_to_achieve.setStyleSheet("""
            QFrame {
                background-color: #fffbe6;
                border: 2.5px solid #FFD700;
                border-radius: 8px;
            }
        """)

        # --- Opsi 2: Tampilkan badge di filter bar ---
        self.achievement_badge.setVisible(True)
        self.btn_prakiraan_bonus.setVisible(True)

        # --- Opsi 3: Tampilkan celebration banner (inline, rapi) ---
        store_name = getattr(self.parent_app.config_manager, 'get_store_name', lambda x: '')(
            self.parent_app.config_manager.get_config().get('site_code', '')
        )
        sub_msg = f"Selamat, {store_name}! Target bulan ini telah tercapai 🎉" if store_name else "Target bulan ini telah tercapai 🎉"
        self._banner.show_banner(sub_msg, auto_hide_ms=8000)

    def _hide_achievement_effects(self):
        """Menyembunyikan semua efek perayaan jika target belum terpenuhi."""
        # --- Reset Card "To Achieve" ke normal ---
        period = self.kpi_to_achieve.title_label.text()
        if "Achieved" in period or "🎉" in period:
            # Restore periode label
            lbl_period = "(MTD)" if self.date_range_combo.currentText() == "Bulan Ini" else "(Period)"
            self.kpi_to_achieve.title_label.setText(f"To Achieve {lbl_period}")

        self.kpi_to_achieve.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
        """)

        # --- Sembunyikan badge ---
        self.achievement_badge.setVisible(False)
        self.btn_prakiraan_bonus.setVisible(False)

        # --- Sembunyikan banner ---
        self._banner.hide_banner()

    def _process_dashboard_metrics(self, s_date, e_date, site_code):
        # 1. Fetch data dari Database Manager untuk tanggal mulai (S_DATE) dan akhir (E_DATE)
        # s_date & e_date akan digunakan untuk hitung MTD Periodical, e_date untuk 'Today' metrics
        metrics = self.db.get_dashboard_metrics(s_date, e_date, site_code)
        
        import datetime
        if isinstance(e_date, str):
            e_date_obj = datetime.datetime.strptime(e_date, "%Y-%m-%d").date()
        else:
            e_date_obj = e_date
        # --- FIND ACTUAL LATEST DATE ---
        actual_latest_str = e_date_obj.strftime('%Y-%m-%d')
        conn = self.db.get_connection()
        if conn:
            try:
                c = conn.cursor()
                site_filter = " AND site_code = ?" if site_code else ""
                params_latest = [e_date_obj.strftime('%Y-%m-%d'), site_code] if site_code else [e_date_obj.strftime('%Y-%m-%d')]
                c.execute(f"SELECT MAX(created_date) as max_date FROM raw_transactions WHERE created_date <= ? AND is_void = 0 {site_filter}", params_latest)
                row = c.fetchone()
                if row and row['max_date']:
                    actual_latest_str = row['max_date']
            except Exception: pass
            finally: conn.close()
        
        try:
            actual_latest_obj = datetime.datetime.strptime(actual_latest_str, "%Y-%m-%d").date()
        except Exception:
            actual_latest_obj = e_date_obj
        
        # --- GET RAW METRICS HELPER ---
        def get_raw_metrics(dt_start_obj, dt_end_obj=None):
            conn = self.db.get_connection()
            if not conn: return {'sales': 0, 'tc': 0, 'large': 0, 'ouast': 0, 'ac': 0}
            try:
                cursor = conn.cursor()
                site_filter = " AND site_code = ?" if site_code else ""
                
                if dt_end_obj:
                    params = [dt_start_obj.strftime('%Y-%m-%d'), dt_end_obj.strftime('%Y-%m-%d')]
                    if site_code: params.append(site_code)
                    date_cond = "created_date BETWEEN ? AND ?"
                else:
                    params = [dt_start_obj.strftime('%Y-%m-%d')]
                    if site_code: params.append(site_code)
                    date_cond = "created_date = ?"
                
                cursor.execute(f"SELECT sum(net_price) as sales, count(DISTINCT receipt_no) as tc FROM raw_transactions WHERE {date_cond} AND is_void = 0 {site_filter}", params)
                r1 = cursor.fetchone()
                sales = (r1['sales'] / 1.1) if r1 and r1['sales'] else 0
                tc = r1['tc'] if r1 and r1['tc'] else 0
                
                cursor.execute(f"SELECT sum(quantity) as qty FROM raw_transactions WHERE {date_cond} AND is_void = 0 AND article_name LIKE '%(L)%' {site_filter}", params)
                r2 = cursor.fetchone()
                large = r2['qty'] if r2 and r2['qty'] else 0
                
                cursor.execute(f"SELECT sum(net_price) as sales FROM raw_transactions WHERE {date_cond} AND is_void = 0 AND (product_group_name LIKE '%Food%' OR product_group_name LIKE '%Snack%' OR product_group_name LIKE '%Ouast%') {site_filter}", params)
                r3 = cursor.fetchone()
                ouast = (r3['sales'] / 1.1) if r3 and r3['sales'] else 0
                
                ac = sales / tc if tc > 0 else 0
                return {'sales': sales, 'tc': tc, 'large': large, 'ouast': ouast, 'ac': ac}
            except Exception:
                return {'sales': 0, 'tc': 0, 'large': 0, 'ouast': 0, 'ac': 0}
            finally:
                conn.close()

        # Dates
        lw_date_obj = actual_latest_obj - datetime.timedelta(days=7)
        lm_date_obj = actual_latest_obj - datetime.timedelta(days=28)
        
        try:
            from dateutil.relativedelta import relativedelta
            s_date_obj = datetime.datetime.strptime(s_date, "%Y-%m-%d").date() if isinstance(s_date, str) else s_date
            mtd_lm_start = s_date_obj - relativedelta(months=1)
            mtd_lm_end = actual_latest_obj - relativedelta(months=1)
        except Exception:
            s_date_obj = datetime.datetime.strptime(s_date, "%Y-%m-%d").date() if isinstance(s_date, str) else s_date
            mtd_lm_start = s_date_obj - datetime.timedelta(days=28)
            mtd_lm_end = actual_latest_obj - datetime.timedelta(days=28)

        metrics['comp_data'] = {
            'Today': get_raw_metrics(actual_latest_obj),
            'Last Week': get_raw_metrics(lw_date_obj),
            'Last Month': get_raw_metrics(lm_date_obj),
            'MTD': get_raw_metrics(s_date_obj, actual_latest_obj),
            'MTD Last Month': get_raw_metrics(mtd_lm_start, mtd_lm_end)
        }
        
        # 2. Update KPI Cards
        sales_mtd = metrics.get('sales_mtd', 0)
        sales_sly = metrics.get('sales_sly', 0)
        
        self.kpi_sales_today.value_label.setText(self._format_currency(metrics.get('sales_today', 0)))

        # ── Konversi e_date ke objek date (diperlukan untuk target_month & forecast) ──
        import calendar
        
        current_day = e_date_obj.day
        total_days_in_month = calendar.monthrange(e_date_obj.year, e_date_obj.month)[1]
        target_month = self.parent_app.config_manager.get_target_for_month(e_date_obj.month)
        
        self.current_sales_mtd = sales_mtd
        self.current_target_month = target_month

        # Sales MTD + persentase pencapaian target
        if target_month > 0:
            mtd_pct = (sales_mtd / target_month) * 100
            mtd_color = "#27ae60" if mtd_pct >= 100 else ("#e67e22" if mtd_pct >= 70 else "#e74c3c")
            self.kpi_sales_mtd.value_label.setTextFormat(Qt.RichText)
            self.kpi_sales_mtd.value_label.setText(
                f"{self._format_currency(sales_mtd)}"
                f"<br><span style='font-size:12px; color:{mtd_color}; font-weight:bold;'>"
                f"({mtd_pct:.1f}%)</span>"
            )
        else:
            self.kpi_sales_mtd.value_label.setTextFormat(Qt.PlainText)
            self.kpi_sales_mtd.value_label.setText(self._format_currency(sales_mtd))
        
        # Calculate SSG YoY %
        yoy_growth = 0
        if sales_sly > 0:
             yoy_growth = ((sales_mtd - sales_sly) / sales_sly) * 100
             
        yoy_color = "green" if yoy_growth > 0 else "red" if yoy_growth < 0 else "black"
        yoy_sign = "+" if yoy_growth > 0 else ""
        sly_text = f"{self._format_currency(sales_sly)}\n(<span style='color:{yoy_color};'>{yoy_sign}{yoy_growth:.1f}%</span>)"
        
        self.kpi_sales_sly.value_label.setTextFormat(Qt.RichText)
        self.kpi_sales_sly.value_label.setText(sly_text)
        
        # Calculate to achieve
        over_rp = 0
        over_pct = 0
        
        # Calculate To Achieve (Target - MTD)
        to_achieve_rp = target_month - sales_mtd
        
        # If target has been surpassed, the to achieve amount should technically be 0 (or negative depending on user preference, we set it to 0 and show positive achievement)
        if to_achieve_rp < 0:
            over_rp = abs(to_achieve_rp)
            to_achieve_rp = 0
            
        # MTD percentage
        if target_month > 0:
            if sales_mtd < target_month:
                lacking_pct = ((target_month - sales_mtd) / target_month) * 100
            else:
                lacking_pct = 0
                over_pct = ((sales_mtd - target_month) / target_month) * 100
        else:
            lacking_pct = 0
            
        # Handle colors: Red if lacking > 0, Green if achieved
        ach_color = "red" if lacking_pct > 0 else "green"
        
        if over_rp > 0 or over_pct > 0:
            lacking_str = f"+{over_pct:.1f}%"
            to_achieve_text = f"+{self._format_currency(over_rp)}\n(<span style='color:{ach_color};'>{lacking_str}</span>)"
        else:
            lacking_str = f"-{lacking_pct:.1f}%" if lacking_pct > 0 else "0.0%"
            to_achieve_text = f"{self._format_currency(to_achieve_rp)}\n(<span style='color:{ach_color};'>{lacking_str}</span>)"
            
        self.kpi_to_achieve.value_label.setTextFormat(Qt.RichText)
        self.kpi_to_achieve.value_label.setText(to_achieve_text)
        
        # Trigger / hide celebration effects based on achievement
        if target_month > 0 and lacking_pct == 0:
            self._show_achievement_effects(over_rp, over_pct)
        else:
            self._hide_achievement_effects()

        
        # Hitung Forecast: Sales MTD dibagi jumlah hari berjalan, dikali total hari sebulan
        if current_day > 0:
            forecast = (sales_mtd / current_day) * total_days_in_month
        else:
            forecast = 0
            
        if target_month > 0:
            forecast_pct = (forecast / target_month) * 100
            fc_color = "green" if forecast_pct >= 100 else "red"
            forecast_text = f"{self._format_currency(forecast)}\n(<span style='color:{fc_color};'>{forecast_pct:.1f}%</span>)"
        else:
            forecast_text = f"{self._format_currency(forecast)}\n(<span style='color:black;'>0.0%</span>)"
            
        self.kpi_forecast.value_label.setTextFormat(Qt.RichText)
        self.kpi_forecast.value_label.setText(forecast_text)
        
        # --- Override Qty Large & Topping from ReportProcessor (Akurasi 100% dgn Sales Report) ---
        qty_large = metrics.get('qty_large', 0)
        perc_large = metrics.get('perc_large', 0)
        qty_topping = metrics.get('qty_topping', 0)
        perc_topping = metrics.get('perc_topping', 0)
        
        # Coba ambil dari memori main_app yang sudah dikalkulasi ReportProcessor
        is_mtd = (self.date_range_combo.currentText() == "Bulan Ini")
        if is_mtd and hasattr(self.parent_app, 'report_results_data') and self.parent_app.report_results_data:
            rp_data = self.parent_app.report_results_data
            if 'mtd_qty_large' in rp_data:
                qty_large = rp_data['mtd_qty_large']
                val = rp_data.get('mtd_pct_large', 0)
                perc_large = val.replace('%', '') if isinstance(val, str) else round(val, 1)
            if 'mtd_qty_topping' in rp_data:
                qty_topping = rp_data['mtd_qty_topping']
                val = rp_data.get('mtd_pct_topping', 0)
                perc_topping = val.replace('%', '') if isinstance(val, str) else round(val, 1)
        
        self.kpi_qty_large.value_label.setText(f"{qty_large}\n({perc_large}%)")
        self.kpi_qty_topping.value_label.setText(f"{qty_topping}\n({perc_topping}%)")
        
        # --- 2.5 Hitung Productivity ---
        from utils.employee_utils import EmployeeDB
        try:
            emp_db = EmployeeDB()
            employees = emp_db.get_all_employees()
            fulltime_count = sum(1 for e in employees if e.get('jabatan') in ['Store Manager', 'Asst. Store Manager', 'Staff'])
            partimer_count = sum(1 for e in employees if e.get('jabatan') == 'Partimer')
            total_emp_value = fulltime_count + (partimer_count * 0.8)
            
            if total_emp_value > 0:
                productivity = forecast / total_emp_value
                # Standar 35 Juta dengan margin +/- 5% (33.25jt - 36.75jt)
                if productivity > 36750000:
                    mpp_status = "MPP Kurang"
                    status_color = "#e74c3c" # Merah
                elif productivity < 33250000:
                    mpp_status = "MPP Lebih"
                    status_color = "#e67e22" # Orange
                else:
                    mpp_status = "MPP Cukup"
                    status_color = "#27ae60" # Hijau
                
                prod_text = f"{self._format_currency(productivity)}<br><span style='color:{status_color}; font-size:12px; font-weight:normal;'>({mpp_status} | {total_emp_value:g} Ppl)</span>"
            else:
                prod_text = "Rp 0<br><span style='color:#7f8c8d; font-size:12px; font-weight:normal;'>(Tidak Ada Data Karyawan)</span>"
        except Exception as e:
            logging.error(f"Error kalkulasi productivity: {e}")
            prod_text = "Rp 0<br><span style='color:#7f8c8d; font-size:12px; font-weight:normal;'>(Error)</span>"
            
        self.kpi_productivity.value_label.setTextFormat(Qt.RichText)
        self.kpi_productivity.value_label.setText(prod_text)

        
        # 3. Process Peak Hour Chart
        self._plot_peak_hour(metrics.get('peak_hour', []))
        
        # 4. Process Top Menus Chart
        import textwrap
        top_menus_clean = []
        for m in metrics.get('top_menus', []):
            label = str(m['article_name'])
            if len(label) > 25:
                # Wrap text or truncate
                label = textwrap.shorten(label, width=25, placeholder="...")
            m_copy = dict(m)
            m_copy['article_name_short'] = label
            top_menus_clean.append(m_copy)
            
        self._plot_top_menus(top_menus_clean)

        # 5. Channel Chart (Ojol vs Instore)
        self._plot_channel_chart(metrics.get('channel_sales', []))

        # 6. Process Dynamic Chart & Comparation Chart
        self._update_dynamic_chart()
        self.current_comp_data = metrics.get('comp_data', None)
        self._update_comparation_chart()

    def _plot_peak_hour(self, data):
        self.fig_peak.clear()
        ax = self.fig_peak.add_subplot(111)
        if data:
            hours = [d['hour'] for d in data]
            sales = [d['sales'] for d in data]
            tc = [d['tc'] for d in data]
            sales_ouast = [d.get('sales_ouast', 0) for d in data]
            sales_non_ouast = [d.get('sales_non_ouast', 0) for d in data]
            
            # Line Chart for Sales
            ax.plot(hours, sales, marker='o', linestyle='-', color='#2ecc71', label="Global", linewidth=2)
            ax.plot(hours, sales_non_ouast, marker='s', linestyle='--', color='#3498db', label="Non-Ouast", linewidth=1.5, alpha=0.8)
            ax.plot(hours, sales_ouast, marker='^', linestyle='-.', color='#f39c12', label="Ouast", linewidth=1.5, alpha=0.8)
            
            ax.set_ylabel("Sales (Rp)")
            
            # Create twin axis for TC
            ax2 = ax.twinx()
            ax2.bar(hours, tc, alpha=0.15, color='#95a5a6', label="TC (Global)")
            ax2.set_ylabel("Transaction Count", color='#7f8c8d')
            ax2.tick_params(axis='y', labelcolor='#7f8c8d')
            
            ax.grid(True, linestyle='--', alpha=0.6)
            
            # Legend mapping
            lines_1, labels_1 = ax.get_legend_handles_labels()
            lines_2, labels_2 = ax2.get_legend_handles_labels()
            ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=8)
            
            self.fig_peak.autofmt_xdate()
        else:
            ax.text(0.5, 0.5, "Tidak ada data Peak Hour", ha='center', va='center')
            
        try: self.chart_peak.draw()
        except Exception: pass

    def _plot_channel_chart(self, data):
        """Donut chart Ojol vs Instore — layout proporsional dengan legend di dalam canvas."""
        self.fig_channel.clear()

        channel_colors = {
            'Instore': '#3498db',
            'Ojol':    '#e67e22',
        }

        if not data:
            ax = self.fig_channel.add_axes([0, 0, 1, 1])
            ax.axis('off')
            ax.text(0.5, 0.5, "Tidak ada\ndata channel",
                    ha='center', va='center', fontsize=9, color='#95a5a6',
                    transform=ax.transAxes)
            try: self.chart_channel.draw()
            except Exception: pass
            return

        labels = [d['channel'] for d in data]
        sizes  = [d['sales']   for d in data]
        pcts   = [d['pct']     for d in data]
        colors = [channel_colors.get(lbl, '#95a5a6') for lbl in labels]

        # --- Donut di area atas (70% tinggi canvas) ---
        # [left, bottom, width, height] dalam koordinat normalisasi figure
        ax_donut = self.fig_channel.add_axes([0.05, 0.28, 0.90, 0.68])

        wedges, _ = ax_donut.pie(
            sizes,
            labels=None,
            startangle=90,
            colors=colors,
            wedgeprops=dict(width=0.52, edgecolor='white', linewidth=2.5),
            counterclock=False,
        )
        ax_donut.axis('equal')

        # --- Legend teks di bawah (30% bawah canvas), disusun horizontal ---
        ax_legend = self.fig_channel.add_axes([0, 0, 1, 0.30])
        ax_legend.axis('off')

        n = len(labels)
        for i, (lbl, s, pct, clr) in enumerate(zip(labels, sizes, pcts, colors)):
            # Posisi X per item: dibagi rata (0.25 dan 0.75 untuk n=2)
            x_center = (i + 0.5) / n
            
            # Bullet warna (unicode kotak)
            ax_legend.text(x_center - 0.02, 0.75, '■',
                           ha='right', va='center', fontsize=10,
                           color=clr, transform=ax_legend.transAxes)
            # Label nama
            ax_legend.text(x_center + 0.02, 0.75, lbl,
                           ha='left', va='center', fontsize=8, fontweight='bold',
                           color='#2c3e50', transform=ax_legend.transAxes)
            # Persen
            ax_legend.text(x_center, 0.40, f"{pct:.1f}%",
                           ha='center', va='center', fontsize=8.5, fontweight='bold',
                           color=clr, transform=ax_legend.transAxes)
            # Nominal
            ax_legend.text(x_center, 0.10, self._format_currency(s),
                           ha='center', va='center', fontsize=7, color='#666666',
                           transform=ax_legend.transAxes)

        try: self.chart_channel.draw()
        except Exception: pass

    def _plot_top_menus(self, data):
        self.fig_top.clear()
        ax = self.fig_top.add_subplot(111)
        if data:
            from utils.app_utils import get_base_article_name
            # Aggregate by base name
            aggregated = {}
            for d in data:
                base_name = get_base_article_name(d['article_name'])
                if base_name in aggregated:
                    aggregated[base_name] += d['qty']
                else:
                    aggregated[base_name] = d['qty']
            
            # Convert back to list of dicts for sorting
            agg_data = [{'article_name': k, 'qty': v} for k, v in aggregated.items()]
            
            # Sort asc so largest is at top in barh, limit to top 10 after aggregation
            data_sorted = sorted(agg_data, key=lambda x: x['qty'])[-10:]
            
            # Truncate names to avoid overlapping y-ticks and fit in figure
            import textwrap
            names = [textwrap.shorten(d['article_name'], width=18, placeholder="..") for d in data_sorted]
            qtys = [d['qty'] for d in data_sorted]
            
            colors = ['#1abc9c', '#2ecc71', '#3498db', '#9b59b6', '#34495e'] * 2
            ax.barh(names, qtys, color=colors[:len(names)], height=0.7)
            
            # Adjust tick label size to prevent vertical overlapping
            ax.tick_params(axis='y', labelsize=6.5)
            
            # Add value labels with padding
            max_qty = max(qtys) if qtys else 1
            pad = max_qty * 0.03
            for i, v in enumerate(qtys):
                ax.text(v + pad, i, str(v), va='center', fontsize=7.5)
            
            # Expand x-limit slightly so text doesn't get cut off
            ax.set_xlim(0, max_qty * 1.20)
            
            ax.grid(axis='x', linestyle='--', alpha=0.5)
        else:
            ax.text(0.5, 0.5, "Tidak ada data Top Menu", ha='center', va='center')
            
        self.fig_top.subplots_adjust(left=0.35, right=0.90, top=0.90, bottom=0.15)
        try: self.chart_top.draw()
        except Exception: pass

    def _update_comparation_chart(self):
        if not hasattr(self, 'current_comp_data') or not self.current_comp_data:
            return
            
        comp_type = self.comp_type_combo.currentText()
        if comp_type == "Today vs Last Month":
            current_data = self.current_comp_data['Today']
            prev_data = self.current_comp_data['Last Month']
        elif comp_type == "Today vs Last Week":
            current_data = self.current_comp_data['Today']
            prev_data = self.current_comp_data['Last Week']
        elif comp_type == "MTD vs Last Month":
            current_data = self.current_comp_data['MTD']
            prev_data = self.current_comp_data['MTD Last Month']
        else:
            return
            
        self._plot_comparation_chart(current_data, prev_data)

    def _plot_comparation_chart(self, current_data, prev_data):
        self.fig_comp.clear()
        if not current_data or not prev_data:
            return
            
        ax = self.fig_comp.add_subplot(111)
        
        metrics_list = [
            ('Sales', current_data['sales'], prev_data['sales'], True),
            ('Ouast', current_data['ouast'], prev_data['ouast'], True),
            ('TC', current_data['tc'], prev_data['tc'], False),
            ('AC', current_data['ac'], prev_data['ac'], True),
            ('Large', current_data['large'], prev_data['large'], False)
        ]
        
        metrics_list.reverse()
        
        labels = []
        growths = []
        colors = []
        texts = []
        
        for name, t_val, lm_val, is_currency in metrics_list:
            labels.append(name)
            if lm_val > 0:
                growth = ((t_val - lm_val) / lm_val) * 100
            else:
                growth = 100 if t_val > 0 else 0
                
            growths.append(growth)
            colors.append('#2ecc71' if growth >= 0 else '#e74c3c')
            
            # Format actual value for display
            if is_currency:
                t_str = f"{t_val/1000:.0f}K" if t_val > 0 else "0"
            else:
                t_str = f"{int(t_val)}"
                
            texts.append(f"{t_str} ({growth:+.1f}%)")
            
        bars = ax.barh(labels, growths, color=colors, alpha=0.8, height=0.6)
        
        ax.axvline(0, color='black', linewidth=1.2, linestyle='-')
        
        for i, (growth, text) in enumerate(zip(growths, texts)):
            if growth >= 0:
                ax.text(growth + 5, i, text, va='center', ha='left', fontsize=8, color='#2c3e50', fontweight='bold')
            else:
                # Draw text to the right of 0-line to avoid overlapping left labels
                ax.text(5, i, text, va='center', ha='left', fontsize=8, color='#2c3e50', fontweight='bold')
                
        max_g = max(growths + [0])
        min_g = min(growths + [0])
        ax.set_xlim(min_g - 10, max_g + 80)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#bdc3c7')
        ax.tick_params(axis='y', length=0, labelsize=9)
        ax.tick_params(axis='x', labelsize=8, colors='#7f8c8d')
        
        self.fig_comp.subplots_adjust(left=0.25, right=0.85, top=0.90, bottom=0.15)
        try: self.chart_comp.draw()
        except Exception: pass

    def _update_dynamic_chart(self):
        s_date = self.start_date.date().toString("yyyy-MM-dd")
        e_date = self.end_date.date().toString("yyyy-MM-dd")
        site_code = self.parent_app.config_manager.get_config().get('site_code')
        
        x_axis = self.dyn_x_combo.currentText()
        y_axis = self.dyn_y_combo.currentText()
        c_type = self.dyn_type_combo.currentText()
        
        # Mapping UI names to Pandas Columns
        col_x = "Tanggal"
        if x_axis == "Tanggal": col_x = "Tanggal"
        elif x_axis == "Jam": col_x = "Created Time"
        elif x_axis == "Kategori": col_x = "Category Name"
        elif x_axis == "Group Produk": col_x = "Product Group Name"
        elif x_axis == "MOP": col_x = "MOP Name" # Note: Needs payment data for MOP
            
        col_y = "Net Price"
        if y_axis == "Net Sales (Rp)": col_y = "Net Price"
        elif y_axis == "Quantity (Qty)": col_y = "Quantity"
        elif y_axis == "Transaction Count (TC)": col_y = "Receipt No"
        
        # Load raw data based on date range (Note: using get_transactions_dataframe)
        df = self.db.get_transactions_dataframe(s_date, e_date, site_code)
        
        self.fig_dyn.clear()
        ax = self.fig_dyn.add_subplot(111)
        
        if not df.empty and col_x in df.columns:
            if col_y == "Receipt No":
                # TC count unique receipts
                grouped = df.groupby(col_x)[col_y].nunique().reset_index()
            else:
                grouped = df.groupby(col_x)[col_y].sum().reset_index()
                
            if col_x == "Tanggal":
                # Jika sumbu X adalah Tanggal, urutkan berdasarkan waktu (kronologis)
                grouped = grouped.sort_values(by=col_x, ascending=True)
            else:
                # Selain tanggal, urutkan berdasarkan nilai Y tertinggi
                grouped = grouped.sort_values(by=col_y, ascending=False).head(15) # Limit for readability
            
            X_data = grouped[col_x].astype(str)
            Y_data = grouped[col_y]
            
            if c_type == "Bar":
                # Styling Bar Chart to look modern
                bars = ax.bar(X_data, Y_data, color='#8e44ad', edgecolor='none', width=0.7)
                # Adds values on top of bars
                for bar in bars:
                    yval = bar.get_height()
                    if y_axis != "Net Sales (Rp)":
                        ax.text(bar.get_x() + bar.get_width()/2, yval + (yval*0.02), f'{int(yval)}', ha='center', va='bottom', fontsize=8, color='#555555')
                        
            elif c_type == "Line":
                grouped = grouped.sort_values(by=col_x) # Sort by X to make lines readable
                ax.plot(grouped[col_x].astype(str), grouped[col_y], marker='o', linestyle='-', color='#8e44ad', linewidth=2, markersize=6)
                
            elif c_type == "Donut":
                # Tampilan Donut Chart yang menarik
                colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f1c40f', '#e67e22', '#1abc9c', '#34495e', '#ecf0f1', '#95a5a6']
                wedges, texts, autotexts = ax.pie(
                    Y_data, 
                    labels=X_data, 
                    autopct='%1.1f%%', 
                    startangle=90, 
                    colors=colors[:len(Y_data)],
                    wedgeprops=dict(width=0.4, edgecolor='w') # parameter 'width' membuatnya jadi Donut
                )
                plt.setp(autotexts, size=8, weight="bold", color="white")
                plt.setp(texts, size=8)
                ax.axis('equal')  # Ensures pie chart is drawn as a circle
            
            if c_type != "Donut":
                ax.set_ylabel(y_axis, color='#7f8c8d')
                self.fig_dyn.autofmt_xdate(rotation=45, ha='right')
                ax.grid(axis='y', linestyle='--', alpha=0.4)
                ax.spines['left'].set_visible(False)
                ax.spines['bottom'].set_color('#bdc3c7')
                ax.tick_params(axis='x', colors='#34495e')
                ax.tick_params(axis='y', colors='#34495e')
        else:
            ax.text(0.5, 0.5, f"Data tidak tersedia untuk kombinasi\n{x_axis} vs {y_axis}", ha='center', va='center', color='#95a5a6')

        self.fig_dyn.tight_layout(pad=1.5)
        try: self.chart_dyn.draw()
        except Exception: pass

    def _show_prakiraan_bonus(self):
        if not hasattr(self, 'current_sales_mtd') or not hasattr(self, 'current_target_month'):
            return
            
        sales = self.current_sales_mtd
        target = self.current_target_month
        
        if target <= 0:
            QMessageBox.warning(self, "Perhatian", "Target belum disetel untuk bulan ini.")
            return
            
        pct = (sales / target) * 100
        
        # Penentuan koefisien bonus berdasarkan persentase (Net Sales based)
        if pct >= 120:
            bonus_pct = 1.65
        elif pct > 100:
            bonus_pct = 1.20
        elif pct >= 95:
            bonus_pct = 0.90
        else:
            bonus_pct = 0
            
        if bonus_pct == 0:
            QMessageBox.information(self, "Informasi", f"Pencapaian target ({pct:.1f}%) belum mencapai 95%, belum ada prakiraan bonus.")
            return
            
        total_bonus = sales * (bonus_pct / 100)
        
        # Hitung share per role
        ratio_sm = 3
        ratio_asm = 2
        ratio_staff = 1.25
        
        from utils.employee_utils import EmployeeDB
        try:
            emp_db = EmployeeDB()
            employees = emp_db.get_all_employees()
            count_sm = sum(1 for e in employees if e.get('jabatan') == 'Store Manager')
            count_asm = sum(1 for e in employees if e.get('jabatan') == 'Asst. Store Manager')
            count_staff = sum(1 for e in employees if e.get('jabatan') == 'Staff')
        except Exception as e:
            logging.error(f"Error fetching employees for bonus: {e}")
            count_sm = 1
            count_asm = 1
            count_staff = 3
            
        # Jika belum ada data karyawan
        if count_sm == 0 and count_asm == 0 and count_staff == 0:
            count_sm = 1
            count_asm = 1
            count_staff = 3
            
        total_shares = (count_sm * ratio_sm) + (count_asm * ratio_asm) + (count_staff * ratio_staff)
        if total_shares <= 0:
            QMessageBox.warning(self, "Error", "Total proporsi share karyawan tidak valid.")
            return
            
        bonus_per_share = total_bonus / total_shares
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Prakiraan Bonus (Estimasi)")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        
        # Info header
        info_lbl = QLabel(f"<b>Pencapaian:</b> {pct:.2f}%<br>"
                          f"<b>Nett Sales (MTD):</b> {self._format_currency(sales)}<br>"
                          f"<b>Persentase Bonus:</b> {bonus_pct:.2f}%<br>"
                          f"<b>Total Estimasi Bonus:</b> <span style='color:#27ae60; font-size:14px; font-weight:bold;'>{self._format_currency(total_bonus)}</span>")
        layout.addWidget(info_lbl)
        
        # Tabel
        table = QTableWidget(3, 4)
        table.setHorizontalHeaderLabels(["Jabatan", "Jml Karyawan", "Rasio", "Estimasi Bonus/Org"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("QTableWidget { background-color: white; border: 1px solid #dcdde1; }")
        
        def add_row(row, title, count, ratio):
            table.setItem(row, 0, QTableWidgetItem(title))
            table.setItem(row, 1, QTableWidgetItem(str(count)))
            table.setItem(row, 2, QTableWidgetItem(str(ratio)))
            val = self._format_currency(bonus_per_share * ratio)
            item_val = QTableWidgetItem(val)
            item_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 3, item_val)
            
        add_row(0, "Store Manager", count_sm, ratio_sm)
        add_row(1, "Asst. Store Manager", count_asm, ratio_asm)
        add_row(2, "Staff", count_staff, ratio_staff)
        
        layout.addWidget(table)
        
        disclaimer = QLabel("<i>*Nilai di atas hanyalah estimasi perhitungan kotor.</i>")
        disclaimer.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        layout.addWidget(disclaimer)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        
        dlg.exec_()

    # ================================================================
    # HOURLY COMPARISON DIALOG
    # ================================================================

    def _open_hourly_comparison_dialog(self):
        """Buka dialog Komparasi Per Jam.
        Default date1 = tanggal yang sudah diset user di filter dashboard (end_date).
        Default time  = jam saat ini.
        """
        site_code = self.parent_app.config_manager.get_config().get('site_code')
        # Gunakan tanggal dari end_date di filter dashboard
        default_date_str = self.end_date.date().toString("yyyy-MM-dd")
        # Gunakan jam saat ini sebagai default cutoff
        from PyQt5.QtCore import QTime
        default_time_str = QTime.currentTime().toString("HH:mm")
        dlg = HourlyComparisonDialog(
            self.db, site_code,
            default_date_str=default_date_str,
            default_time_str=default_time_str,
            parent=self
        )
        dlg.exec_()


class HourlyComparisonDialog(QDialog):
    """Dialog popup Komparasi Sales Per Jam."""

    def __init__(self, db, site_code, default_date_str=None, default_time_str=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.site_code = site_code
        self.setWindowTitle("📊 Komparasi Sales Per Jam")
        self.setMinimumSize(820, 520)
        self.resize(900, 560)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        # Tentukan default date1
        if default_date_str:
            try:
                import datetime as _dt
                d = _dt.datetime.strptime(default_date_str, "%Y-%m-%d").date()
                self._default_date1 = QDate(d.year, d.month, d.day)
            except Exception:
                self._default_date1 = QDate.currentDate()
        else:
            self._default_date1 = QDate.currentDate()

        # Tentukan default time
        if default_time_str:
            try:
                self._default_time = QTime.fromString(default_time_str, "HH:mm")
            except Exception:
                self._default_time = QTime.currentTime()
        else:
            self._default_time = QTime.currentTime()

        self._build_ui()
        # Auto-run saat dialog dibuka (tampilkan data awal)
        self._run_comparison()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 14, 16, 14)

        # ── Header ────────────────────────────────────────────────────
        hdr = QLabel("Bandingkan performa sales, TC, AC, Large, dan Ouast pada dua tanggal di jam yang sama.")
        hdr.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
        root.addWidget(hdr)

        # ── Row Kontrol ───────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        # Tanggal 1
        lbl1 = QLabel("Tanggal:")
        lbl1.setStyleSheet("font-weight: bold; font-size: 11px;")
        ctrl.addWidget(lbl1)
        self.date1 = QDateEdit(self._default_date1)
        self.date1.setCalendarPopup(True)
        self.date1.setDisplayFormat("dd/MM/yyyy")
        self.date1.setFixedWidth(115)
        ctrl.addWidget(self.date1)

        ctrl.addSpacing(4)
        lbl_time = QLabel("s/d Jam:")
        lbl_time.setStyleSheet("font-weight: bold; font-size: 11px;")
        ctrl.addWidget(lbl_time)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(self._default_time)
        self.time_edit.setFixedWidth(72)
        ctrl.addWidget(self.time_edit)

        # Separator
        sep = QLabel("vs")
        sep.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 14px; padding: 0 8px;")
        ctrl.addWidget(sep)

        # Mode pembanding
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Last Week", "Last Month", "Custom"])
        self.mode_combo.setFixedWidth(115)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        ctrl.addWidget(self.mode_combo)

        # Tanggal 2 custom
        self.date2 = QDateEdit(self._default_date1.addDays(-7))
        self.date2.setCalendarPopup(True)
        self.date2.setDisplayFormat("dd/MM/yyyy")
        self.date2.setFixedWidth(115)
        self.date2.setVisible(False)
        ctrl.addWidget(self.date2)

        ctrl.addStretch()

        # Tombol Bandingkan
        self.btn_run = QPushButton("🔍  Bandingkan")
        self.btn_run.setFixedHeight(32)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 20px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover { background-color: #2471a3; }
            QPushButton:pressed { background-color: #1a5276; }
        """)
        self.btn_run.clicked.connect(self._run_comparison)
        ctrl.addWidget(self.btn_run)
        root.addLayout(ctrl)

        # ── Info Label ────────────────────────────────────────────────
        self.info_lbl = QLabel("Memuat data...")
        self.info_lbl.setStyleSheet(
            "color: #2c3e50; font-size: 11px; font-weight: bold; "
            "background: #eaf4fb; padding: 6px 10px; border-radius: 6px;"
        )
        root.addWidget(self.info_lbl)

        # ── Tabel + Chart berdampingan ────────────────────────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # ---- Tabel ----
        self.table = QTableWidget(5, 4)
        self.table.setHorizontalHeaderLabels(["Metrik", "TW", "Pembanding", "Δ (%)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(190)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #d5d8dc;
                border-radius: 6px;
                gridline-color: #ecf0f1;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 4px;
                border: none;
            }
            QTableWidget::item { padding: 4px 6px; }
            QTableWidget::item:alternate { background-color: #f4f6f7; }
        """)
        # Placeholder rows
        for r, name in enumerate(["Sales", "TC", "AC", "Large", "Ouast"]):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            for c in range(1, 4):
                self.table.setItem(r, c, QTableWidgetItem("-"))
        content_row.addWidget(self.table, 4)

        # ---- Chart ----
        self.fig = Figure(figsize=(5.5, 3.5), dpi=90)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setMinimumHeight(190)
        content_row.addWidget(self.canvas, 6)

        root.addLayout(content_row)

        # ── Tombol Tutup ──────────────────────────────────────────────
        btn_close = QDialogButtonBox(QDialogButtonBox.Close)
        btn_close.rejected.connect(self.accept)
        root.addWidget(btn_close)

    def _on_mode_changed(self, mode):
        self.date2.setVisible(mode == "Custom")

    def _run_comparison(self):
        """Query data dan update tabel + chart."""
        import datetime

        date1 = self.date1.date().toPyDate()
        date1_str = date1.strftime('%Y-%m-%d')
        cutoff_str = self.time_edit.time().toString("HH:mm")

        mode = self.mode_combo.currentText()
        if mode == "Last Week":
            date2 = date1 - datetime.timedelta(days=7)
        elif mode == "Last Month":
            try:
                from dateutil.relativedelta import relativedelta
                date2 = date1 - relativedelta(months=1)
            except ImportError:
                date2 = date1 - datetime.timedelta(days=28)
        else:
            date2 = self.date2.date().toPyDate()
        date2_str = date2.strftime('%Y-%m-%d')

        fmt_d = lambda d: d.strftime('%d/%m/%Y')
        self.info_lbl.setText(
            f"🗓  {fmt_d(date1)} s/d jam {cutoff_str}   vs   {fmt_d(date2)} s/d jam {cutoff_str}"
        )

        result = self.db.get_hourly_comparison_metrics(date1_str, date2_str, cutoff_str, self.site_code)
        cur = result.get('current') or {}
        cmp = result.get('compare') or {}

        def fmt_rp(v):
            return f"Rp {v:,.0f}".replace(",", ".")

        def calc_delta(cur_v, cmp_v):
            if cmp_v and cmp_v > 0:
                d = ((cur_v - cmp_v) / cmp_v) * 100
                return d, f"{'+' if d >= 0 else ''}{d:.1f}%"
            elif cur_v > 0:
                return 100.0, "+100.0%"
            return 0.0, "0.0%"

        rows_def = [
            ("Sales",  cur.get('sales', 0),  cmp.get('sales', 0),  True),
            ("TC",     cur.get('tc', 0),     cmp.get('tc', 0),     False),
            ("AC",     cur.get('ac', 0),     cmp.get('ac', 0),     True),
            ("Large",  cur.get('large', 0),  cmp.get('large', 0),  False),
            ("Ouast",  cur.get('ouast', 0),  cmp.get('ouast', 0),  True),
        ]

        delta_values = []
        for row_i, (name, cur_v, cmp_v, is_rp) in enumerate(rows_def):
            cur_str = fmt_rp(cur_v) if is_rp else str(int(cur_v))
            cmp_str = fmt_rp(cmp_v) if is_rp else str(int(cmp_v))
            delta_num, delta_str = calc_delta(cur_v, cmp_v)
            delta_values.append(delta_num)

            self.table.setItem(row_i, 0, QTableWidgetItem(name))

            item_c = QTableWidgetItem(cur_str)
            item_c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_i, 1, item_c)

            item_p = QTableWidgetItem(cmp_str)
            item_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_i, 2, item_p)

            item_d = QTableWidgetItem(delta_str)
            item_d.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_d.setForeground(QColor('#27ae60') if delta_num >= 0 else QColor('#e74c3c'))
            self.table.setItem(row_i, 3, item_d)

        self._plot_chart([r[0] for r in rows_def], delta_values)

    def _plot_chart(self, metric_names, delta_values):
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        names_rev = list(reversed(metric_names))
        vals_rev  = list(reversed(delta_values))
        colors    = ['#27ae60' if v >= 0 else '#e74c3c' for v in vals_rev]

        ax.barh(names_rev, vals_rev, color=colors, alpha=0.85, height=0.55)
        ax.axvline(0, color='#2c3e50', linewidth=1.0)

        for i, v in enumerate(vals_rev):
            sign = "+" if v >= 0 else ""
            x_pos = v + (1.5 if v >= 0 else -1.5)
            ha = 'left' if v >= 0 else 'right'
            ax.text(x_pos, i, f"{sign}{v:.1f}%", va='center', ha=ha,
                    fontsize=9, color='#2c3e50', fontweight='bold')

        max_v = max((abs(v) for v in delta_values), default=10)
        pad = max(max_v * 0.45, 15)
        ax.set_xlim(-max_v - pad, max_v + pad)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#bdc3c7')
        ax.tick_params(axis='y', length=0, labelsize=10)
        ax.tick_params(axis='x', labelsize=8, colors='#7f8c8d')
        ax.set_xlabel("% Perubahan vs Periode Pembanding", fontsize=9, color='#7f8c8d')

        self.fig.subplots_adjust(left=0.15, right=0.88, top=0.95, bottom=0.15)
        try:
            self.canvas.draw()
        except Exception:
            pass

