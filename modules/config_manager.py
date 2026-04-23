import configparser
import logging
import json
import pandas as pd
import requests
import os
from utils.constants import CONFIG_FILE_NAME, SITE_LIST_URL, SITE_DATA_FILE
from datetime import date

class ConfigManager:
    def __init__(self):
        self.config_file = CONFIG_FILE_NAME
        self.config = configparser.ConfigParser()
        self.site_list = []
        self._load_config()
        self._load_site_list()
    
    def get_recent_files(self):
        """Mengambil daftar file terbaru dari konfigurasi."""
        files_str = self.config.get('DEFAULT', 'recent_files', fallback='[]')
        try:
            return json.loads(files_str)
        except json.JSONDecodeError:
            return []

    def add_recent_file(self, file_path):
        """Menambah file ke daftar terbaru, menjaga agar daftar tidak lebih dari 5."""
        recent_files = self.get_recent_files()
        # Hapus jika sudah ada untuk dipindahkan ke atas
        if file_path in recent_files:
            recent_files.remove(file_path)
        # Tambahkan ke posisi paling atas (indeks 0)
        recent_files.insert(0, file_path)
        # Batasi daftar hanya 5 file
        self.config.set('DEFAULT', 'recent_files', json.dumps(recent_files[:5]))
        self.save_config()
    # --------------------------------------------------------------------
    
    def _load_config(self):
        if not self.config.read(self.config_file, encoding='utf-8'):
            self._create_default_config()
            
    def reread_config(self):
        """
        Membersihkan konfigurasi di memori dan membacanya kembali dari file.
        Ini untuk memastikan aplikasi mendapat data ter-update setelah penyimpanan.
        """
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file)
        logging.info("Configuration has been re-read from disk.")
    # ---------------------------------------------------
    
    def _create_default_config(self):
        self.config['DEFAULT'] = {
            'site_code': '',
            'monthly_targets': json.dumps({str(i): 0 for i in range(1, 13)}),
            'metric_targets': '{}',
            'running_text': 'Selamat datang di Repot.in!',
            'default_template': 'Default Template',
            'eula_agreed': 'false',
            'device_authorized_hash': '',
            'last_known_ip': '',
            'last_known_mac': '',
            'last_validated_date': '',
            'weekday_weight': '1.0',
            'weekend_weight': '1.8604651',
            'chat_it_link': '',
            'auto_update': 'false',
            'visible_tabs': '{}',
        }
        self.save_config()

    def save_config(self):
        """Menulis konfigurasi dari memori ke file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            logging.info("Configuration successfully saved to file.")
            return True
        except Exception as e:
            logging.error(f"Failed to save config file: {e}")
            return False

    def get_config(self):
        # Mengambil konfigurasi umum
        return {
            'site_code': self.config.get('DEFAULT', 'site_code', fallback=''),
            'running_text': self.config.get('DEFAULT', 'running_text', fallback=''),
            'default_template': self.config.get('DEFAULT', 'default_template', fallback='Default Template'),
            'google_sheet_id': self.config.get('DEFAULT', 'google_sheet_id', fallback=''),
            'chat_it_link': self.config.get('DEFAULT', 'chat_it_link', fallback=''),
            'weekday_weight': float(self.config.get('DEFAULT', 'weekday_weight', fallback='1.0')),
            'weekend_weight': float(self.config.get('DEFAULT', 'weekend_weight', fallback='1.8604651')),
            'auto_update': self.config.getboolean('DEFAULT', 'auto_update', fallback=False),
        }

    def get_monthly_targets(self):
        """Membaca target bulanan dari config dan mengembalikan dictionary."""
        targets_str = self.config.get('DEFAULT', 'monthly_targets', fallback='{}')
        try:
            targets_dict = json.loads(targets_str)
            # Pastikan semua 12 bulan ada dan tipenya benar
            return {int(k): int(v) for k, v in targets_dict.items()}
        except (json.JSONDecodeError, TypeError):
            # Jika data korup atau tidak ada, kembalikan default
            return {i: 0 for i in range(1, 13)}

    def get_target_for_month(self, month):
        """Mendapatkan nilai target untuk bulan spesifik (angka 1-12)."""
        targets = self.get_monthly_targets()
        return targets.get(month, 0)

    def save_monthly_targets(self, targets_dict):
        """Menyimpan dictionary target bulanan sebagai JSON string."""
        self.config['DEFAULT']['monthly_targets'] = json.dumps(targets_dict)
        return self.save_config()

    def get_monthly_metric_targets(self, month_year_str):
        """Membaca metric target harian untuk bulan tertentu (format YYYY-MM)."""
        metrics_dict_str = self.config.get('DEFAULT', 'metric_targets', fallback='{}')
        try:
            metrics_dict = json.loads(metrics_dict_str)
            return metrics_dict.get(month_year_str, {})
        except (json.JSONDecodeError, TypeError):
            return {}

    def save_monthly_metric_targets(self, month_year_str, data_dict):
        """Menyimpan metric target harian untuk bulan tertentu (format YYYY-MM)."""
        metrics_dict_str = self.config.get('DEFAULT', 'metric_targets', fallback='{}')
        try:
            metrics_dict = json.loads(metrics_dict_str)
        except (json.JSONDecodeError, TypeError):
            metrics_dict = {}
        
        metrics_dict[month_year_str] = data_dict
        if 'DEFAULT' not in self.config:
            self.config.add_section('DEFAULT')
        self.config['DEFAULT']['metric_targets'] = json.dumps(metrics_dict)
        return self.save_config()
    
    def update_general_config(self, site_code, running_text, default_template, weekday_weight, weekend_weight, google_sheet_id, chat_it_link="", auto_update=False):
        """
        Memperbarui SEMUA pengaturan umum di memori DAN langsung menyimpannya ke file.
        """
        try:
            if 'DEFAULT' not in self.config:
                self.config.add_section('DEFAULT')
            
            # Set semua nilai di memori
            self.config.set('DEFAULT', 'site_code', site_code)
            self.config.set('DEFAULT', 'running_text', running_text)
            self.config.set('DEFAULT', 'default_template', default_template)
            self.config.set('DEFAULT', 'weekday_weight', str(weekday_weight))
            self.config.set('DEFAULT', 'weekend_weight', str(weekend_weight))
            self.config.set('DEFAULT', 'google_sheet_id', google_sheet_id) # Pastikan baris ini ada
            self.config.set('DEFAULT', 'chat_it_link', chat_it_link)
            self.config.set('DEFAULT', 'auto_update', 'true' if auto_update else 'false')

            # Tulis semua perubahan ke file
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)
            logging.info("General settings successfully saved to file.")
            # Jangan gabungkan dengan save_monthly_targets, biarkan terpisah
            return True
        except Exception as e:
            logging.error(f"Gagal menyimpan pengaturan umum: {e}")
            return False

    def get_read_broadcasts(self):
        """Mendapatkan list ID broadcast yang sudah pernah dibaca."""
        ids_str = self.config.get('DEFAULT', 'read_broadcasts', fallback='')
        return [b_id.strip() for b_id in ids_str.split(',') if b_id.strip()]

    def mark_broadcast_read(self, broadcast_id):
        """Menandai suatu ID broadcast sebagai sudah dibaca dan menyimpannya ke konfigurasi."""
        read_ids = self.get_read_broadcasts()
        if broadcast_id not in read_ids:
            read_ids.append(broadcast_id)
            self.config.set('DEFAULT', 'read_broadcasts', ','.join(read_ids))
            self.save_config()

    def has_user_agreed_eula(self):
        return self.config.getboolean('DEFAULT', 'eula_agreed', fallback=False)

    def set_eula_agreed(self, agreed):
        self.config['DEFAULT']['eula_agreed'] = 'true' if agreed else 'false'
        self.save_config()
    
    def _generate_auth_hash(self, ip_address, mac_address, date_str):
        """Menghasilkan hash aman untuk mencegah tamper konfigurasi."""
        import hashlib
        salt = "r3p0t1n_S3cur3!"
        data_to_hash = f"{ip_address}|{mac_address}|{date_str}|{salt}"
        return hashlib.sha256(data_to_hash.encode()).hexdigest()

    def get_validation_status(self, current_ip, current_mac):
        """
        Mengambil status validasi terakhir dari file config dan memverifikasi hash.
        Mencegah user mengedit file konfigurasi manual.
        """
        auth_hash = self.config.get('DEFAULT', 'device_authorized_hash', fallback='')
        last_ip = self.config.get('DEFAULT', 'last_known_ip', fallback='')
        last_mac = self.config.get('DEFAULT', 'last_known_mac', fallback='')
        last_date = self.config.get('DEFAULT', 'last_validated_date', fallback='')
        
        if not auth_hash:
            return False, last_ip, last_mac, last_date
            
        # Verifikasi integritas hash menggunakan last_date dari config
        expected_hash = self._generate_auth_hash(current_ip, current_mac, last_date)
        is_hash_valid = (auth_hash == expected_hash)
        
        return is_hash_valid, last_ip, last_mac, last_date

    def save_validation_status(self, is_authorized, ip_address, mac_address, validation_date):
        """Menyimpan status validasi menggunakan sistem hash aman ke config."""
        if is_authorized:
            auth_hash = self._generate_auth_hash(ip_address, mac_address, validation_date)
            self.config.set('DEFAULT', 'device_authorized_hash', auth_hash)
        else:
            self.config.set('DEFAULT', 'device_authorized_hash', '')
            
        self.config.set('DEFAULT', 'last_known_ip', str(ip_address))
        self.config.set('DEFAULT', 'last_known_mac', str(mac_address))
        self.config.set('DEFAULT', 'last_validated_date', str(validation_date))
        self.save_config()
        
    def update_validation_status(self, is_authorized: bool, ip_address: str, mac_address: str):
        today_str = date.today().isoformat()
        return self.save_validation_status(is_authorized, ip_address, mac_address, today_str)

    def _load_site_list(self):
        """
        Memuat daftar site dari file lokal. Jika file tidak valid, coba unduh dari URL.
        """
        try:
            if os.path.exists(SITE_DATA_FILE) and os.path.getsize(SITE_DATA_FILE) > 5:
                with open(SITE_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # PERBAIKAN: Pastikan data yang dimuat adalah list dan tidak kosong
                    if isinstance(data, list) and data:
                        self.site_list = data
                        logging.info(f"Berhasil memuat {len(self.site_list)} site dari file lokal.")
                        return

            logging.warning(f"'{SITE_DATA_FILE}' tidak valid atau tidak ditemukan. Mencoba mengunduh...")
            self.download_site_list()

        except Exception as e:
            logging.error(f"Terjadi error saat memuat daftar site. Mencoba mengunduh ulang: {e}")
            self.download_site_list()

    def download_site_list(self):
        """
        Mengunduh daftar site dari URL dan menyimpannya ke file JSON lokal
        dalam format list of dictionary.
        """
        logging.info(f"Mencoba mengunduh daftar site dari URL...")
        try:
            # Menggunakan pandas untuk membaca CSV dari URL
            df = pd.read_csv(SITE_LIST_URL)
            
            # --- PERBAIKAN: Konversi DataFrame ke format list of dictionary ---
            # Ini memastikan formatnya selalu sama dengan yang diharapkan
            self.site_list = df.to_dict('records')
            
            with open(SITE_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.site_list, f, indent=4)
            
            logging.info(f"Berhasil mengunduh dan menyimpan {len(self.site_list)} site ke '{SITE_DATA_FILE}'.")
            return True, f"Berhasil mengunduh {len(self.site_list)} data site."
        except Exception as e:
            logging.error(f"Gagal memproses data site yang diunduh: {e}")
            self.site_list = []
            return False, f"Gagal memproses data site.\n\nError: {e}"

    # --- PATCH: Perbaiki logika pencarian nama toko ---
    def get_store_name(self, site_code):
        """Mencari nama toko berdasarkan site_code dari list of dictionary."""
        if not site_code or not self.site_list:
            return ""
        
        # PERBAIKAN: Iterasi melalui list untuk menemukan site yang cocok
        for site in self.site_list:
            # Menggunakan .get() untuk keamanan jika key tidak ada
            # Mengonversi keduanya ke string untuk perbandingan yang konsisten
            if str(site.get('Kode Site')) == str(site_code):
                return site.get('Nama Toko', '')
        return ""

    # --- Tab Visibility ---
    def get_tab_visibility(self, tab_id: str) -> bool:
        """Mendapatkan status show/hide dari sebuah tab. Default: True"""
        visible_tabs_str = self.config.get('DEFAULT', 'visible_tabs', fallback='{}')
        try:
            visible_tabs = json.loads(visible_tabs_str)
            # Default ke True jika tidak ada pengaturan sebelumnya
            return visible_tabs.get(tab_id, True)
        except json.JSONDecodeError:
            return True

    def set_tab_visibility(self, tab_id: str, is_visible: bool):
        """Menyimpan status show/hide untuk sebuah tab."""
        visible_tabs_str = self.config.get('DEFAULT', 'visible_tabs', fallback='{}')
        try:
            visible_tabs = json.loads(visible_tabs_str)
        except json.JSONDecodeError:
            visible_tabs = {}
            
        visible_tabs[tab_id] = is_visible
        
        if 'DEFAULT' not in self.config:
            self.config.add_section('DEFAULT')
        self.config['DEFAULT']['visible_tabs'] = json.dumps(visible_tabs)
        self.save_config()
        
    # --- Metode untuk menyimpan tema ---
    def save_theme(self, theme_name):
        """Menyimpan pengaturan tema ke file konfigurasi."""
        try:
            self.config['DEFAULT']['theme'] = theme_name
            with open(self.config_file, 'w') as configfile:
                self.config.write(configfile)
            return True
        except Exception as e:
            logging.error(f"Gagal menyimpan tema: {e}")
            return False