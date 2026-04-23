# modules/workers.py
import pandas as pd
from PyQt5.QtCore import QObject, pyqtSignal
import logging
import os
import requests
import json
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from datetime import datetime
import time

# --- PERBAIKAN: Import Path yang Benar dari Constants ---
from utils.constants import (
    PAYMENTS_SHEET, TRANSACTIONS_SHEET, 
    CLIENT_SECRET_FILE, TOKEN_FILE  # <--- Import Path Kredensial
)

class FileWorker(QObject):
    # Worker ini untuk file Excel (.xlsx). 
    # Jika Anda menggunakan CSV, logika utama ada di CsvImportWorker di main_app.py
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object, object)
    error = pyqtSignal(str)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.progress.emit(10, f"Membaca data '{PAYMENTS_SHEET}'...")
            payments_df = pd.read_excel(self.file_path, sheet_name=PAYMENTS_SHEET, engine='openpyxl')
            logging.info(f"Sheet '{PAYMENTS_SHEET}' berhasil dibaca, {len(payments_df)} baris.")
            
            self.progress.emit(50, f"Membaca data '{TRANSACTIONS_SHEET}'...")
            transactions_df = pd.read_excel(self.file_path, sheet_name=TRANSACTIONS_SHEET, engine='openpyxl')
            logging.info(f"Sheet '{TRANSACTIONS_SHEET}' berhasil dibaca, {len(transactions_df)} baris.")
            
            self.progress.emit(85, "Memvalidasi data dasar...")
            if payments_df.empty or transactions_df.empty:
                logging.warning(f"Salah satu DataFrame kosong.")
            
            self.progress.emit(100, "Selesai!")
            self.finished.emit(payments_df, transactions_df)
            
        except Exception as e:
            logging.error(f"Error di FileWorker saat memproses '{self.file_path}': {e}", exc_info=True)
            self.error.emit(str(e))
            
