import sqlite3
import logging
import pandas as pd
from datetime import datetime, date
import os
from utils.constants import (
    BASE_DIR, 
    COL_RECEIPT_NO, COL_CREATED_DATE, COL_AMOUNT, COL_MOP_NAME, 
    COL_ARTICLE_NAME, COL_NET_PRICE, COL_QUANTITY, COL_SITE_CODE,
    COL_VOID, COL_DEPARTMENT_NAME, COL_PRODUCT_GROUP_NAME, COL_MOP_CODE,
    COL_MERCHANDISE_NAME, COL_CHANNEL, COL_PROMOTION_NAME
)

class DatabaseManager:
    def __init__(self, db_name="History.db"):
        data_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, db_name)
        self._init_db()

    def get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            return None

    def _init_db(self):
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        # 1. SUMMARY HARIAN
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_sales (
            tanggal TEXT, site_code TEXT, net_sales REAL, tc INTEGER,
            large_cups INTEGER, toping INTEGER, ouast_sales REAL,
            PRIMARY KEY (tanggal, site_code))''')

        # 2. KAS & TIPS
        cursor.execute('''CREATE TABLE IF NOT EXISTS kas_tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT, jenis TEXT,
            kategori TEXT, nominal REAL, keterangan TEXT, input_by TEXT, site_code TEXT)''')

        # 3. RAW TRANSACTIONS
        cursor.execute('''CREATE TABLE IF NOT EXISTS raw_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            receipt_no TEXT, order_no TEXT,
            created_date TEXT, created_time TEXT, 
            site_code TEXT, article_name TEXT,
            quantity INTEGER, net_price REAL, 
            void_status TEXT, department_name TEXT,
            category_name TEXT, product_group_name TEXT,  
            merchandise_name TEXT, channel TEXT,             
            promotion_name TEXT,
            is_void INTEGER DEFAULT 0
        )''')
        try:
            cursor.execute("ALTER TABLE raw_transactions ADD COLUMN original_price REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Kolom sudah ada

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trx_date ON raw_transactions(created_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trx_site_date ON raw_transactions(site_code, created_date)')

        # 4. RAW PAYMENTS
        cursor.execute('''CREATE TABLE IF NOT EXISTS raw_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, receipt_no TEXT, order_no TEXT,
            payment_date TEXT, mop_code TEXT, mop_name TEXT, amount REAL)''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pay_date ON raw_payments(payment_date)')

        # Migration: Add site_code to raw_payments if not exists
        try:
            cursor.execute("ALTER TABLE raw_payments ADD COLUMN site_code TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists



        # 8. [BARU] PRODUCT REPORTING MASTER (Sesuai Excel User)
        # Columns: A=Code, B=Name, C=Size, D=Type, E=Series, F=Brand
        cursor.execute('''CREATE TABLE IF NOT EXISTS product_reporting_master (
            article_code TEXT PRIMARY KEY,
            article_name TEXT,
            size_category TEXT,  -- L / R / S
            product_type TEXT,   -- Drink / Food
            series TEXT,         -- Golden Pearl / Popcorn
            brand TEXT           -- Chatime
        )''')
        
        # 9. IN-USE MASTER
        cursor.execute('''CREATE TABLE IF NOT EXISTS inuse_master (
            article_code TEXT PRIMARY KEY,
            article_description TEXT,
            gl_account TEXT,
            uom TEXT,
            sloc TEXT,
            cost_ctr TEXT
        )''')
        
        try:
            cursor.execute("ALTER TABLE inuse_master ADD COLUMN is_hidden INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute("ALTER TABLE inuse_master ADD COLUMN custom_group TEXT DEFAULT 'Semua'")
        except sqlite3.OperationalError:
            pass
        
        # 10. BPK HISTORY
        cursor.execute('''CREATE TABLE IF NOT EXISTS bpk_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            tanggal TEXT,
            dokumen_no TEXT,
            rek_lawan TEXT,
            uraian TEXT,
            nominal REAL,
            pdf_path TEXT,
            status TEXT DEFAULT 'Store',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.commit()
        conn.close()

    # ==========================================
    # [BARU] IMPORT MASTER DATA DARI EXCEL USER
    # ==========================================
    def import_master_attributes_from_excel(self, file_path):
        """
        Import Master Data dari Excel secara AMAN.
        Otomatis menghapus duplikat jika ada kode barang ganda di Excel.
        """
        conn = self.get_connection()
        if not conn: return False, "Koneksi Database Gagal"
        
        try:
            # Baca Excel - Tentukan engine berdasarkan ekstensi file
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.xlsx':
                engine = 'openpyxl'
            elif ext == '.xls':
                engine = 'xlrd'
            else:
                engine = None
            df = pd.read_excel(file_path, header=0, engine=engine)
            
            # Validasi Kolom
            if len(df.columns) < 3:
                return False, "Format Excel salah. Pastikan kolom: Code, Name, Size, ..."

            # Normalisasi Nama Kolom
            df = df.iloc[:, :6] 
            df.columns = ['code', 'name', 'size', 'type', 'series', 'brand']
            
            # Bersihkan Data (String & Strip)
            df['code'] = df['code'].astype(str).str.strip()
            df['name'] = df['name'].astype(str).str.strip()
            df['size'] = df['size'].astype(str).str.strip().str.upper()
            
            # --- [FIX UTAMA: HAPUS DUPLIKAT] ---
            # Cek apakah ada kode ganda
            duplicate_count = df.duplicated(subset=['code']).sum()
            if duplicate_count > 0:
                logging.warning(f"Ditemukan {duplicate_count} kode duplikat di file Excel. Mengambil data baris terakhir untuk kode tersebut.")
                # keep='last' berarti jika ada duplikat, yang diambil adalah baris paling bawah di Excel
                df = df.drop_duplicates(subset=['code'], keep='last')
            # -----------------------------------
            
            cursor = conn.cursor()
            conn.execute("BEGIN TRANSACTION")
            
            # 1. Kosongkan Tabel Lama
            cursor.execute("DELETE FROM product_reporting_master")
            
            # 2. Insert Data Baru (Yang sudah bersih)
            data_tuples = []
            for _, row in df.iterrows():
                data_tuples.append((
                    row['code'], row['name'], row['size'], 
                    row['type'], row['series'], row['brand']
                ))
            
            cursor.executemany('''
                INSERT INTO product_reporting_master 
                (article_code, article_name, size_category, product_type, series, brand)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', data_tuples)
            
            conn.commit()
            return True, f"Sukses! {len(data_tuples)} data master berhasil diperbarui (Duplikat dibersihkan: {duplicate_count})."
            
        except Exception as e:
            conn.rollback()
            logging.error(f"Import Master Error: {e}")
            return False, f"Error: {str(e)}"
        finally:
            conn.close()

    def get_product_size_map(self):
        """
        Mengembalikan Dictionary { 'Nama Artikel': 'Size' } untuk mapping cepat di ReportProcessor.
        Contoh: {'POPCORN LT FRAPPE (L)': 'L', 'OSC HZ...': 'R'}
        """
        conn = self.get_connection()
        if not conn: return {}
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT article_name, size_category FROM product_reporting_master")
            rows = cursor.fetchall()
            # Buat Dictionary: Key = Nama, Value = Size
            return {row['article_name']: row['size_category'] for row in rows}
        finally:
            conn.close()

    # ==========================================
    # RAW DATA STORAGE
    # ==========================================
    def save_bulk_raw_data(self, transactions_df, payments_df):
        conn = self.get_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            dates = []
            if COL_CREATED_DATE in transactions_df.columns:
                dates.extend(pd.to_datetime(transactions_df[COL_CREATED_DATE], errors='coerce').dropna().dt.strftime('%Y-%m-%d').unique())
            if 'Tanggal' in payments_df.columns:
                dates.extend(pd.to_datetime(payments_df['Tanggal'], errors='coerce').dropna().dt.strftime('%Y-%m-%d').unique())
            
            dates = sorted(list(set(dates)))
            if not dates: return
            min_date, max_date = dates[0], dates[-1]

            cursor.execute("DELETE FROM raw_transactions WHERE created_date BETWEEN ? AND ?", (min_date, max_date))
            cursor.execute("DELETE FROM raw_payments WHERE payment_date BETWEEN ? AND ?", (min_date, max_date))

            # --- TRANSACTIONS ---
            if not transactions_df.empty:
                df = transactions_df.copy()
                df['db_date'] = pd.to_datetime(df[COL_CREATED_DATE], errors='coerce').dt.strftime('%Y-%m-%d')
                df = df.dropna(subset=['db_date'])
                
                c_void = COL_VOID if COL_VOID else 'Void'
                if c_void in df.columns:
                    df['is_void_flag'] = df[c_void].astype(str).str.lower().apply(lambda x: 1 if x in ['void', 'yes', 'true', 'v'] else 0)
                else: df['is_void_flag'] = 0

                trx_data = []
                for _, row in df.iterrows():
                    net_price = float(row.get(COL_NET_PRICE, 0))
                    # Ambil Original Price (Harga sebelum diskon)
                    orig_price = float(row.get('Original Price', net_price)) 
                    
                    trx_data.append((
                        str(row.get(COL_RECEIPT_NO, '')),
                        str(row.get('Order No', '')),
                        row['db_date'],
                        str(row.get('Created Time', '00:00')),
                        str(row.get(COL_SITE_CODE, '')),
                        str(row.get(COL_ARTICLE_NAME, '')),
                        int(row.get(COL_QUANTITY, 0)),
                        net_price,
                        orig_price, 
                        str(row.get(c_void, '')),
                        str(row.get(COL_DEPARTMENT_NAME, 'Department Name')),
                        str(row.get('Category Name', '')),          # <--- INI YANG SEBELUMNYA HILANG (Item ke-12)
                        str(row.get(COL_PRODUCT_GROUP_NAME, '')), 
                        str(row.get('Merchandise Name', '')), 
                        str(row.get('Channel', '')), 
                        str(row.get(COL_PROMOTION_NAME, '')),
                        int(row.get('is_void_flag', 0))
                    ))
                
                if trx_data:
                    # Statement SQL diperbarui
                    cursor.executemany('''INSERT INTO raw_transactions 
                        (receipt_no, order_no, created_date, created_time, site_code, article_name, 
                        quantity, net_price, original_price, void_status, department_name, category_name, product_group_name, 
                        merchandise_name, channel, promotion_name, is_void) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', trx_data)

            # --- PAYMENTS ---
            if not payments_df.empty:
                df = payments_df.copy()
                if 'Tanggal' in df.columns: df['db_date'] = pd.to_datetime(df['Tanggal'], errors='coerce').dt.strftime('%Y-%m-%d')
                else: df['db_date'] = min_date

                # Determine site_code from transactions if available
                pay_site_code = ''
                if not transactions_df.empty and COL_SITE_CODE in transactions_df.columns:
                    pay_site_code = str(transactions_df[COL_SITE_CODE].iloc[0])
                
                pay_data = []
                for _, row in df.iterrows():
                    pay_data.append((
                        str(row.get(COL_RECEIPT_NO, '')), str(row.get('Order No', '')),
                        row['db_date'], str(row.get(COL_MOP_CODE, '')),
                        str(row.get(COL_MOP_NAME, '')), float(row.get(COL_AMOUNT, 0)),
                        pay_site_code
                    ))
                if pay_data:
                    cursor.executemany('''INSERT INTO raw_payments (receipt_no, order_no, payment_date, mop_code, mop_name, amount, site_code) VALUES (?,?,?,?,?,?,?)''', pay_data)

            conn.commit() 
            logging.info("Raw Data Transaction & Payment berhasil disimpan.")
        except Exception as e:
            logging.error(f"Save Raw Data Error: {e}", exc_info=True)
            conn.rollback()
        finally:
            conn.close()

    # ==========================================
    # DATA RETRIEVAL
    # ==========================================
    def get_transactions_dataframe(self, start_date, end_date, site_code=None):
        import pandas as pd
        conn = self.get_connection()
        if not conn: return pd.DataFrame()
        try:
            if hasattr(start_date, 'toString'): start_date = start_date.toString("yyyy-MM-dd")
            elif hasattr(start_date, 'strftime'): start_date = start_date.strftime("%Y-%m-%d")
            else: start_date = str(start_date)[:10]

            if hasattr(end_date, 'toString'): end_date = end_date.toString("yyyy-MM-dd")
            elif hasattr(end_date, 'strftime'): end_date = end_date.strftime("%Y-%m-%d")
            else: end_date = str(end_date)[:10]
            
            query = "SELECT * FROM raw_transactions WHERE created_date BETWEEN ? AND ? AND is_void = 0"
            params = [start_date, end_date]
            if site_code:
                query += " AND site_code = ?"; params.append(site_code)
            
            df = pd.read_sql_query(query, conn, params=params)
            
            column_mapping = {
                'receipt_no': 'Receipt No', 'created_date': 'Tanggal',
                'created_time': 'Created Time', 'order_no': 'Order No',  # ← tambah
                'article_name': 'Article Name', 'category_name': 'Category Name',
                'product_group_name': 'Product Group Name', 'department_name': 'Department Name',
                'quantity': 'Quantity', 'net_price': 'Net Price', 
                'original_price': 'Original Price',
                'site_code': 'Site Code', 'merchandise_name': 'Merchandise Name',
                'channel': 'Channel', 'promotion_name': 'Promotion Name'
            }
            df.rename(columns=column_mapping, inplace=True)
            if not df.empty and 'Tanggal' in df.columns:
                df['Tanggal'] = pd.to_datetime(df['Tanggal'])
                df['Created Date'] = df['Tanggal'] 
            return df
        finally:
            conn.close()

    def get_payments_dataframe(self, start_date, end_date, site_code=None):
        """
        Mengambil data pembayaran (MOP) dari SQLite dan mengubahnya menjadi Pandas DataFrame.
        Penting untuk laporan Sales by Payment dan Channel Analysis.
        Filter by site_code via JOIN ke raw_transactions jika site_code diberikan.
        """
        import pandas as pd
        conn = self.get_connection()
        if not conn: return pd.DataFrame()
        
        try:
            # Pastikan format tanggal string YYYY-MM-DD
            if hasattr(start_date, 'toString'): start_date = start_date.toString("yyyy-MM-dd")
            elif hasattr(start_date, 'strftime'): start_date = start_date.strftime("%Y-%m-%d")
            else: start_date = str(start_date)[:10]

            if hasattr(end_date, 'toString'): end_date = end_date.toString("yyyy-MM-dd")
            elif hasattr(end_date, 'strftime'): end_date = end_date.strftime("%Y-%m-%d")
            else: end_date = str(end_date)[:10]
            
            params = [start_date, end_date]
            
            if site_code:
                # Filter payments by site_code: prefer direct column, fallback to JOIN
                query = """
                    SELECT 
                        p.receipt_no, 
                        p.order_no, 
                        p.payment_date, 
                        p.mop_code, 
                        p.mop_name, 
                        p.amount 
                    FROM raw_payments p
                    WHERE p.payment_date BETWEEN ? AND ?
                    AND p.site_code = ?
                    AND p.receipt_no IN (
                        SELECT DISTINCT receipt_no FROM raw_transactions 
                        WHERE created_date BETWEEN ? AND ? AND site_code = ? AND is_void = 0
                    )
                """
                params = [start_date, end_date, site_code, start_date, end_date, site_code]
            else:
                query = """
                    SELECT 
                        receipt_no, 
                        order_no, 
                        payment_date, 
                        mop_code, 
                        mop_name, 
                        amount 
                    FROM raw_payments 
                    WHERE payment_date BETWEEN ? AND ?
                """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            # MAPPING: Nama Kolom DB -> Nama Kolom Aplikasi (Sesuai Constants)
            column_mapping = {
                'receipt_no': 'Receipt No',  # COL_RECEIPT_NO
                'payment_date': 'Tanggal',   # ReportProcessor butuh 'Tanggal'
                'mop_code': 'MOP Code',      # COL_MOP_CODE
                'mop_name': 'MOP Name',      # COL_MOP_NAME
                'amount': 'Amount',          # COL_AMOUNT
                'order_no': 'Order No'
            }
            
            df.rename(columns=column_mapping, inplace=True)
            
            # Konversi Tipe Data
            if not df.empty:
                df['Tanggal'] = pd.to_datetime(df['Tanggal'])
                df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
                
            return df
            
        except Exception as e:
            logging.error(f"Gagal load Payments dari DB: {e}")
            return pd.DataFrame()
        finally:
            conn.close()



    # ==========================================
    # METHODS LAIN
    # ==========================================
    def upsert_daily_history(self, summaries):
        conn = self.get_connection(); 
        if not conn: return
        try:
            cursor = conn.cursor()
            for s in summaries:
                tgl = s['tanggal'].strftime('%Y-%m-%d') if isinstance(s['tanggal'], (date, datetime)) else s['tanggal']
                cursor.execute('INSERT OR REPLACE INTO daily_sales (tanggal, site_code, net_sales, tc, large_cups, toping, ouast_sales) VALUES (?,?,?,?,?,?,?)',
                               (tgl, s['site_code'], s['net_sales'], s['tc'], s['large_cups'], s['toping'], s['ouast_sales']))
            conn.commit()
        finally: conn.close()

    def get_history_for_date(self, target_date, site_code):
        conn = self.get_connection(); 
        if not conn: return {}
        try:
            d = target_date.strftime('%Y-%m-%d') if isinstance(target_date, (date, datetime)) else target_date
            # Directly source from daily_sales table as it contains the correctly mapped calculate values
            query = """
                SELECT 
                    net_sales,
                    tc,
                    large_cups,
                    toping,
                    ouast_sales
                FROM daily_sales 
                WHERE tanggal=? AND site_code=?
            """
            res = conn.cursor().execute(query, (d, site_code)).fetchone()
            
            if res:
                 return {
                     'net_sales': res['net_sales'] or 0,
                     'tc': res['tc'] or 0,
                     'large_cups': res['large_cups'] or 0,
                     'toping': res['toping'] or 0,
                     'ouast_sales': res['ouast_sales'] or 0
                 }
            return {}
        finally: conn.close()

    def get_total_sales_for_period(self, start, end, site):
        conn = self.get_connection(); 
        if not conn: return 0
        try:
            # Switch to sourcing from raw_transactions
            res = conn.cursor().execute('SELECT SUM(net_price) as total FROM raw_transactions WHERE site_code=? AND is_void=0 AND created_date BETWEEN ? AND ?',
                                        (site, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))).fetchone()
            return res['total'] if res and res['total'] else 0
        finally: conn.close()
        
    def get_all_kas_tips_transactions(self, site):
        conn = self.get_connection(); 
        if not conn: return []
        try:
            return [dict(r) for r in conn.cursor().execute('SELECT * FROM kas_tips WHERE site_code=? ORDER BY tanggal DESC', (site,)).fetchall()]
        finally: conn.close()

    def add_kas_tips_transaction(self, data):
        if isinstance(data, dict):
            tgl = data.get('tanggal')
            tgl_str = tgl.strftime('%Y-%m-%d') if hasattr(tgl, 'strftime') else str(tgl)
            jns = data.get('tipe_transaksi')
            kat = data.get('tipe_dana')
            nom = data.get('jumlah')
            ket = data.get('deskripsi')
            iby = data.get('diinput_oleh')
            site = data.get('site_code')
        else: return False

        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute('INSERT INTO kas_tips (tanggal, jenis, kategori, nominal, keterangan, input_by, site_code) VALUES (?,?,?,?,?,?,?)',
                                  (tgl_str, jns, kat, nom, ket, iby, site))
            conn.commit(); return True
        finally: conn.close()

    def delete_kas_tips_transaction(self, tid):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute('DELETE FROM kas_tips WHERE id=?', (tid,))
            conn.commit(); return True
        finally: conn.close()
        
    def get_all_inuse_articles(self):
        """Ambil data master khusus In-Use."""
        conn = self.get_connection()
        if not conn: return []
        try:
            query = """
                SELECT 
                    article_code, 
                    article_description, 
                    gl_account,
                    uom,
                    sloc,
                    cost_ctr,
                    COALESCE(is_hidden, 0) as is_hidden,
                    COALESCE(custom_group, 'Semua') as custom_group
                FROM inuse_master
                ORDER BY article_description
            """
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Gagal get_all_inuse_articles dari DB: {e}")
            return []
        finally:
            conn.close()
    
    def batch_import_inuse(self, data_list, overwrite=True):
        """Menyimpan data impor Master In-Use ke tabel inuse_master."""
        conn = self.get_connection()
        if not conn: return False, "Database Error"
        try:
            cursor = conn.cursor()
            conn.execute("BEGIN TRANSACTION")
            
            existing_data = {}
            if overwrite:
                cursor.execute("SELECT article_code, is_hidden, custom_group FROM inuse_master")
                for row in cursor.fetchall():
                    existing_data[row[0]] = {'is_hidden': row[1], 'custom_group': row[2]}
                cursor.execute("DELETE FROM inuse_master")
            
            data_tuples = []
            for d in data_list:
                article_code = str(d.get('article_code', 'N/A'))
                existing_info = existing_data.get(article_code, {})
                is_hid = existing_info.get('is_hidden', 0)
                custom_grp = existing_info.get('custom_group', 'Semua')
                
                data_tuples.append((
                    article_code,
                    str(d.get('article_description', '')),
                    str(d.get('gl_account', '')),
                    str(d.get('uom', '')),
                    str(d.get('sloc', '')),
                    str(d.get('cost_ctr', '')),
                    is_hid,
                    custom_grp
                ))
            
            cursor.executemany('''
                INSERT OR REPLACE INTO inuse_master 
                (article_code, article_description, gl_account, uom, sloc, cost_ctr, is_hidden, custom_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_tuples)
            
            conn.commit()
            return True, f"{len(data_list)} Artikel In-Use berhasil disimpan."
        except Exception as e:
            conn.rollback()
            return False, f"Db error: {e}"
        finally:
            conn.close()

    def toggle_inuse_article_hidden(self, article_code, is_hidden):
        conn = self.get_connection()
        if not conn: return False
        try:
            conn.cursor().execute("UPDATE inuse_master SET is_hidden = ? WHERE article_code = ?", (int(is_hidden), article_code))
            conn.commit()
            return True
        finally:
            conn.close()

    def update_inuse_article_group(self, article_code, new_group):
        conn = self.get_connection()
        if not conn: return False
        try:
            conn.cursor().execute("UPDATE inuse_master SET custom_group = ? WHERE article_code = ?", (new_group, article_code))
            conn.commit()
            return True
        finally:
            conn.close()

    
    # ==========================================
    # UTILS: CHECK DATA AVAILABILITY
    # ==========================================
    def get_available_date_range(self, site_code=None):
        """
        Mengecek range tanggal data yang tersedia di Database.
        Jika site_code diberikan, hanya return range untuk store tersebut.
        Return: (min_date, max_date) atau (None, None) jika kosong.
        """
        conn = self.get_connection()
        if not conn: return None, None
        try:
            cursor = conn.cursor()
            if site_code:
                cursor.execute("SELECT MIN(created_date), MAX(created_date) FROM raw_transactions WHERE is_void = 0 AND site_code = ?", (site_code,))
            else:
                cursor.execute("SELECT MIN(created_date), MAX(created_date) FROM raw_transactions WHERE is_void = 0")
            row = cursor.fetchone()
            if row and row[0] and row[1]:
                return row[0], row[1] # Format string YYYY-MM-DD
            return None, None
        except Exception as e:
            logging.error(f"Gagal cek range tanggal: {e}")
            return None, None
        finally:
            conn.close()

    # ==========================================
    # DASHBOARD METRICS QUERIES
    # ==========================================
    def get_dashboard_metrics(self, start_date, end_date, site_code=None):
        """
        Mengambil semua data agregasi untuk Dashboard:
        1. Peak Hour (pada end_date)
        2. Sales Achievement (End Date & Total Periode)
        3. Forecast
        4. Top Menus
        5. Qty Large & Toppings
        Returns a dictionary with all the data.
        """
        conn = self.get_connection()
        if not conn: return {}
        
        metrics = {
            'peak_hour': [],
            'sales_today': 0,
            'sales_mtd': 0,
            'sales_sly': 0,
            'top_menus': [],
            'qty_large': 0,
            'qty_topping': 0,
            'channel_sales': []   # [{channel, sales, pct}]
        }
        
        try:
            cursor = conn.cursor()
            date_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, (date, datetime)) else str(end_date)
            start_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, (date, datetime)) else str(start_date)
            
            # --- Perhitungan Tanggal SLY (Tahun Lalu) ---
            if isinstance(end_date, (date, datetime)):
                 try:
                     sly_end_date = end_date.replace(year=end_date.year - 1)
                     sly_start_date = start_date.replace(year=start_date.year - 1)
                 except ValueError:
                     # Handle kabisat if needed
                     sly_end_date = end_date - timedelta(days=365)
                     sly_start_date = start_date - timedelta(days=365)
            else:
                 sly_end_date = None
                 sly_start_date = None
                 
            site_filter = ""
            params_today = [date_str]
            params_mtd = [start_str, date_str]
            params_sly = []
            
            if sly_end_date and sly_start_date:
                params_sly = [sly_start_date.strftime('%Y-%m-%d'), sly_end_date.strftime('%Y-%m-%d')]
            
            if site_code:
                site_filter = " AND site_code = ?"
                params_today.append(site_code)
                params_mtd.append(site_code)
                if params_sly: params_sly.append(site_code)
                
            # 1. Peak Hour (Created Time vs Net Sales & Transaction Count for Period)
            query_peak = f"""
                SELECT 
                    substr(created_time, 1, 2) as hour, 
                    sum(net_price) as sales, 
                    count(DISTINCT receipt_no) as tc,
                    SUM(CASE 
                        WHEN product_group_name LIKE '%Ouast%' 
                          OR product_group_name LIKE '%K-Food%' 
                          OR product_group_name LIKE '%Korean Street Food%' 
                          OR category_name LIKE '%Ouast%' 
                          OR category_name LIKE '%Korean Street Food%' 
                        THEN net_price ELSE 0 END) as sales_ouast,
                    SUM(CASE 
                        WHEN product_group_name NOT LIKE '%Ouast%' 
                         AND product_group_name NOT LIKE '%K-Food%' 
                         AND product_group_name NOT LIKE '%Korean Street Food%' 
                         AND category_name NOT LIKE '%Ouast%' 
                         AND category_name NOT LIKE '%Korean Street Food%' 
                        THEN net_price ELSE 0 END) as sales_non_ouast
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                GROUP BY hour
                ORDER BY hour
            """
            cursor.execute(query_peak, params_mtd)
            peak_data = [dict(row) for row in cursor.fetchall()]

            # Fallback jika periode adalah "Hari Ini" dan belum ada data penjualan, tampilkan MTD sebagai default
            today_dt = date.today()
            today_str = today_dt.strftime('%Y-%m-%d')
            if not peak_data and start_str == today_str and date_str == today_str:
                first_day_str = today_dt.replace(day=1).strftime('%Y-%m-%d')
                params_fallback = [first_day_str, today_str]
                if site_code: 
                    params_fallback.append(site_code)
                cursor.execute(query_peak, params_fallback)
                peak_data = [dict(row) for row in cursor.fetchall()]

            metrics['peak_hour'] = peak_data

            # 2. Sales Achievement Today
            query_sales_today = f"""
                SELECT sum(net_price) as total_sales
                FROM raw_transactions
                WHERE created_date = ? AND is_void = 0 {site_filter}
            """
            cursor.execute(query_sales_today, params_today)
            row = cursor.fetchone()
            metrics['sales_today'] = (row['total_sales'] / 1.1) if row and row['total_sales'] else 0

            # 3. Sales MTD (Month to Date / Selected Period)
            query_sales_mtd = f"""
                SELECT sum(net_price) as total_sales
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
            """
            cursor.execute(query_sales_mtd, params_mtd)
            row = cursor.fetchone()
            metrics['sales_mtd'] = (row['total_sales'] / 1.1) if row and row['total_sales'] else 0
            
            # 3.5 Sales SLY (Sales Last Year) for the Selected Period
            if params_sly:
                query_sales_sly = f"""
                    SELECT sum(net_price) as total_sales
                    FROM raw_transactions
                    WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                """
                cursor.execute(query_sales_sly, params_sly)
                row_sly = cursor.fetchone()
                metrics['sales_sly'] = (row_sly['total_sales'] / 1.1) if row_sly and row_sly['total_sales'] else 0

            # 4. Top Selling Menus Today by Quantity (Exclude modifiers/toppings if possible, assuming Category != 'Topping')
            query_top = f"""
                SELECT article_name, sum(quantity) as qty, sum(net_price) as sales
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                AND product_group_name NOT LIKE '%Topping%'
                AND category_name NOT LIKE '%Topping%'
                AND product_group_name NOT LIKE '%Modifier%'
                AND category_name NOT LIKE '%Modifier%'
                AND article_name NOT LIKE '%Ice%'
                AND article_name NOT LIKE '%Sugar%'
                AND article_name NOT LIKE '+%'
                GROUP BY article_name
                ORDER BY qty DESC
                LIMIT 30
            """
            cursor.execute(query_top, params_mtd)
            metrics['top_menus'] = [dict(row) for row in cursor.fetchall()]

            # --- Total Qty MTD for percentage calculation ---
            query_total_qty_mtd = f"""
                SELECT sum(quantity) as total_qty
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
            """
            cursor.execute(query_total_qty_mtd, params_mtd)
            row_total = cursor.fetchone()
            total_qty_mtd = row_total['total_qty'] if row_total and row_total['total_qty'] else 1 # Avoid div by zero
            
            # 5. Qty Large (MTD)
            query_large_mtd = f"""
                SELECT sum(quantity) as qty
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                AND article_name LIKE '%(L)%'
            """
            cursor.execute(query_large_mtd, params_mtd)
            row = cursor.fetchone()
            qty_large_val = row['qty'] if row and row['qty'] else 0
            
            metrics['qty_large'] = qty_large_val
            # 6. Qty Toppings (MTD)
            # Menyesuaikan dengan logika di report_processor yang memeriksa COL_PRODUCT_GROUP_NAME
            query_topping_mtd = f"""
                SELECT sum(quantity) as qty
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                AND product_group_name LIKE '%Topping%'
            """
            cursor.execute(query_topping_mtd, params_mtd)
            row = cursor.fetchone()
            qty_topping_val = row['qty'] if row and row['qty'] else 0
            
            # --- Total Qty Cup (Exclude Topping) untuk Percentages ---
            # Di Sales Report, persentase LTB dihitung dari Total Sold Cup (Large + Reg + Small + Popcan)
            # Karena Qty Large adalah subset dari Total Cup, dan Topping dihitung terhadap Total Cup.
            query_total_cup = f"""
                SELECT sum(quantity) as cup_qty
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                AND product_group_name NOT LIKE '%Topping%'
            """
            cursor.execute(query_total_cup, params_mtd)
            row_cup = cursor.fetchone()
            total_sold_cup = row_cup['cup_qty'] if row_cup and row_cup['cup_qty'] else 1 # Avoid div by zero

            metrics['qty_topping'] = qty_topping_val
            metrics['perc_large'] = round((qty_large_val / total_sold_cup) * 100, 1) if total_sold_cup > 0 else 0
            metrics['perc_topping'] = round((qty_topping_val / total_sold_cup) * 100, 1) if total_sold_cup > 0 else 0

            # 7. Channel Sales (Ojol vs Instore) untuk periode
            query_channel = f"""
                SELECT
                    CASE
                        WHEN LOWER(channel) IN ('instore', 'dine in', 'take away', 'takeaway', '')
                            OR channel IS NULL OR TRIM(channel) = ''
                        THEN 'Instore'
                        ELSE 'Ojol'
                    END AS channel_group,
                    SUM(net_price) as sales
                FROM raw_transactions
                WHERE created_date BETWEEN ? AND ? AND is_void = 0 {site_filter}
                GROUP BY channel_group
            """
            cursor.execute(query_channel, params_mtd)
            channel_rows = [dict(row) for row in cursor.fetchall()]
            total_channel_sales = sum(r['sales'] for r in channel_rows) or 1
            metrics['channel_sales'] = [
                {
                    'channel': r['channel_group'],
                    'sales': r['sales'],
                    'pct': round((r['sales'] / total_channel_sales) * 100, 1)
                }
                for r in channel_rows
            ]

            return metrics
            
        except Exception as e:
            logging.error(f"Failed to fetch dashboard metrics: {e}")
            return metrics
        finally:
            conn.close()

    def get_hourly_comparison_metrics(self, date1_str, date2_str, cutoff_time_str, site_code=None):
        """
        Ambil metrik Sales, TC, AC, Large, Ouast untuk dua tanggal
        dengan batas waktu tepat: created_time <= cutoff_time_str (format 'HH:MM').
        
        Args:
            date1_str: Tanggal periode saat ini (YYYY-MM-DD)
            date2_str: Tanggal periode pembanding (YYYY-MM-DD)
            cutoff_time_str: Batas waktu, misal '14:00' → filter created_time <= '14:00'
            site_code: Kode toko (opsional)
        
        Returns:
            dict: {'current': {sales, tc, ac, large, ouast}, 'compare': {...}}
        """
        conn = self.get_connection()
        if not conn:
            return {'current': None, 'compare': None}
        
        empty_metrics = {'sales': 0, 'tc': 0, 'ac': 0, 'large': 0, 'ouast': 0}
        
        try:
            cursor = conn.cursor()
            site_filter = " AND site_code = ?" if site_code else ""
            
            def fetch_metrics_for_date(date_str):
                """Query metrik untuk satu tanggal dengan cutoff waktu."""
                params = [date_str, cutoff_time_str]
                if site_code:
                    params.append(site_code)
                
                # Sales & TC
                cursor.execute(f"""
                    SELECT 
                        SUM(net_price) as gross_sales,
                        COUNT(DISTINCT receipt_no) as tc,
                        SUM(CASE 
                            WHEN article_name LIKE '%(L)%' THEN quantity 
                            ELSE 0 
                        END) as large_qty,
                        SUM(CASE 
                            WHEN product_group_name LIKE '%Ouast%'
                              OR product_group_name LIKE '%K-Food%'
                              OR product_group_name LIKE '%Korean Street Food%'
                              OR category_name LIKE '%Ouast%'
                              OR category_name LIKE '%Korean Street Food%'
                            THEN net_price ELSE 0 
                        END) as ouast_sales
                    FROM raw_transactions
                    WHERE created_date = ?
                      AND substr(created_time, 1, 5) <= ?
                      AND is_void = 0
                      {site_filter}
                """, params)
                
                row = cursor.fetchone()
                if row:
                    gross = row['gross_sales'] or 0
                    nett = gross / 1.1
                    tc = row['tc'] or 0
                    ac = nett / tc if tc > 0 else 0
                    large = row['large_qty'] or 0
                    ouast = (row['ouast_sales'] or 0) / 1.1
                    return {
                        'sales': nett,
                        'tc': tc,
                        'ac': ac,
                        'large': large,
                        'ouast': ouast
                    }
                return dict(empty_metrics)
            
            current_data = fetch_metrics_for_date(date1_str)
            compare_data = fetch_metrics_for_date(date2_str)
            
            return {
                'current': current_data,
                'compare': compare_data
            }
            
        except Exception as e:
            logging.error(f"get_hourly_comparison_metrics error: {e}", exc_info=True)
            return {'current': dict(empty_metrics), 'compare': dict(empty_metrics)}
        finally:
            conn.close()

    # ==========================================
    # BPK HISTORY METHODS
    # ==========================================
    def save_bpk_history(self, store_code, tanggal, dokumen_no, rek_lawan, uraian, nominal, pdf_path):
        conn = self.get_connection()
        if not conn: return False
        try:
            conn.cursor().execute('''
                INSERT INTO bpk_history (store_code, tanggal, dokumen_no, rek_lawan, uraian, nominal, pdf_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Store')
            ''', (store_code, tanggal, dokumen_no, rek_lawan, uraian, nominal, pdf_path))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to save BPK history: {e}")
            return False
        finally:
            conn.close()
            
    def get_bpk_history(self, store_code=None):
        conn = self.get_connection()
        if not conn: return []
        try:
            cursor = conn.cursor()
            if store_code:
                cursor.execute("SELECT * FROM bpk_history WHERE store_code = ? ORDER BY created_at DESC", (store_code,))
            else:
                cursor.execute("SELECT * FROM bpk_history ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Failed to get BPK history: {e}")
            return []
        finally:
            conn.close()

    def update_bpk_status(self, bpk_id, status):
        conn = self.get_connection()
        if not conn: return False
        try:
            conn.cursor().execute("UPDATE bpk_history SET status = ? WHERE id = ?", (status, bpk_id))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to update BPK status: {e}")
            return False
        finally:
            conn.close()

    def delete_bpk_history(self, bpk_id):
        conn = self.get_connection()
        if not conn: return False
        try:
            conn.cursor().execute("DELETE FROM bpk_history WHERE id = ?", (bpk_id,))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to delete BPK history: {e}")
            return False
        finally:
            conn.close()