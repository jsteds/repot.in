import logging
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QDateEdit, QGroupBox, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QDate, QTimer, QPropertyAnimation, QEasingCurve, QPoint
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
        
        main_layout.addLayout(filter_layout)
        
        # --- 2. KPI CARDS (Top Row) ---
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)
        
        self.kpi_sales_today = self._create_kpi_card("Sales Today", "Rp 0")
        self.kpi_sales_mtd = self._create_kpi_card("Sales MTD", "Rp 0")
        self.kpi_to_achieve = self._create_kpi_card("To Achieve (MTD)", "Rp 0\n(0%)")
        self.kpi_sales_sly = self._create_kpi_card("Sales SLY (YoY)", "Rp 0\n(0%)")
        self.kpi_forecast = self._create_kpi_card("Forecast Sales", "Rp 0")
        self.kpi_qty_large = self._create_kpi_card("Qty Large (MTD)", "0\n(0%)")
        self.kpi_qty_topping = self._create_kpi_card("Qty Topping (MTD)", "0\n(0%)")
        
        kpi_layout.addWidget(self.kpi_sales_today)
        kpi_layout.addWidget(self.kpi_sales_mtd)
        kpi_layout.addWidget(self.kpi_to_achieve)
        kpi_layout.addWidget(self.kpi_sales_sly)
        kpi_layout.addWidget(self.kpi_forecast)
        kpi_layout.addWidget(self.kpi_qty_large)
        kpi_layout.addWidget(self.kpi_qty_topping)
        
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
        
        # Bottom Row: Dynamic Chart
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
        self.fig_dyn = Figure(figsize=(10, 3), dpi=100)
        self.chart_dyn = FigureCanvas(self.fig_dyn)
        dyn_layout.addWidget(self.chart_dyn)
        
        main_layout.addWidget(self.chart_dyn_group)
        
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
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #7f8c8d; font-size: 12px; font-weight: bold; border: none;")
        lbl_title.setAlignment(Qt.AlignCenter)
        
        lbl_value = QLabel(initial_value)
        lbl_value.setStyleSheet("color: #2c3e50; font-size: 18px; font-weight: bold; border: none;")
        lbl_value.setAlignment(Qt.AlignCenter)
        
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
        
        # --- Update KPI Dynamic Labels ---
        lbl_period = "(MTD)" if selection == "Bulan Ini" else "(Period)"
        self.kpi_sales_mtd.title_label.setText(f"Sales {lbl_period.replace('(', '').replace(')', '')}")
        self.kpi_to_achieve.title_label.setText(f"To Achieve {lbl_period}")
        self.kpi_qty_large.title_label.setText(f"Qty Large {lbl_period}")
        self.kpi_qty_topping.title_label.setText(f"Qty Topping {lbl_period}")
        
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

        # --- Sembunyikan banner ---
        self._banner.hide_banner()

    def _process_dashboard_metrics(self, s_date, e_date, site_code):
        # 1. Fetch data dari Database Manager untuk tanggal mulai (S_DATE) dan akhir (E_DATE)
        # s_date & e_date akan digunakan untuk hitung MTD Periodical, e_date untuk 'Today' metrics
        metrics = self.db.get_dashboard_metrics(s_date, e_date, site_code)
        
        # 2. Update KPI Cards
        sales_mtd = metrics.get('sales_mtd', 0)
        sales_sly = metrics.get('sales_sly', 0)
        
        self.kpi_sales_today.value_label.setText(self._format_currency(metrics.get('sales_today', 0)))

        # ── Konversi e_date ke objek date (diperlukan untuk target_month & forecast) ──
        import calendar
        from datetime import datetime
        if isinstance(e_date, str):
            e_date_obj = datetime.strptime(e_date, "%Y-%m-%d").date()
        else:
            e_date_obj = e_date

        current_day = e_date_obj.day
        total_days_in_month = calendar.monthrange(e_date_obj.year, e_date_obj.month)[1]
        target_month = self.parent_app.config_manager.get_target_for_month(e_date_obj.month)

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
            
        self.kpi_forecast.value_label.setText(self._format_currency(forecast))
        
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

        # 6. Process Dynamic Chart
        self._update_dynamic_chart()

    def _plot_peak_hour(self, data):
        self.fig_peak.clear()
        ax = self.fig_peak.add_subplot(111)
        if data:
            hours = [d['hour'] for d in data]
            sales = [d['sales'] for d in data]
            tc = [d['tc'] for d in data]
            
            # Line Chart for Sales
            ax.plot(hours, sales, marker='o', linestyle='-', color='#3498db', label="Sales")
            ax.set_ylabel("Sales (Rp)", color='#3498db')
            ax.tick_params(axis='y', labelcolor='#3498db')
            
            # Create twin axis for TC
            ax2 = ax.twinx()
            ax2.bar(hours, tc, alpha=0.3, color='#e74c3c', label="TC")
            ax2.set_ylabel("Transaction Count", color='#e74c3c')
            ax2.tick_params(axis='y', labelcolor='#e74c3c')
            
            ax.grid(True, linestyle='--', alpha=0.6)
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
            # Posisi X per item: dibagi rata
            x_center = (i + 0.5) / n
            # Bullet warna (unicode kotak)
            ax_legend.text(x_center - 0.12, 0.80, '■',
                           ha='center', va='center', fontsize=14,
                           color=clr, transform=ax_legend.transAxes)
            # Label nama
            ax_legend.text(x_center - 0.01, 0.80, lbl,
                           ha='left', va='center', fontsize=8.5, fontweight='bold',
                           color='#2c3e50', transform=ax_legend.transAxes)
            # Persen
            ax_legend.text(x_center - 0.06, 0.46, f"{pct:.1f}%",
                           ha='center', va='center', fontsize=9.5, fontweight='bold',
                           color=clr, transform=ax_legend.transAxes)
            # Nominal
            ax_legend.text(x_center - 0.06, 0.15, self._format_currency(s),
                           ha='center', va='center', fontsize=7.5, color='#666666',
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
            names = [d['article_name'] for d in data_sorted]
            qtys = [d['qty'] for d in data_sorted]
            
            colors = ['#1abc9c', '#2ecc71', '#3498db', '#9b59b6', '#34495e'] * 2
            ax.barh(names, qtys, color=colors[:len(names)])
            for i, v in enumerate(qtys):
                ax.text(v, i, str(v), va='center')
            
            ax.grid(axis='x', linestyle='--', alpha=0.5)
        else:
            ax.text(0.5, 0.5, "Tidak ada data Top Menu", ha='center', va='center')
            
        self.fig_top.tight_layout()
        try: self.chart_top.draw()
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