class HistoricalDataWorker(QObject):
    """Worker untuk membaca dan memproses file Excel data historis secara fleksibel."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path, db_manager, expected_site_code):
        super().__init__()
        self.file_path = file_path
        self.db_manager = db_manager
        self.expected_site_code = expected_site_code

    def run(self):
        try:
            self.progress.emit(10, "Membaca file Excel historis...")
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext == '.xlsx':
                excel_engine = 'openpyxl'
            elif ext == '.xls':
                excel_engine = 'xlrd'
            else:
                excel_engine = None
            df = pd.read_excel(self.file_path, engine=excel_engine)

            self.progress.emit(30, "Mencocokkan dan memvalidasi kolom...")
            
            column_map = {
                'tanggal': ['Date', 'tanggal', 'Trans Date'], 
                'site_code': ['Site', 'Store Code', 'site_code'],
                'net_sales': ['Net Sales', 'Nett Sales', 'net_sales', 'Sales'], 
                'tc': ['TC', 'tc'],
                'large_cups': ['Large', 'LC', 'large_cups'],
                'toping': ['Topping', 'TP', 'toping'],
                'ouast_sales': ['OUAST', 'K-Food', 'ouast_sales', 'Ouast/ Foods AT'] 
            }
            
            rename_dict = {}
            found_cols = []
            for db_col, possible_names in column_map.items():
                for name in possible_names:
                    if name in df.columns:
                        rename_dict[name] = db_col
                        found_cols.append(db_col)
                        break
            
            if len(found_cols) != len(column_map):
                missing = [db_col for db_col in column_map if db_col not in found_cols]
                raise ValueError(f"Kolom esensial berikut tidak ditemukan: {', '.join(missing)}")

            df = df[list(rename_dict.keys())].rename(columns=rename_dict)

            self.progress.emit(50, "Membersihkan dan memformat data...")
            df['tanggal'] = pd.to_datetime(df['tanggal'], errors='coerce').dt.date

            def clean_numeric(series):
                return pd.to_numeric(
                    series.astype(str).str.replace(r'[^\d.]', '', regex=True),
                    errors='coerce'
                ).fillna(0)

            numeric_cols = ['net_sales', 'tc', 'large_cups', 'toping', 'ouast_sales']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = clean_numeric(df[col])

            if not df['site_code'].astype(str).eq(self.expected_site_code).all():
                raise ValueError(f"File berisi data untuk site selain '{self.expected_site_code}'. Impor dibatalkan.")

            records = df.to_dict('records')
            
            self.progress.emit(70, "Menyimpan data ke database...")
            self.db_manager.upsert_daily_history(records)
            
            self.progress.emit(100, "Selesai!")
            self.finished.emit(f"Berhasil mengimpor dan menyimpan {len(records)} baris data historis.")

        except Exception as e:
            logging.error(f"Error di HistoricalDataWorker: {e}", exc_info=True)
            self.error.emit(str(e))
            
class GoogleSheetWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, payments_df, transactions_df, sheet_id, client_secret_path=None):
        super().__init__()
        self.payments_df = payments_df.copy()
        if 'Tanggal' in self.payments_df.columns:
            self.payments_df['Tanggal'] = pd.to_datetime(self.payments_df['Tanggal'], errors='coerce').dt.date
        
        self.transactions_df = transactions_df.copy()
        if 'Created Date' in self.transactions_df.columns:
            self.transactions_df['Created Date'] = pd.to_datetime(self.transactions_df['Created Date'], errors='coerce').dt.date
        
        self.sheet_id = sheet_id
        self.client_secret_path = client_secret_path if client_secret_path else CLIENT_SECRET_FILE
        self.token_path = TOKEN_FILE
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']
        self.cancel_requested = False  # Flag cancel aman (tanpa terminate())

    def _get_credentials(self):
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)
            except Exception as e:
                logging.warning(f"Token file invalid, will re-auth: {e}")
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.progress.emit(15, "Refreshing access token...")
                try:
                    creds.refresh(Request())
                except Exception:
                    logging.warning("Refresh token failed. Deleting token file and asking for re-login.")
                    if os.path.exists(self.token_path):
                        os.remove(self.token_path)
                    creds = None
            
            if not creds:
                self.progress.emit(10, "Awaiting user authorization in browser...")
                os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
                if not os.path.exists(self.client_secret_path):
                    raise FileNotFoundError(f"File kredensial tidak ditemukan di: {self.client_secret_path}")
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_path, self.scopes)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        return creds
    
    def _find_latest_date(self, date_strings: list):
        latest_date = None
        formats_to_try = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]
        
        for date_str in reversed(date_strings): 
            if not date_str or str(date_str).isalpha(): 
                continue
            for fmt in formats_to_try:
                try:
                    clean_date_str = str(date_str).split(" ")[0]
                    current_date = datetime.strptime(clean_date_str, fmt).date() 
                    if latest_date is None or current_date > latest_date:
                        latest_date = current_date
                    break 
                except ValueError:
                    continue 
        return latest_date
    
    def _upload_in_chunks(self, worksheet, data, chunk_size=500):
        """Helper untuk mengupload data dalam potongan-potongan kecil."""
        total_rows = len(data)
        for i in range(0, total_rows, chunk_size):
            chunk = data[i:i + chunk_size]
            try:
                # Convert chunk to list of lists
                values = chunk.astype(str).values.tolist()
                worksheet.append_rows(values, value_input_option='USER_ENTERED')
                time.sleep(1) # Delay kecil antar chunk untuk menghindari rate limit
            except Exception as e:
                logging.error(f"Gagal mengupload chunk {i}-{i+len(chunk)}: {e}")
                raise e # Lempar error agar ditangkap di method pemanggil

    def _process_sheet(self, gc, spreadsheet, sheet_name, dataframe, date_col_name_df, date_col_name_gsheet, start_progress):
        self.progress.emit(start_progress, f"Mengecek sheet '{sheet_name}'...")
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logging.warning(f"Worksheet '{sheet_name}' tidak ditemukan. Membuat baru...")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            worksheet.append_row(dataframe.columns.tolist())
        
        all_col1_values = worksheet.col_values(1) 
        last_row_index = len(list(filter(None, all_col1_values)))
        
        latest_date = None
        if last_row_index > 1: 
            header = worksheet.row_values(1)
            try:
                header_lower = [h.lower() for h in header]
                target_col_lower = date_col_name_gsheet.lower()
                
                if target_col_lower in header_lower:
                    date_col_index = header_lower.index(target_col_lower) + 1
                    
                    # Ambil beberapa baris terakhir untuk cek tanggal
                    check_rows = 50 
                    start_check = max(2, last_row_index - check_rows)
                    date_values = worksheet.col_values(date_col_index)[start_check-1:]
                    latest_date = self._find_latest_date(date_values) 
                else:
                    logging.warning(f"Kolom '{date_col_name_gsheet}' tidak ditemukan di sheet '{sheet_name}'.")
            except Exception as e:
                logging.error(f"Error saat mencari tanggal terakhir di sheet '{sheet_name}': {e}")

        df_to_upload = dataframe
        if latest_date:
            logging.info(f"Tanggal terakhir di '{sheet_name}': {latest_date}")
            df_to_upload = dataframe[dataframe[date_col_name_df] > latest_date]
        else:
            logging.info(f"Upload Full ke '{sheet_name}' (Belum ada data/tanggal tidak ketemu).")

        if not df_to_upload.empty:
            self.progress.emit(start_progress + 5, f"Mengupload {len(df_to_upload)} baris baru ke '{sheet_name}'...")
            
            data_to_append = df_to_upload.copy()
            if date_col_name_df in data_to_append.columns:
                 data_to_append[date_col_name_df] = pd.to_datetime(data_to_append[date_col_name_df]).dt.strftime('%Y-%m-%d')
            
            final_data_to_upload = data_to_append.fillna('').replace('nan', '')
            
            # --- IMPLEMENTASI CHUNKING & DELAY ---
            self._upload_in_chunks(worksheet, final_data_to_upload)
            # -------------------------------------
            
            return len(df_to_upload)
        
        self.progress.emit(start_progress + 20, f"Tidak ada data baru untuk '{sheet_name}'.")
        return 0
    
    def run(self):
        try:
            if self.cancel_requested:
                self.error.emit("Upload dibatalkan oleh pengguna.")
                return
                
            self.progress.emit(5, "Otentikasi Google...")
            credentials = self._get_credentials()
            if not credentials: raise Exception("Otentikasi dibatalkan.")

            if self.cancel_requested:
                self.error.emit("Upload dibatalkan oleh pengguna.")
                return

            self.progress.emit(20, "Menghubungi Spreadsheet...")
            gc = gspread.authorize(credentials)
            
            # --- PERBAIKAN: Tangkap error spesifik saat buka sheet ---
            try:
                spreadsheet = gc.open_by_key(self.sheet_id)
            except gspread.exceptions.APIError as e:
                # Cek jika error 403 (Permission Denied)
                if e.response.status_code == 403:
                    raise PermissionError("Akses Ditolak! Pastikan email Anda sudah diinvite sebagai Editor di Google Sheet ini.")
                else:
                    raise e
            # ---------------------------------------------------------
            
            cnt1 = self._process_sheet(gc, spreadsheet, "Payment Aurora", self.payments_df, 'Tanggal', 'Tanggal', 30)
            time.sleep(2)
            
            if self.cancel_requested:
                self.error.emit("Upload dibatalkan oleh pengguna.")
                return
            
            cnt2 = self._process_sheet(gc, spreadsheet, "Detail Aurora", self.transactions_df, 'Created Date', 'Created Date', 60)

            self.progress.emit(100, "Selesai!")
            self.finished.emit(f"Sukses upload: {cnt1} Payments, {cnt2} Transactions.")
        
        except PermissionError as e:
             # Pesan ini akan ditangkap oleh _handle_gsheet_upload_error di atas
             self.error.emit(str(e)) 
        except gspread.exceptions.WorksheetNotFound as e:
            self.error.emit(f"Error: Sheet tidak ditemukan.\nPastikan nama sheet '{e.args[0]}' ada di Google Sheet.")
        except Exception as e:
            logging.error(f"Google Sheet upload failed: {e}", exc_info=True)
            # Sertakan detail error asli agar user tahu kenapa
            self.error.emit(f"Terjadi kesalahan teknis:\n{str(e)}")

class VersionWorker(QObject):
    """Worker untuk mengecek versi terbaru aplikasi dari URL online."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=5)
            response.raise_for_status()
            if not response.text.strip():
                self.error.emit("File versi di server kosong atau tidak valid.")
                return
            version_data = response.json()
            self.finished.emit(version_data)
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Gagal terhubung ke server pembaruan: {e}")
        except json.JSONDecodeError:
            self.error.emit("Gagal membaca data versi (format JSON tidak valid).")
        except Exception as e:
            self.error.emit(f"Terjadi error tak terduga: {e}")

