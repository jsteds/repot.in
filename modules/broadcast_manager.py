import json
import logging
from PyQt5.QtCore import QThread, pyqtSignal
from datetime import datetime
import requests

class BroadcastCheckerThread(QThread):
    """
    Thread for checking the central broadcast JSON file via HTTP GET.
    It fetches the JSON, parses the broadcasts, checks if they are active
    and unexpired, and emits a signal containing valid broadcasts to the main UI.
    """
    # Signal emitted when a valid active broadcast is found
    # Parameter is a dictionary containing the broadcast data
    broadcasts_fetched = pyqtSignal(list)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        
    def run(self):
        # Gunakan User-Agent awam agar server (terutama image hoster seperti Imgur) tidak memblokir traffic bot (menghasilkan HTTP 429/403)
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            # We use a 10s timeout so if the network is down or slow, 
            # the thread gracefully aborts instead of hanging forever.
            response = requests.get(self.url, headers=default_headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    logging.error("BroadcastCheckerThread: Response is not valid JSON.")
                    return
                    
                if data.get('status') == 'success' and 'broadcasts' in data:
                    valid_broadcasts = []
                    today_date = datetime.now().date()
                    
                    for item in data['broadcasts']:
                        # Only consider active broadcasts
                        if not item.get('is_active', False):
                            continue
                            
                        # Check expiry
                        expires_string = item.get('expires_at', '')
                        if expires_string:
                            try:
                                expires_date = datetime.strptime(expires_string, "%Y-%m-%d").date()
                                if today_date > expires_date:
                                    continue # Skipped, already expired
                            except ValueError:
                                logging.warning(f"BroadcastCheckerThread: Invalid date format in broadcast id '{item.get('id')}'. Expected YYYY-MM-DD.")
                        
                        # Optional: Fetch Image if provided
                        img_url = item.get('image_url', '')
                        if img_url:
                            try:
                                img_resp = requests.get(img_url, headers=default_headers, timeout=5)
                                if img_resp.status_code == 200:
                                    item['image_data'] = img_resp.content
                                else:
                                    logging.warning(f"BroadcastCheckerThread: Server menolak gambar HTTP {img_resp.status_code}")
                            except Exception as e:
                                logging.warning(f"BroadcastCheckerThread: Gagal mengunduh gambar {img_url}: {e}")
                                
                        valid_broadcasts.append(item)
                    
                    if valid_broadcasts:
                        self.broadcasts_fetched.emit(valid_broadcasts)
            else:
                logging.error(f"BroadcastCheckerThread: Received HTTP {response.status_code} while fetching broadcasts.")
        except requests.exceptions.RequestException as e:
            logging.error(f"BroadcastCheckerThread: Failed to connect or request timed out: {e}")
        except Exception as e:
            logging.error(f"BroadcastCheckerThread: An unexpected error occurred: {e}")
