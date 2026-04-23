import os
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from PyQt5.QtCore import QObject, pyqtSignal, QUrl, QTimer, Qt
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
from utils.constants import BASE_DIR

class AuroraWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        logging.info(f"Aurora JS Console [{lineNumber}]: {message}")

class AuroraScraper(QObject):
    finished = pyqtSignal(bool, str, list)
    progress = pyqtSignal(str)
    _download_done = pyqtSignal(str)  # Thread-safe: worker thread → main thread

    def __init__(self, username, password, start_date, end_date, target_site_code=None):
        super().__init__()
        self.username = username
        self.password = password
        self.start_date = start_date  # str: MM/dd/yyyy
        self.end_date = end_date      # str: MM/dd/yyyy
        self.target_site_code = target_site_code
        
        self.downloaded_files = []
        self.expected_downloads = 2
        self._cerberus_login_attempted = False
        self._finished_emitted = False  # Guard: prevent double finished signal
        
        # Connect thread-safe download completion signal
        self._download_done.connect(self._on_download_complete)
        self.auth_cookies = {}  # Collected dari browser profile
        
        self.download_dir = os.path.join(BASE_DIR, "data", "temp_aurora")
        os.makedirs(self.download_dir, exist_ok=True)
        
        for f in os.listdir(self.download_dir):
            try:
                os.remove(os.path.join(self.download_dir, f))
            except:
                pass
                
        self.view = QWebEngineView()
        
        # PENTING: Gunakan profil anonim (off-the-record) agar WebEngine tidak menyimpan
        # state lintas sesi. Profil bernama (named profile) di Qt dapat menyebabkan crash
        # jika dipakai ulang sebelum renderer subprocess sebelumnya selesai ditutup.
        self.profile = QWebEngineProfile(self.view)  # off-the-record / anonymous profile
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        
        # Kumpulkan cookies dari browser — ini akan digunakan untuk API download
        self.profile.cookieStore().cookieAdded.connect(self._collect_cookie)
        
        self.page = AuroraWebPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.loadFinished.connect(self.on_load_finished)
        self.view.hide()
        
        self._inject_polyfills()
        
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)
    
    def _collect_cookie(self, cookie):
        """Kumpulkan semua cookies dari browser untuk digunakan di Python urllib."""
        try:
            name = bytes(cookie.name()).decode()
            value = bytes(cookie.value()).decode()
            domain = cookie.domain()
            if 'klgsys' in domain:
                self.auth_cookies[name] = value
        except:
            pass

    def _inject_polyfills(self):
        from PyQt5.QtWebEngineWidgets import QWebEngineScript
        polyfill_js = """
        if (!String.prototype.replaceAll) {
            String.prototype.replaceAll = function(search, replacement) {
                var target = this;
                if (search instanceof RegExp) {
                    return target.replace(new RegExp(search.source, search.flags.replace('g','') + 'g'), replacement);
                }
                return target.split(search).join(replacement);
            };
        }
        if (!Array.prototype.at) {
            Array.prototype.at = function(index) {
                var len = this.length;
                if (index < 0) index = len + index;
                if (index < 0 || index >= len) return undefined;
                return this[index];
            };
        }
        """
        script = QWebEngineScript()
        script.setName("aurora_polyfills")
        script.setSourceCode(polyfill_js)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        self.profile.scripts().insert(script)
        
    def start(self):
        self.progress.emit("Membuka halaman login Aurora...")
        logging.info(f"[AuroraScraper] Memulai proses sync Aurora untuk rentang {self.start_date} - {self.end_date}")
        self.view.load(QUrl("https://aurora.klgsys.com"))
        self.timeout_timer.start(300000)  # 5 menit
        
    def on_timeout(self):
        # Only emit once — if downloads already succeeded, ignore the timeout
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit(False, "Proses timeout. Website Aurora terlalu lama merespons.", [])
        try:
            self.view.deleteLater()
        except:
            pass

    # ================================================================
    # LOGIN FLOW
    # ================================================================

    def on_load_finished(self, ok):
        if not ok:
            logging.warning("[AuroraScraper] Load finished with ok=False.")
            return
            
        current_url = self.view.url().toString()
        logging.info(f"[AuroraScraper] Page loaded: {current_url}")
            
        # STEP 1: Cerberus SSO Login
        if "cerberus.klgsys.com" in current_url:
            self._cerberus_login_attempted = True
            self.progress.emit("(1/3) Mengisi kredensial di Cerberus SSO...")
            js_code = f"""
            (function() {{
                var attempt = 0;
                var interval = setInterval(function() {{
                    attempt++;
                    if (attempt > 20) {{
                        clearInterval(interval);
                        console.log("aurora_scraper: Gagal menemukan form Cerberus SSO.");
                        return;
                    }}
                    
                    var inputs = document.querySelectorAll('input');
                    var userInp = null;
                    var passInp = null;
                    for(var i=0; i<inputs.length; i++) {{
                        if(inputs[i].type === 'password' || (inputs[i].placeholder && inputs[i].placeholder.toLowerCase().includes('sandi'))) {{
                            passInp = inputs[i];
                        }} else if(inputs[i].type === 'text' || (inputs[i].placeholder && inputs[i].placeholder.toLowerCase().includes('nip'))) {{
                            userInp = inputs[i];
                        }}
                    }}
                    
                    var submitBtn = document.evaluate("//button[contains(text(), 'Login')]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (!submitBtn) submitBtn = document.querySelector('button[type="submit"]');
                    
                    if (userInp && passInp && submitBtn) {{
                        clearInterval(interval);
                        console.log("aurora_scraper: Mengisi Cerberus SSO...");
                        userInp.value = "{self.username}";
                        passInp.value = "{self.password}";
                        
                        userInp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passInp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        
                        submitBtn.click();
                    }}
                }}, 500);
            }})();
            """
            self.page.runJavaScript(js_code)
            
        # STEP 2: Aurora Auth/Login Page — klik tombol SSO
        elif "aurora.klgsys.com/auth/login" in current_url.lower():
            if getattr(self, '_cerberus_login_attempted', False):
                logging.info("[AuroraScraper] Kembali dari SSO, menunggu auto-redirect Aurora...")
                return
                
            self.progress.emit("(1/3) Membuka jembatan SSO Aurora...")
            js_code = """
            (function() {
                var attempt = 0;
                var interval = setInterval(function() {
                    attempt++;
                    if (attempt > 20) {
                        clearInterval(interval);
                        return;
                    }
                    var loginBtn = document.getElementById('___klg_btn');
                    if (!loginBtn) loginBtn = document.querySelector('button'); 
                    if (loginBtn) {
                        clearInterval(interval);
                        loginBtn.click();
                    }
                }, 500);
            })();
            """
            self.page.runJavaScript(js_code)
            
        # STEP 3: Sudah di halaman Sales Reports — mulai direct API download
        elif "phoenix/sales-reports" in current_url.lower():
            self._extract_auth_and_download()
            
        # Post-SSO redirect handler
        else:
            if ("aurora.klgsys.com" in current_url and 
                "auth" not in current_url.lower() and 
                self._cerberus_login_attempted and 
                not getattr(self, '_navigation_to_reports_queued', False)):
                
                logging.info(f"[AuroraScraper] Token URL detected, menunggu 3 detik...")
                self.progress.emit("(2/3) Login berhasil! Menunggu sesi Aurora aktif...")
                self._navigation_to_reports_queued = True
                QTimer.singleShot(3000, lambda: self._navigate_to_sales_reports())
            else:
                logging.info(f"[AuroraScraper] URL tidak dikenali: {current_url}")
    
    def _navigate_to_sales_reports(self):
        logging.info("[AuroraScraper] Navigating to SalesReports...")
        self.progress.emit("(2/3) Membuka halaman Sales Report...")
        self.view.load(QUrl("https://aurora.klgsys.com/phoenix/sales-reports"))

    # ================================================================
    # DIRECT API DOWNLOAD — Bypass Vue UI + CORS
    # ================================================================

    def _extract_auth_and_download(self):
        """
        Setelah sampai di halaman sales-reports (berarti sudah login),
        extract auth token dan site code dari browser, lalu download 
        data langsung via Python urllib dengan date filtering.
        """
        self.progress.emit("(3/3) Mengekstrak data autentikasi...")
        
        # Tunggu 3 detik agar halaman selesai render & cookies terisi
        QTimer.singleShot(3000, self._do_extract_auth)
    
    def _do_extract_auth(self):
        js_code = """
        (function() {
            var result = {token: '', site_code: '', company_code: '', company_desc: '', all_keys: []};
            
            // === localStorage ===
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                result.all_keys.push(key);
            }
            
            // Auth token - Aurora menyimpan di 'auth.access_token'
            var token = localStorage.getItem('auth.access_token') || '';
            if (!token) token = localStorage.getItem('auth._token.local') || '';
            if (!token) token = localStorage.getItem('token') || '';
            if (!token) token = localStorage.getItem('access_token') || '';
            result.token = token;
            
            // === sessionStorage ===
            for (var i = 0; i < sessionStorage.length; i++) {
                var key = sessionStorage.key(i);
                result.all_keys.push('ss:' + key);
            }
            
            // Site code - Aurora menyimpan di sessionStorage 'bussiness_area.site'
            var siteRaw = sessionStorage.getItem('bussiness_area.site') || '';
            if (siteRaw) {
                try {
                    // Mungkin berformat JSON atau plain string
                    var parsed = JSON.parse(siteRaw);
                    if (typeof parsed === 'string') result.site_code = parsed;
                    else if (parsed.code) result.site_code = parsed.code;
                    else if (parsed.site_code) result.site_code = parsed.site_code;
                    else result.site_code = siteRaw;
                } catch(e) {
                    // Coba extract kode site (contoh: "F413" dari "F413 - nama toko")
                    var match = siteRaw.match(/([A-Z]\\d{3})/);
                    result.site_code = match ? match[1] : siteRaw;
                }
            }
            
            // Company info
            var compRaw = sessionStorage.getItem('bussiness_area.company') || '';
            if (compRaw) {
                try {
                    var parsed = JSON.parse(compRaw);
                    if (parsed.code) result.company_code = parsed.code;
                    if (parsed.description) result.company_desc = parsed.description;
                } catch(e) {
                    result.company_code = compRaw;
                }
            }
            
            // Log detail untuk debug
            console.log('aurora_scraper: token length=' + result.token.length + ', site=' + result.site_code + ', company=' + result.company_code);
            
            return JSON.stringify(result);
        })();
        """
        self.page.runJavaScript(js_code, self._on_auth_extracted)
    
    def _on_auth_extracted(self, result_json):
        try:
            data = json.loads(result_json)
            auth_token = data.get('token', '')
            # Prioritaskan site_code dari konfigurasi aplikasi, fallback ke sessionStorage
            site_code = self.target_site_code if self.target_site_code else data.get('site_code', '')
            company_code = data.get('company_code', '')
            company_desc = data.get('company_desc', '')
            all_keys = data.get('all_keys', [])
            
            logging.info(f"[AuroraScraper] Auth token: {'✓ found (' + str(len(auth_token)) + ' chars)' if auth_token else '✗ NOT found'}")
            logging.info(f"[AuroraScraper] Site code: {site_code or 'NOT found'}")
            logging.info(f"[AuroraScraper] Company: {company_code} - {company_desc}")
            logging.info(f"[AuroraScraper] Browser cookies: {len(self.auth_cookies)} collected")
            logging.info(f"[AuroraScraper] Storage keys: {all_keys}")
            
            if not auth_token and not self.auth_cookies:
                if not self._finished_emitted:
                    self._finished_emitted = True
                    self.finished.emit(False, "Gagal mendapatkan autentikasi dari Aurora. Tidak ada token atau cookies.", [])
                return
            
            self._download_reports(auth_token, site_code, company_code, company_desc)
            
        except Exception as e:
            logging.error(f"[AuroraScraper] Auth extraction failed: {e}")
            if not self._finished_emitted:
                self._finished_emitted = True
                self.finished.emit(False, f"Gagal mengekstrak autentikasi: {str(e)}", [])
    
    def _download_reports(self, auth_token, site_code, company_code='', company_desc=''):
        """Download AH Commodity dan MOP Report via Python urllib dengan date filtering."""
        self.progress.emit("(3/3) Mengunduh laporan AH Commodity dan MOP...")
        
        # Konversi tanggal dari MM/DD/YYYY ke UTC ISO format
        # WIB = UTC+7, jadi midnight WIB = 17:00 UTC hari sebelumnya
        start_dt = datetime.strptime(self.start_date, "%m/%d/%Y")
        end_dt = datetime.strptime(self.end_date, "%m/%d/%Y")
        
        start_utc = (start_dt - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_utc = (end_dt.replace(hour=23, minute=59, second=59) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        logging.info(f"[AuroraScraper] Date range UTC: {start_utc} to {end_utc}")
        
        base_url = "https://api-phoenix.klgsys.com/v1/sales_reports/export_to_excel"
        
        # Common params
        common = {}
        if site_code:
            common['q[schedule_site_code_in][]'] = site_code
        common['q[order_date_gteq]'] = start_utc
        common['q[order_date_lteq]'] = end_utc
        
        # AH Commodity Report — memerlukan company params (F100)
        # Dari CORS URL asli: report_type=order_details + company_code=F100
        ah_params = {**common}
        ah_params['q[schedule_site_sales_office_sales_organisation_company_code_eq]'] = 'F100'
        ah_params['q[schedule_site_sales_office_sales_organisation_company_description_eq]'] = 'PT Foods Beverages Indonesia'
        ah_params['report_type'] = 'order_details'
        ah_url = base_url + '?' + urlencode(ah_params)
        
        # MOP Report — report_type=order_payments (dari Chrome DevTools)
        mop_params = {**common, 'report_type': 'order_payments'}
        mop_url = base_url + '?' + urlencode(mop_params)
        
        logging.info(f"[AuroraScraper] AH Commodity URL: {ah_url}")
        logging.info(f"[AuroraScraper] MOP URL: {mop_url}")
        
        # Download keduanya via Python
        self._api_download(ah_url, auth_token, 'AH_Commodity_Report.csv')
        self._api_download(mop_url, auth_token, 'MOP_Report.csv')
    
    def _api_download(self, url, auth_token, default_filename):
        """Download file dari API Aurora via Python urllib (bypass CORS)."""
        def _download():
            try:
                req = Request(url)
                
                # Set auth headers
                if auth_token:
                    token = auth_token
                    if not token.startswith('Bearer'):
                        token = f'Bearer {token}'
                    req.add_header('Authorization', token)
                
                # Set cookies dari browser
                if self.auth_cookies:
                    cookie_str = '; '.join(f'{k}={v}' for k, v in self.auth_cookies.items())
                    req.add_header('Cookie', cookie_str)
                
                req.add_header('Accept', 'text/csv, application/vnd.ms-excel, */*')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
                req.add_header('Origin', 'https://aurora.klgsys.com')
                req.add_header('Referer', 'https://aurora.klgsys.com/phoenix/sales-reports')
                
                logging.info(f"[AuroraScraper] Downloading {default_filename}...")
                response = urlopen(req, timeout=180)
                
                # Log response info
                status = response.status if hasattr(response, 'status') else response.getcode()
                content_type = response.headers.get('Content-Type', 'unknown')
                logging.info(f"[AuroraScraper] Response status={status}, content-type={content_type}")
                
                data = response.read()
                
                # Debug: log preview of response content
                preview = data[:500].decode('utf-8', errors='replace') if data else '(empty)'
                logging.info(f"[AuroraScraper] Response preview ({len(data):,} bytes): {preview}")
                
                # Skip file kosong (0 bytes) — tidak ada data untuk di-parse
                if len(data) == 0:
                    logging.warning(f"[AuroraScraper] ⚠ {default_filename}: Response kosong (0 bytes), skip.")
                    self.expected_downloads -= 1
                    if self.expected_downloads <= 0 or len(self.downloaded_files) >= self.expected_downloads:
                        self._download_done.emit('')  # Trigger completion check
                    return
                
                # Selalu gunakan default_filename (bukan Content-Disposition)
                # agar _on_sync_finished bisa identifikasi file via keyword
                # (Content-Disposition selalu "Sales Report.csv" untuk semua report)
                filename = default_filename
                content_disp = response.headers.get('Content-Disposition', '')
                logging.info(f"[AuroraScraper] Content-Disposition: {content_disp}, using filename: {filename}")
                
                save_path = os.path.join(self.download_dir, filename)
                counter = 1
                base, ext = os.path.splitext(save_path)
                while os.path.exists(save_path):
                    save_path = f"{base}_{counter}{ext}"
                    counter += 1
                
                with open(save_path, 'wb') as f:
                    f.write(data)
                
                logging.info(f"[AuroraScraper] ✓ Downloaded: {save_path} ({len(data):,} bytes)")
                # Emit signal ke main thread (thread-safe)
                self._download_done.emit(save_path)
                
            except Exception as e:
                error_msg = str(e)
                logging.error(f"[AuroraScraper] Download failed for {default_filename}: {error_msg}")
                self.progress.emit(f"⚠ Download {default_filename} gagal: {error_msg}")
        
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()
    
    def _on_download_complete(self, save_path):
        """Callback di main thread setelah download selesai."""
        # Skip empty path (dari 0-byte file yang di-skip)
        if save_path:
            self.downloaded_files.append(save_path)
            self.progress.emit(f"✓ Berhasil: {os.path.basename(save_path)} ({len(self.downloaded_files)}/{self.expected_downloads})")
        
        logging.info(f"[AuroraScraper] Total downloads: {len(self.downloaded_files)}/{self.expected_downloads}")
        
        if len(self.downloaded_files) >= self.expected_downloads:
            self.timeout_timer.stop()
            self.progress.emit("Semua file berhasil diunduh! Memproses data...")
            logging.info(f"[AuroraScraper] Selesai mengunduh {len(self.downloaded_files)} file.")
            
            if self._finished_emitted:
                logging.warning("[AuroraScraper] finished already emitted (timeout race?), skipping success emit.")
                return
                
            self._finished_emitted = True
            # Filter: hanya kirim file yang valid (non-empty)
            valid_files = [f for f in self.downloaded_files if f and os.path.exists(f) and os.path.getsize(f) > 0]
            self.finished.emit(True, "Berhasil mengunduh data dari Aurora.", valid_files)
            try:
                self.view.deleteLater()
            except:
                pass
