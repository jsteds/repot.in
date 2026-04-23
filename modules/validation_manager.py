# validation_manager.py
import socket
import urllib.request
import logging
import pandas as pd
import json
import os
import requests
from datetime import date, timedelta
# URL Web App Google Apps Script dari User
AUTHORIZED_IPS_URL = "https://script.google.com/macros/s/AKfycbxDP8yRPAgt7pjiijXqPYOx4O1WKP9Gahr05HO5ZhjnakFDRNiAvm45CrpTxj7780Hz/exec"

def get_local_ip_address():
    """Mendapatkan alamat IP lokal yang digunakan untuk koneksi keluar."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try: return socket.gethostbyname(socket.gethostname())
        except Exception: return None

def get_mac_address():
    """Mendapatkan alamat MAC fisik perangkat dalam format XX:XX:XX:XX:XX:XX."""
    import uuid
    try:
        mac_num = uuid.getnode()
        mac_address = ':'.join(['{:02x}'.format((mac_num >> ele) & 0xff) for ele in range(0,8*6,8)][::-1])
        return mac_address.upper()
    except Exception as e:
        logging.error(f"Gagal mendapatkan MAC address: {e}")
        return "UNKNOWN_MAC"

def verify_device_with_server(ip_address, mac_address):
    """Memeriksa otorisasi perangkat ke Google Apps Script (REST API)."""
    if not ip_address or not mac_address: return False
    
    logging.info(f"Memverifikasi perangkat dengan IP: {ip_address} dan MAC: {mac_address} ke server...")
    try:
        # Kirim GET request dengan parameter ip dan mac
        params = {
            'ip': ip_address,
            'mac': mac_address
        }
        response = requests.get(AUTHORIZED_IPS_URL, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        is_auth = data.get('authorized', False)
        message = data.get('message', '')
        
        logging.info(f"Respons server: {message} (Authorized: {is_auth})")
        return is_auth
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error koneksi ke server validasi: {e}")
        raise ConnectionError(f"Tidak dapat mengakses server validasi: {e}")
    except Exception as e:
        logging.error(f"Error parsing respons server validasi: {e}")
        return False

def is_device_authorized(config_manager):
    """
    Memvalidasi perangkat menggunakan IP dan MAC Address, didukung dengan integritas hash.
    """
    today_str = date.today().isoformat()
    
    # Dapatkan identifier saat ini
    current_ip = get_local_ip_address()
    current_mac = get_mac_address()
    
    if not current_ip: current_ip = "UNKNOWN_IP"
    if not current_mac: current_mac = "UNKNOWN_MAC"
    
    logging.info(f"--- MEMULAI PROSES VALIDASI ---")
    logging.info(f"Perangkat saat ini - IP: {current_ip}, MAC: {current_mac}")
    
    # Cek cache lokal menggunakan verifikasi hash
    is_hash_valid, last_ip, last_mac, last_date_str = config_manager.get_validation_status(current_ip, current_mac)
    logging.info(f"Status cache lokal: Hash Valid={is_hash_valid}, Valid s/d={last_date_str}")
    
    if is_hash_valid and last_date_str == today_str:
        logging.info("Validasi lokal berhasil (Hash Cocok). Melewatkan pengecekan online.")
        return True, "Otorisasi perangkat berhasil (cache lokal terverifikasi)."

    logging.info("Memerlukan validasi online ke server...")
    
    try:
        # Validasi Online
        if verify_device_with_server(current_ip, current_mac):
            config_manager.save_validation_status(True, current_ip, current_mac, today_str)
            logging.info(f"VALIDASI ONLINE BERHASIL. Status hash disimpan.")
            return True, f"Otorisasi perangkat berhasil."
        else:
            config_manager.save_validation_status(False, current_ip, current_mac, today_str)
            return False, f"Perangkat (IP: {current_ip}, MAC: {current_mac}) tidak terdaftar. Silakan foto error ini dan kirim via WA."
            
    except ConnectionError as e:
        logging.warning(f"Validasi online gagal (Koneksi Error): {e}.")
        
        # Fallback offline
        if is_hash_valid:
            from datetime import datetime
            try:
                last_val_date_obj = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                days_diff = (date.today() - last_val_date_obj).days
                
                # Toleransi penggunaan offline maksimum 3 hari
                if days_diff <= 3:
                     logging.info(f"Otorisasi offline aktif (berumur {days_diff} hari). Mengizinkan akses.")
                     return True, f"Otorisasi perangkat berhasil (Mode Offline - {days_diff} hari)."
                else:
                     return False, f"Sesi offline kadaluwarsa ({days_diff} hari). Harap hubungkan ke internet jaringan kantor."
            except Exception:
                 return True, "Otorisasi perangkat berhasil (Mode Offline Terpaksa)."
        else:
            return False, "Tidak terhubung ke server validasi dan otorisasi offline lokal tidak valid/absah."
    except Exception as e:
         logging.error(f"Validasi gagal karena error tidak terduga: {e}")
         return False, f"Terjadi kesalahan saat validasi perangkat: {e}"