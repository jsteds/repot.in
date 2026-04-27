import os
import json
import logging
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import requests

from utils.constants import BASE_DIR

def drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"

class StartupAssetWorker(QThread):
    """
    Worker untuk mengecek dan mengunduh aset yang hilang pada saat startup.
    Akan membaca manifest.json lokal.
    """
    progress = pyqtSignal(int, str)  # Emit (progress_percentage, file_name)
    finished = pyqtSignal(bool, str) # Emit (success, message)
    
    def __init__(self, manifest_path=None):
        super().__init__()
        self.manifest_path = manifest_path or os.path.join(BASE_DIR, "manifest.json")
        
    def run(self):
        try:
            if not os.path.exists(self.manifest_path):
                self.finished.emit(True, "Manifest tidak ditemukan, melewati pengecekan aset.")
                return
                
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
                
            files_to_check = [f for f in manifest_data.get("files", []) if f.get("category") in ["Asset", "Style"]]
            
            missing_files = []
            for file_info in files_to_check:
                local_path = os.path.join(BASE_DIR, file_info.get("target_folder", ""), file_info.get("name", ""))
                if not os.path.exists(local_path):
                    missing_files.append(file_info)
                    
            if not missing_files:
                self.finished.emit(True, "Semua aset tersedia.")
                return
                
            # Proses download file yang hilang
            total_files = len(missing_files)
            for idx, file_info in enumerate(missing_files):
                file_name = file_info.get("name", "Unknown")
                drive_id = file_info.get("drive_id", "")
                target_folder = file_info.get("target_folder", "")
                local_path = os.path.join(BASE_DIR, target_folder, file_name)
                
                if not drive_id or drive_id.startswith("GANTI"):
                    logging.warning(f"File {file_name} hilang tetapi drive_id belum di-set di manifest.")
                    continue
                    
                self.progress.emit(int((idx / total_files) * 100), f"Mengunduh {file_name}...")
                
                try:
                    self._download_file(drive_id, local_path)
                except Exception as e:
                    logging.error(f"Gagal mengunduh {file_name}: {e}")
                    
            self.progress.emit(100, "Selesai mengunduh aset.")
            self.finished.emit(True, "Pengecekan aset selesai.")
            
        except Exception as e:
            self.finished.emit(False, f"Terjadi kesalahan saat mengecek aset: {str(e)}")
            
    def _download_file(self, drive_id, local_path):
        url = drive_download_url(drive_id)
        session = requests.Session()
        response = session.get(url, stream=True, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # Handle Google Drive large file warning
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            content = response.content.decode('utf-8', errors='ignore')
            import re
            from urllib.parse import urljoin
            action_match = re.search(r'<form[^>]*action="([^"]+)"', content)
            if action_match:
                action_url = action_match.group(1)
                inputs = re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', content)
                params = {name: value for name, value in inputs}
                if action_url.startswith('/'):
                    action_url = urljoin("https://drive.google.com", action_url)
                response = session.get(action_url, params=params, stream=True, timeout=30)
                response.raise_for_status()
                
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
