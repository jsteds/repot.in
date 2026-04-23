# main_app.py
import sys
import os
import pandas as pd
import traceback
import time
import logging
import html
import shutil
import tempfile
import json
from utils.constants import BASE_DIR
from datetime import datetime
from ui.waste_conversion_tab import WasteConversionTab
from ui.dashboard_tab import DashboardTab

# --- [PENTING] Import Tab Baru ---
from ui.sales_report_tab import SalesReportTab 

import matplotlib.pyplot as plt

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QMessageBox, QLabel,
    QFileDialog, QTableWidget, QTableWidgetItem, QHBoxLayout, QHeaderView,
    QProgressDialog, QFrame, QSplashScreen, QTabWidget, QDialog, QMainWindow,
    QSizePolicy, QMenuBar, QAction, QTextBrowser, QDialogButtonBox, QStackedWidget, QDesktopWidget,
    QActionGroup, QLineEdit, QCheckBox, QRadioButton, QDateEdit,
    QAbstractItemView, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import (
    QTimer, QDateTime, QDate, Qt, QObject, pyqtSignal, QThread, QProcess, QSizeF, QMarginsF
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from PyQt5.QtGui import QFont, QIcon, QPixmap, QTextDocument, QMovie, QPageSize, QPageLayout

from ui.order_tab_ui import OrderTab
from modules.validation_manager import is_device_authorized
from modules.notification_manager import NotificationManager
from utils.constants import (
    APP_ICON_PATH, SPLASH_IMAGE_PATH, DEFAULT_MARQUEE_TEXT, EMPTY_DATA_MESSAGE,
    COL_ARTICLE_NAME, COL_NET_PRICE, COL_QUANTITY, ERROR_DATA_NOT_AVAILABLE, 
    CONFIG_FILE_NAME, COL_PROMOTION_NAME, PROMO_CALC_BY_ITEM, PROMO_CALC_BY_RECEIPT, 
    ARTICLE_PREFS_FILE, NEW_SERIES_PREFS_FILE, PROMO_PREFS_FILE, APP_VERSION, VERSION_URL, COL_AMOUNT, COL_RECEIPT_NO, 
    COL_CREATED_DATE, BASE_DIR, LOG_FILE_PATH
)
from modules.config_manager import ConfigManager
from modules.report_processor import ReportProcessor
from ui.dialogs import (
    AgreementDialog, ConfigDialog, CalculatorDialog, 
    LogDialog, TemplateEditorDialog, PromotionSelectionDialog, NewSeriesGroupDialog,
    DualFileDialog, AuroraSyncDialog
)
from ui.todo_dialog import TodoListDialog
from ui.notes_dialog import NotesDialog
from ui.downloader_dialog import DownloaderDialog, FileDownloadWorker
from modules.workers import FileWorker, HistoricalDataWorker, GoogleSheetWorker, VersionWorker, CsvImportWorker
from ui.minum_tab import MinumTab

# --- [FIX CRITICAL] HAPUS SalesReportTab DARI SINI AGAR TIDAK MENIMPA YANG DI ATAS ---
from ui.ui_components import (
    EdspayedTab, MainDashboardUI, BSCDTab, KasDanTipsTab, InUseTab, ReportSectionWidget, ChatITWidget,
    AnimatedSplashScreen
)
from modules.aurora_scraper import AuroraScraper
# -------------------------------------------------------------------------------------

from utils.employee_utils import LoginDialog, EmployeeManagementDialog, CredentialManagementDialog, ROLE_ADMIN, ROLE_USER, EmployeeDB
from utils.app_settings_utils import has_user_agreed_eula, set_eula_agreed_status
from modules.database_manager import DatabaseManager
from modules.order_db_manager import OrderDBManager


# --- KONFIGURASI LOGGING ---
log_dir = os.path.dirname(LOG_FILE_PATH)
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
pd.set_option('mode.chained_assignment', None)



class ReportingApp(QMainWindow):
    def __init__(self, config_manager, db_manager, order_db_manager): 
        super().__init__()
        self.app_version = APP_VERSION
        self.notification_manager = NotificationManager(self)
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.order_db_manager = order_db_manager
        
        if not self.config_manager.site_list:
            success, message = self.config_manager.download_site_list()
            if not success:
                QTimer.singleShot(1000, lambda: self.notification_manager.show('ERROR', 'Gagal Memuat Data Site', message))
        
        self.calculator_dialog = None
        self.log_dialog = None
        self.todo_dialog = None
        self.notes_dialog = None
        self.downloader_dialog = None
        
        self.current_file_path = None
        self.original_payments_df = None
        self.original_transactions_df = None
        self.processed_transactions_df = None 
        self.processed_payments_df = None 
        self.report_results_data = {}

        self.selected_column_widget = None
        self.selected_promos_for_report = []
        self.new_series_preferences = []
        self.is_article_view_grouped = False
        
        self.promo_calc_method = PROMO_CALC_BY_ITEM
        self.promo_metrics_config = {"qty_today": True, "qty_mtd": True, "sales_today": True, "sales_mtd": True, "contrib": True}
        self.promo_group_data = []
        
        try:
            plt.style.use('seaborn-v0_8-pastel') 
            plt.rcParams.update({'font.size': 8, 'font.family': 'Segoe UI', 'figure.autolayout': True})
        except Exception as e:
            logging.warning(f"Gagal menerapkan style matplotlib: {e}. Menggunakan default.")

        self._init_base_ui()    
        self._init_header_ui()     
        self._init_main_view()      
        self._connect_tab_signals() 
        self.update_marquee_text_from_config()

        self.global_timer = QTimer(self)
        self.global_timer.timeout.connect(self._update_ui_elements)
        self.global_timer.start(200)
        self._update_ui_elements()

        # --- LOAD SETTINGS (SIMPAN & TERAPKAN FIX) ---
        from PyQt5.QtCore import QSettings
        self.settings = QSettings("RepotinApp", "SalesDashboard")
        
        # --- Load New Series dari JSON ---
        self.new_series_preferences = []
        try:
            if os.path.exists(NEW_SERIES_PREFS_FILE):
                with open(NEW_SERIES_PREFS_FILE, 'r') as f:
                    self.new_series_preferences = json.load(f)
                    logging.info(f"[INIT] Loaded {len(self.new_series_preferences)} New Series groups from {NEW_SERIES_PREFS_FILE}")
        except Exception as e:
            logging.warning(f"Gagal load new_series_preferences.json: {e}")
        
        promos = self.settings.value("selected_promos", [], type=list)
        self.selected_promos_for_report = [p for p in promos if p] if promos else []
        
        # Load promo metrics config from settings
        saved_promo_metrics = self.settings.value("promo_metrics_config", None)
        if saved_promo_metrics and isinstance(saved_promo_metrics, dict):
            self.promo_metrics_config = saved_promo_metrics
        
        # Load promo group data from JSON file
        try:
            if os.path.exists(PROMO_PREFS_FILE):
                with open(PROMO_PREFS_FILE, 'r') as f:
                    self.promo_group_data = json.load(f)
                    logging.info(f"[INIT] Loaded {len(self.promo_group_data)} promo groups from {PROMO_PREFS_FILE}")
        except Exception as e:
            logging.warning(f"Gagal load promo_group_preferences.json: {e}")
        
        grp = self.settings.value("is_article_grouped", False)
        self.is_article_view_grouped = str(grp).lower() == 'true'
        
        # Populate contrib table with saved groups (zero data) on startup
        if self.new_series_preferences:
            try:
                self.sales_report_tab_ui.update_contribution_table(
                    None, None, 0.0, 0.0, self.new_series_preferences
                )
            except Exception: pass
        # ----------------------------------------------

        # Set upload button visibility based on config
        self._refresh_upload_button_visibility()
        
        # --- BROADCAST INFO ---
        self._init_broadcast_checker()
        
        # --- CHAT WIDGET ---
        chat_link = self.config_manager.get_config().get('chat_it_link', '')
        self.chat_it_widget = ChatITWidget(self, link=chat_link)
        self._refresh_chat_widget_visibility()

    def _init_broadcast_checker(self):
        # Default JSON URL (developer can change this URL)
        self.broadcast_url = "https://gist.githubusercontent.com/e001red-coder/7a93b33c84e6e3d145653517184c8ea9/raw/gistfile1.txt"
        
        # Timer untuk mengecek berkala setiap 2.5 menit (150.000 ms)
        self.broadcast_timer = QTimer(self)
        self.broadcast_timer.timeout.connect(self._check_broadcast_now)
        self.broadcast_timer.start(150000)
        
        # Eksekusi pengecekan pertama setelah delay 5 detik agar splash screen lewat
        QTimer.singleShot(5000, self._check_broadcast_now)

    def _check_broadcast_now(self):
        from modules.broadcast_manager import BroadcastCheckerThread
        
        # Jangan start thread baru jika pengecekan sebelumnya masih berjalan (jaringan lemot, dll)
        if hasattr(self, 'broadcast_checker') and self.broadcast_checker.isRunning():
            return
            
        self.broadcast_checker = BroadcastCheckerThread(self.broadcast_url)
        self.broadcast_checker.broadcasts_fetched.connect(self._handle_broadcasts)
        self.broadcast_checker.start()

    def _handle_broadcasts(self, valid_broadcasts):
        from ui.dialogs import BroadcastDialog
        read_ids = self.config_manager.get_read_broadcasts()
        
        for bcast in valid_broadcasts:
            b_id = bcast.get('id')
            if b_id and b_id not in read_ids:
                dialog = BroadcastDialog(bcast, self)
                # Show popup and save ID if 'Saya Mengerti' is clicked
                if dialog.exec_() == QDialog.Accepted:
                    self.config_manager.mark_broadcast_read(b_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'chat_it_widget') and self.chat_it_widget:
            self.chat_it_widget.reposition_to_edge()

    def _init_base_ui(self):
        self.setWindowTitle(f"Repot.in - Ver.{self.app_version}")
        # Default geometry made slightly shorter so it doesn't crop out on 1366x768 laptops
        self.setGeometry(100, 50, 1100, 720) 
        app_icon = QIcon(APP_ICON_PATH)
        if app_icon.isNull():
            logging.warning(f"Icon aplikasi '{APP_ICON_PATH}' tidak ditemukan.")
        self.setWindowIcon(app_icon)

        self._init_menu_bar() 

        self.statusBar_widget = self.statusBar()
        self.status_label = QLabel("Siap")
        self.statusBar_widget.addWidget(self.status_label, 1)
        
        self.file_info_label = QLabel("Selamat Datang! Import CSV untuk memulai.") 
        self.statusBar_widget.addPermanentWidget(self.file_info_label)

    def _init_menu_bar(self):
        self.menu_bar = self.menuBar()

        file_menu = self.menu_bar.addMenu("&File")
        
        view_menu = self.menu_bar.addMenu("&Tampilan")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        light_theme_action = QAction("Tema Terang", self, checkable=True)
        light_theme_action.triggered.connect(lambda: self._set_theme('light'))
        theme_group.addAction(light_theme_action)
        view_menu.addAction(light_theme_action)
        
        dark_theme_action = QAction("Tema Gelap", self, checkable=True)
        dark_theme_action.triggered.connect(lambda: self._set_theme('dark'))
        theme_group.addAction(dark_theme_action)
        view_menu.addAction(dark_theme_action)
        
        current_theme = self.config_manager.get_config().get('theme', 'light')
        if current_theme == 'dark':
            dark_theme_action.setChecked(True)
        else:
            light_theme_action.setChecked(True)
        
        open_file_action = QAction("Import Data CSV...", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.load_sbd_file)
        file_menu.addAction(open_file_action)

        sync_aurora_action = QAction("Sync Data Aurora...", self)
        sync_aurora_action.triggered.connect(self._show_aurora_sync_dialog)
        file_menu.addAction(sync_aurora_action)
        
        print_action = QAction("Cetak Laporan Terpilih...", self)
        print_action.setShortcut("Ctrl+P")
        print_action.triggered.connect(self.print_selected_report)
        file_menu.addAction(print_action)
        
        config_action = QAction("Konfigurasi...", self)
        config_action.setShortcut("Ctrl+,")
        config_action.triggered.connect(self._show_config_dialog)
        file_menu.addAction(config_action)
        
        manage_templates_action = QAction("Kelola Template Report...", self)
        manage_templates_action.setShortcut("Ctrl+/")
        manage_templates_action.triggered.connect(self._show_template_editor)
        file_menu.addAction(manage_templates_action)
        
        file_menu.addSeparator()
        import_history_action = QAction("Impor Data Historis (Excel)...", self)
        import_history_action.triggered.connect(self._import_historical_data)
        file_menu.addAction(import_history_action)
        
        file_menu.addSeparator() 
        exit_action = QAction("Keluar", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        master_data_menu = self.menu_bar.addMenu("Data")
        employee_data_action = QAction("Data Karyawan", self)
        employee_data_action.triggered.connect(self.show_employee_management)
        master_data_menu.addAction(employee_data_action)
        app_pass_action = QAction("Kredensial Aplikasi Karyawan", self)
        app_pass_action.triggered.connect(self.show_credential_management)
        master_data_menu.addAction(app_pass_action)

        tools_menu = self.menu_bar.addMenu("&Tools")
        edspayed_action = QAction("Edspayed - Exp. List", self)
        edspayed_action.triggered.connect(self._show_edspayed_tab)
        tools_menu.addAction(edspayed_action)
        
        calculator_action = QAction("Kalkulator", self)
        calculator_action.setStatusTip("Buka kalkulator sederhana")
        calculator_action.setShortcut("Ctrl+Shift+C") 
        calculator_action.triggered.connect(self._show_calculator)
        tools_menu.addAction(calculator_action)
        tools_menu.addSeparator()

        log_action = QAction("Data Log", self)
        log_action.triggered.connect(self._show_log_dialog)
        tools_menu.addAction(log_action)
        
        todo_action = QAction("Todo List", self)
        todo_action.setShortcut("Ctrl+T")
        todo_action.triggered.connect(self._show_todo_list)
        tools_menu.addAction(todo_action)

        notes_action = QAction("Notes", self)
        notes_action.setShortcut("Ctrl+N")
        notes_action.triggered.connect(self._show_notes)
        tools_menu.addAction(notes_action)

        downloader_action = QAction("📥  Unduh File Online...", self)
        downloader_action.setShortcut("Ctrl+Shift+D")
        downloader_action.setStatusTip("Unduh file pendukung dari server Google Drive")
        downloader_action.triggered.connect(self._show_downloader)
        tools_menu.addAction(downloader_action)
        
        tools_menu.addSeparator()

        export_settings_action = QAction("Ekspor Pengaturan...", self)
        export_settings_action.triggered.connect(self._export_settings)
        tools_menu.addAction(export_settings_action)

        import_settings_action = QAction("Impor Pengaturan...", self)
        import_settings_action.triggered.connect(self._import_settings)
        tools_menu.addAction(import_settings_action)
        
        # --- [MENU BARU: MASTER DATA] ---
        # Menu ini dipisah agar user sadar ini untuk konfigurasi, bukan operasional harian
        master_menu = self.menu_bar.addMenu("&Master Data")
        
        import_master_action = QAction("Update Master Produk (Excel)...", self)
        import_master_action.setStatusTip("Upload file Excel referensi Artikel, Size, dan Brand")
        import_master_action.triggered.connect(self.import_master_excel_action) # Hubungkan ke fungsi baru
        master_menu.addAction(import_master_action)
        # -------------------------------------------------

        # --- [MENU BARU: PENGATURAN] ---
        settings_menu = self.menu_bar.addMenu("&Settings")
        tab_vis_menu = settings_menu.addMenu("Visibilitas Tab Laporan")
        
        self.tab_visibility_actions = {}
        tab_names = ["BSCD", "Kas & Tips", "Order Barang", "In-Use", "Konversi Waste", "Edspayed", "Minum"]
        
        for name in tab_names:
            action = QAction(name, self, checkable=True)
            is_vis = self.config_manager.get_tab_visibility(name)
            action.setChecked(is_vis)
            action.toggled.connect(lambda checked, n=name: self._toggle_tab_visibility(n, checked))
            tab_vis_menu.addAction(action)
            self.tab_visibility_actions[name] = action
        # -------------------------------------------------

        help_menu = self.menu_bar.addMenu("&Bantuan")
        about_action = QAction("Tentang Repot.in", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
        user_guide_action = QAction("Panduan Penggunaan", self)
        user_guide_action.triggered.connect(self._show_user_guide_dialog)
        help_menu.addAction(user_guide_action)
        check_update_action = QAction("Periksa Pembaruan...", self)
        check_update_action.triggered.connect(self._check_for_updates_manual) 
        help_menu.addAction(check_update_action)
        
        changelog_action = QAction("Log Perubahan (Changelog)", self)
        changelog_action.setStatusTip("Lihat riwayat pembaruan aplikasi")
        changelog_action.triggered.connect(self._show_changelog_dialog)
        help_menu.addAction(changelog_action)
    
    def _toggle_tab_visibility(self, tab_id, is_visible):
        self.config_manager.set_tab_visibility(tab_id, is_visible)
        
        if hasattr(self, 'main_dashboard_ui') and self.main_dashboard_ui:
            btn_map = {
                "BSCD": self.main_dashboard_ui.btn_bscd,
                "Kas & Tips": self.main_dashboard_ui.btn_kas,
                "Order Barang": self.main_dashboard_ui.btn_order,
                "In-Use": self.main_dashboard_ui.btn_inuse,
                "Konversi Waste": self.main_dashboard_ui.btn_waste,
                "Edspayed": self.main_dashboard_ui.btn_edspayed,
                "Minum": self.main_dashboard_ui.btn_minum
            }
            if tab_id in btn_map:
                btn_map[tab_id].setVisible(is_visible)

    def _show_calculator(self):
        if self.calculator_dialog is None or not self.calculator_dialog.isVisible():
            self.calculator_dialog = CalculatorDialog(self) 
            self.calculator_dialog.show() 
        else:
            self.calculator_dialog.activateWindow()
            self.calculator_dialog.raise_()
            
    def _init_header_ui(self):
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(5,5,5,5)

        # Marquee label dipindahkan ke sidebar (MainDashboardUI)
        
        self.datetime_label = QLabel()
        self.datetime_label.setObjectName("datetime_label")
        self.datetime_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_layout.addStretch(1) # Stretch ke kiri biar datetime di kanan full
        header_layout.addWidget(self.datetime_label)
        
    def _set_theme(self, theme_name):
        style_folder = os.path.join(BASE_DIR, "assets", "styles")
        
        if theme_name == 'dark':
            file_path = os.path.join(style_folder, "dark_style.qss")
        else:
            file_path = os.path.join(style_folder, "style.qss")
            
        try:
            with open(file_path, "r", encoding='utf-8') as f:
                self.setStyleSheet(f.read())
            self.config_manager.save_theme(theme_name)
            logging.info(f"Tema diubah menjadi: {theme_name}")
            # Update BSCD inline header styles karena inline setStyleSheet tidak di-override oleh QSS
            if hasattr(self, 'bscd_tab_ui') and self.bscd_tab_ui is not None:
                self.bscd_tab_ui.apply_bscd_theme(is_dark=(theme_name == 'dark'))
        except FileNotFoundError:
            logging.error(f"File style tidak ditemukan di: {file_path}")
            QMessageBox.warning(self, "Error", f"File style tidak ditemukan:\n{file_path}")
    
    def _center_window(self):
        try:
            frame_geometry = self.frameGeometry()
            center_point = QDesktopWidget().availableGeometry().center()
            frame_geometry.moveCenter(center_point)
            self.move(frame_geometry.topLeft())
        except Exception as e:
            logging.warning(f"Gagal menengahkan window: {e}")
            
    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_window_centered') or not self._window_centered:
            self._center_window()
            self._window_centered = True

    def _update_ui_elements(self):
        # Update marquee yang sekarang ada di MainDashboardUI (sidebar)
        if hasattr(self, 'main_dashboard_ui') and hasattr(self.main_dashboard_ui, 'marquee_label') and hasattr(self, 'current_marquee_full_text'):
            self.current_marquee_full_text = self.current_marquee_full_text[1:] + self.current_marquee_full_text[0]
            self.main_dashboard_ui.marquee_label.setText(self.current_marquee_full_text[:100])

        if hasattr(self, 'main_dashboard_ui'):
            self.main_dashboard_ui.update_time()
        else:
            current_dt_str = QDateTime.currentDateTime().toString("dd/MM/yyyy HH:mm:ss")
            if hasattr(self, 'datetime_label'):
                self.datetime_label.setText(current_dt_str)
        
        # Sembunyikan Menubar jika di Dashboard
        if hasattr(self, 'main_dashboard_ui'):
            if self.main_dashboard_ui.main_stack.currentIndex() == 0:
                self.menu_bar.setVisible(False)
            else:
                self.menu_bar.setVisible(True)
                
            # Update tabel Edspayed secara real-time jika tab aktif
            if hasattr(self, 'edspayed_idx') and self.main_dashboard_ui.main_stack.currentIndex() == self.edspayed_idx:
                try:
                    if hasattr(self, 'edspayed_tab_ui') and hasattr(self.edspayed_tab_ui, 'edspayed_content_widget'):
                        widget = self.edspayed_tab_ui.edspayed_content_widget
                        if not getattr(widget, 'is_custom_date', False):
                            # Gunakan fungsi refresh string waktu tanpa merusak item state
                            if hasattr(widget, 'refresh_times_only'):
                                widget.refresh_times_only()
                except Exception as e:
                    pass
            
    def _init_main_view(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 1. NEW MAIN DASHBOARD UI (Satu-satunya widget utama) ---
        self.main_dashboard_ui = MainDashboardUI(self)
        self.main_layout.addWidget(self.main_dashboard_ui)

        # Inisialisasi Tab UI
        self.sales_report_tab_ui = SalesReportTab(self)
        self.sales_report_tab_ui.copy_action_requested.connect(self.copy_selected_column_content)
        # Load templates and apply the default template from config
        _cfg_default_tpl = self.config_manager.get_config().get('default_template', '')
        self._load_report_templates(_cfg_default_tpl if _cfg_default_tpl else None)
        self.bscd_tab_ui = BSCDTab(self)
        self.kas_dan_tips_tab = KasDanTipsTab(self)
        self.order_tab_ui = OrderTab(self)
        self.inuse_tab = InUseTab(self)
        self.edspayed_tab_ui = EdspayedTab(self)
        self.waste_tab_ui = WasteConversionTab(self)

        # Masukkan ke Main Stack Sidebar (Index 0 sudah Dashboard dari ui_components)
        self.sales_report_idx = self.main_dashboard_ui.main_stack.addWidget(self.sales_report_tab_ui) # Index 1
        self.bscd_idx = self.main_dashboard_ui.main_stack.addWidget(self.bscd_tab_ui) # Index 2
        self.kas_idx = self.main_dashboard_ui.main_stack.addWidget(self.kas_dan_tips_tab) # Index 3
        self.order_idx = self.main_dashboard_ui.main_stack.addWidget(self.order_tab_ui) # Index 4
        self.inuse_idx = self.main_dashboard_ui.main_stack.addWidget(self.inuse_tab) # Index 5
        self.waste_idx = self.main_dashboard_ui.main_stack.addWidget(self.waste_tab_ui) # Index 6
        self.edspayed_idx = self.main_dashboard_ui.main_stack.addWidget(self.edspayed_tab_ui) # Index 7
        self.minum_tab = MinumTab(self)
        self.minum_idx = self.main_dashboard_ui.main_stack.addWidget(self.minum_tab) # Index 8

        # --- Apply visibility based on config ---
        btn_map = {
            "BSCD": self.main_dashboard_ui.btn_bscd,
            "Kas & Tips": self.main_dashboard_ui.btn_kas,
            "Order Barang": self.main_dashboard_ui.btn_order,
            "In-Use": self.main_dashboard_ui.btn_inuse,
            "Konversi Waste": self.main_dashboard_ui.btn_waste,
            "Edspayed": self.main_dashboard_ui.btn_edspayed,
            "Minum": self.main_dashboard_ui.btn_minum
        }
        for name, btn in btn_map.items():
            btn.setVisible(self.config_manager.get_tab_visibility(name))
        # ----------------------------------------

        # Tombol report di sidebar sekarang aktif dari awal sesuai request user

        # Auto-select the main report section so Salin Teks works without clicking first
        self.selected_column_widget = self.sales_report_tab_ui.main_report_section
        self.sales_report_tab_ui.main_report_section.set_selected(True)
    def _show_edspayed_tab(self):
        self.main_dashboard_ui.main_stack.setCurrentIndex(self.edspayed_idx)
        self.main_dashboard_ui.btn_edspayed.setChecked(True)
        
    def _handle_nav_change(self, clicked_btn):
        if clicked_btn in self.btn_index_map:
            target_idx = self.btn_index_map[clicked_btn]
            
            # --- FIX LAYOUT STRETCH BUG ---
            # QStackedWidget tends to reserve space for the largest widget.
            # We must set all inactive widgets to Ignored and the active one to Expanding.
            from PyQt5.QtWidgets import QSizePolicy
            for i in range(self.main_dashboard_ui.main_stack.count()):
                widget = self.main_dashboard_ui.main_stack.widget(i)
                if i == target_idx:
                    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                else:
                    widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            
            self.main_dashboard_ui.main_stack.setCurrentIndex(target_idx)
            # Do NOT call adjustSize() here, as it forces the layout to collapse to sizeHint
    
    def _connect_tab_signals(self):
        sales_ui = self.sales_report_tab_ui
        
        # Connect MainDashboardUI Sidebar signals
        self.main_dashboard_ui.open_file_requested.connect(self.load_sbd_file)
        self.main_dashboard_ui.sync_aurora_requested.connect(self._show_aurora_sync_dialog)
        self.main_dashboard_ui.db_analysis_requested.connect(self._direct_db_analysis)
        
        # Mapping Sidebar buttons ke index widget
        self.btn_index_map = {
            self.main_dashboard_ui.btn_dashboard: 0,
            self.main_dashboard_ui.btn_sales_report: self.sales_report_idx,
            self.main_dashboard_ui.btn_bscd: self.bscd_idx,
            self.main_dashboard_ui.btn_kas: self.kas_idx,
            self.main_dashboard_ui.btn_order: self.order_idx,
            self.main_dashboard_ui.btn_inuse: self.inuse_idx,
            self.main_dashboard_ui.btn_waste: self.waste_idx,
            self.main_dashboard_ui.btn_edspayed: self.edspayed_idx,
            self.main_dashboard_ui.btn_minum: self.minum_idx,
        }
        self.main_dashboard_ui.nav_index_requested.connect(self._handle_nav_change)
        
        # Connect standalone popup buttons
        self.main_dashboard_ui.btn_todo.clicked.connect(self._show_todo_list)
        self.main_dashboard_ui.btn_notes.clicked.connect(self._show_notes)
        
        sales_ui.clear_ui_button.clicked.connect(self.confirm_clear_ui_data)
        sales_ui.refresh_button.clicked.connect(self.refresh_report_data)
        self.sales_report_tab_ui.select_articles_button.clicked.connect(self.open_article_selection_dialog)

        # --- Upload ke Google Sheet button ---
        # Separator (hidden by default, shown together with button)
        from PyQt5.QtWidgets import QFrame as _QFrame
        self._gsheet_sep = _QFrame()
        self._gsheet_sep.setFrameShape(_QFrame.VLine)
        self._gsheet_sep.setFrameShadow(_QFrame.Sunken)
        self._gsheet_sep.setVisible(False)

        self.upload_gsheet_button = QPushButton("☁ Upload ke Google Sheet")
        self.upload_gsheet_button.setFixedHeight(30)
        self.upload_gsheet_button.setEnabled(False)   # disabled until CSV loaded
        self.upload_gsheet_button.setVisible(False)   # hidden until sheet ID set
        self.upload_gsheet_button.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                border-radius: 4px; padding: 4px 12px;
                font-weight: bold; font-size: 9pt;
            }
            QPushButton:hover:enabled { background-color: #1558b0; }
            QPushButton:disabled { background-color: #9ab7e0; color: #e8f0fe; }
        """)
        self.upload_gsheet_button.clicked.connect(self.start_google_sheet_upload)

        # Inject into the real toolbar (toolbar_layout exposed by SalesReportTab)
        if hasattr(sales_ui, 'toolbar_layout'):
            sales_ui.toolbar_layout.addWidget(self._gsheet_sep)
            sales_ui.toolbar_layout.addWidget(self.upload_gsheet_button)

        self.sales_report_tab_ui.main_report_section.template_combo.currentIndexChanged.connect(self._on_template_changed)
        self.sales_report_tab_ui.today_mop_section.view_combo.currentIndexChanged.connect(self._on_mop_view_changed)

        self.sales_report_tab_ui.main_report_section.template_combo.currentTextChanged.connect(
            self._on_template_changed
        )
        self.sales_report_tab_ui.select_promos_button.clicked.connect(self.open_promo_selection_dialog)

    def _refresh_upload_button_visibility(self):
        """Show the upload button only when google_sheet_id is configured in settings."""
        sheet_id = self.config_manager.get_config().get('google_sheet_id', '').strip()
        has_id = bool(sheet_id)
        self.upload_gsheet_button.setVisible(has_id)
        self._gsheet_sep.setVisible(has_id)

    def _show_aurora_sync_dialog(self):
        try:
            dialog = AuroraSyncDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                start_date, end_date = dialog.get_dates()
                is_shift1 = dialog.is_shift1()
                
                # Ambil kredensial
                db = EmployeeDB()
                username, password = db.get_aurora_credentials()
                
                if not username or not password:
                    QMessageBox.critical(self, "Kredensial Tidak Ditemukan", "Gagal menemukan kredensial Aurora di database.\nPastikan terdapat karyawan dengan jabatan Store Manager/Asst. Store Manager dan passwordnya telah diset di menu Kredensial Aplikasi (menggunakan keyword 'Aurora').")
                    return
                
                # --- CLEANUP SCRAPER LAMA ---
                # Penting: hapus reference lama agar WebEngine renderer bisa ditutup
                # sebelum membuat QWebEngineView baru. Tidak melakukan cleanup bisa menyebabkan crash.
                if hasattr(self, 'scraper') and self.scraper is not None:
                    try:
                        old_scraper = self.scraper
                        self.scraper = None
                        old_scraper._finished_emitted = True  # Hentikan signal dari session lama
                        old_scraper.timeout_timer.stop()
                        old_scraper.page.loadFinished.disconnect()
                        old_scraper.view.stop()
                        old_scraper.view.setPage(None)
                        old_scraper.view.deleteLater()
                        del old_scraper
                        logging.info("[AuroraScraper] Old scraper instance cleaned up.")
                    except Exception as cleanup_err:
                        logging.warning(f"[AuroraScraper] Cleanup warning (non-fatal): {cleanup_err}")
                    
                self.progress_sync = QProgressDialog("Menyiapkan sinkronisasi...", "Batal", 0, 0, self)
                self.progress_sync.setWindowTitle("Sync Aurora")
                self.progress_sync.setWindowModality(Qt.WindowModal)
                self.progress_sync.show()
                
                target_site_code = self.config_manager.get_config().get('site_code')
                self.scraper = AuroraScraper(username, password, start_date, end_date, target_site_code=target_site_code)
                # Store the is_shift1 flag so we can pass it when download completes
                self.scraper.is_shift1 = is_shift1 
                
                self.scraper.progress.connect(self._update_sync_progress)
                self.scraper.finished.connect(self._on_sync_finished)
                
                # Batal: hanya panggil on_timeout jika scraper belum selesai
                def _safe_cancel():
                    if not getattr(self.scraper, '_finished_emitted', False):
                        self.scraper.on_timeout()
                self.progress_sync.canceled.connect(_safe_cancel)
                
                self.scraper.start()
        except Exception as e:
            logging.error(f"Error when preparing Aurora Sync: {e}", exc_info=True)
            QMessageBox.critical(self, "Error Sistem", f"Terjadi kesalahan saat memulai sinkronisasi:\n{str(e)}")
            
    def _update_sync_progress(self, msg):
        if hasattr(self, 'progress_sync'):
            self.progress_sync.setLabelText(msg)
            
    def _on_sync_finished(self, success, msg, files):
        if hasattr(self, 'progress_sync') and self.progress_sync:
            try:
                self.progress_sync.close()
            except:
                pass
            
        if success:
            QMessageBox.information(self, "Berhasil", msg)
            if files:
                # Cari mana yang transaksi (AH Commodity) dan laporan MOP
                trans_file = next((f for f in files if "commodity" in f.lower() or "transaction" in f.lower()), None)
                mop_file = next((f for f in files if "mop" in f.lower() or "payment" in f.lower()), None)
                
                # Fallback: jika keyword tidak cocok, gunakan urutan
                if not trans_file and not mop_file:
                    if len(files) >= 2:
                        trans_file = files[0]
                        mop_file = files[1]
                
                if trans_file and mop_file and trans_file != mop_file:
                    logging.info(f"Sync Aurora success. Processing Trans: {trans_file}, MOP: {mop_file}")
                    
                    # Fetching the stored checkbox state
                    is_shift1 = getattr(self.scraper, 'is_shift1', False)
                    
                    self._start_csv_import_worker(mop_file, trans_file, is_shift1=is_shift1)
                    
                    # Auto-tampilkan tombol Upload Google Sheet jika Google Sheet ID sudah dikonfigurasi
                    sheet_id = self.config_manager.get_config().get('google_sheet_id', '').strip()
                    if sheet_id and hasattr(self, 'upload_gsheet_button'):
                        self.upload_gsheet_button.setVisible(True)
                        self._gsheet_sep.setVisible(True)
                        # tombol akan di-enable oleh _handle_file_data_loaded setelah import selesai
                        logging.info("[AuroraScraper] Upload GSheet button visible after sync.")
                else:
                    downloaded_names = [os.path.basename(f) for f in files]
                    QMessageBox.warning(self, "Data Tidak Lengkap", 
                        f"Hanya berhasil mengunduh: {', '.join(downloaded_names)}\n\n"
                        f"Diperlukan kedua file (AH Commodity Report & MOP Report) untuk memproses data.\n"
                        f"Silakan coba lagi.")
            else:
                QMessageBox.warning(self, "Perhatian", "Tidak ada file yang berhasil diunduh (semua kosong).")
        else:
            QMessageBox.critical(self, "Gagal", f"Gagal mensinkronisasi data Aurora:\n{msg}")
    
    def _start_csv_import_worker(self, pay_path, trans_path, is_shift1=False):
        """Memulai import file CSV Aurora menggunakan CsvImportWorker di QThread."""
        from PyQt5.QtCore import QThread
        
        self.progress_dialog = QProgressDialog("Memproses file CSV...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("Import Data Aurora")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()
        
        self._import_thread = QThread()
        self._import_worker = CsvImportWorker(trans_path, pay_path)
        self._import_worker.moveToThread(self._import_thread)
        
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.progress.connect(lambda pct, msg: self.progress_dialog.setLabelText(msg) if hasattr(self, 'progress_dialog') else None)
        self._import_worker.finished.connect(self._handle_file_data_loaded)
        self._import_worker.error.connect(self._handle_file_load_error)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.error.connect(self._import_thread.quit)
        
        self._import_thread.start()

    def _refresh_chat_widget_visibility(self):
        """Update and show/hide the chat widget based on configuration."""
        chat_link = self.config_manager.get_config().get('chat_it_link', '').strip()
        self.chat_it_widget.set_link(chat_link)
        self.chat_it_widget.reposition_to_edge()

    def _direct_db_analysis(self):
        """Bypass the Startup choice dialog since Database DB assumes we want Database Analisa."""
        site_code = self.config_manager.get_config().get('site_code')
        min_date, max_date = self.db_manager.get_available_date_range(site_code)
        self.load_from_database_ui(min_date, max_date)

    # ==========================================
    # STARTUP FLOW BARU (FLEXIBLE)
    # ==========================================
    
    def show_startup_options(self):
        """Menampilkan pilihan: Import Baru atau Pakai Database."""
        
        # Cek apakah ada data di DB
        site_code = self.config_manager.get_config().get('site_code')
        min_date, max_date = self.db_manager.get_available_date_range(site_code)
        has_data = (min_date is not None)
        
        dialog = StartupChoiceDialog(has_db_data=has_data, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            if dialog.choice == 'import':
                self.load_sbd_file() # Panggil logika import CSV lama (DualFileDialog)
            elif dialog.choice == 'db':
                self.load_from_database_ui(min_date, max_date)

    def load_from_database_ui(self, min_date_str, max_date_str):
        """Flow jika user memilih load dari database tanpa import."""
        
        # 1. Tanya Range Tanggal
        date_dialog = DatabaseDateSelectionDialog(min_date_str, max_date_str, self)
        if date_dialog.exec_() == QDialog.Accepted:
            start_date, end_date = date_dialog.get_dates()
            
            # 2. Set Filter di UI Sales Report
            self.sales_report_tab_ui.all_dates_radio.setChecked(False)
            self.sales_report_tab_ui.date_range_radio.setChecked(True)
            self.sales_report_tab_ui.start_date_edit.setDate(start_date)
            self.sales_report_tab_ui.end_date_edit.setDate(end_date)
            
            # 3. Trigger Refresh (Engine kita sudah support DB-centric!)
            self.refresh_progress_dialog = QProgressDialog("Mengambil data dari Database...", None, 0, 0, self)
            self.refresh_progress_dialog.show()
            
            self.refresh_report_data() # Ini akan otomatis baca DB sesuai tanggal UI
            
            # 4. Enable button reports di sidebar
            logging.info(f"Mengaktifkan {len(self.main_dashboard_ui.report_buttons)} tombol laporan di sidebar...")
            for btn in self.main_dashboard_ui.report_buttons:
                btn.setEnabled(True)
                logging.info(f"Tombol {btn.text().strip()} enabled state: {btn.isEnabled()}")
            
            self.main_dashboard_ui.main_stack.setCurrentIndex(self.sales_report_idx)
            self.main_dashboard_ui.btn_sales_report.setChecked(True)
            
            self.file_info_label.setText(f"Mode: Database Analysis | {start_date.toString('dd/MM/yy')} - {end_date.toString('dd/MM/yy')}")
            QMessageBox.information(self, "Siap", "Data berhasil dimuat dari Database.")

    def _on_template_changed(self, template_name):
        if not self.report_results_data or not template_name: return
        logging.info(f"Template diganti ke '{template_name}'.")

        processor = self.report_results_data.get('processor')
        all_data = self.report_results_data
        promo_text_block = self.report_results_data.get('promo_text_block', '')
        new_series_text_block = self.report_results_data.get('new_series_text_block', '')

        if not processor:
            self.refresh_report_data()
            return

        new_report_text = processor.regenerate_main_report_text(
            template_name, all_data, promo_text_block, new_series_text_block
        )
        
        self.sales_report_tab_ui.update_main_report_text(new_report_text)
        self.notification_manager.show('SUCCESS', 'Template Diubah', f"Laporan diperbarui.")

    def update_marquee_text_from_config(self):
        config = self.config_manager.get_config()
        running_text = config.get('running_text', '').strip()
        
        base_text = ""
        if not running_text:
            site_code = config.get('site_code')
            store_name = self.config_manager.get_store_name(site_code) if site_code else "di Repot.in!"
            base_text = f"Hi, {store_name}"
        else:
            base_text = running_text
        
        separator = " " * 40 
        self.current_marquee_full_text = f"{base_text}{separator}{base_text}{separator}"
        
        if hasattr(self, 'main_dashboard_ui') and hasattr(self.main_dashboard_ui, 'marquee_label'):
             self.main_dashboard_ui.marquee_label.setText(self.current_marquee_full_text)

    
    def switch_to_sales_report_tab(self):
        self.main_dashboard_ui.main_stack.setCurrentIndex(self.sales_report_idx)
        self.main_dashboard_ui.btn_sales_report.setChecked(True)

    def column_clicked(self, section_widget: 'ReportSectionWidget'):
        if self.selected_column_widget:
            self.selected_column_widget.set_selected(False)
        self.selected_column_widget = section_widget
        self.selected_column_widget.set_selected(True)

    def copy_selected_column_content(self):
        if not self.selected_column_widget:
            self.notification_manager.show('WARNING', 'Tidak Ada Pilihan', 'Klik area laporan yang ingin disalin.')
            return

        content = self.selected_column_widget.text_edit.toPlainText()
        if not content.strip():
            self.notification_manager.show('INFO', 'Konten Kosong', 'Area laporan yang dipilih tidak berisi teks.')
            return

        site_code = self.config_manager.get_config().get('site_code', 'N/A')
        current_datetime = QDateTime.currentDateTime().toString("dd MMM yyyy hh:mm:ss")
        header_text = ""
        store_name = self.report_results_data.get('store_name', '""')

        if self.selected_column_widget == self.sales_report_tab_ui.main_report_section:
            report_date = self.report_results_data.get('daily_used_date_str', 'N/A').replace('-', ' ')
            header_text = ""
        elif self.selected_column_widget == self.sales_report_tab_ui.today_mop_section:
            selected_view = self.sales_report_tab_ui.today_mop_section.view_combo.currentText()
            if selected_view == "Today":
                report_date = self.report_results_data.get('daily_used_date_str', 'N/A').replace('-', ' ')
                header_text = (
                    f"{'SALES BY DATE':^40}\n\n"
                    f"Site       : {site_code} - {store_name}\n"
                    f"Print date : {current_datetime}\n"
                    f"Date       : {report_date}\n"
                    f"{'-'*3}\n\n"
                )
            else: 
                from_date = self.report_results_data.get('min_date_str', 'N/A').replace('-', ' ')
                to_date = self.report_results_data.get('max_date_str', 'N/A').replace('-', ' ')
                header_text = (
                    f"{'SALES BY DATE':^40}\n\n"
                    f"Site       : {site_code} - {store_name}\n"
                    f"Print date : {current_datetime}\n"
                    f"From       : {from_date}\n"
                    f"To         : {to_date}\n"
                    f"{'-'*3}\n\n"
                )

        full_text_to_copy = header_text + content

        clipboard = QApplication.clipboard()
        clipboard.setText(full_text_to_copy)
        self.notification_manager.show('SUCCESS', 'Berhasil Disalin', 'Konten laporan dan header telah disalin.')
        

    def print_selected_report(self):
        if not self.selected_column_widget:
            QMessageBox.warning(self, "Peringatan", "Silakan klik area laporan yang ingin dicetak.")
            return

        content_to_print = self.selected_column_widget.text_edit.toPlainText().strip()
        if not content_to_print:
            QMessageBox.warning(self, "Peringatan", "Area laporan yang dipilih kosong.")
            return

        site_code = self.config_manager.get_config().get('site_code', 'N/A')
        current_datetime_for_print = QDateTime.currentDateTime().toString("dd MMMM yyyy hh:mm:ss")
        store_name = self.report_results_data.get('store_name', 'Nama Toko Tidak Ditemukan')
        header_text = ""
        
        if self.selected_column_widget == self.sales_report_tab_ui.main_report_section:
            report_date = self.report_results_data.get('daily_used_date_str', 'N/A').replace('-', ' ')
            #header_text = (f"Sales Report {site_code}\n" f"Tanggal {report_date}\n" f"{'_'*30}\n\n")
        elif self.selected_column_widget == self.sales_report_tab_ui.today_mop_section:
            selected_view = self.sales_report_tab_ui.today_mop_section.view_combo.currentText()
            if selected_view == "Today":
                report_date = self.report_results_data.get('day_date_full', 'N/A')
                header_text = (f"{'SALES BY DATE':^40}\n\n" f"Site     : {store_name} - {site_code}\n" f"Print date : {current_datetime_for_print}\n" f"Date       : {report_date}\n" f"{'---'}\n\n")
            else:
                from_date = self.report_results_data.get('min_date_str', 'N/A').replace('-', ' ')
                to_date = self.report_results_data.get('max_date_str', 'N/A').replace('-', ' ')
                header_text = (f"{'SALES BY DATE':^40}\n\n" f"Site     : {store_name} - {site_code}\n" f"Print date : {current_datetime_for_print}\n" f"From       : {from_date}\n" f"To         : {to_date}\n" f"{'---'}\n\n")

        full_text = header_text + content_to_print

        self._print_thermal_receipt(full_text)

    
    def print_report_from_text(self, text):
        """
        Menerima string teks dari widget yang aktif dan mengirimkannya ke Printer.
        Menggunakan rendering native dengan padding khusus thermal agar tidak ada margin berlebih.
        """
        if not text or not text.strip():
            QMessageBox.warning(self, "Peringatan", "Tidak ada data untuk diprint.")
            return
            
        self._print_thermal_receipt(text)
        
    def _print_thermal_receipt(self, text):
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt5.QtWidgets import QMessageBox
        import win32print
        
        # Inisialisasi printer dialog untuk memilih printer dari Windows
        printer = QPrinter()
        
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() == QPrintDialog.Accepted:
            try:
                printer_name = printer.printerName()
                
                # Menyiapkan data RAW (ESC/POS) untuk print
                # 1. Inisialisasi ESC/POS (ESC @)
                raw_data = b'\x1B\x40' 
                
                # 2. Tambahkan text konten
                # Konversi newline ke Windows CRLF agar konsisten, lalu encode
                text_crlf = text.replace('\n', '\r\n')
                try:
                    raw_data += text_crlf.encode('utf-8')
                except UnicodeEncodeError:
                    raw_data += text_crlf.encode('ascii', errors='ignore')
                
                # Jeda 3 baris kosong dari teks utama
                raw_data += b'\r\n\r\n\r\n'
                
                # Tambahkan watermark repot.in dengan font lebih kecil (Font B) dan rata tengah
                watermark = f"-- repot.in v.{self.app_version} --\r\n"
                raw_data += b'\x1B\x61\x01' # ESC a 1 (Justify Center)
                raw_data += b'\x1B\x21\x01' # ESC ! 1 (Select Font B)
                try:
                    raw_data += watermark.encode('utf-8')
                except UnicodeEncodeError:
                    raw_data += watermark.encode('ascii', errors='ignore')
                raw_data += b'\x1B\x21\x00' # ESC ! 0 (Select Font A / Normal)
                raw_data += b'\x1B\x61\x00' # ESC a 0 (Justify Left)
                
                # 3. Baris kosong (Line Feeds) agar kertas naik melewatis printhead ke posisi cutter
                # Ditambah menjadi 6 baris agar tidak memotong isi teks pada akhir struk
                raw_data += b'\r\n\r\n\r\n\r\n\r\n\r\n'
                
                # 4. Perintah Auto-Cut ESC/POS untuk Janz PT350 dan printer generic (GS V 0)
                raw_data += b'\x1D\x56\x00'
                
                # Buka koneksi ke Windows Spooler
                hprinter = win32print.OpenPrinter(printer_name)
                try:
                    # Mulai job print bertipe 'RAW', bypass rendering Windows
                    job_info = ("Repotin Receipt Job", None, "RAW")
                    win32print.StartDocPrinter(hprinter, 1, job_info)
                    win32print.StartPagePrinter(hprinter)
                    
                    # Kirim ESC/POS raw bytes langsung ke printer buffer
                    win32print.WritePrinter(hprinter, raw_data)
                    
                    win32print.EndPagePrinter(hprinter)
                    win32print.EndDocPrinter(hprinter)
                finally:
                    win32print.ClosePrinter(hprinter)
                
                logging.info(f"Berhasil mencetak raw laporan ke printer '{printer_name}'")
                self.notification_manager.show('SUCCESS', 'Mencetak', f"Laporan RAW dikirim ke '{printer_name}'.")
                
            except Exception as e:
                logging.error(f"Gagal mencetak RAW laporan: {e}", exc_info=True)
                QMessageBox.critical(self, "Error Print", f"Terjadi kesalahan mencetak RAW:\n{str(e)}")

    # --- METODE LOAD FILE YANG DIPERBARUI (DUAL CSV) ---
    def load_sbd_file(self):
        dialog = DualFileDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            trans_path, pay_path = dialog.get_files()
            self._start_csv_import_worker(pay_path, trans_path, is_shift1=dialog.is_shift1())

    def _start_csv_import_worker(self, pay_path, trans_path, is_shift1=False):
        self.is_processing_shift1 = is_shift1
        self.current_file_path = trans_path 
        
        self.progress_dialog = QProgressDialog("Membaca file CSV...", "Batal", 0, 100, self)
        self.progress_dialog.setWindowTitle("Loading Data")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None) 
        self.progress_dialog.show()

        thread = QThread()
        # Perhatikan: CsvImportWorker urutan argumennya adalah (trans_path, pay_path)
        worker = CsvImportWorker(trans_path, pay_path)
        worker.moveToThread(thread)
        
        self.sbd_worker_thread = thread 
        self.sbd_worker = worker
        
        thread.started.connect(worker.run)
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.progress_dialog.close)
        worker.finished.connect(self._handle_file_data_loaded)
        worker.error.connect(self._handle_file_load_error)
        
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        
        thread.start()

    def update_progress(self, percent, message):
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.setValue(percent)
            self.progress_dialog.setLabelText(message)

    # --- METODE HANDLE DATA YANG DIPERBARUI (DATA CLEANING) ---
    # GANTI METHOD INI DI main_app.py
    def _handle_file_data_loaded(self, payments_df, transactions_df):
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.close()
        
        logging.info("Memulai pembersihan data CSV...")

        try:
            # --- [BAGIAN CLEANING SAMA SEPERTI SEBELUMNYA] ---
            def clean_currency(x):
                if pd.isna(x) or x == '': return 0
                if isinstance(x, (int, float)): return x
                if isinstance(x, str):
                    clean = x.replace('Rp', '').replace(' ', '').strip()
                    if ',' in clean and '.' in clean: clean = clean.replace('.', '').replace(',', '.')
                    elif ',' in clean and '.' not in clean: clean = clean.replace(',', '.')
                    return pd.to_numeric(clean, errors='coerce')
                return 0

            if COL_AMOUNT in payments_df.columns:
                payments_df[COL_AMOUNT] = payments_df[COL_AMOUNT].apply(clean_currency).fillna(0)
            if COL_NET_PRICE in transactions_df.columns:
                transactions_df[COL_NET_PRICE] = transactions_df[COL_NET_PRICE].apply(clean_currency).fillna(0)
            if COL_QUANTITY in transactions_df.columns:
                 transactions_df[COL_QUANTITY] = pd.to_numeric(transactions_df[COL_QUANTITY], errors='coerce').fillna(0)

            if COL_CREATED_DATE in transactions_df.columns:
                # Prioritaskan format YYYY/MM/DD sesuai CSV Anda
                transactions_df[COL_CREATED_DATE] = pd.to_datetime(
                    transactions_df[COL_CREATED_DATE], format='%Y/%m/%d', errors='coerce'
                )
                # Fallback jika format campur
                mask_nat = transactions_df[COL_CREATED_DATE].isna()
                if mask_nat.any():
                    transactions_df.loc[mask_nat, COL_CREATED_DATE] = pd.to_datetime(
                        transactions_df.loc[mask_nat, COL_CREATED_DATE], dayfirst=True, errors='coerce'
                    )

            if COL_RECEIPT_NO in payments_df.columns:
                payments_df['Tanggal'] = pd.to_datetime(
                    payments_df[COL_RECEIPT_NO].astype(str).str.extract(r'(\d{8})', expand=False), 
                    format='%Y%m%d', errors='coerce'
                ).dt.date
                
            # Drop rows with invalid dates
            transactions_df = transactions_df.dropna(subset=[COL_CREATED_DATE])
            
        except Exception as e:
            logging.error(f"Gagal cleaning data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error Data Cleaning", f"Gagal membersihkan format data CSV: {e}")
            return
        
        # Simpan ke RAM (Opsional, tapi bagus untuk backup/export)
        self.original_payments_df = payments_df
        self.original_transactions_df = transactions_df
        
        # --- [SIMPAN KE DATABASE] ---
        if self.db_manager:
            progress = QProgressDialog("Menyimpan data ke Database...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()
            
            try:
                self.db_manager.save_bulk_raw_data(transactions_df, payments_df)
                logging.info("Data berhasil disimpan ke Database SQLite.")
            except Exception as e:
                logging.error(f"Gagal simpan ke DB: {e}")
                QMessageBox.warning(self, "Database Warning", f"Gagal menyimpan ke database: {e}")
            finally:
                progress.close()

        # Load Preferences
        self.new_series_preferences = [] 
        try:
            if os.path.exists(NEW_SERIES_PREFS_FILE):
                with open(NEW_SERIES_PREFS_FILE, 'r') as f:
                    self.new_series_preferences = json.load(f)
        except Exception: pass
        
        if self.current_file_path:
            self.config_manager.add_recent_file(self.current_file_path)
            # self.landing_page_ui.refresh_data() # Removed because it was moved to main_dashboard_ui or dashboard_tab
            
        self.upload_gsheet_button.setEnabled(True)
        
        # --- [SETTING TANGGAL OTOMATIS] ---
        if not transactions_df.empty:
            min_date = transactions_df[COL_CREATED_DATE].min()
            max_date = transactions_df[COL_CREATED_DATE].max()
            
            if pd.notna(min_date) and pd.notna(max_date):
                self.sales_report_tab_ui.start_date_edit.setDate(min_date.date())
                self.sales_report_tab_ui.end_date_edit.setDate(max_date.date())
                self.sales_report_tab_ui.date_range_radio.setChecked(True)

        logging.info("Memicu refresh report data (from DB)...")
        self.refresh_report_data() 

        # --- [FIX: GUNAKAN SIDEBAR BUTTONS BUKAN TABS] ---
        logging.info(f"[_handle_file_data_loaded] Mengaktifkan {len(self.main_dashboard_ui.report_buttons)} tombol laporan di sidebar...")
        for btn in self.main_dashboard_ui.report_buttons:
            btn.setEnabled(True)
            logging.info(f"Tombol {btn.text().strip()} enabled state: {btn.isEnabled()}")
        
        if hasattr(self, 'main_dashboard_ui') and hasattr(self.main_dashboard_ui, 'dashboard_content'):
            QTimer.singleShot(1000, lambda: self.main_dashboard_ui.dashboard_content.update_date_range_auto())
            QTimer.singleShot(1500, lambda: self.main_dashboard_ui.dashboard_content.load_data())

        self.main_dashboard_ui.main_stack.setCurrentIndex(self.sales_report_idx)
        self.main_dashboard_ui.btn_sales_report.setChecked(True)
            
        QMessageBox.information(self, "Sukses", "Data berhasil diimpor ke Database dan diproses.")      

    def _handle_file_load_error(self, error_message):
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Error Baca File", f"Gagal memuat file CSV:\n{error_message}")
        self._clear_all_views_and_data()

    def _handle_recent_file_selected(self, file_path):
        self.load_sbd_file()

    def _handle_quick_access(self, tab_name):
        if tab_name == "order":
            self.main_dashboard_ui.main_stack.setCurrentIndex(self.order_idx)
            self.main_dashboard_ui.btn_order.setChecked(True)
        elif tab_name == "edspayed":
            self.main_dashboard_ui.main_stack.setCurrentIndex(self.edspayed_idx)
            self.main_dashboard_ui.btn_edspayed.setChecked(True)

    def refresh_report_data(self):
        # 1. Cek apakah DB Manager siap
        if not self.db_manager:
            return

        if not hasattr(self, 'refresh_progress_dialog') or self.refresh_progress_dialog is None:
            self.refresh_progress_dialog = QProgressDialog("Menyiapkan data...", None, 0, 0, self)
            self.refresh_progress_dialog.setWindowModality(Qt.WindowModal)
        
        self.refresh_progress_dialog.show()
        QApplication.processEvents()

        try:
            # 1. Ambil site_code dari konfigurasi
            site_code = self.config_manager.get_config().get('site_code')
            
            # 2. Ambil Filter Tanggal
            date_filter = self.sales_report_tab_ui.get_date_filter_settings()
            
            if date_filter['all_dates']:
                min_db, max_db = self.db_manager.get_available_date_range(site_code)
                if min_db and max_db:
                    start_date = min_db
                    end_date = max_db
                    # --- [FIX CRASH] UPDATE UI & DICTIONARY ---
                    # Karena jika string diproses sebagai Date di bawahnya akan error
                    self.sales_report_tab_ui.start_date_edit.setDate(QDate.fromString(start_date, "yyyy-MM-dd"))
                    self.sales_report_tab_ui.end_date_edit.setDate(QDate.fromString(end_date, "yyyy-MM-dd"))
                    date_filter['start_date'] = QDate.fromString(start_date, "yyyy-MM-dd")
                    date_filter['end_date'] = QDate.fromString(end_date, "yyyy-MM-dd")
                else:
                    start_date = QDate.currentDate().toString("yyyy-MM-dd")
                    end_date = QDate.currentDate().toString("yyyy-MM-dd")
            else:
                start_date = date_filter['start_date'].toString("yyyy-MM-dd")
                end_date = date_filter['end_date'].toString("yyyy-MM-dd")
            
            self.refresh_progress_dialog.setLabelText("Mengambil data dari Database...")
            QApplication.processEvents()
            
            # A. Ambil Transaksi dari Database
            transactions_small_df = self.db_manager.get_transactions_dataframe(start_date, end_date, site_code)
            payments_small_df = self.db_manager.get_payments_dataframe(start_date, end_date, site_code)
            
            # Fallback (Jaga-jaga jika DB gagal, tapi harusnya tidak perlu jika DB sehat)
            if payments_small_df.empty and self.original_payments_df is not None:
                 # Coba ambil dari RAM jika User baru saja import dan DB belum sempat commit (edge case)
                 payments_small_df = self.original_payments_df[
                    (self.original_payments_df['Tanggal'] >= pd.to_datetime(start_date).date()) & 
                    (self.original_payments_df['Tanggal'] <= pd.to_datetime(end_date).date())
                ]

            # Cek Data Kosong
            if transactions_small_df.empty:
                self._clear_all_views_and_data()
                if not date_filter['all_dates']: # Hanya warn jika user memfilter spesifik
                     QMessageBox.information(self, "Info", f"Tidak ada data transaksi di Database untuk periode {start_date} s/d {end_date}.\nSilakan Import CSV jika data belum masuk.")
                return

            # 3. Proses Menggunakan ReportProcessor
            self.refresh_progress_dialog.setLabelText("Mengkalkulasi Laporan...")
            QApplication.processEvents()

            
            # --- [FIX NameError] ---
            # Jangan gunakan 'payments_to_process' lagi. Gunakan end_date untuk menentukan bulan target.
            current_month = pd.to_datetime(end_date).month
            target_for_month = self.config_manager.get_target_for_month(current_month)
            
            processor = ReportProcessor(
                payments_small_df,      # Gunakan DataFrame kecil (filtered)
                transactions_small_df,  # Gunakan DataFrame kecil (filtered)
                target_for_month, 
                site_code,
                self.db_manager
            )
            
            config_dict = self.config_manager.get_config()
            config_dict['site_list'] = self.config_manager.site_list
            config_dict['store_name'] = self.config_manager.get_store_name(site_code)
            
            processor.set_article_filter(self.article_filter_input.text() if hasattr(self, 'article_filter_input') else "")
            processor.set_article_filter(self.article_filter_input.text() if hasattr(self, 'article_filter_input') else "")
            processor.set_promo_preferences(self.selected_promos_for_report)

            # 4. Generate Result (filter new_series_prefs sesuai template aktif)
            _active_tpl = self.sales_report_tab_ui.main_report_section.template_combo.currentText()
            self.report_results_data = processor.process(
                template_name=_active_tpl, 
                config_data=config_dict,
                selected_promos=self.selected_promos_for_report,
                new_series_prefs=self._get_filtered_new_series_prefs(_active_tpl),
                promo_calc_method=self.promo_calc_method,
                promo_metrics=self.promo_metrics_config,
                promo_groups=self._get_filtered_promo_group_data(_active_tpl)
            )
            
            # Simpan hasil olahan untuk keperluan UI lain
            self.processed_transactions_df = processor.transactions_df 
            self.processed_payments_df = processor.payments_df
            
            # 5. Update UI
            self._update_sales_report_ui(self.report_results_data)
            
            # --- [FIX CRITICAL] TRIGGER PENYIMPANAN SHIFT 1 JIKA FLAG AKTIF ---
            if hasattr(self, 'is_processing_shift1') and self.is_processing_shift1:
                logging.info("Memproses penyimpanan Actual Shift 1 karena flag dicentang.")
                if hasattr(self, 'bscd_tab_ui') and hasattr(self.bscd_tab_ui, 'save_shift1_actuals'):
                    self.bscd_tab_ui.save_shift1_actuals(self.report_results_data)
                # Reset flag agar tidak ikut terus ketika refresh manual
                self.is_processing_shift1 = False
            # ------------------------------------------------------------------    

            # Update Dashboard Grafik (jika ada)
            if hasattr(self, 'main_dashboard_ui') and hasattr(self.main_dashboard_ui, 'dashboard_content'):
                # Sinkronkan tanggal dashboard dengan filter laporan
                self.main_dashboard_ui.dashboard_content.start_date.setDate(date_filter['start_date'])
                self.main_dashboard_ui.dashboard_content.end_date.setDate(date_filter['end_date'])
                # Trigger load dashboard
                QTimer.singleShot(500, lambda: self.main_dashboard_ui.dashboard_content.load_data())

            # Aktifkan Tab (Gunakan sidebar buttons)
            logging.info(f"[refresh_report_data] Mengaktifkan {len(self.main_dashboard_ui.report_buttons)} tombol laporan di sidebar...")
            for btn in self.main_dashboard_ui.report_buttons:
                btn.setEnabled(True)
                logging.info(f"Tombol {btn.text().strip()} enabled state: {btn.isEnabled()}")

        except Exception as e:
            logging.error(f"Error refresh (DB Mode): {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Gagal memproses data:\n{str(e)}")
        finally:
            if hasattr(self, 'refresh_progress_dialog'): self.refresh_progress_dialog.close()
                   
    def _update_sales_report_ui(self, data):
        """Memperbarui seluruh komponen UI di Tab Sales Report."""
        if not data: return
        
        # 1. Update Report Text
        self.sales_report_tab_ui.update_main_report_text(data.get('main_report_text', ""))

        # 2. Update MOP
        self._update_mop_display(data)

        # 3. Update Contribution Table
        mtd_contrib = data.get('contribution_mtd_df')
        day_contrib = data.get('contribution_today_df')
        self.sales_report_tab_ui.update_contribution_table(
            mtd_contrib, 
            day_contrib, 
            data.get('day_net', 0.0), 
            data.get('mtd_nett_sales', 0.0), 
            self.new_series_preferences
        )

        # 4. Update Dynamic Table (Kanan Bawah)
        payment_df = data.get('sales_by_payment_df')
        menu_mtd = data.get('menu_summary_df')      
        menu_today = data.get('menu_summary_today_df')
        
        # --- [CRITICAL] AMBIL RAW DATA ---
        raw_trx = None
        
        # Coba ambil dari processor results (jika disimpan di sana)
        if 'day_trx' in data: # Ini hanya daily, kita butuh full MTD untuk search semua resi
             # Kita ambil dari memory main_app saja yang paling lengkap (hasil refresh)
             if hasattr(self, 'processed_transactions_df'):
                 raw_trx = self.processed_transactions_df
        
        if raw_trx is None and hasattr(self, 'processed_transactions_df'):
             raw_trx = self.processed_transactions_df

        # Raw Payment
        raw_pay = payment_df # Payment DF sebenarnya sudah bentuk raw list, jadi bisa dipakai langsung
        
        # Kirim ke UI
        self.sales_report_tab_ui.dynamic_table_widget.set_data(
            payment_df, 
            menu_today, 
            menu_mtd,
            raw_trx_df=raw_trx,
            raw_pay_df=raw_pay
        )

        # 5. Update Waste Budget Info
        if hasattr(self, 'waste_tab_ui'):
            try:
                self.waste_tab_ui.update_budget_info(data.get('mtd_nett_sales', 0.0))
            except Exception as _e:
                logging.warning(f"Gagal update waste budget info: {_e}")

        # 6. [FIX] Update BSCD Tab Data
        if hasattr(self, 'report_results_data'):
            processor = self.report_results_data.get('processor')
            if processor:
                custom_tw = getattr(self, 'bscd_tw_custom_date', None)
                bscd_data = processor.get_bscd_data(self.db_manager, self.config_manager, custom_tw_date=custom_tw)
                self.bscd_tab_ui.update_view(bscd_data)
                self.bscd_tab_ui.update_data(self.report_results_data)

        logging.info("UI Sales Report dan BSCD berhasil diperbarui.")

    def _recalculate_bscd_only(self):
        """Called when the user changes the TW date picker in the BSCD tab."""
        if hasattr(self, 'report_results_data') and hasattr(self, 'db_manager') and hasattr(self, 'config_manager'):
            processor = self.report_results_data.get('processor')
            if processor:
                custom_tw = getattr(self, 'bscd_tw_custom_date', None)
                # Re-fetch only the BSCD data for the new date
                bscd_data = processor.get_bscd_data(self.db_manager, self.config_manager, custom_tw_date=custom_tw)
                self.bscd_tab_ui.update_view(bscd_data)
                self.bscd_tab_ui.update_data(self.report_results_data)
                logging.info(f"BSCD UI re-calculated for new TW date: {custom_tw}")
        
    def _on_mop_view_changed(self):
        """Dipanggil saat user mengganti dropdown MOP (Today <-> MTD)."""
        if hasattr(self, 'report_results_data') and self.report_results_data:
            self._update_mop_display(self.report_results_data)

    def _update_mop_display(self, data):
        """
        Logika filter MOP berdasarkan Today/MTD.
        FIX: Menggunakan self.processed_payments_df agar kolom 'Tanggal' tersedia.
        """
        # 1. Gunakan Dataframe Lengkap (yang tersimpan di app) jika ada
        # Ini mencegah error "Unknown Date" karena kolom Tanggal hilang di 'data' biasa
        if hasattr(self, 'processed_payments_df') and self.processed_payments_df is not None:
            full_df = self.processed_payments_df
        else:
            full_df = data.get('sales_by_payment_df')

        if full_df is None or full_df.empty:
            self.sales_report_tab_ui.update_today_mop_text("Tidak ada data pembayaran.", "-")
            return

        target_df = full_df.copy()
        
        # 2. Validasi Kolom Tanggal (Critical Fix)
        if 'Tanggal' not in target_df.columns:
            # Coba recovery dari kolom lain
            if 'payment_date' in target_df.columns:
                target_df['Tanggal'] = pd.to_datetime(target_df['payment_date'])
            elif 'Created Date' in target_df.columns:
                target_df['Tanggal'] = pd.to_datetime(target_df['Created Date'])
            else:
                self.sales_report_tab_ui.update_today_mop_text("Error: Kolom Tanggal tidak ditemukan.", "Error Data")
                return

        # Pastikan tipe datetime
        target_df['Tanggal'] = pd.to_datetime(target_df['Tanggal'])
        
        # 3. Logika Filter Today vs MTD
        view_mode = self.sales_report_tab_ui.today_mop_section.view_combo.currentText()
        
        max_date = target_df['Tanggal'].max()
        min_date = target_df['Tanggal'].min()
        date_label = ""
        
        bulan_indo = {
            "January": "Januari", "February": "Februari", "March": "Maret",
            "April": "April", "May": "Mei", "June": "Juni",
            "July": "Juli", "August": "Agustus", "September": "September",
            "October": "Oktober", "November": "November", "December": "Desember"
        }
        
        if view_mode == "Today":
            # MODE TODAY: Ambil hanya data pada tanggal TERAKHIR di dataset
            target_df = target_df[target_df['Tanggal'] == max_date]
            b_indo = bulan_indo.get(max_date.strftime("%B"), max_date.strftime("%B"))
            date_label = f"{max_date.strftime('%d')} {b_indo} {max_date.strftime('%Y')}"
        else:
            # MODE MTD: Ambil SEMUA data dalam rentang yang dipilih user
            if min_date == max_date:
                b_indo = bulan_indo.get(min_date.strftime("%B"), min_date.strftime("%B"))
                date_label = f"{min_date.strftime('%d')} {b_indo} {min_date.strftime('%Y')}"
            else:
                date_label = f"{min_date.strftime('%d/%m')} - {max_date.strftime('%d/%m/%Y')}"

        # 4. Generate Text Summary
        if target_df.empty:
            self.sales_report_tab_ui.update_today_mop_text("Tidak ada data untuk tanggal ini.", date_label)
            return

        # Group by MOP Name & Sum Amount
        mop_summary = target_df.groupby('MOP Name')['Amount'].sum().sort_values(ascending=False)
        
        def fmt(val): return f"{val:,.0f}".replace(",", ".")
        
        # Get Store name/Site code
        site_code = getattr(self, 'report_results_data', {}).get('sbd_site_code')
        if not site_code or site_code == "N/A":
             site_code = self.config_manager.get_config().get('site_code', 'N/A')
             
        store_name = self.config_manager.get_store_name(site_code)
        
        # Avoid duplicate store name if report_processor already added it:
        if store_name and store_name not in site_code:
            full_site_name = f"{site_code} - {store_name}"
        else:
            full_site_name = site_code
        
        lines = []
        lines.append(f"Site       : {full_site_name}")
        lines.append(f"Sales Date : {date_label}")
        lines.append("---")
        lines.append("")
        
        idx = 1
        for name, amount in mop_summary.items():
            lines.append(f"{idx}. {name}: {fmt(amount)}")
            idx += 1
        
        gross_sales = mop_summary.sum()
        nett_sales = gross_sales / 1.1
        service_charge = gross_sales - nett_sales
        
        lines.append("")
        lines.append("---")
        lines.append(f"Gross Sales: {fmt(gross_sales)}")
        lines.append(f"Service Charge: {fmt(service_charge)}")
        lines.append(f"Nett Sales: {fmt(nett_sales)}")

        mop_text = "\n".join(lines)

        # Update UI
        self.sales_report_tab_ui.update_today_mop_text(mop_text, date_label)
    def confirm_clear_ui_data(self):
        if not self.current_file_path and (not hasattr(self, 'sales_report_tab_ui') or self.sales_report_tab_ui.result_text_main.toPlainText().strip() == ""):
             QMessageBox.warning(self, "Peringatan", "Tidak ada data untuk dihapus. Tampilan sudah kosong.")
             return

        confirm = QMessageBox.question(self, "Konfirmasi Hapus", "Anda yakin ingin menghapus semua data?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm == QMessageBox.Yes:
            self._clear_all_views_and_data()
            QMessageBox.information(self, "Informasi", "Tampilan dan data internal telah dibersihkan.")

    def _clear_all_views_and_data(self):
        if hasattr(self, 'sales_report_tab_ui'): self.sales_report_tab_ui.clear_all_dynamic_content()
        if hasattr(self, 'bscd_tab_ui'): self.bscd_tab_ui.clear_view()
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setTabEnabled(self.sales_report_tab_idx, False)
            self.tab_widget.setTabEnabled(self.bscd_tab_idx, False)

        self.file_info_label.setText("Data dibersihkan. Buka file baru untuk memulai analisis baru.")
        
        if hasattr(self, 'upload_gsheet_button'):
            self.upload_gsheet_button.setEnabled(False)
        
        self.current_file_path = None
        self.original_payments_df, self.original_transactions_df = None, None
        self.processed_transactions_df, self.processed_payments_df = None, None 
        self.report_results_data = {} 
        self.selected_column_widget = None

    def open_article_selection_dialog(self):
        if self.processed_transactions_df is None or self.processed_transactions_df.empty:
            QMessageBox.warning(self, "Peringatan", "Tidak ada data untuk dipilih. Proses laporan terlebih dahulu.")
            return
        
        articles = self.processed_transactions_df[COL_ARTICLE_NAME].dropna().unique().tolist()
        if not articles:
            QMessageBox.warning(self, "Peringatan", "Tidak ada nama artikel unik yang ditemukan.")
            return

        # Load daftar template yang tersedia untuk dipass ke dialog
        try:
            import json as _json
            from utils.constants import REPORT_TEMPLATE_FILE as _REPORT_TEMPLATE_FILE
            _available_templates = []
            if os.path.exists(_REPORT_TEMPLATE_FILE):
                with open(_REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as _f:
                    _available_templates = list(_json.load(_f).keys())
        except Exception:
            _available_templates = []

        dialog = NewSeriesGroupDialog(articles, pre_selected_data=self.new_series_preferences, available_templates=_available_templates, parent=self)
        
        if dialog.exec_() == QDialog.Accepted:
            self.new_series_preferences = dialog.get_selection_data()
            try:
                os.makedirs(os.path.dirname(NEW_SERIES_PREFS_FILE), exist_ok=True)
                with open(NEW_SERIES_PREFS_FILE, 'w') as f:
                    json.dump(self.new_series_preferences, f, indent=4)
            except Exception as e:
                logging.error(f"Gagal menyimpan preferensi: {e}")
            
            self._handle_article_selection_changed()       
    
    def _handle_article_selection_changed(self):
        if not self.report_results_data: return

        logging.info("Pilihan artikel diubah. Mengolah ulang bagian New Series...")
        
        progress = QProgressDialog("Memperbarui laporan New Series...", None, 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        processor = self.report_results_data.get('processor')
        day_trx = self.report_results_data.get('day_trx')
        day_net = self.report_results_data.get('day_net', 0)
        mtd_nett_sales = self.report_results_data.get('mtd_nett_sales', 0)

        _active_tpl = self.sales_report_tab_ui.main_report_section.template_combo.currentText()
        new_series_outputs = processor.regenerate_new_series_outputs(
            day_trx, 
            day_net, 
            mtd_nett_sales, 
            self._get_filtered_new_series_prefs(_active_tpl)    
        )

        self.report_results_data.update(new_series_outputs)

        _active_tpl = self.sales_report_tab_ui.main_report_section.template_combo.currentText()
        new_main_text = processor.regenerate_main_report_text(
            _active_tpl,
            self.report_results_data,
            self.report_results_data.get('promo_text_block', ''),
            new_series_outputs.get('new_series_text_block', '')
        )

        self.sales_report_tab_ui.update_main_report_text(new_main_text)
        self.sales_report_tab_ui.update_contribution_table(
            new_series_outputs.get('contribution_mtd_df'),
            new_series_outputs.get('contribution_today_df'),
            day_net,
            mtd_nett_sales,
            self._get_filtered_new_series_prefs(_active_tpl)
        )
        
        progress.close()
        self.notification_manager.show('SUCCESS', 'Laporan Diperbarui', 'Tampilan New Series telah diperbarui.')
    
    def _get_filtered_new_series_prefs(self, template_name: str) -> list:
        """Filter new_series_preferences: hanya kembalikan grup yang sesuai template aktif.
        Jika grup tidak punya key 'templates' atau list kosong, anggap tampil di semua template."""
        if not template_name:
            return self.new_series_preferences
        return [
            g for g in self.new_series_preferences
            if not g.get('templates')  # kosong = semua template
            or template_name in g.get('templates', [])
        ]

    def print_selected_column(self):
        self.print_selected_report()

    def _show_config_dialog(self):
        dialog = ConfigDialog(self.config_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            # Re-read config from file to get latest values
            self.config_manager.reread_config()
            
            # Refresh all UI elements that depend on config
            self._refresh_upload_button_visibility()
            self._refresh_chat_widget_visibility()
            self.update_marquee_text_from_config()
            
            # Refresh dashboard welcome greeting (store name)
            if hasattr(self, 'main_dashboard_ui'):
                self.main_dashboard_ui.refresh_data()
                # Refresh dashboard charts/KPIs with new site_code
                if hasattr(self.main_dashboard_ui, 'dashboard_content'):
                    self.main_dashboard_ui.dashboard_content.load_data()
            
            # Refresh report data with the new site_code (handles multi-store filtering)
            self.refresh_report_data()
        else:
            # Even on cancel, re-sync UI state
            self._refresh_upload_button_visibility()
            self._refresh_chat_widget_visibility()

    def show_employee_management(self):
        dialog = LoginDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.logged_in_role:
            EmployeeManagementDialog(dialog.logged_in_role, self).exec_()

    def show_credential_management(self):
        dialog = LoginDialog(self); dialog.role_combo.setCurrentText(ROLE_ADMIN)
        if dialog.exec_() == QDialog.Accepted:
            role = dialog.logged_in_role
            if role == ROLE_ADMIN: 
                CredentialManagementDialog(role, self).exec_()
            elif role == ROLE_USER:
                 QMessageBox.information(self, "Akses Ditolak", "Fitur ini hanya untuk Administrator.")

    def _show_about_dialog(self):
        about_text = f"""
        <h2>Repot.in - v{self.app_version}</h2>
        <p>Sebaik baik manusia adalah manusia yang bermanfaat bagi manusia lainnya.</p>
        <p>Seburuk buruk manusia adalah BAHLIL, JOKOWI, DAN PARA TERMUL, AWOKWOKWOWKOKOK.</p>
        
        <p><b>Developed by:</b> JstEd </p>
        <p>Hak Cipta &copy; {QDate.currentDate().year()} editude - 158599 </p>
        <hr>
        <p>Dibuat dengan bantuan AI (Gemini, Claude, ChatGPT), Python, dan ❤️</p>
        """
        QMessageBox.about(self, f"Tentang Repot.in v{self.app_version}", about_text)

    def _show_user_guide_dialog(self):
        guide_dialog = QDialog(self)
        guide_dialog.setWindowTitle("Panduan Penggunaan Repot.in")
        guide_dialog.setGeometry(150, 150, 750, 600) # Perbesar sedikit dialognya

        layout = QVBoxLayout(guide_dialog)
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        
        guide_html = """
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; padding: 15px; background-color: #f7f9fc; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; font-size: 24px; margin-top: 5px; }
            h2 { color: #2980b9; margin-top: 25px; font-size: 18px; margin-bottom: 10px; }
            h3 { color: #e67e22; margin-top: 15px; font-size: 15px; font-weight: bold; margin-bottom: 5px; }
            p { margin-bottom: 10px; font-size: 13px; }
            ul { margin-bottom: 15px; font-size: 13px; background: #ffffff; padding: 15px 15px 15px 35px; border-radius: 8px; border: 1px solid #e1e8ed; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
            li { margin-bottom: 8px; }
            .highlight { background-color: #e8f4f8; padding: 15px; border-left: 4px solid #3498db; border-radius: 5px; margin-bottom: 15px; }
            code { background-color: #f1f2f6; padding: 2px 6px; border-radius: 4px; color: #d35400; font-family: Consolas, monospace; }
            .footer { text-align: center; font-size: 11px; color: #7f8c8d; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px; }
        </style>
        <h1>🚀 Panduan Penggunaan Repot.in</h1>
        <div class="highlight">
            <p>Selamat datang di <b>Repot.in</b>! Aplikasi ini dirancang untuk mempermudah analisis penjualan harian, manajemen stok In-Use, hingga pelacakan laporan operasional secara real-time. Ikuti panduan di bawah ini untuk memulai.</p>
        </div>

        <h2>⚙️ 1. Konfigurasi Awal</h2>
        <p>Gunakan menu <b>File > Konfigurasi...</b> di bar atas untuk menyesuaikan aplikasi dengan toko Anda:</p>
        <ul>
            <li><b>Site Code:</b> Masukkan kode toko Anda. Nama toko akan otomatis muncul jika terdaftar.</li>
            <li><b>Target Bulanan:</b> Masukkan target penjualan bulanan toko untuk memantau performa <i>Achievement</i> harian Anda.</li>
            <li><b>Google Sheet ID:</b> (Opsional) Masukkan ID Spreadsheet untuk menggunakan tombol sinkronisasi "Upload ke Google Sheet".</li>
            <li><b>Running Text:</b> Teks motivasional yang akan bergerak di area Dashboard.</li>
        </ul>

        <h2>📂 2. Mengolah Data Laporan (Sales Report)</h2>
        <p>Aplikasi memproses file CSV dari Aurora Anda menjadi ringkasan penjualan komprehensif. Ada dua pilihan load data:</p>
        <ul>
            <li><b>Impor CSV Aktif:</b> Melalui menu <b>File > Import Data CSV...</b> untuk menarik data sales harian (Gabungan file <i>Transactions</i> dan <i>Payments</i> SBD).</li>
            <li><b>Database Analysis:</b> Klik rentang tanggal di mode Database untuk menarik penjualan minggu lalu / bulan lalu secara instan tanpa mengunggah file.</li>
        </ul>
        <h3>Tab Laporan Penjualan Menampilkan:</h3>
        <ul>
            <li>Net Sales, Target, AC (Average Check), TC (Total Check).</li>
            <li>Detail Transaksi per Channel (Instore, Ojol, dll.) dan jumlah qty Cup/Topping terjual.</li>
            <li>Detail MOP yang dikuratori per tanggal (Today/MTD).</li>
            <li>Grup khusus New Series atau Promo sesuai dengan *Template Laporan* Anda.</li>
        </ul>

        <h2>📈 3. Balance Score Card (BSCD) & Dashboard</h2>
        <p>Visualisasi canggih kemajuan bisnis Anda:</p>
        <ul>
            <li><b>Dashboard:</b> Lihat rasio target harian melingkar serta grafik kontribusi kanal Ojol vs Instore.</li>
            <li><b>Tab BSCD:</b> Komparasi performa This Week vs Last Week vs Last Month. Berguna untuk presentasi evaluasi mingguan. Data pembanding dicari otomatis di *history.db*.</li>
        </ul>

        <h2>🛠️ 4. Tools Ekstra & Utilitas Operasional</h2>
        <p>Tombol-tombol sakti di Sidebar dan Menu Tools:</p>
        <ul>
            <li><b>Chat IT:</b> Kirim pesan ke tim IT dari panel Chat IT tanpa perlu ganti aplikasi.</li>
            <li><b>Edspayed (Exp. List):</b> Kalkulator perhitungan tanggal expired yang akurat.</li>
            <li><b>Kas & Tips:</b> Catat uang tips dengan transparan dan mudah dilacak!</li>
            <li><b>Order Barang (Warehouse):</b> Minimalisir kesalahan input artikel dan qty order!</li>
            <li><b>In Use & Waste:</b> Tools untuk membantu proses insue dan waste.</li>
            <li><b>Todo List & Notes:</b> Checklist pekerjaan serta papan corat-coretan harian.</li>
        </ul>

        <div class="footer">
            <p><i>Masih bingung? "Sama, saya juga. Nanti kalo udah di surga baru ngga bingung." - Aldi Taher</i><br>
            Disclaimer: Aplikasi ini bukan peranti lunak resmi FnB. Segala kesalahan data yang dihasilkan bukan tanggung jawab pengembang.</p>
        </div>
        """
        text_browser.setHtml(guide_html)
        layout.addWidget(text_browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(guide_dialog.accept)
        layout.addWidget(buttons)
        guide_dialog.exec_()
    
    def _show_changelog_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Log Perubahan - Repot.in")
        dialog.resize(700, 500) # Ukuran yang nyaman untuk membaca
        
        layout = QVBoxLayout(dialog)
        
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        
        # Konten Log (HTML Format)
        html_content = """
        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.7</h2>
<p><b>Status:</b> Patch Update<br><b>Tanggal:</b> 23 April 2026</p>
<hr>

<h3 style="color: #c0392b;">🐞 Bugs n Urgent Fixes</h3>
<ul>
    <li><b>Sales Report:</b> Fix error mengupload CSV dan mengambil data dari Aurora, ini dikarenakan terdapat penyesuaian format data yang digunakan (output) sistem Aurora.</li>
    <li><b>Sales Report:</b> Fix Detail tabel pada deatil receipt, semua informasi sudah lengkap ditampilkan.</li>
    <li><b>Dashboard:</b> FIx ukuran grafik sales Instore vs Ojol yang tidak proporsional.</li>
</ul>

        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.6</h2>
<p><b>Status:</b> Patch Update<br><b>Tanggal:</b> 20 April 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Fitur dan Optimasi </h3>
<ul>
    <li><b>Sales Report:</b> Penambahan Sales Per-Hour ke Detail Table.</li>
    <li><b>Sales Report:</b> Optimasi fungsionalitas table, sekarang bisa di sort dan di sesuaikan ukuran kolomnya.</li>
    <li><b>Sales Report:</b> Double klik jam pada sales per-hour akan menampilkan data transaksi pada rentang jam tersebut.</li>
    <li><b>Konversi Waste:</b> Penambahan Budget Waste ke dalam Konversi Waste, thanks to <b>Mastah Ananda Pratama</b> untuk referensi implementasinya.</li>
</ul>

<h3 style="color: #c0392b;">🐞 Bug Fixes</h3>
<ul>
    <li>Fix known bugs.</li>
</ul>
        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.5</h2>
<p><b>Status:</b> Patch Update<br><b>Tanggal:</b> 7 April 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Fitur dan Optimasi </h3>
<ul>
    <li><b>Sales Report:</b> Penambahan placeholder dan template baru, mengikuti format terbaru sales report PBI.</li>
    <li><b>Sales Report:</b> Optimasi display table new series.</li>
    <li><b>Dashboard:</b> Penambahan persentase achievment MTD.</li>
    <li><b>Dashboard:</b> Penambahan grafik perbandingan penjualan Ojol vs Instore.</li>
</ul>

<h3 style="color: #c0392b;">🐞 Bug Fixes</h3>
<ul>
    <li><b>Dashboard:</b> Fix persentase Large dan Topping yang tidak sesuai.</li>
    <li><b>Inuse:</b> Fix tidak bisa impor dan penambahan opsi ekstensi file.</li>
</ul>

        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.4</h2>
<p><b>Status:</b> Patch Update<br><b>Tanggal:</b> 28 Maret 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Fitur dan Optimasi </h3>
<ul>
    <li><b>Sales Report:</b> Optimasi Filter artikel dan Promosi, setiap grup yang dibuat sekarang bisa untuk template tertentu saja.</li>
    <li><b>Dashboard:</b> Penambahan Achievement Badge, akan muncul jika target tercapai.</li>
    <li><b>Konfigurasi:</b> Penambahan auto generate link Chat IT, cukup ketik cerberus.klgsys.com/sso dan klik ambil token.</li>
</ul>

<h3 style="color: #c0392b;">🐞 Bug Fixes</h3>
<ul>
    <li>Fix knowing bug.</li>
</ul>
        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.3</h2>
<p><b>Status:</b> Patch Update<br><b>Tanggal:</b> 25 Maret 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Features & Optimations </h3>
<ul>
    <li>GUE GAK NAMBAHIN FITUR, CUMA FIX SALAH PERHITUNGAN SR DARI GROSS SALES KE NETT SALES, ITU DOANG.</li>
    <li><b>Hehehehehe....</li>
</ul>
        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.2</h2>
<p><b>Status:</b>Stabil Patch Update<br><b>Tanggal:</b> 22 Maret 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Features & Optimations </h3>
<ul>
    <li><b>Sales Report:</b> Optimizing print function (add watermark).</li>
    <li><b>System:</b> Add developer broadcast info.</li>
    <li><b>Workflow:</b> Add daily matric target, now can automatically sync daily matric target to Upselling and Promo table.</li>
    <li><b>System:</b> Add automatic update option to get latest version of repot.in.</li>
    <li><b>Security:</b> Added hash encryption to authorized device configuration.</li>
</ul>

        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.1</h2>
<p><b>Status:</b>Minor Update<br><b>Tanggal:</b> 17 Maret 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Optimasi & Fitur</h3>
<ul>
    <li><b>BSCD:</b> Add backdate option, bisa ubah tanggal TW.</li>
    <li><b>INUSE:</b> Grup management, mempermudah pengelolaan artikel inuse.</li>
    <li><b>WASTE:</b> Recent waste list, mempermudah pengelolaan waste.</li>
</ul>

<h3 style="color: #c0392b;">🐞 Bug Fixes</h3>
<ul>
    <li><b>Aurora Sync:</b> fix double thread, proses sinkronisasi sudah berjalan normal.</li>
    <li><b>GS Upload:</b> Fix issue upload file ke Google Sheet.</li>
    <li><b>PRINT:</b> Fix gagal print ke printer Receipt.</li>
</ul>


        <h2 style="color: #2980b9;">Repot.in - Versi 5.0.0</h2>
<p><b>Status:</b> Major Release<br><b>Tanggal:</b> 11 Maret 2026</p>
<hr>

<h3 style="color: #2980b9;">🌟 Fitur Baru</h3>
<ul>
    <li><b>Sync Aurora:</b> Fitur Auto Sync dengan Aurora untuk mengunduh data AH Commodity Report dan MOP Report secara otomatis.</li>
    <li><b>Server Dependencies:</b> Penambahan semua file dependensi ke server.</li>
</ul>

<h3 style="color: #e67e22;">🚀 Optimasi & Fitur</h3>
<ul>
    <li><b>BSCD:</b> Perbaikan data OUAST yang tidak tampil pada tabel.</li>
    <li><b>Database:</b> Optimasi database untuk performa lebih baik.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Bug Fixes</h3>
<ul>
    <li><b>General:</b> Fix beberapa known bug, kecuali fungsi printing 🥺.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Known Bug</h3>
<ul>
    <li><b>Printing:</b> Direct print to receipt belum tersedia, akan diperbaiki di update selanjutnya.</li>
    <li><b>Menemukan bug lain?</b> Sila informasikan via email atau whatsapp.</li>
</ul>
<br>

        <h2 style="color: #2980b9;">Repot.in - Versi 4.1.6</h2>
<p><b>Status:</b> Stable Update<br><b>Tanggal:</b> 9 Maret 2026</p>
<hr>

<h3 style="color: #e67e22;">🚀 Optimasi & Fitur</h3>
<ul>
    <li><b>Dashboard:</b> Penambahan SSG/YoY sales.</li>
    <li><b>BSCD:</b> Penambahan Business Review auto analysis.</li>
    <li><b>Sales report-new series:</b> Optimasi fitur simpan grup artikel.</li>
    <li><b>Todolist:</b> Optimasi short by periode.</li>
    <li><b>Notes:</b> Penambahan judul dan pin on top.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Bug Fixes</h3>
<ul>
    <li><b>Printing:</b> Gegara gapunya printer thermal, jadi gabisa test langsung, ini percobaan ke-28 semoga bisa :(.</li>
    <li><b>General:</b> Fix beberapa known bug dari versi sebelumnya.</li>
</ul>
<br>

        <h2 style="color: #2980b9;">Repot.in - Versi 4.0.6 build 060326</h2>
<p><b>Status:</b> Stable Update<br><b>Tanggal:</b> 6 Maret 2026</p>
<hr>

<h3 style="color: #2980b9;">🌟 Info Penting</h3>
<ul>
    <li><b>Database:</b> Versi ini mengalami perubahan struktur database, silakan backup data sebelum update.</li>
</ul>

<h3 style="color: #e67e22;">🚀 Optimasi & Fitur</h3>
<ul>
    <li><b>Chat With IT:</b> Fitur Chat with IT sudah bisa digunakan sepenuhnya (pastikan link sudah diisi pada konfigurasi).</li>
    <li><b>New Series:</b> Optimasi pemilihan artikel New Series.</li>
    <li><b>Edspayed:</b> Optimasi tab Edspayed.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Bug Fixes</h3>
<ul>
    <li><b>Printing:</b> Perbaikan bug margin kosong saat mencetak struk laporan ke Printer Thermal (Percobaan ke-27 fix).</li>
    <li><b>General:</b> Fix beberapa known bug dari versi sebelumnya.</li>
</ul>
<br>

        <h2 style="color: #2980b9;">Repot.in - Versi 4.0.6</h2>
<p><b>Status:</b> Stable Release<br><b>Tanggal:</b> 2 Maret 2026</p>
<hr>

<h3 style="color: #2980b9;">🌟 Fitur Baru</h3>
<ul>
    <li><b>Todo List:</b> Catat dan track issue harian.</li>
    <li><b>Notes:</b> Buat catatan bebas yang akan tersimpan otomatis.</li>
    <li><b>File Downloader:</b> Cek dan unduh file tambahan yang dibutuhkan langsung melalui aplikasi.</li>
</ul>

<h3 style="color: #e67e22;">🎨 Tampilan & UX</h3>
<ul>
    <li><b>Tampilan Utama Diperbarui:</b> Redesign main interface dengan tampilan yang lebih segar dengan sidebar menu.</li>
    <li><b>Sales Report:</b> Reposisi beberapa element UI, dictionary template sales report kini lebih lengkap.</li>
    <li><b>Kas & Tips:</b> Redesign layout, tampilan lebih segar .</li>
    <li><b>Edspayed Tab:</b> Penambahan format Expired by Hour (Jam) dan pencatatan suhu.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Bug Fixes</h3>
<ul>
    <li><b>Sales Report:</b> Fix multiple thread yang menyebabkan crash/hang pada saat refresh data.</li>
    <li><b>BSCD:</b> Fix Upselling dan Promo, data shift 1 sekarang terpisah sepenuhnya.</li>
    <li><b>Layout Graphics:</b> Merapikan efek bayangan pada beberapa elemen yang terpotong.</li>
</ul>

<h3 style="color: #c0392b;">🐛 Known Bug</h3>
<ul>
    <li><b>Chat With IT:</b> Fungsi chat ini masih dalam pengembangan, terdapat bug pada webview internal, i'll fix it on next release.</li>
    <li><b>Menemukan bug lain?</b> Sila informasikan via email atau whatsapp.</li>
</ul>
<br>

<h2 style="color: #2980b9;">Repot.in - Versi 4.0.5</h2>
<p><b>Status:</b> Beta Release<br><b>Tanggal:</b> 16 Desember 2025</p>
<hr>

<h3 style="color: #2980b9;">🌟 Fitur Baru (Beta)</h3>
<ul>
    <li>Penambahan fungsi "Tandai sebagai shift 1", Penambahan table Upselling dan Promo tracking. Fitur otomatis target akan segera tersedia.</li>
</ul>
<h3 style="color: #e67e22;">🎨 Tampilan & UX (Order Tab)</h3>
<ul>
    <li>Modern UI Redesign, Status Badges, dan High Contrast Buttons.</li>
</ul>
<h3 style="color: #c0392b;">🛠️ Perbaikan Fungsional & Bug</h3>
<ul>
    <li>SAP Copy Fix, Filter Logic, Google Sheet Upload Format Fix, Perbaikan Crash (variabel `req`).</li>
</ul>
<br>

        <h2 style="color: #2980b9;">Repot.in - Versi 4.0.4</h2>
        Tanggal: 30 November 2025<br>
        Status: <i>Stable Release</i></p>
        <hr>

        <h3 style="color: #2980b9;">🌟 Fitur Baru (New Features)</h3>
        <ul>
            <li><b>Tab In-Use (Peningkatan Besar mengikuti format standar FnB):</b>
                <ul>
                    <li><b>Input Header Otomatis:</b> Format teks SAP otomatis: <code>[KATEGORI]-NAMA/TGL/REMARK</code>.</li>
                    <li><b>Header Text Short:</b> Kolom copy cepat untuk format <code>NAMA/TGL</code>.</li>
                    <li><b>CRUD Manual:</b> Tombol tambah, edit, dan hapus item In-Use secara manual.</li>
                    <li><b>Indikator Karakter:</b> Validasi batas 50 karakter pada Preview Text SAP.</li>
                    <li><b>UX:</b> Penyesuaian warna pada kolom input Qty.</li>
                </ul>
            </li>
            <li><b>Template Editor (Makeover UI):</b>
                <ul>
                    <li>Tampilan modern dengan Split View (Editor & Placeholder).</li>
                    <li>Fitur CRUD untuk Placeholder (Tambah Kategori & Item dinamis).</li>
                </ul>
            </li>
            <li><b>Sistem Notifikasi (Toast):</b>
                <ul>
                    <li>Notifikasi melayang (non-blocking) untuk pesan Sukses/Info.</li>
                    <li>Tidak lagi mengganggu fokus keyboard saat input data.</li>
                </ul>
            </li>
        </ul>

        <h3 style="color: #e67e22;">🛠️ Perbaikan & Optimasi</h3>
        <ul>
            <li><b>Article Selection:</b> Pencarian lebih cerdas & pengelompokan varian nama (Regex).</li>
            <li><b>Promotion Selection:</b> Tampilan baru dengan fitur "Pilih Semua".</li>
            <li><b>Google Sheet Upload:</b> Perbaikan format tanggal/angka (menggunakan <code>USER_ENTERED</code>).</li>
            <li><b>Struktur File:</b> Pemisahan modul ke folder <code>ui/</code>, <code>utils/</code>, <code>modules/</code>.</li>
        </ul>

        <h3 style="color: #c0392b;">🐛 Bug Fixes</h3>
        <ul>
            <li>Fix crash pada inisialisasi InUseTab.</li>
            <li>Fix warna teks tombol "Pilih dari Daftar" yang tidak terbaca.</li>
            <li>Fix input angka desimal presisi tinggi pada Konversi Waste.</li>
        </ul>
        <hr>
        <p align="center" style="color: gray; font-size: small;">Developed by JstEd</p>
        """
        
        text_browser.setHtml(html_content)
        layout.addWidget(text_browser)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(dialog.accept)
        layout.addWidget(btn_box)
        
        dialog.exec_()
    
    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Konfirmasi Keluar', "Anda yakin ingin keluar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes: 
            logging.info("Aplikasi ditutup oleh pengguna.")
            event.accept()
        else: 
            event.ignore()
            
    def _show_calculator(self):
        if self.calculator_dialog is None or not self.calculator_dialog.isVisible():
            self.calculator_dialog = CalculatorDialog(self) 
            self.calculator_dialog.show() 
        else:
            self.calculator_dialog.activateWindow()
            self.calculator_dialog.raise_()
            
    def _show_log_dialog(self):
        if self.log_dialog is None or not self.log_dialog.isVisible():
            self.log_dialog = LogDialog(LOG_FILE_PATH, self)
            self.log_dialog.show()
        else:
            self.log_dialog.activateWindow()
            self.log_dialog.raise_()
            self.log_dialog.load_log_content() 
            
    def _export_settings(self):
        default_filename = f"repotin_settings_backup_{datetime.now().strftime('%Y%m%d')}.ini"
        save_path, _ = QFileDialog.getSaveFileName(self, "Ekspor Pengaturan ke...", default_filename, "INI Files (*.ini);;All Files (*)")
        if save_path:
            try:
                shutil.copyfile(CONFIG_FILE_NAME, save_path)
                self.notification_manager.show('SUCCESS', 'Ekspor Berhasil', f"Pengaturan disimpan ke {os.path.basename(save_path)}")
            except Exception as e:
                self.notification_manager.show('ERROR', 'Ekspor Gagal', f"Gagal menyimpan pengaturan: {e}")

    def _import_settings(self):
        open_path, _ = QFileDialog.getOpenFileName(self, "Impor Pengaturan dari...", "", "INI Files (*.ini);;All Files (*)")
        if open_path:
            reply = QMessageBox.question(self, "Konfirmasi Impor", "Tindakan ini akan me-restart aplikasi. Lanjutkan?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    shutil.copyfile(open_path, CONFIG_FILE_NAME)
                    self._restart_application()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Gagal impor: {e}")

    def _restart_application(self):
        QApplication.instance().quit()
        QProcess.startDetached(sys.executable, sys.argv)
        
    def _show_template_editor(self):
        dialog = TemplateEditorDialog(self)
        dialog.exec_()
        selected_template = dialog.current_template_name
        self._load_report_templates(default_template_name=selected_template)
        
    def _show_todo_list(self):
        if self.todo_dialog is None:
            self.todo_dialog = TodoListDialog(self)
        self.todo_dialog.show()

    def _show_notes(self):
        if self.notes_dialog is None:
            self.notes_dialog = NotesDialog(self)
        self.notes_dialog.show()
        self.notes_dialog.raise_()
        self.notes_dialog.activateWindow()

    def _show_downloader(self):
        if self.downloader_dialog is None:
            self.downloader_dialog = DownloaderDialog(self)
        self.downloader_dialog.show()
        self.downloader_dialog.raise_()
        self.downloader_dialog.activateWindow()
        
    def open_promo_selection_dialog(self):
        promo_names = self.report_results_data.get('all_promotions_list', [])
        if not promo_names:
            QMessageBox.warning(self, "Data Tidak Tersedia", "Tidak ada data promosi pada periode ini.")
            return
        
        # Load daftar template untuk assignment
        try:
            import json as _json
            from utils.constants import REPORT_TEMPLATE_FILE as _REPORT_TEMPLATE_FILE
            _available_templates = []
            if os.path.exists(_REPORT_TEMPLATE_FILE):
                with open(_REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as _f:
                    _available_templates = list(_json.load(_f).keys())
        except Exception:
            _available_templates = []

        dialog = PromotionSelectionDialog(
            promo_names, 
            pre_selected_data=self.promo_group_data,
            current_method=self.promo_calc_method, 
            available_templates=_available_templates,
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            selection_data = dialog.get_selected_data()
            self.selected_promos_for_report = selection_data["promos"]
            self.promo_calc_method = selection_data["method"]
            self.promo_group_data = selection_data.get("groups", [])
            
            # Persist promo groups to JSON file
            try:
                with open(PROMO_PREFS_FILE, 'w') as f:
                    json.dump(self.promo_group_data, f, indent=2)
            except Exception as e:
                logging.warning(f"Gagal menyimpan promo_group_preferences.json: {e}")
            
            self._handle_promo_selection_changed()
    
    def _handle_promo_selection_changed(self):
        if not self.report_results_data: return

        logging.info("Pilihan promosi diubah.")
        processor = self.report_results_data.get('processor')
        merged_promo_df = self.report_results_data.get('merged_promo_df')
        day_net = self.report_results_data.get('day_net', 0)
        mtd_nett_sales = self.report_results_data.get('mtd_nett_sales', 0)
        _active_tpl = self.sales_report_tab_ui.main_report_section.template_combo.currentText()

        new_promo_block = processor.regenerate_promo_block_text(
            merged_promo_df, self.selected_promos_for_report, day_net, mtd_nett_sales,
            promo_metrics=self.promo_metrics_config,
            promo_groups=self._get_filtered_promo_group_data(_active_tpl),
            merged_by_receipt=self.report_results_data.get("merged_promo_by_receipt"),
            merged_by_item=self.report_results_data.get("merged_promo_by_item"),
        )

        self.report_results_data['promo_text_block'] = new_promo_block
        new_main_text = processor.regenerate_main_report_text(
            _active_tpl,
            self.report_results_data,
            new_promo_block,
            self.report_results_data.get('new_series_text_block', '')
        )

        self.sales_report_tab_ui.update_main_report_text(new_main_text)
        self.notification_manager.show('SUCCESS', 'Laporan Diperbarui', 'Tampilan blok promo telah diperbarui.')
    
    def _get_filtered_promo_group_data(self, template_name: str) -> list:
        """Filter promo_group_data: hanya kembalikan grup yang sesuai template aktif.
        Jika grup tidak punya key 'templates' atau list kosong, anggap tampil di semua template."""
        if not template_name:
            return self.promo_group_data
        return [
            g for g in self.promo_group_data
            if not g.get('templates')  # kosong = semua template
            or template_name in g.get('templates', [])
        ]

    def _import_historical_data(self):
        site_code = self.config_manager.get_config().get('site_code')
        if not site_code:
            QMessageBox.warning(self, "Konfigurasi Dibutuhkan", "Harap atur 'Site Code' dahulu.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih File Data Historis", "", "Excel Files (*.xlsx *.xls)")
        
        if file_path:
            self.progress_dialog = QProgressDialog("Mengimpor data historis...", "Batal", 0, 100, self)
            self.progress_dialog.setWindowTitle("Proses Impor")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.show()

            thread = QThread()
            worker = HistoricalDataWorker(file_path, self.db_manager, site_code)
            worker.moveToThread(thread)
            self.history_worker_thread = thread
            self.history_worker = worker

            thread.started.connect(worker.run)
            worker.progress.connect(self.update_progress)
            worker.finished.connect(self._handle_historical_import_finished)
            worker.error.connect(self._handle_historical_import_error)

            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            
            thread.start()

    def _handle_historical_import_finished(self, message):
        self.progress_dialog.close()
        QMessageBox.information(self, "Impor Selesai", message)
        if self.bscd_tab_ui.isVisible() and self.report_results_data:
            custom_tw = getattr(self, 'bscd_tw_custom_date', None)
            bscd_data = self.report_results_data.get('processor').get_bscd_data(self.db_manager, self.config_manager, custom_tw_date=custom_tw)
            self.bscd_tab_ui.update_view(bscd_data)
            
    def _handle_historical_import_error(self, error_message):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Error Impor", f"Gagal mengimpor data:\n{error_message}")

    def start_google_sheet_upload(self):
        sheet_id = self.config_manager.get_config().get('google_sheet_id', '').strip()
        if not sheet_id:
            QMessageBox.warning(self, "Konfigurasi Belum Lengkap", "Harap isi 'Google Sheet ID' di menu Konfigurasi.")
            return

        if self.original_payments_df is None or self.original_transactions_df is None:
            QMessageBox.warning(self, "Data Tidak Ditemukan", "Tidak ada data untuk di-upload.")
            return
            
        # Cek apakah thread masih ada dan valid secara aman
        if hasattr(self, 'gsheet_thread') and self.gsheet_thread is not None:
            try:
                if self.gsheet_thread.isRunning():
                    self.notification_manager.show('WARNING', 'Tunggu', 'Proses upload sebelumnya masih berjalan...')
                    return
            except RuntimeError:
                self.gsheet_thread = None

        self.upload_progress_dialog = QProgressDialog("Memulai upload...", "Batal", 0, 100, self)
        self.upload_progress_dialog.setWindowTitle("Upload Google Sheet")
        self.upload_progress_dialog.setWindowModality(Qt.WindowModal)
        self.upload_progress_dialog.setMinimumDuration(0)
        self.upload_progress_dialog.show()

        self.gsheet_thread = QThread()
        self.gsheet_worker = GoogleSheetWorker(
            payments_df=self.original_payments_df,
            transactions_df=self.original_transactions_df,
            sheet_id=sheet_id
        )
        self.gsheet_worker.moveToThread(self.gsheet_thread)
        
        self.gsheet_thread.started.connect(self.gsheet_worker.run)
        
        self.gsheet_worker.progress.connect(self._update_gsheet_progress)
        self.gsheet_worker.finished.connect(self._handle_gsheet_upload_finished)
        self.gsheet_worker.error.connect(self._handle_gsheet_upload_error)
        
        # Cleanup aman: quit thread lalu bersihkan setelah thread benar-benar selesai
        # Gunakan thread.finished (bukan worker.finished) agar cleanup tidak berjalan
        # saat thread masih sibuk memproses signal worker.
        self.gsheet_worker.finished.connect(self.gsheet_thread.quit)
        self.gsheet_worker.error.connect(self.gsheet_thread.quit)
        self.gsheet_thread.finished.connect(self._reset_gsheet_thread)
        
        # Tombol Batal: set flag cancel pada worker, JANGAN pakai terminate()
        # terminate() memotong thread secara paksa dan merusak state Python/Qt
        self.upload_progress_dialog.canceled.connect(self._cancel_gsheet_upload)
        
        self.gsheet_thread.start()

    def _cancel_gsheet_upload(self):
        """Permintaan cancel yang aman: set flag, jangan terminate()."""
        if hasattr(self, 'gsheet_worker') and self.gsheet_worker is not None:
            try:
                self.gsheet_worker.cancel_requested = True
                logging.info("[GSheet] Cancel requested by user.")
            except RuntimeError:
                pass
        self._close_upload_dialog()

    def _update_gsheet_progress(self, p, m):
        """Update dialog progress dengan aman."""
        try:
            if hasattr(self, 'upload_progress_dialog') and self.upload_progress_dialog and \
               self.upload_progress_dialog.isVisible():
                self.upload_progress_dialog.setValue(p)
                self.upload_progress_dialog.setLabelText(m)
        except RuntimeError:
            pass

    def _close_upload_dialog(self):
        """Tutup dialog upload dengan aman."""
        try:
            if hasattr(self, 'upload_progress_dialog') and self.upload_progress_dialog and \
               self.upload_progress_dialog.isVisible():
                self.upload_progress_dialog.close()
        except RuntimeError:
            pass

    def _reset_gsheet_thread(self):
        """Membersihkan thread dengan aman SETELAH thread benar-benar selesai (dipanggil dari thread.finished)."""
        try:
            if hasattr(self, 'gsheet_worker') and self.gsheet_worker is not None:
                self.gsheet_worker.deleteLater()
                self.gsheet_worker = None
        except RuntimeError:
            pass
        
        try:
            if hasattr(self, 'gsheet_thread') and self.gsheet_thread is not None:
                self.gsheet_thread.deleteLater()
                self.gsheet_thread = None
        except RuntimeError:
            pass
        
        logging.info("[GSheet] Thread cleanup complete.")
    
    def _handle_gsheet_upload_finished(self, message):
        self._close_upload_dialog()
        self.notification_manager.show('SUCCESS', 'Upload Berhasil', message)

    def _handle_gsheet_upload_error(self, error_message):
        """Menangani error upload dan menampilkan pesan yang jelas."""
        self._close_upload_dialog()
        logging.error(f"Upload GSheet Error Handler: {error_message}")
        self.notification_manager.show('ERROR', 'Gagal Upload', error_message)
    
    def _check_for_updates_manual(self):
        self.notification_manager.show('INFO', 'Pengecekan Versi', 'Menghubungi server pembaruan...')
        self.manual_version_thread = QThread()
        self.manual_version_worker = VersionWorker(VERSION_URL)
        self.manual_version_worker.moveToThread(self.manual_version_thread)

        self.manual_version_thread.started.connect(self.manual_version_worker.run)
        self.manual_version_worker.finished.connect(self._handle_manual_update_check_finished)
        self.manual_version_worker.error.connect(self._handle_update_check_error)
        self.manual_version_worker.finished.connect(self.manual_version_thread.quit)
        self.manual_version_worker.finished.connect(self.manual_version_worker.deleteLater)
        self.manual_version_thread.finished.connect(self.manual_version_thread.deleteLater)
        self.manual_version_thread.start()
    
    def _handle_manual_update_check_finished(self, version_data):
        latest_version = version_data.get("latest_version")
        if latest_version and latest_version > self.app_version:
            self._handle_update_check_finished(version_data)
        else:
            QMessageBox.information(self, "Versi Terbaru", f"Anda sudah menggunakan versi terbaru ({self.app_version}).")
    
    def _check_for_updates(self):
        self.version_thread = QThread()
        self.version_worker = VersionWorker(VERSION_URL)
        self.version_worker.moveToThread(self.version_thread)

        self.version_thread.started.connect(self.version_worker.run)
        self.version_worker.finished.connect(self._handle_update_check_finished)
        self.version_worker.error.connect(self._handle_update_check_error)
        self.version_worker.finished.connect(self.version_thread.quit)
        self.version_worker.finished.connect(self.version_worker.deleteLater)
        self.version_thread.finished.connect(self.version_thread.deleteLater)
        self.version_thread.start()

    def _handle_update_check_finished(self, version_data):
        latest_version = version_data.get("latest_version")
        if latest_version and latest_version > self.app_version:
            auto_update_enabled = self.config_manager.get_config().get('auto_update', False)
            download_file_id = version_data.get("download_file_id")
            
            if auto_update_enabled and download_file_id:
                self.notification_manager.show('INFO', 'Pembaruan Ditemukan', f"Mengunduh pembaruan versi {latest_version} di latar belakang...")
                self._start_update_download(download_file_id, silent=True)
                return

            release_notes = version_data.get("release_notes", "Tidak ada catatan rilis.")
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setWindowTitle("Pembaruan Tersedia!")
            msg_box.setText(f"<b>Versi {latest_version} tersedia!</b>")
            msg_box.setInformativeText(f"Catatan rilis:\n{release_notes}")
            download_button = msg_box.addButton("Unduh & Install", QMessageBox.AcceptRole)
            later_button = msg_box.addButton("Nanti Saja", QMessageBox.RejectRole)
            msg_box.exec_()
            
            if msg_box.clickedButton() == download_button:
                # Jaga kompatibilitas ke belakang: jika tidak ada file ID, arahkan ke browser
                if not download_file_id:
                    download_url = version_data.get("download_url")
                    if download_url:
                        import webbrowser
                        webbrowser.open(download_url)
                else:
                    self._start_update_download(download_file_id)

    def _start_update_download(self, drive_id, silent=False):
        self.silent_update = silent
        if not silent:
            # Buat progress dialog
            self.update_progress_dialog = QProgressDialog("Mengunduh pembaruan...", "Batal", 0, 100, self)
            self.update_progress_dialog.setWindowTitle("Unduh Pembaruan")
            self.update_progress_dialog.setWindowModality(Qt.ApplicationModal)
            self.update_progress_dialog.setMinimumDuration(0)
            self.update_progress_dialog.setValue(0)
            self.update_progress_dialog.canceled.connect(lambda: self.update_worker_thread.quit()) # Handle batal
        
        # Path sementara untuk executable baru
        self.update_temp_path = os.path.join(tempfile.gettempdir(), "Repotin_Update.exe")
        
        # Mulai worker
        self.update_worker_thread = QThread()
        self.update_worker = FileDownloadWorker(drive_id, self.update_temp_path)
        self.update_worker.moveToThread(self.update_worker_thread)
        
        self.update_worker_thread.started.connect(self.update_worker.run)
        self.update_worker.progress.connect(self._on_update_download_progress)
        self.update_worker.finished.connect(self._on_update_download_finished)
        self.update_worker.error.connect(self._on_update_download_error)
        
        self.update_worker.finished.connect(self.update_worker_thread.quit)
        self.update_worker.finished.connect(self.update_worker.deleteLater)
        self.update_worker_thread.finished.connect(self.update_worker_thread.deleteLater)
        self.update_worker_thread.start()

    def _on_update_download_progress(self, percent):
        if hasattr(self, 'silent_update') and not self.silent_update and hasattr(self, 'update_progress_dialog'):
            self.update_progress_dialog.setValue(percent)

    def _on_update_download_error(self, error_msg):
        if hasattr(self, 'silent_update') and not self.silent_update and hasattr(self, 'update_progress_dialog'):
            self.update_progress_dialog.close()
        self.notification_manager.show('ERROR', 'Pembaruan Gagal', f"Gagal mengunduh pembaruan:\n{error_msg}")

    def _on_update_download_finished(self, local_path):
        if hasattr(self, 'silent_update') and not self.silent_update and hasattr(self, 'update_progress_dialog'):
            self.update_progress_dialog.close()
        
        if getattr(self, 'silent_update', False):
            self.notification_manager.show('SUCCESS', 'Pembaruan Siap', 'Pembaruan berhasil diunduh. Aplikasi akan merestart otomatis dalam beberapa detik...')
            QTimer.singleShot(3000, self._apply_update)
        else:
            reply = QMessageBox.question(
                self, "Pembaruan Siap",
                "Pembaruan berhasil diunduh. Aplikasi harus di-restart untuk menerapkan pembaruan.\n\nRestart sekarang?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._apply_update()

    def _apply_update(self):
        # Pastikan file unduhan ada
        if not os.path.exists(self.update_temp_path):
            self.notification_manager.show('ERROR', 'Error', "File update tidak ditemukan.")
            return

        import subprocess
        current_exe = sys.executable
        
        # Jika bukan aplikasi frozen (jalan dari script Python), kita tidak bisa melakukan swap exe.
        if not getattr(sys, 'frozen', False):
            self.notification_manager.show('INFO', 'Mode Developer', 
                f"Aplikasi dijalankan lewat script Python.\nFile update (.exe) telah diunduh ke:\n{self.update_temp_path}")
            return
            
        # Buat script batch yang robust:
        # 1. Tunggu proses Repotin benar-benar mati (taskkill + loop cek)
        # 2. Copy new exe menimpa old exe
        # 3. Delay sebelum launch agar PyInstaller punya waktu ekstrak _MEI baru
        bat_path = os.path.join(tempfile.gettempdir(), "repotin_updater.bat")
        exe_name = os.path.basename(current_exe)   # misal "Repotin.exe"
        current_pid = os.getpid()

        script_content = f"""@echo off
setlocal

echo [Updater] Menunggu proses {exe_name} (PID {current_pid}) ditutup...

rem Tunggu hingga proses dengan PID spesifik benar-benar tidak ada
:wait_loop
tasklist /FI "PID eq {current_pid}" 2>nul | find /I "{current_pid}" >nul
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto wait_loop
)

echo [Updater] Proses lama sudah tutup. Menimpa executable...
ping 127.0.0.1 -n 3 >nul

copy /Y "{self.update_temp_path}" "{current_exe}"
if errorlevel 1 (
    echo [Updater] GAGAL menimpa file. Coba jalankan sebagai Administrator.
    pause
    exit /b 1
)

echo [Updater] Copy berhasil. Menunggu sejenak sebelum restart...
ping 127.0.0.1 -n 4 >nul

echo [Updater] Memulai ulang {exe_name}...
start "" "{current_exe}"

echo [Updater] Membersihkan file sementara...
del "{self.update_temp_path}" 2>nul
del "%~f0"
exit /b 0
"""
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Jalankan updater batch secara terpisah (DETACHED agar tidak ikut exit), lalu exit app ini
        subprocess.Popen(
            f'cmd /c "{bat_path}"',
            shell=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        QApplication.quit()

    def _handle_update_check_error(self, error_message):
        logging.warning(f"Gagal mengecek pembaruan: {error_message}")

    # --- METHOD BARU: IMPORT MASTER DATA ---
    def import_master_excel_action(self):
        """
        Menangani logika UI untuk import master data.
        Dilengkapi peringatan keamanan (Safety Check).
        """
        # 1. Safety Check / Warning Dialog
        warning_msg = (
            "Fitur ini akan <b>MENGGANTI TOTAL</b> referensi Master Produk (Size/Series) di database.\n\n"
            "Pastikan file Excel Anda memiliki urutan kolom:\n"
            "1. Article Code\n"
            "2. Article Name\n"
            "3. Size (L/R)\n"
            "4. Type\n"
            "5. Series\n"
            "6. Brand\n\n"
            "Apakah Anda yakin ingin melanjutkan?"
        )
        
        reply = QMessageBox.question(
            self, 
            "Konfirmasi Update Master", 
            warning_msg,
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return

        # 2. File Dialog (Filter Excel Only)
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Pilih File Master Excel", 
            "", 
            "Excel Files (*.xlsx *.xls)"
        )
        
        if file_path:
            # 3. Proses Import
            # Tampilkan loading karena baca Excel bisa agak lama
            progress = QProgressDialog("Membaca & Memperbarui Master Data...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            QApplication.processEvents()
            
            # Panggil Backend
            success, message = self.db_manager.import_master_attributes_from_excel(file_path)
            
            progress.close()
            
            if success:
                QMessageBox.information(self, "Sukses", message)
                # Opsional: Jika Sales Report sedang terbuka, refresh otomatis
                if hasattr(self, 'report_results_data') and self.report_results_data:
                    self.refresh_report_data()
            else:
                QMessageBox.critical(self, "Gagal", message)

    def _load_report_templates(self, default_template_name=None):
        """Mengisi Combo Box Template dari file JSON."""
        try:
            import json
            from utils.constants import REPORT_TEMPLATE_FILE
            
            combo = self.sales_report_tab_ui.main_report_section.template_combo
            
            # Simpan current text jika tidak ada default yang diminta, agar user tidak kehilangan pilihan saaat auto-refresh
            if default_template_name is None:
                default_template_name = combo.currentText()
                
            combo.blockSignals(True)
            combo.clear()
            
            if os.path.exists(REPORT_TEMPLATE_FILE):
                with open(REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                    templates = json.load(f)
                    # Masukkan nama template ke combo box
                    for name in templates.keys():
                        combo.addItem(name)
            else:
                combo.addItem("Default Template") # Fallback
            
            # Kembalikan ke pilihan sebelumnya atau pilihan baru
            if default_template_name:
                idx = combo.findText(default_template_name)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    
            combo.blockSignals(False)
            
            # Memicu update preview (opsional) dengan memanggil handler
            self._on_template_changed()
            
        except Exception as e:
            logging.error(f"Gagal load template: {e}")

    def _on_template_changed(self):
        """Dipanggil saat user memilih template berbeda."""
        # Jika data sudah ada (sudah pernah refresh), regenerate reportnya saja tanpa query DB ulang
        if hasattr(self, 'report_results_data') and self.report_results_data:
            processor = self.report_results_data.get('processor')
            if processor:
                template_name = self.sales_report_tab_ui.main_report_section.template_combo.currentText()
                filtered_prefs = self._get_filtered_new_series_prefs(template_name)
                
                # Regenerate new_series_block untuk template aktif (grup berbeda per template)
                day_trx = self.report_results_data.get('day_trx')
                day_net = self.report_results_data.get('day_net', 0)
                mtd_nett_sales = self.report_results_data.get('mtd_nett_sales', 0)
                
                if day_trx is not None:
                    new_series_outputs = processor.regenerate_new_series_outputs(
                        day_trx, day_net, mtd_nett_sales, filtered_prefs
                    )
                    self.report_results_data.update(new_series_outputs)
                    new_series_block = new_series_outputs.get('new_series_text_block', '')
                else:
                    new_series_block = self.report_results_data.get('new_series_text_block', '')
                
                # Regenerate promo_block untuk template aktif (grup promo berbeda per template)
                merged_promo_df = self.report_results_data.get('merged_promo_df')
                day_net = self.report_results_data.get('day_net', 0)
                mtd_nett_sales = self.report_results_data.get('mtd_nett_sales', 0)
                if merged_promo_df is not None:
                    new_promo_block = processor.regenerate_promo_block_text(
                        merged_promo_df, self.selected_promos_for_report, day_net, mtd_nett_sales,
                        promo_metrics=self.promo_metrics_config,
                        promo_groups=self._get_filtered_promo_group_data(template_name)
                    )
                    self.report_results_data['promo_text_block'] = new_promo_block
                else:
                    new_promo_block = self.report_results_data.get('promo_text_block', '')
                
                # Update text block
                new_text = processor.regenerate_main_report_text(
                    template_name, 
                    self.report_results_data, 
                    new_promo_block, 
                    new_series_block
                )
                
                # Update UI
                self.sales_report_tab_ui.update_main_report_text(new_text)
                # Simpan text baru ke results data
                self.report_results_data['main_report_text'] = new_text
            else:
                # Fallback: Refresh full
                self.refresh_report_data()

    # =========================================================
    # DIALOG FILTER ARTIKEL & PROMO (BUILT-IN FIX)
    # =========================================================
    def open_article_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QCheckBox, QDialogButtonBox
        
        # 1. Ambil Master Data dari DB
        master_map = self.db_manager.get_product_size_map()
        master_articles = list(master_map.keys()) if master_map else []
        
        # 2. Ambil Transaksi saat ini
        raw_articles = []
        if hasattr(self, 'processed_transactions_df') and not self.processed_transactions_df.empty:
            raw_articles = self.processed_transactions_df['Article Name'].dropna().unique().tolist()
            
        all_articles = sorted(list(set(master_articles + raw_articles)))
        
        if not all_articles:
            QMessageBox.warning(self, "Data Kosong", "Belum ada data Artikel. Silakan load database.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Pilih Artikel (New Series)")
        dialog.setMinimumSize(350, 450)
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        
        for art in all_articles:
            item = QListWidgetItem(art)
            if art in self.selected_articles_for_report:
                item.setSelected(True)
            list_widget.addItem(item)
            
        cb_group = QCheckBox("Gabungkan item dengan nama mirip (Berdasarkan Database/Master)")
        cb_group.setChecked(self.is_article_view_grouped)
        
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Simpan & Terapkan")
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        
        layout.addWidget(QLabel("Pilih artikel untuk dipantau di tabel kontribusi:"))
        layout.addWidget(list_widget)
        layout.addWidget(cb_group)
        layout.addWidget(btns)
        
        if dialog.exec_() == QDialog.Accepted:
            self.selected_articles_for_report = [item.text() for item in list_widget.selectedItems()]
            self.is_article_view_grouped = cb_group.isChecked()
            
            # Simpan ke CSV (article_preferences.csv)
            try:
                pref_dir = os.path.dirname(ARTICLE_PREFS_FILE)
                os.makedirs(pref_dir, exist_ok=True)
                df = pd.DataFrame({COL_ARTICLE_NAME: self.selected_articles_for_report})
                df.to_csv(ARTICLE_PREFS_FILE, index=False)
                logging.info(f"Artikel tersimpan ke {ARTICLE_PREFS_FILE}: {len(self.selected_articles_for_report)} item")
            except Exception as e:
                logging.warning(f"Gagal simpan article_preferences.csv: {e}")
            
            self.settings.setValue("is_article_grouped", self.is_article_view_grouped)
            self.settings.sync()
            
            # Terapkan langsung ke layar
            self.refresh_report_data()

    def open_promo_dialog(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox, QMessageBox, QLabel, QAbstractItemView
        import logging
        
        promo_list = []
        if hasattr(self, 'processed_transactions_df') and not self.processed_transactions_df.empty:
            df = self.processed_transactions_df
            
            # 1. Cari kolom promo secara dinamis (mengatasi huruf besar/kecil/underscore)
            promo_col = None
            for col in df.columns:
                if str(col).lower().strip() in ['promotion name', 'promotion_name']:
                    promo_col = col
                    break
            
            if promo_col:
                # 2. Ekstrak dan bersihkan data secara aman
                # Konversi semua ke string lalu hilangkan spasi depan/belakang
                promos = df[promo_col].astype(str).str.strip()
                
                # Filter out kata-kata yang mengindikasikan kosong ('nan', 'none', dll)
                valid_promos = promos[~promos.str.lower().isin(['', 'nan', 'none', 'null', '<na>'])]
                
                # Ambil daftar unik dan urutkan
                promo_list = sorted(valid_promos.unique().tolist())
            else:
                logging.warning(f"Kolom Promo tidak ditemukan. Kolom yang tersedia: {df.columns.tolist()}")
                
        if not promo_list:
            QMessageBox.warning(self, "Data Tidak Tersedia", "Tidak ada data promosi di database pada periode ini.")
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle("Pilih Promosi")
        dialog.setMinimumSize(350, 400)
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        
        # 3. Masukkan ke dalam UI List
        for promo in promo_list:
            item = QListWidgetItem(promo)
            # Tandai jika sebelumnya sudah terpilih
            if promo in self.selected_promos_for_report:
                item.setSelected(True)
            list_widget.addItem(item)
            
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Simpan & Terapkan")
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        
        layout.addWidget(QLabel("Pilih promosi untuk di-highlight pada laporan:"))
        layout.addWidget(list_widget)
        layout.addWidget(btns)
        
        if dialog.exec_() == QDialog.Accepted:
            # Simpan pilihan user
            self.selected_promos_for_report = [item.text() for item in list_widget.selectedItems()]
            
            # Simpan permanen ke file konfigurasi aplikasi
            if hasattr(self, 'settings'):
                self.settings.setValue("selected_promos", self.selected_promos_for_report)
            
            # Langsung perbarui data di layar
            self.refresh_report_data()
                    
# --- CLASS BARU: DIALOG STARTUP OPTION ---
class StartupChoiceDialog(QDialog):
    def __init__(self, has_db_data=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mulai Aplikasi")
        self.setFixedSize(450, 280)
        self.choice = None # 'import' atau 'db'
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        lbl = QLabel("<b>Bagaimana Anda ingin memulai hari ini?</b>")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 16px; margin-bottom: 10px;")
        layout.addWidget(lbl)
        
        # Tombol 1: Import Baru
        self.btn_import = QPushButton("📁  Olah Data Baru (Import CSV)")
        self.btn_import.setStyleSheet("""
            QPushButton { 
                background-color: #3498db; color: white; 
                font-weight: bold; font-size: 14px; padding: 12px; 
                border-radius: 8px; text-align: left; padding-left: 30px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.btn_import.clicked.connect(self._choose_import)
        layout.addWidget(self.btn_import)
        
        # Tombol 2: Gunakan Database
        self.btn_db = QPushButton("🗄️  Lanjut Analisa (Data Database)")
        self.btn_db.setStyleSheet("""
            QPushButton { 
                background-color: #27ae60; color: white; 
                font-weight: bold; font-size: 14px; padding: 12px; 
                border-radius: 8px; text-align: left; padding-left: 30px;
            }
            QPushButton:hover { background-color: #219150; }
            QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
        """)
        self.btn_db.clicked.connect(self._choose_db)
        
        if not has_db_data:
            self.btn_db.setEnabled(False)
            self.btn_db.setText("🗄️  Database Kosong (Import Dulu)")
            
        layout.addWidget(self.btn_db)
        
        # Cancel
        layout.addStretch()
        btn_cancel = QPushButton("Batal")
        btn_cancel.setFlat(True)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel, alignment=Qt.AlignCenter)
    
    def _choose_import(self):
        self.choice = 'import'
        self.accept()

    def _choose_db(self):
        self.choice = 'db'
        self.accept()

# --- CLASS BARU: DIALOG PILIH TANGGAL DATABASE ---
class DatabaseDateSelectionDialog(QDialog):
    def __init__(self, min_date_str, max_date_str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Rentang Data")
        self.setFixedSize(400, 200)
        
        layout = QVBoxLayout(self)
        
        info = QLabel(f"Data tersedia di Database:\n{min_date_str} s/d {max_date_str}")
        info.setStyleSheet("color: #7f8c8d; font-style: italic; margin-bottom: 10px;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        form_layout = QHBoxLayout()
        
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-7)) # Default 7 hari lalu
        
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        
        # Set range maksimum sesuai DB
        if min_date_str and max_date_str:
            q_min = QDate.fromString(min_date_str, "yyyy-MM-dd")
            q_max = QDate.fromString(max_date_str, "yyyy-MM-dd")
            if q_min.isValid() and q_max.isValid():
                self.start_date.setDateRange(q_min, q_max)
                self.end_date.setDateRange(q_min, q_max)
                self.start_date.setDate(q_min) # Default ambil semua jika user mau
                self.end_date.setDate(q_max)

        form_layout.addWidget(QLabel("Dari:"))
        form_layout.addWidget(self.start_date)
        form_layout.addWidget(QLabel("Sampai:"))
        form_layout.addWidget(self.end_date)
        
        layout.addLayout(form_layout)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
    
    def get_dates(self):
        return self.start_date.date(), self.end_date.date()
    
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # ── Cegah aplikasi dibuka lebih dari satu instance (Windows Named Mutex) ──
    import ctypes
    _MUTEX_NAME = "Global\\ReportinApp_SingleInstance_Mutex"
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    _last_error   = ctypes.windll.kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183

    if _last_error == ERROR_ALREADY_EXISTS:
        QMessageBox.warning(
            None,
            "Aplikasi Sudah Berjalan",
            "Aplikasi sudah berjalan!\n\n"
            "Hanya satu instance yang diizinkan.\n"
            "Cek taskbar atau system tray.",
            QMessageBox.Ok
        )
        sys.exit(0)
    # ─────────────────────────────────────────────────────────────────────────
    
    config_dir = os.path.join(BASE_DIR, 'config')
    data_dir = os.path.join(BASE_DIR, 'data')
    
    config = ConfigManager()
    db_manager = DatabaseManager()
    order_db_manager = OrderDBManager()

    is_authorized, message = is_device_authorized(config)
    
    if not is_authorized:
        QMessageBox.critical(None, "Akses Ditolak", message)
        sys.exit(1)
    
    if not config.has_user_agreed_eula():
        agreement_dialog = AgreementDialog()
        result = agreement_dialog.exec_()
        if result == QDialog.Accepted:
            config.set_eula_agreed(True)
        else:
            sys.exit(0)
    
    # 1. Tentukan folder style menggunakan BASE_DIR
    style_folder = os.path.join(BASE_DIR, "assets", "styles")
    
    # 2. Ambil tema yang tersimpan
    saved_theme = config.get_config().get('theme', 'light')
    
    # 3. Tentukan file yang tepat
    if saved_theme == 'dark':
        qss_file = os.path.join(style_folder, "dark_style.qss")
    else:
        qss_file = os.path.join(style_folder, "style.qss")

    # 4. Terapkan style
    try:
        if os.path.exists(qss_file):
            with open(qss_file, "r", encoding='utf-8') as f:
                app.setStyleSheet(f.read())
            logging.info(f"Style startup berhasil dimuat: {os.path.basename(qss_file)}")
        else:
            logging.warning(f"File style startup tidak ditemukan di: {qss_file}")
    except Exception as e:
        logging.error(f"Gagal memuat style saat startup: {e}")



    # Splash screen logic refactored for smoother GIF playback
    splash = AnimatedSplashScreen(SPLASH_IMAGE_PATH)
    splash.show()
    
    # We use a loop of rapid processEvents to allow the GIF to start playing immediately
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)

    splash.showMessage("Memuat konfigurasi dan aset...")
    for _ in range(10):
        app.processEvents()

    # Create the main window (this heavily blocks the thread)
    start_time = time.time()
    main_window = ReportingApp(config_manager=config, db_manager=db_manager, order_db_manager=order_db_manager)
    
    # Pad out the remaining time up to 3000ms, constantly processing events to keep GIF moving
    while (time.time() - start_time) < 3.0:
        app.processEvents()
        time.sleep(0.05)
        
    splash.showMessage("Selesai, Membuka Aplikasi...")
    for _ in range(10):
        app.processEvents()

    main_window.showMaximized()
    main_window.main_dashboard_ui.refresh_data()
    splash.close()
    main_window._check_for_updates()
    
    sys.exit(app.exec_())