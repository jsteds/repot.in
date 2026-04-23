# app_settings_utils.py
import configparser
import os
import logging

APP_SETTINGS_FILE = "app_settings.ini" # Akan dibuat di direktori yang sama dengan aplikasi

def has_user_agreed_eula():
    """Mengecek apakah pengguna sudah menyetujui EULA."""
    if not os.path.exists(APP_SETTINGS_FILE):
        return False # File tidak ada, anggap belum setuju
    
    config = configparser.ConfigParser()
    try:
        config.read(APP_SETTINGS_FILE)
        # Menggunakan fallback=False jika section atau key tidak ada
        return config.getboolean('Application', 'EULAAccepted', fallback=False)
    except configparser.Error as e:
        logging.error(f"Error membaca file pengaturan EULA: {e}")
        return False # Anggap belum setuju jika ada error baca

def set_eula_agreed_status(agreed: bool):
    """Menyimpan status persetujuan EULA."""
    config = configparser.ConfigParser()
    # Baca file yang ada jika ada, untuk mempertahankan setting lain (jika ada di masa depan)
    if os.path.exists(APP_SETTINGS_FILE):
        try:
            config.read(APP_SETTINGS_FILE)
        except configparser.Error as e:
            logging.warning(f"Gagal membaca file pengaturan EULA yang ada saat menyimpan: {e}. Membuat file baru.")
            # Jika file korup, kita akan timpa saja

    if 'Application' not in config:
        config['Application'] = {}
    
    config['Application']['EULAAccepted'] = 'true' if agreed else 'false'
    
    try:
        with open(APP_SETTINGS_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        logging.info(f"Status EULA disimpan: EULAAccepted = {config['Application']['EULAAccepted']}")
        return True
    except IOError as e:
        logging.error(f"Gagal menyimpan file pengaturan EULA: {e}")
        # Mungkin tampilkan QMessageBox error ke pengguna di sini jika ini terjadi dari UI
        return False