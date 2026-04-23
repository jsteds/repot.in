import sqlite3
import logging
import os
from utils.constants import BASE_DIR

class OrderDBManager:
    def __init__(self, db_name="order_barang.db", history_db_name="History.db"):
        data_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, db_name)
        self.history_db_path = os.path.join(data_dir, history_db_name)
        self._init_db()

    def get_connection(self, path=None):
        try:
            conn = sqlite3.connect(path or self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logging.error(f"Error connecting to database: {e}")
            return None

    def _init_db(self):
        conn = self.get_connection()
        if not conn: return
        cursor = conn.cursor()
        
        # 1. MASTER BARANG (Inventory/Order)
        cursor.execute('''CREATE TABLE IF NOT EXISTS master_barang (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_code TEXT, site_code TEXT, spec TEXT,
            nama_barang TEXT, kemasan TEXT, isi INTEGER DEFAULT 1,
            satuan TEXT, max_order INTEGER DEFAULT 0, status TEXT DEFAULT 'Aktif'
        )''')

        # 2. CART ORDER
        cursor.execute('''CREATE TABLE IF NOT EXISTS cart_order (
            id_barang INTEGER PRIMARY KEY, qty_order INTEGER
        )''')

        # 3. ORDER HISTORY
        cursor.execute('''CREATE TABLE IF NOT EXISTS order_history (
            order_id TEXT PRIMARY KEY, site_code TEXT, created_date TEXT,
            created_time TEXT, total_items INTEGER, status TEXT
        )''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT,
            article_code TEXT, nama_barang TEXT, qty INTEGER, uom TEXT
        )''')
        
        conn.commit()
        conn.close()

        # Migrate data from History.db if order_barang is empty but History.db has these tables
        self._migrate_from_history()

    def _migrate_from_history(self):
        """
        Migrates existing data from History.db to order_barang.db if running for the first time.
        """
        if not os.path.exists(self.history_db_path):
            return

        conn_new = self.get_connection()
        if not conn_new: return
        
        # Check if master_barang is empty in the new DB
        cur_new = conn_new.cursor()
        cur_new.execute("SELECT COUNT(*) FROM master_barang")
        count = cur_new.fetchone()[0]
        
        if count == 0:
            logging.info("Migrating Order Barang data from History.db...")
            conn_old = self.get_connection(self.history_db_path)
            if conn_old:
                try:
                    cur_old = conn_old.cursor()
                    
                    # Migrate master_barang
                    cur_old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='master_barang'")
                    if cur_old.fetchone():
                        cur_old.execute("SELECT * FROM master_barang")
                        rows = cur_old.fetchall()
                        if rows:
                            # Reconstruct columns assuming order: id, article_code, site_code, spec, nama_barang, kemasan, isi, satuan, max_order, status
                            cur_new.executemany('''INSERT INTO master_barang 
                                (id, article_code, site_code, spec, nama_barang, kemasan, isi, satuan, max_order, status)
                                VALUES (?,?,?,?,?,?,?,?,?,?)''', 
                                [tuple(row) for row in rows])

                    # Migrate cart_order
                    cur_old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cart_order'")
                    if cur_old.fetchone():
                        cur_old.execute("SELECT * FROM cart_order")
                        rows = cur_old.fetchall()
                        if rows:
                            cur_new.executemany("INSERT INTO cart_order (id_barang, qty_order) VALUES (?,?)", [tuple(row) for row in rows])

                    # Migrate order_history
                    cur_old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_history'")
                    if cur_old.fetchone():
                        cur_old.execute("SELECT * FROM order_history")
                        rows = cur_old.fetchall()
                        if rows:
                            cur_new.executemany("INSERT INTO order_history (order_id, site_code, created_date, created_time, total_items, status) VALUES (?,?,?,?,?,?)", [tuple(row) for row in rows])

                    # Migrate order_items
                    cur_old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_items'")
                    if cur_old.fetchone():
                        cur_old.execute("SELECT * FROM order_items")
                        rows = cur_old.fetchall()
                        if rows:
                            cur_new.executemany("INSERT INTO order_items (id, order_id, article_code, nama_barang, qty, uom) VALUES (?,?,?,?,?,?)", [tuple(row) for row in rows])

                    conn_new.commit()
                    logging.info("Migration successful.")
                except Exception as e:
                    logging.error(f"Migration error: {e}")
                    conn_new.rollback()
                finally:
                    conn_old.close()
        
        conn_new.close()

    # ==========================================
    # ORDER BARANG METHODS
    # ==========================================
    def get_all_specs(self):
        conn = self.get_connection(); 
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT spec FROM master_barang WHERE spec != '' ORDER BY spec")
            return [r[0] for r in cur.fetchall()]
        finally: conn.close()

    def get_master_barang(self, spec_filter=None, include_discontinued=False):
        conn = self.get_connection(); 
        if not conn: return []
        try:
            cur = conn.cursor()
            query = "SELECT * FROM master_barang"
            conds = []
            params = []
            if not include_discontinued: conds.append("status = 'Aktif'")
            if spec_filter and spec_filter != "ALL": 
                conds.append("spec = ?"); params.append(spec_filter)
            
            if conds: query += " WHERE " + " AND ".join(conds)
            query += " ORDER BY nama_barang"
            
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        finally: conn.close()

    def add_or_update_master_item(self, data):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM master_barang WHERE article_code = ?", (data.get('article_code'),))
            row = cur.fetchone()
            if row: 
                cur.execute('''UPDATE master_barang SET 
                    site_code=?, spec=?, nama_barang=?, kemasan=?, isi=?, satuan=?, max_order=?, status='Aktif'
                    WHERE article_code=?''',
                    (data.get('sites', ''), data.get('spec', ''), data.get('article_description', ''), 
                     data.get('packages', ''), data.get('contain', 1), data.get('uom', ''), 
                     data.get('max_order', 0), data.get('article_code', '')))
            else: 
                cur.execute('''INSERT INTO master_barang 
                    (article_code, site_code, spec, nama_barang, kemasan, isi, satuan, max_order)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (data.get('article_code', ''), data.get('sites', ''), data.get('spec', ''), 
                     data.get('article_description', ''), data.get('packages', ''), 
                     data.get('contain', 1), data.get('uom', ''), data.get('max_order', 0)))
            conn.commit(); return True
        except Exception as e: logging.error(f"Master Item Error: {e}"); return False
        finally: conn.close()
        
    def delete_master_item(self, article_code):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute("DELETE FROM master_barang WHERE article_code=?", (article_code,))
            conn.commit(); return True
        finally: conn.close()
    
    def get_all_units(self):
        conn = self.get_connection();
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT satuan FROM master_barang WHERE satuan IS NOT NULL AND satuan != '' ORDER BY satuan")
            return [r[0] for r in cur.fetchall() if r[0]]
        finally: conn.close()

    def get_all_sites(self):
        conn = self.get_connection()
        if not conn: return ["F001"]
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT site_code FROM master_barang WHERE site_code IS NOT NULL AND site_code != '' ORDER BY site_code")
            return [r[0] for r in cur.fetchall() if r[0]] or ["F001"]
        finally: conn.close()

    def get_all_specs(self):
        conn = self.get_connection()
        if not conn: return ["CHATIME"]
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT spec FROM master_barang WHERE spec IS NOT NULL AND spec != '' ORDER BY spec")
            return [r[0] for r in cur.fetchall() if r[0]] or ["CHATIME"]
        finally: conn.close()

    def get_all_packages(self):
        conn = self.get_connection()
        if not conn: return ["EA"]
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT kemasan FROM master_barang WHERE kemasan IS NOT NULL AND kemasan != '' ORDER BY kemasan")
            return [r[0] for r in cur.fetchall() if r[0]] or ["EA"]
        finally: conn.close()


    def get_summary_stats(self):
        """Returns a dict with counts: total, aktif, non_aktif, per_site."""
        conn = self.get_connection()
        if not conn: return {}
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM master_barang")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM master_barang WHERE status='Aktif'")
            aktif = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM master_barang WHERE status='Non-Aktif'")
            non_aktif = cur.fetchone()[0]
            cur.execute("SELECT site_code, COUNT(*) FROM master_barang GROUP BY site_code ORDER BY COUNT(*) DESC")
            per_site = {r[0]: r[1] for r in cur.fetchall()}
            return {'total': total, 'aktif': aktif, 'non_aktif': non_aktif, 'per_site': per_site}
        except: return {}
        finally: conn.close()

    def update_item_order_status(self, article_code, is_active):
        conn = self.get_connection();
        if not conn: return False
        try:
            status = 'Aktif' if is_active else 'Non-Aktif'
            conn.cursor().execute("UPDATE master_barang SET status=? WHERE article_code=?", (status, article_code))
            conn.commit(); return True
        except Exception as e: logging.error(f"Status Update Error: {e}"); return False
        finally: conn.close()

    def reverse_all_statuses(self):
        """Flip all Aktif → Non-Aktif and Non-Aktif → Aktif in one shot."""
        conn = self.get_connection()
        if not conn: return False, "Gagal koneksi ke database."
        try:
            conn.execute("""
                UPDATE master_barang
                SET status = CASE WHEN status = 'Aktif' THEN 'Non-Aktif' ELSE 'Aktif' END
            """)
            conn.commit()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM master_barang WHERE status='Aktif'")
            aktif = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM master_barang WHERE status='Non-Aktif'")
            non_aktif = cur.fetchone()[0]
            return True, f"Status dibalik: {aktif} Aktif, {non_aktif} Non-Aktif."
        except Exception as e:
            logging.error(f"Reverse Status Error: {e}")
            return False, str(e)
        finally: conn.close()

    def import_master_from_excel(self, file_path):
        import pandas as pd
        
        conn = self.get_connection()
        if not conn: return False, "Gagal koneksi ke database."
        try:
            # Check file extension and read accordingly
            if file_path.endswith('.csv'):
                try:
                    df = pd.read_csv(file_path, sep=',')
                    if len(df.columns) < 2:
                        df = pd.read_csv(file_path, sep=';')
                except:
                    df = pd.read_csv(file_path, sep=';')
            else:
                try:
                    import openpyxl
                    df = pd.read_excel(file_path, header=0, engine='openpyxl')
                except ImportError:
                    return False, "Library 'openpyxl' belum terinstall. Silakan restart aplikasi atau hubungi teknisi."
                except Exception as e:
                    # Fallback if openpyxl isn't available or file is malformed
                    df = pd.read_excel(file_path, header=0)
            
            # Map Excel/CSV columns to master_barang columns.
            # Actual CSV headers from Google Sheets:
            # Sites, Spec, Article, Article Description, Lock / Open, Packages, Contain, UOM, Max Order, ...
            
            col_map = {}
            cols_lower = {str(c).lower().strip(): c for c in df.columns}
            
            # Step 1: Exact / priority matches first (most specific)
            for lower_c, orig_c in cols_lower.items():
                if lower_c in ('article', 'article code', 'article no', 'sku', 'kode'):
                    col_map['ac'] = orig_c
                elif lower_c in ('article description', 'description', 'nama barang', 'item description', 'nama'):
                    col_map['desc'] = orig_c
                elif lower_c in ('sites', 'site', 'site code'):
                    col_map['sites'] = orig_c
                elif lower_c in ('spec', 'specification', 'spesifikasi'):
                    col_map['spec'] = orig_c
                elif lower_c in ('packages', 'package', 'pkg', 'kemasan'):
                    col_map['pkg'] = orig_c
                elif lower_c in ('contain', 'contains', 'cont', 'isi', 'isi per kemasan'):
                    col_map['cont'] = orig_c
                elif lower_c in ('uom', 'unit', 'satuan', 'unit of measure'):
                    col_map['uom'] = orig_c
                elif lower_c in ('max order', 'max', 'maksimum', 'max qty'):
                    col_map['max'] = orig_c
            
            # Step 2: Fallback fuzzy matching for columns not yet mapped
            for lower_c, orig_c in cols_lower.items():
                if 'ac' not in col_map and 'site' not in lower_c and 'article' in lower_c and 'desc' not in lower_c:
                    col_map['ac'] = orig_c
                elif 'desc' not in col_map and ('desc' in lower_c or 'nama' in lower_c):
                    col_map['desc'] = orig_c
                elif 'pkg' not in col_map and ('pkg' in lower_c or 'package' in lower_c or 'kemas' in lower_c):
                    col_map['pkg'] = orig_c
                elif 'cont' not in col_map and ('cont' in lower_c or 'isi' in lower_c):
                    col_map['cont'] = orig_c
                elif 'uom' not in col_map and ('uom' in lower_c or 'satuan' in lower_c):
                    col_map['uom'] = orig_c
                elif 'max' not in col_map and 'max' in lower_c:
                    col_map['max'] = orig_c
                
            if 'ac' not in col_map or 'desc' not in col_map:
                # If explicit mapping fails, fallback to positional if at least 4 columns
                if len(df.columns) >= 4:
                    df = df.iloc[:, :9]
                    df.columns = ['Sites', 'Spec', 'Article', 'Description', 'Lock', 'Pkg', 'Cont', 'UOM', 'Max'][:len(df.columns)]
                else:
                    return False, "Format file tidak dikenali. Kolom 'Article' dan 'Description' diperlukan."
            else:
                # Rename for standardizing parsing loop
                rename_dict = {
                    col_map.get('sites'): 'Sites', col_map.get('spec'): 'Spec', 
                    col_map.get('ac'): 'Article', col_map.get('desc'): 'Description',
                    col_map.get('pkg'): 'Pkg', col_map.get('cont'): 'Cont', 
                    col_map.get('uom'): 'UOM', col_map.get('max'): 'Max'
                }
                df = df.rename(columns={k:v for k,v in rename_dict.items() if k is not None})
                
            # Also map Lock column
            for lower_c, orig_c in cols_lower.items():
                if 'lock' in lower_c or 'open' in lower_c:
                    col_map['lock'] = orig_c
                    break
            if col_map.get('lock') and col_map['lock'] not in rename_dict.values():
                if col_map.get('lock') is not None:
                    df = df.rename(columns={col_map['lock']: 'Lock'})
                
            # Clean data
            df['Article'] = df['Article'].astype(str).str.strip()
            df = df.dropna(subset=['Article'])
            df = df[df['Article'] != 'nan']
            # Filter out rows where Article looks like a header or metadata (all-alpha non-code)
            df = df[df['Article'].str.match(r'^[A-Za-z0-9]')].copy()
            
            # Clean duplicates by keeping the last occurrence (override)
            df = df.drop_duplicates(subset=['Article'], keep='last')
                
            cursor = conn.cursor()
            conn.execute("BEGIN TRANSACTION")
            
            for _, row in df.iterrows():
                ac = str(row.get('Article', '')).strip()
                desc = str(row.get('Description', ''))
                site = str(row.get('Sites', 'F001')).upper()
                spec = str(row.get('Spec', 'CHATIME')).upper()
                pkg = str(row.get('Pkg', 'EA'))
                uom = str(row.get('UOM', 'EA'))
                
                try: cont = int(float(row.get('Cont', 1)))
                except: cont = 1
                
                try: mx = int(float(row.get('Max', 0)))
                except: mx = 0
                
                # Determine status from Lock / Open column
                # TRUE / 1 / non-empty = item is open/orderable = Aktif
                # FALSE / 0 / empty = item is locked = Non-Aktif
                lock_val = row.get('Lock', True)
                if isinstance(lock_val, bool):
                    status = 'Aktif' if lock_val else 'Non-Aktif'
                elif isinstance(lock_val, str):
                    lock_str = lock_val.strip().upper()
                    status = 'Non-Aktif' if lock_str in ('FALSE', '0', 'NO', 'TIDAK', 'LOCK', '') else 'Aktif'
                else:
                    try: status = 'Aktif' if bool(float(lock_val)) else 'Non-Aktif'
                    except: status = 'Aktif'
                
                cursor.execute("SELECT id FROM master_barang WHERE article_code = ?", (ac,))
                if cursor.fetchone():
                    cursor.execute('''UPDATE master_barang SET 
                        site_code=?, spec=?, nama_barang=?, kemasan=?, isi=?, satuan=?, max_order=?, status=?
                        WHERE article_code=?''',
                        (site, spec, desc, pkg, cont, uom, mx, status, ac))
                else:
                    cursor.execute('''INSERT INTO master_barang 
                        (article_code, site_code, spec, nama_barang, kemasan, isi, satuan, max_order, status)
                        VALUES (?,?,?,?,?,?,?,?,?)''',
                        (ac, site, spec, desc, pkg, cont, uom, mx, status))
            
            conn.commit()
            return True, f"Sukses! {len(df)} data master barang berhasil diimpor/diperbarui."
            
        except Exception as e:
            conn.rollback()
            logging.error(f"Import Order Master Error: {e}")
            return False, f"Gagal mengimpor file: {e}"
        finally:
            conn.close()
        
    # --- CART METHODS ---
    def get_cart_items(self):
        conn = self.get_connection(); 
        if not conn: return []
        try:
            cur = conn.cursor()
            query = '''SELECT c.id_barang, m.article_code, m.nama_barang, m.satuan, m.isi, c.qty_order 
                       FROM cart_order c JOIN master_barang m ON c.id_barang = m.id'''
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]
        finally: conn.close()

    def add_to_cart(self, item_id, qty):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute("INSERT OR REPLACE INTO cart_order (id_barang, qty_order) VALUES (?, ?)", (item_id, qty))
            conn.commit(); return True
        finally: conn.close()

    def remove_from_cart(self, item_id):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute("DELETE FROM cart_order WHERE id_barang=?", (item_id,))
            conn.commit(); return True
        finally: conn.close()
        
    def clear_cart(self):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            conn.cursor().execute("DELETE FROM cart_order")
            conn.commit(); return True
        finally: conn.close()
        
    def update_cart_qty(self, item_id, qty):
        return self.add_to_cart(item_id, qty)

    # --- HISTORY METHODS ---
    def save_order(self, order_data, cart_items):
        conn = self.get_connection(); 
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO order_history (order_id, site_code, created_date, created_time, total_items, status) VALUES (?,?,?,?,?,?)",
                        (order_data['order_id'], order_data['site_code'], order_data['created_date'], order_data['created_time'], order_data['total_items'], 'Saved'))
            items = []
            for item in cart_items:
                items.append((order_data['order_id'], item.get('article_code'), item['nama_barang'], item['qty_order'], item['satuan']))
            cur.executemany("INSERT INTO order_items (order_id, article_code, nama_barang, qty, uom) VALUES (?,?,?,?,?)", items)
            conn.commit(); return True
        except Exception as e: logging.error(f"Save Order Error: {e}"); conn.rollback(); return False
        finally: conn.close()
        
    def get_order_history(self):
        conn = self.get_connection();
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM order_history ORDER BY created_date DESC, created_time DESC")
            return [dict(r) for r in cur.fetchall()]
        finally: conn.close()
        
    def get_order_items(self, order_id):
        conn = self.get_connection();
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
            return [dict(r) for r in cur.fetchall()]
        finally: conn.close()
