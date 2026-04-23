# constants.py
# --- FUNGSI PEMBANTU JALUR ABSOLUT ---
import sys
import os

def get_base_path():
    """
    Mendapatkan jalur dasar absolut (absolute base path) dari aplikasi.
    Berfungsi baik saat dijalankan sebagai skrip Python mentah maupun saat dibekukan (exe) dengan PyInstaller.
    """
    if getattr(sys, 'frozen', False):
        # Jika dijalankan sebagai exe (PyInstaller)
        # Gunakan direktori tempat file exe berada
        return os.path.dirname(sys.executable)
    else:
        # Jika dijalankan sebagai skrip normal
        # Gunakan direktori tempat main_app.py berada (asumsi constants.py ada di utils/)
        # Kita naik satu level dari folder 'utils' untuk ke root
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

BASE_DIR = get_base_path()

# Pastikan folder penting ada saat runtime (terutama untuk file exe PyInstaller)
for folder_name in ['config', 'data', 'assets', os.path.join('assets', 'styles')]:
    folder_path = os.path.join(BASE_DIR, folder_name)
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path)
        except Exception as e:
            print(f"Gagal membuat direktori {folder_path}: {e}")

LOG_FILE_PATH = os.path.join(BASE_DIR, 'data', 'app_log.txt')
REPORT_TEMPLATE_FILE = os.path.join(BASE_DIR, 'config', 'report_templates.json')
EDSPAYED_DATA_FILE = os.path.join(BASE_DIR, 'config', 'edspayed_data.json')
PLACEHOLDER_FILE = os.path.join(BASE_DIR, 'config', 'placeholders.json')
WASTE_RECIPES_FILE = os.path.join(BASE_DIR, 'config', 'waste_recipes.json')
TODO_FILE_PATH = os.path.join(BASE_DIR, 'data', 'todos.json')
NOTES_FILE_PATH = os.path.join(BASE_DIR, 'data', 'notes.json')
MINUM_DATA_FILE = os.path.join(BASE_DIR, 'data', 'minum_data.json')

# --- [DOWNLOADER] ID file manifest.json di Google Drive ---
# Langkah: Upload manifest.json ke Google Drive → Share (Anyone with link) →
# Salin ID dari URL: drive.google.com/file/d/[ID INI]/view
# Lalu ganti string di bawah dengan ID tersebut.
MANIFEST_DRIVE_ID = "1elnS3CEPL48sVJg7l1ebLTzBgXiEX4EL"
# --- [UBAH: Hapus atau abaikan Sheet Names lama] ---
# Sheet names ini mungkin tidak lagi relevan untuk loading file, 
# tapi bisa dibiarkan jika digunakan sebagai 'key' dalam dictionary hasil.
PAYMENTS_SHEET = 'Payments'
TRANSACTIONS_SHEET = 'Transactions'

# --- [TAMBAH: Konstanta untuk Penanganan CSV] ---
# Opsi delimiter yang akan dicoba oleh Worker
CSV_DELIMITERS = [',', ';', '\t'] 

# Format tanggal yang diharapkan (untuk fallback parsing)
# Sesuaikan dengan format output dari sistem POS Anda (SBD)
DATE_FMT_DMY = '%d/%m/%Y'       # Contoh: 25/12/2024
DATE_FMT_YMD = '%Y-%m-%d'       # Contoh: 2024-12-25
DATE_FMT_DATETIME = '%Y-%m-%d %H:%M:%S' # Contoh: 2024-12-25 14:30:00
# ---------------------------------------------------

