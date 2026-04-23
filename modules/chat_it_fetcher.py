import logging
from PyQt5.QtCore import QObject, pyqtSignal, QUrl, QTimer
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage

class ChatTokenInterceptor(QWebEngineUrlRequestInterceptor):
    token_intercepted = pyqtSignal(str)

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if "julia.klgsys.com/widget?website_token=" in url:
            logging.info(f"[ChatTokenFetcher] Ditemukan request widget: {url}")
            self.token_intercepted.emit(url)
            # Batalkan request agar tidak perlu memuat seluruh widget
            info.block(True)

class ChatTokenFetcher(QObject):
    finished = pyqtSignal(bool, str, str)  # success, message, token_url
    progress = pyqtSignal(str)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password
        self.found_url = ""
        self._finished_emitted = False
        
        # Gunakan profile off-the-record
        self.view = QWebEngineView()
        self.profile = QWebEngineProfile(self.view)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        
        # Setup interceptor
        self.interceptor = ChatTokenInterceptor()
        self.interceptor.token_intercepted.connect(self._on_token_intercepted)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        
        self.page.loadFinished.connect(self._on_load_finished)
        self.view.hide()
        
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

    def start(self):
        logging.info("[ChatTokenFetcher] Memulai proses pencarian token via SSO...")
        self.progress.emit("Membuka Cerberus SSO...")
        self.view.load(QUrl("https://cerberus.klgsys.com/sso"))
        self.timeout_timer.start(60000)  # 60 detik timeout

    def _on_load_finished(self, ok):
        if not ok:
            logging.warning("[ChatTokenFetcher] Gagal meload halaman.")
            return
            
        current_url = self.view.url().toString()
        logging.info(f"[ChatTokenFetcher] Page loaded: {current_url}")
        
        if "cerberus.klgsys.com" in current_url and "sso" in current_url:
            self.progress.emit("Mengisi kredensial SSO otomatis...")
            # Inject login otomatis dengan XPath fallback
            js_code = f"""
            (function() {{
                var attempt = 0;
                var interval = setInterval(function() {{
                    attempt++;
                    if (attempt > 20) {{
                        clearInterval(interval);
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
                        console.log("ChatTokenFetcher: Mengisi Form SSO");
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
        elif self.found_url:
            # Apabila setelah selesai render URL sudah ditemukan, pastikan tidak tertimpa
            pass
        else:
            self.progress.emit("Menunggu widget Chat terbuka...")
            
    def _on_token_intercepted(self, url):
        self.found_url = url
        logging.info("[ChatTokenFetcher] Token berhasil dicegat!")
        self._finish_process(True, "Token berhasil ditemukan!", url)

    def _on_timeout(self):
        self._finish_process(False, "Waktu tunggu habis (timeout) saat mencoba mengambil token.", "")

    def _finish_process(self, success, message, token_url):
        if self._finished_emitted:
            return
            
        self._finished_emitted = True
        self.timeout_timer.stop()
        self.finished.emit(success, message, token_url)
        
        try:
            self.view.deleteLater()
        except:
            pass