class CsvImportWorker(QObject):
    finished = pyqtSignal(object, object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, trans_path, pay_path):
        super().__init__()
        self.trans_path = trans_path
        self.pay_path = pay_path

    @staticmethod
    def _read_file_smart(file_path):
        """
        Membaca file secara cerdas: deteksi otomatis apakah JSON atau CSV.

        Aurora API sekarang mengembalikan content-type: application/json
        dan isi file adalah JSON array ([{...}, {...}]), bukan CSV.
        Fungsi ini menangani kedua format secara transparan.
        """
        with open(file_path, 'rb') as f:
            raw_head = f.read(512)

        # Deteksi JSON: isi file diawali '[' (setelah strip whitespace/BOM)
        text_head = raw_head.lstrip(b'\xef\xbb\xbf').lstrip()  # strip BOM + spasi
        is_json = text_head.startswith(b'[') or text_head.startswith(b'{')

        if is_json:
            logging.info(f"[CsvImportWorker] Detected JSON format: {os.path.basename(file_path)}")
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            data = json.loads(content)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # Mungkin wrapped dalam key tertentu
                for key in ('data', 'records', 'results', 'items'):
                    if key in data and isinstance(data[key], list):
                        df = pd.DataFrame(data[key])
                        break
                else:
                    df = pd.DataFrame([data])
            else:
                raise ValueError(f"Format JSON tidak dikenali di: {os.path.basename(file_path)}")

            # Normalisasi nama kolom JSON → nama kolom PascalCase yang diharapkan aplikasi
            # Mapping: snake_case JSON API → PascalCase nama kolom internal
            col_rename = {
                # AH Commodity (Transactions)
                'created_date': 'Created Date',
                'created_time': 'Created Time',
                'order_no': 'Order No',
                'receipt_no': 'Receipt No',
                'invoice_reference': 'Invoice Reference',
                'void': 'Void',
                'site_code': 'Site Code',
                'site_description': 'Site Description',
                'article_code': 'Article Code',
                'article_name': 'Article Name',
                'quantity': 'Quantity',
                'original_price': 'Original Price',  # PascalCase sesuai save_bulk_raw_data
                'net_price': 'Net Price',
                'promotion_amount': 'Promotion Amount',
                'promotion_code': 'Promotion Code',
                'promotion_name': 'Promotion Name',
                # PENTING: order_type dari JSON Aurora ('Ojol'/'Take Away'/'FnB Order')
                # harus di-map ke 'Channel' agar laporan Ojol vs Instore bekerja!
                'order_type': 'Channel',
                'ah_department_code': 'Department Code',
                'ah_department_name': 'Department Name',
                'ah_commodity_code': 'Commodity Code',
                'ah_commodity_name': 'Commodity Name',
                'ah_merchandise_code': 'Merchandise Code',
                'ah_merchandise_name': 'Merchandise Name',
                'ah_product_group_code': 'Product Group Code',
                'ah_product_group_name': 'Product Group Name',
                # MOP (Payments)
                'amount': 'Amount',
                'mop_code': 'MOP Code',
                'mop_name': 'MOP Name',
            }
            # Hanya rename kolom yang ada di dataframe
            rename_map = {k: v for k, v in col_rename.items() if k in df.columns}
            df = df.rename(columns=rename_map)
            logging.info(f"[CsvImportWorker] JSON parsed: {len(df)} rows, columns: {list(df.columns)}")
            return df
        else:
            # Format CSV biasa
            logging.info(f"[CsvImportWorker] Detected CSV format: {os.path.basename(file_path)}")
            try:
                df = pd.read_csv(file_path, sep=',', encoding='utf-8', encoding_errors='replace')
                if df.shape[1] < 2:
                    df = pd.read_csv(file_path, sep=';', encoding='utf-8', encoding_errors='replace')
            except Exception:
                df = pd.read_csv(file_path, sep=';', encoding='utf-8', encoding_errors='replace')

            # --- Normalisasi kolom CSV legacy (nama kolom berbeda-beda tergantung versi Aurora) ---
            # Mapping: nama lama/alternatif → nama kolom internal yang diharapkan aplikasi
            csv_col_aliases = {
                'Created Date':       ['Tanggal', 'Date', 'Trans Date', 'created_date', 'CREATED DATE'],
                'Created Time':       ['Time', 'Trans Time', 'created_time'],
                'Receipt No':         ['receipt_no', 'Receipt Number', 'No Struk', 'ReceiptNo'],
                'Order No':           ['order_no', 'OrderNo'],
                'Article Name':       ['article_name', 'Item Name', 'Nama Artikel'],
                'Article Code':       ['article_code', 'Item Code'],
                'Quantity':           ['quantity', 'Qty'],
                'Net Price':          ['net_price', 'Nett Price', 'Price'],
                'Original Price':     ['original_price'],  # Harga sebelum diskon
                'Void':               ['void', 'void_status', 'VoidStatus', 'Is Void'],
                'Site Code':          ['site_code', 'Store Code', 'Site'],
                'Department Name':    ['ah_department_name', 'department_name', 'Dept Name'],
                'Merchandise Name':   ['ah_merchandise_name', 'merchandise_name'],
                'Product Group Name': ['ah_product_group_name', 'product_group_name'],
                'Promotion Name':     ['promotion_name'],
                'MOP Code':           ['mop_code', 'MOPCode', 'Payment Code'],
                'MOP Name':           ['mop_name', 'MOPName', 'Payment Name'],
                'Amount':             ['amount', 'Payment Amount'],
                # PENTING: order_type di CSV Aurora = Channel (Ojol / Take Away / FnB Order)
                # Sama seperti mapping di path JSON (baris col_rename di atas)
                'Channel':            ['order_type', 'Order Type', 'Channel Type'],
            }
            for target_col, aliases in csv_col_aliases.items():
                if target_col not in df.columns:
                    for alias in aliases:
                        if alias in df.columns:
                            df = df.rename(columns={alias: target_col})
                            logging.info(f"[CsvImportWorker] CSV alias: '{alias}' → '{target_col}'")
                            break

            logging.info(f"[CsvImportWorker] CSV columns after normalization: {list(df.columns)}")
            return df

    def _infer_channel_from_payments(self, trans_df, pay_df):
        """
        Deduksi kolom 'Channel' dari MOP Name jika CSV tidak punya info channel.
        
        - GoFood / GoPay food-related → 'Ojol'
        - GrabFood / Grab-Food → 'Ojol'
        - SHOPEEFOOD / Shopee Food → 'Ojol'
        - Lainnya → 'Take Away'
        
        Bergabung via Receipt No dari pay_df ke trans_df.
        """
        import re

        # Keyword pattern untuk Ojol MOP
        OJOL_PATTERN = re.compile(
            r'gofood|go-food|go food|gopay.*food|grabfood|grab.food|grab-food|shopeefood|shopee.food',
            re.IGNORECASE
        )

        # Buat mapping receipt_no → channel dari pay_df
        rcp_col_pay = next((c for c in ['Receipt No', 'receipt_no', 'ReceiptNo', 'No Struk'] if c in pay_df.columns), None)
        mop_col = next((c for c in ['MOP Name', 'mop_name', 'MOPName', 'Payment Name'] if c in pay_df.columns), None)

        if rcp_col_pay is None or mop_col is None:
            logging.warning("[CsvImportWorker] Tidak dapat deduksi channel: kolom Receipt No atau MOP Name tidak ditemukan di payment file.")
            return trans_df

        # Ambil MOP Name terdominan per receipt (prioritaskan Ojol)
        def classify_mop(mop_name):
            if pd.isna(mop_name) or str(mop_name).strip() == '':
                return 'Take Away'
            return 'Ojol' if OJOL_PATTERN.search(str(mop_name)) else 'Take Away'

        pay_channel = pay_df[[rcp_col_pay, mop_col]].copy()
        pay_channel['_ch'] = pay_channel[mop_col].apply(classify_mop)
        # Jika ada 1 Ojol MOP dalam receipt → receipt = Ojol (prioritas)
        rcp_channel_map = (
            pay_channel.groupby(rcp_col_pay)['_ch']
            .apply(lambda x: 'Ojol' if 'Ojol' in x.values else 'Take Away')
            .to_dict()
        )

        # Terapkan ke trans_df
        rcp_col_trx = next((c for c in ['Receipt No', 'receipt_no', 'ReceiptNo'] if c in trans_df.columns), None)
        if rcp_col_trx is None:
            logging.warning("[CsvImportWorker] Tidak dapat deduksi channel: kolom Receipt No tidak ditemukan di transactions file.")
            return trans_df

        trans_df = trans_df.copy()
        trans_df['Channel'] = trans_df[rcp_col_trx].map(rcp_channel_map).fillna('Take Away')
        
        ojol_count = (trans_df['Channel'] == 'Ojol').sum()
        take_away_count = (trans_df['Channel'] == 'Take Away').sum()
        logging.info(f"[CsvImportWorker] Channel inferred dari MOP: Ojol={ojol_count} rows, Take Away={take_away_count} rows")
        return trans_df

    def run(self):
        try:
            self.progress.emit(10, "Membaca file Transaksi...")
            trans_df = self._read_file_smart(self.trans_path)

            self.progress.emit(50, "Membaca file Pembayaran...")
            pay_df = self._read_file_smart(self.pay_path)

            self.progress.emit(80, "Memvalidasi data...")
            if trans_df.empty or pay_df.empty:
                raise ValueError("Salah satu file kosong setelah di-parse.")

            # --- Deduksi Channel dari MOP jika CSV tidak punya kolom Channel ---
            # (Saat sync Aurora, kolom Channel sudah terisi dari field order_type)
            channel_col = next((c for c in ['Channel', 'channel', 'Order Type', 'order_type'] if c in trans_df.columns), None)
            channel_is_empty = (
                channel_col is None
                or trans_df[channel_col].astype(str).str.strip().eq('').all()
                or trans_df[channel_col].isna().all()
            )
            if channel_is_empty:
                logging.info("[CsvImportWorker] Kolom Channel kosong/tidak ada → deduksi dari MOP Name...")
                trans_df = self._infer_channel_from_payments(trans_df, pay_df)

            self.progress.emit(100, "Selesai.")
            self.finished.emit(pay_df, trans_df)

        except Exception as e:
            logging.error(f"[CsvImportWorker] Error: {e}", exc_info=True)
            self.error.emit(str(e))