# File Names
TARGET_FILE_NAME = os.path.join(BASE_DIR, "config", "target_bulanan.csv")
ARTICLE_PREFS_FILE = os.path.join(BASE_DIR, "config", "article_preferences.csv")
NEW_SERIES_PREFS_FILE = os.path.join(BASE_DIR, "config", "new_series_preferences.json")
PROMO_PREFS_FILE = os.path.join(BASE_DIR, "config", "promo_group_preferences.json")
SPLASH_IMAGE_PATH = os.path.join(BASE_DIR, "assets", "images", "splashnime.gif")
APP_ICON_PATH = os.path.join(BASE_DIR, "assets", "images", "repotin.ico")
SITE_DATA_FILE = os.path.join(BASE_DIR, "config", "site_data.json")
CONFIG_FILE_NAME = os.path.join(BASE_DIR, "config", "app_settings.ini")
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, 'config', 'client_secret.json')
TOKEN_FILE = os.path.join(BASE_DIR, 'config', 'token.json')
SITE_LIST_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTZfbICmtpc1dfOVOJuJy2or1NoB2BIEMhwbPHg2Y6tDdK2Vk3OfRyQIjV0ba6_Am040vh9WkZVTFPH/pub?gid=299900014&single=true&output=csv"

# --- [UBAH: Update Versi Aplikasi] ---
VERSION_URL = "https://drive.google.com/uc?export=download&id=1Jy7_CodkCJu4wCCo-6lu3D3OTCwrwT5o"
APP_VERSION = "5.0.7"
# ---------------------------------------------------

# MOP Codes
MOP_CODE_GOBIZ = 'ZQ36'
MOP_CODE_GRAB = 'ZQ24'
MOP_CODE_SHOPEEFOOD = 'ZH30'
OJOL_MOP_CODES = [MOP_CODE_GOBIZ, MOP_CODE_GRAB, MOP_CODE_SHOPEEFOOD]

FNB_ORDER_MOP_CODES = [
    'ZP51', # CashPoint(PoinRwd)
    'ZQ71', # Midtrans VA
    'ZQ65', # MOBILE Shopeepay
    'ZQ66', # MOBILE OVO
    'ZQ72', # Midtrans CC
    'ZQ67', # MOBILE GOPAY
    'ZQ68', # Voucher Rfund Mobile
]

# Product/Merchandise Keywords
VALID_MERCHANDISE_FOR_CUPS = ['Large', 'Regular', 'Cup Hot Coffee', 'Cup Cold Coffee', 'Small', 'Limited Menu', 'Pop Can']
LARGE_CUP_KEYWORDS = ['Large']
LIMITED_MENU_KEYWORDS = ['Limited Menu']
POP_CAN_KEYWORDS = ['Pop Can']
REGULAR_CUP_KEYWORDS = ['Regular', 'Cup Cold Coffee', 'Cup Hot Coffee', 'Small']
TOPPING_KEYWORD = 'Topping'
OUAST_KEYWORD = 'Korean Street Food'

# Default Texts
DEFAULT_MARQUEE_TEXT = "  Selamat datang di REPOT.IN!  "
EMPTY_DATA_MESSAGE = "Sepi amaaat yaakk :("
NO_DATA_TO_PROCESS_FILTERED = "Tidak ada data untuk diproses setelah filter."
NO_DATA_FOR_SECTION = "Tidak ada data."
ERROR_DATA_NOT_AVAILABLE = "Error: Data tidak tersedia"

# Column Names 
# PENTING: Pastikan header di file CSV Anda sama persis dengan ini.
# Jika CSV menggunakan "trx_date" tapi di sini "Created Date", aplikasi akan error.
COL_RECEIPT_NO = 'Receipt No'
COL_CREATED_DATE = 'Created Date'
COL_AMOUNT = 'Amount'
COL_MOP_NAME = 'MOP Name'
COL_MOP_CODE = 'MOP Code'
COL_ARTICLE_NAME = 'Article Name'
COL_NET_PRICE = 'Net Price'
COL_QUANTITY = 'Quantity'
COL_PROMOTION_NAME = 'Promotion Name'
COL_PROMOTION_AMOUNT = 'Promotion Amount'
COL_SITE_CODE = 'Site Code'
COL_CHANNEL = 'Channel'
COL_MERCHANDISE_NAME = 'Merchandise Name'
COL_PRODUCT_GROUP_NAME = 'Product Group Name'
COL_TARGET = 'Target' 
COL_RUNTEX = 'Runtex' 
PROMO_CALC_BY_ITEM = 'by_item'
PROMO_CALC_BY_RECEIPT = 'by_receipt'
COL_DEPARTMENT_NAME = 'Department Name'
COL_VOID = 'Void'