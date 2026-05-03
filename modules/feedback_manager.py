# modules/feedback_manager.py
"""
Feedback Manager
Mengirim data feedback ke Google Sheets via Apps Script Web App.
Jika gagal (offline / error), data disimpan ke antrian lokal (JSON)
dan akan di-upload otomatis saat koneksi tersedia.
"""
import json
import logging
import os
import platform
from datetime import datetime
from urllib import request, error
from urllib.request import Request

from utils.constants import APP_VERSION, FEEDBACK_QUEUE_FILE

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # detik


def _post_json(url: str, payload: dict) -> bool:
    """
    POST JSON ke Google Apps Script Web App.
    Apps Script SELALU mengembalikan 302 setelah menjalankan doPost.
    Kita TIDAK perlu mengikuti redirect — 302 = doPost berhasil dieksekusi.
    """
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    # Blokir redirect agar tidak ada POST ganda ke URL hasil redirect
    class _StopRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # Hentikan redirect

    opener = request.build_opener(_StopRedirect)
    try:
        with opener.open(req, timeout=_TIMEOUT) as resp:
            # 200 langsung (jarang dari Apps Script) — parse JSON jika ada
            raw = resp.read().decode("utf-8").strip()
            if not raw:
                return resp.status == 200
            try:
                data = json.loads(raw)
                return data.get("status") == "ok"
            except json.JSONDecodeError:
                return True
    except error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            # Redirect = Apps Script menerima dan menjalankan doPost ✓
            return True
        logger.warning(f"feedback POST gagal (HTTP {e.code}): {e.reason}")
    except error.URLError as e:
        logger.warning(f"feedback POST gagal (URLError): {e}")
    except Exception as e:
        logger.warning(f"feedback POST gagal: {e}")
    return False




def _load_queue() -> list:
    if not os.path.exists(FEEDBACK_QUEUE_FILE):
        return []
    try:
        with open(FEEDBACK_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(items: list):
    os.makedirs(os.path.dirname(FEEDBACK_QUEUE_FILE), exist_ok=True)
    with open(FEEDBACK_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def save_to_queue(payload: dict):
    """Simpan satu entri feedback ke antrian lokal."""
    queue = _load_queue()
    queue.append(payload)
    _save_queue(queue)
    logger.info(f"Feedback disimpan ke antrian lokal ({len(queue)} item).")


def submit_feedback(payload: dict, sheet_url: str) -> bool:
    """
    Kirim feedback ke Sheets. Return True jika berhasil dikirim online.
    Jika gagal, otomatis simpan ke antrian lokal.
    """
    if not sheet_url:
        save_to_queue(payload)
        return False

    ok = _post_json(sheet_url, payload)
    if not ok:
        save_to_queue(payload)
    return ok


def flush_queue(sheet_url: str) -> int:
    """
    Upload semua antrian lokal ke Sheets.
    Dipanggil saat startup. Return jumlah item yang berhasil dikirim.
    """
    if not sheet_url:
        return 0

    queue = _load_queue()
    if not queue:
        return 0

    remaining = []
    sent = 0
    for item in queue:
        if _post_json(sheet_url, item):
            sent += 1
        else:
            remaining.append(item)

    _save_queue(remaining)
    if sent:
        logger.info(f"flush_queue: {sent} feedback terkirim, {len(remaining)} tersisa.")
    return sent


def build_payload(site_code: str, store_name: str,
                  feedback_type: str, title: str, description: str) -> dict:
    """Buat dict payload yang akan dikirim ke Sheets."""
    return {
        "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store_code":    site_code,
        "store_name":    store_name,
        "app_version":   APP_VERSION,
        "feedback_type": feedback_type,
        "title":         title,
        "description":   description,
        "os_info":       f"{platform.system()} {platform.release()}",
    }
