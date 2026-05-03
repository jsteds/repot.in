import os
import subprocess
import logging
from datetime import datetime
from dataclasses import dataclass
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, inch, mm
from reportlab.pdfgen import canvas
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

from utils.constants import BASE_DIR
from modules.config_manager import ConfigManager

@dataclass
class BPKEntry:
    counterparty_account: str
    description: str
    amount: float
    check_number: str
    date: str
    diajukan_info: str = ""
    disetujui_info: str = ""
    diberikan_info: str = ""
    diterima_info: str = ""

def terbilang(n: int) -> str:
    if n < 0:
        return "MINUS " + terbilang(abs(n))
    satuan = ["", "SATU", "DUA", "TIGA", "EMPAT", "LIMA", "ENAM", "TUJUH", "DELAPAN", "SEMBILAN", "SEPULUH", "SEBELAS"]
    if n < 12:
        return satuan[n]
    elif n < 20:
        return terbilang(n - 10) + " BELAS"
    elif n < 100:
        return (terbilang(n // 10) + " PULUH " + terbilang(n % 10)).strip()
    elif n < 200:
        return ("SERATUS " + terbilang(n - 100)).strip()
    elif n < 1000:
        return (terbilang(n // 100) + " RATUS " + terbilang(n % 100)).strip()
    elif n < 2000:
        return ("SERIBU " + terbilang(n - 1000)).strip()
    elif n < 1000000:
        return (terbilang(n // 1000) + " RIBU " + terbilang(n % 1000)).strip()
    elif n < 1000000000:
        return (terbilang(n // 1000000) + " JUTA " + terbilang(n % 1000000)).strip()
    elif n < 1000000000000:
        return (terbilang(n // 1000000000) + " MILYAR " + terbilang(n % 1000000000)).strip()
    else:
        return str(n)

class BPKGenerator:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        config_data = self.config.get_config()
        self.store_code = config_data.get('site_code', 'UNKNOWN')
        self.store_name = self.config.get_store_name(self.store_code)
        self.bpk_dir = os.path.join(BASE_DIR, 'data', 'bpk')
        os.makedirs(self.bpk_dir, exist_ok=True)

    def _get_next_serial(self) -> str:
        return datetime.now().strftime("%H%M%S")

    def generate_pdf(self, entry: BPKEntry) -> str:
        try:
            try:
                if '-' in entry.date:
                    dt = datetime.strptime(entry.date, "%Y-%m-%d")
                elif '/' in entry.date:
                    dt = datetime.strptime(entry.date, "%d/%m/%Y")
                else:
                    dt = datetime.now()
            except ValueError:
                dt = datetime.now()

            date_str = dt.strftime("%d%m%y")
            months = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                      "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            display_date = f"{dt.day} {months[dt.month]} {dt.year}"
            short_date = dt.strftime("%d.%m.%y")
            serial = self._get_next_serial()

            filename = f"BPK_{date_str}_{self.store_code}_{serial}.pdf"
            filepath = os.path.join(self.bpk_dir, filename)

            # Read settings
            cfg = self.config.get_config()
            paper_mode = cfg.get('bpk_paper_mode', 'a4')
            offset_x = float(cfg.get('bpk_offset_x', 0.0)) * mm
            offset_y = float(cfg.get('bpk_offset_y', 0.0)) * mm

            # --- Page size & scale ---
            # Layout reference frame is always A4 landscape (29.7 x 21 cm).
            # 'a4'        → A4 Portrait (21 x 29.7 cm); scale content so it
            #               fits the top half, identical to the Excel original.
            # 'continuous'→ 9.5 x 5.5 inch custom page.
            if paper_mode == 'continuous':
                page_w = 9.5 * inch
                page_h = 5.5 * inch
                sx = page_w / landscape(A4)[0]
                sy = page_h / landscape(A4)[1]
                sf = min(sx, sy) * 0.95
            else:
                # A4 Portrait — content scaled so width fits A4 portrait width.
                # sf = A4_portrait_width / A4_landscape_width = 210/297 ≈ 0.707
                # This makes the form fill the top ~127 mm of the 297 mm page
                # (same as the original Excel which prints to top half of A4).
                page_w, page_h = A4   # A4[0]=210mm, A4[1]=297mm (portrait)
                sf = A4[0] / landscape(A4)[0]   # ≈ 0.707
                offset_x = 0.0
                offset_y = 0.0

            c = canvas.Canvas(filepath, pagesize=(page_w, page_h))
            width, height = page_w, page_h

            # Margins (scaled)
            mx = 1 * cm * sf
            my = 1 * cm * sf

            # --- Helper drawing functions ---
            def tx(x_cm):
                """Convert layout x (cm) to canvas x, with offset."""
                return mx + x_cm * cm * sf + offset_x

            def ty(y_cm):
                """Convert layout y (cm) to canvas y (flipped), with offset."""
                return height - my - y_cm * cm * sf - offset_y

            def drect(x, y, w, h):
                c.rect(tx(x), ty(y) - h*cm*sf, w*cm*sf, h*cm*sf)

            def dline(x1, y1, x2, y2):
                c.line(tx(x1), ty(y1), tx(x2), ty(y2))

            def dstr(x, y, text, font="Helvetica", size=10, align="left"):
                c.setFont(font, size * sf)
                px, py = tx(x), ty(y)
                if align == "center":
                    c.drawCentredString(px, py, text)
                elif align == "right":
                    c.drawRightString(px, py, text)
                else:
                    c.drawString(px, py, text)

            # ===================== DRAW LOGO =====================
            logo_path = os.path.join(BASE_DIR, 'assets', 'kawan_lama_logo.png')
            logo_h_cm = 2.0
            logo_w_cm = 4.5
            if os.path.exists(logo_path):
                try:
                    # ty(0.2) = top area; logo placed downward from that point
                    c.drawImage(logo_path,
                                tx(0.3), ty(0.3) - logo_h_cm*cm*sf,
                                width=logo_w_cm*cm*sf, height=logo_h_cm*cm*sf,
                                preserveAspectRatio=True, mask='auto')
                except Exception as e:
                    logging.error(f"Logo draw failed: {e}")
                    dstr(0.5, 1.5, "Kawan Lama.", font="Helvetica-Bold", size=14)
            else:
                dstr(0.5, 1.5, "Kawan Lama.", font="Helvetica-Bold", size=14)

            # ===================== HEADER BOX =====================
            # hdr_w is ALWAYS the A4 layout constant (27.7 virtual cm)
            # sf handles the physical scaling; do NOT derive hdr_w from page_w
            hdr_w = (landscape(A4)[0] - 2*cm) / cm   # = 27.7 virtual cm
            drect(0, 0, hdr_w, 2.8)
            dline(5.5, 0, 5.5, 2.8)

            hdr_x = 5.5
            hdr_inner_w = hdr_w - hdr_x

            dstr(hdr_x + hdr_inner_w/2, 0.8, "BUKTI PENGELUARAN KAS / BANK",
                 font="Helvetica-Bold", size=14, align="center")
            dstr(hdr_x + hdr_inner_w - 0.2, 0.4, "Dokumen # :", size=8, align="right")
            dstr(hdr_x + hdr_inner_w - 0.2, 0.8, "F-SS9.27-01 (01)",
                 font="Helvetica-Bold", size=9, align="right")

            dline(hdr_x, 1.2, hdr_x + hdr_inner_w, 1.2)
            dline(hdr_x + hdr_inner_w - 4, 0, hdr_x + hdr_inner_w - 4, 1.2)

            # Checkboxes
            cb_y1, cb_y2, cb_y3 = 1.6, 2.1, 2.6
            col1_x = hdr_x + 0.5
            col2_x = hdr_x + 8.0
            col3_x = hdr_x + 15.0

            def dcheckbox(x, y, label, checked=False):
                drect(x, y - 0.3, 0.3, 0.3)
                if checked:
                    dstr(x + 0.15, y - 0.05, "X", font="Helvetica-Bold", size=8, align="center")
                dstr(x + 0.5, y - 0.05, label, size=8)

            dcheckbox(col1_x, cb_y1, "Aspirasi Hidup Indonesia", False)
            dcheckbox(col1_x, cb_y2, "Foods Beverages Indonesia", True)
            dcheckbox(col1_x, cb_y3, "Home Center Indonesia", False)
            dcheckbox(col2_x, cb_y1, "Kawan Lama Inovasi", False)
            dcheckbox(col2_x, cb_y2, "Kawan Lama Sejahtera", False)
            dcheckbox(col2_x, cb_y3, "Krisbow Indonesia", False)
            dcheckbox(col3_x, cb_y1, "Tiga Dua Delapan", False)
            dcheckbox(col3_x, cb_y2, "Toys Games Indonesia", False)
            dcheckbox(col3_x, cb_y3, "Others : ..............................", False)

            # ===================== DETAILS SECTION 1 =====================
            dy = 3.5
            dstr(0, dy, "Dibayarkan ke", size=9)
            dstr(2.8, dy, ":")
            dstr(3.3, dy, f"{self.store_code} - {self.store_name}", font="Helvetica-Bold", size=9)
            dline(3.3, dy + 0.1, 13, dy + 0.1)

            dstr(0, dy + 0.8, "Tanggal", size=9)
            dstr(2.8, dy + 0.8, ":")
            dstr(3.3, dy + 0.8, display_date, font="Helvetica-Bold", size=9)
            dline(3.3, dy + 0.9, 13, dy + 0.9)

            dstr(14.5, dy, "WBS/ IO", size=9)
            dstr(17.5, dy, ":")
            dline(18.0, dy + 0.1, hdr_w, dy + 0.1)

            dstr(14.5, dy + 0.8, "Cost Center", size=9)
            dstr(17.5, dy + 0.8, ":")
            dstr(18.0, dy + 0.8, f"{self.store_code}2801", font="Helvetica-Bold", size=9)
            dline(18.0, dy + 0.9, hdr_w, dy + 0.9)

            # ===================== DETAILS SECTION 2 =====================
            b2_y = 4.8
            drect(0, b2_y, hdr_w, 1.6)

            dstr(0.2, b2_y + 0.6, "No. Cek", size=9)
            dstr(2.8, b2_y + 0.6, ":")
            dstr(3.3, b2_y + 0.6, entry.check_number, font="Helvetica-Bold", size=9)
            dline(3.3, b2_y + 0.7, 13, b2_y + 0.7)

            dstr(0.2, b2_y + 1.3, "Jatuh Tempo", size=9)
            dstr(2.8, b2_y + 1.3, ":")
            dline(3.3, b2_y + 1.4, 13, b2_y + 1.4)

            dstr(14.5, b2_y + 0.6, "Bank", size=9)
            dstr(17.5, b2_y + 0.6, ":")
            dline(18.0, b2_y + 0.7, hdr_w, b2_y + 0.7)

            dstr(14.5, b2_y + 1.3, "A/C", size=9)
            dstr(17.5, b2_y + 1.3, ":")
            dline(18.0, b2_y + 1.4, hdr_w, b2_y + 1.4)

            # ===================== MAIN TABLE =====================
            ty_tbl = 6.6
            row_h = 0.8
            col_no = 1.2
            col_rek = 5.0
            col_jum = 4.5
            col_uraian = hdr_w - col_no - col_rek - col_jum

            x_no = 0
            x_rek = col_no
            x_uraian = col_no + col_rek
            x_jum = col_no + col_rek + col_uraian

            def draw_row(y_off, t1, t2, t3, t4, bold=False):
                fnt = "Helvetica-Bold" if bold else "Helvetica"
                sz = 9 if bold else 8
                drect(x_no, y_off, col_no, row_h)
                drect(x_rek, y_off, col_rek, row_h)
                drect(x_uraian, y_off, col_uraian, row_h)
                drect(x_jum, y_off, col_jum, row_h)
                if t1: dstr(x_no + col_no/2, y_off + 0.5, t1, font=fnt, size=sz, align="center")
                if t2: dstr(x_rek + col_rek/2, y_off + 0.5, t2, font=fnt, size=sz, align="center")
                if t3:
                    if bold:
                        dstr(x_uraian + col_uraian/2, y_off + 0.5, t3, font=fnt, size=sz, align="center")
                    else:
                        dstr(x_uraian + 0.2, y_off + 0.5, t3, font=fnt, size=sz)
                if t4: dstr(x_jum + col_jum/2, y_off + 0.5, t4, font=fnt, size=sz, align="center")

            # Header row
            draw_row(ty_tbl, "", "", "", "", bold=True)
            dstr(x_no + col_no/2, ty_tbl + 0.5, "NO.", font="Helvetica-Bold", size=9, align="center")
            dstr(x_rek + col_rek/2, ty_tbl + 0.35, "NO. REK LAWAN", font="Helvetica-Bold", size=9, align="center")
            dstr(x_rek + col_rek/2, ty_tbl + 0.65, "(DEBIT)", font="Helvetica-Bold", size=9, align="center")
            dstr(x_uraian + col_uraian/2, ty_tbl + 0.5, "U R A I A N", font="Helvetica-Bold", size=9, align="center")
            dstr(x_jum + col_jum/2, ty_tbl + 0.5, "JUMLAH (RP)", font="Helvetica-Bold", size=9, align="center")

            # Data row
            formatted_amount = f"{entry.amount:,.0f}".replace(',', '.')
            draw_row(ty_tbl + row_h, "1", entry.counterparty_account, entry.description.upper(), formatted_amount)

            # Empty rows
            for i in range(2, 8):
                draw_row(ty_tbl + row_h * i, "", "", "", "")

            # ===================== TERBILANG =====================
            fy = ty_tbl + row_h * 8
            dstr(0.2, fy + 0.8, "TERBILANG", font="Helvetica-Bold", size=9)
            dstr(3.5, fy + 0.8, ":", font="Helvetica-Bold", size=9)

            c.setFillColorRGB(0.9, 0.9, 0.9)
            drect(4, fy + 0.2, x_jum - 4 - 0.5, 1.2)
            c.setFillColorRGB(0, 0, 0)

            terbilang_text = f"# {terbilang(int(entry.amount))} RUPIAH #"
            dstr(4 + (x_jum - 4 - 0.5)/2, fy + 0.9, terbilang_text,
                 font="Helvetica-Bold", size=9, align="center")

            drect(x_jum, fy + 0.2, col_jum, 1.2)
            dstr(x_jum + col_jum/2, fy + 0.9, formatted_amount,
                 font="Helvetica-Bold", size=10, align="center")

            drect(x_jum, fy + 1.6, col_jum, 0.8)
            dstr(x_jum + col_jum/2, fy + 2.1, "Accounting",
                 font="Helvetica-Bold", size=9, align="center")
            drect(x_jum, fy + 2.4, col_jum, 2.5)

            # ===================== SIGNATURES =====================
            sig_y = fy + 2.0
            sig_w = 4.5

            def draw_sig(x, label, is_date=False, employee_info=""):
                dstr(x + sig_w/2, sig_y, label, size=9, align="center")
                dstr(x + 0.5, sig_y + 0.5, "Tgl.", size=8)
                if is_date:
                    dstr(x + 1.2, sig_y + 0.5, short_date, size=8)
                if employee_info:
                    dstr(x + sig_w/2, sig_y + 2.7, employee_info,
                         font="Helvetica-Bold", size=8, align="center")
                dline(x + 0.5, sig_y + 3.0, x + sig_w - 0.5, sig_y + 3.0)

            draw_sig(0, "Diajukan oleh,", True, entry.diajukan_info)
            draw_sig(5.5, "Disetujui oleh,", False, entry.disetujui_info)
            draw_sig(11, "Diberikan oleh,", False, entry.diberikan_info)
            draw_sig(16.5, "Diterima oleh,", False, entry.diterima_info)

            c.save()
            return filepath

        except Exception as e:
            logging.error(f"Error generating BPK PDF: {e}")
            raise

    def print_pdf(self, filepath: str, printer_name: str = "", parent: QWidget = None):
        """
        Print PDF to the specified printer.
        Strategy:
          1. SumatraPDF  (most reliable, silent, supports printer name)
          2. Adobe Reader (silent print via command line)
          3. win32print   (temporarily swap default printer, print, restore)
          4. os.startfile (last resort, uses default printer)
        """
        import threading, time

        def _try_sumatra(pdf, printer):
            candidates = [
                r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
                os.path.join(BASE_DIR, "SumatraPDF.exe"),
            ]
            for exe in candidates:
                if os.path.exists(exe):
                    cmd = [exe, "-print-to", printer, "-print-settings", "fit", pdf] if printer else [exe, "-print-to-default", "-print-settings", "fit", pdf]
                    subprocess.Popen(cmd)
                    return True
            return False

        def _try_foxit(pdf, printer):
            candidates = [
                r"C:\Program Files (x86)\Foxit Software\Foxit PDF Editor\FoxitPDFEditor.exe",
                r"C:\Program Files\Foxit Software\Foxit PDF Editor\FoxitPDFEditor.exe",
                r"C:\Program Files (x86)\Foxit Software\Foxit PDF Reader\FoxitPDFReader.exe",
                r"C:\Program Files\Foxit Software\Foxit PDF Reader\FoxitPDFReader.exe",
                r"C:\Program Files (x86)\Foxit Software\Foxit Reader\FoxitReader.exe",
                r"C:\Program Files\Foxit Software\Foxit Reader\FoxitReader.exe",
            ]
            for exe in candidates:
                if os.path.exists(exe):
                    if printer:
                        subprocess.Popen([exe, "/t", pdf, printer], shell=False)
                    else:
                        subprocess.Popen([exe, "/p", pdf], shell=False)
                    return True
            return False

        def _try_acrord(pdf, printer):
            candidates = [
                r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            ]
            for exe in candidates:
                if os.path.exists(exe):
                    subprocess.Popen(f'"{exe}" /t "{pdf}" "{printer}"' if printer else f'"{exe}" /p "{pdf}"', shell=True)
                    return True
            return False

        def _try_win32print(pdf, printer):
            """Temporarily set default printer, send print via ShellExecuteW."""
            try:
                import win32print
                import ctypes
                old_default = win32print.GetDefaultPrinter()
                if printer and printer != old_default:
                    win32print.SetDefaultPrinter(printer)
                # Use ShellExecuteW with 'print' verb (more robust than os.startfile)
                result = ctypes.windll.shell32.ShellExecuteW(None, "print", pdf, None, None, 1)
                def restore(prev):
                    time.sleep(4)
                    try:
                        win32print.SetDefaultPrinter(prev)
                    except Exception:
                        pass
                threading.Thread(target=restore, args=(old_default,), daemon=True).start()
                return result > 32  # >32 means success
            except ImportError:
                return False
            except Exception as e:
                logging.warning(f"win32print swap failed: {e}")
                return False

        if not os.path.exists(filepath):
            if parent:
                QMessageBox.warning(parent, "Tidak Ditemukan", "File PDF tidak ditemukan.")
            return

        try:
            if _try_sumatra(filepath, printer_name):
                if parent:
                    QMessageBox.information(parent, "Print", f"Mencetak via SumatraPDF ke:\n{printer_name or '(default)'}")
                return
            if _try_foxit(filepath, printer_name):
                if parent:
                    QMessageBox.information(parent, "Print", f"Mencetak via Foxit ke:\n{printer_name or '(default)'}")
                return
            if _try_acrord(filepath, printer_name):
                if parent:
                    QMessageBox.information(parent, "Print", f"Mencetak via Adobe Reader ke:\n{printer_name or '(default)'}")
                return
            if _try_win32print(filepath, printer_name):
                if parent:
                    QMessageBox.information(parent, "Print", f"Mengirim ke printer:\n{printer_name or '(default)'}")
                return
            # Last resort: open file for manual print (avoids WinError 1155)
            try:
                os.startfile(filepath)   # 'open' verb — selalu ada asosiasi
                if parent:
                    QMessageBox.information(parent, "Print",
                        "File PDF dibuka di viewer.\n"
                        "Silakan tekan Ctrl+P untuk mencetak.\n\n"
                        "(Tip: Install SumatraPDF untuk cetak otomatis.)")
            except Exception as e2:
                if parent:
                    QMessageBox.warning(parent, "Gagal Cetak",
                        f"Tidak dapat mencetak otomatis.\n"
                        f"Buka file berikut secara manual lalu cetak (Ctrl+P):\n\n{filepath}")
        except Exception as e:
            logging.error(f"print_pdf error: {e}")
            if parent:
                QMessageBox.warning(parent, "Error",
                    f"Gagal cetak:\n{e}\n\nSolusi: Klik 'Buka File' lalu Print manual (Ctrl+P).")

