import os
import logging
from datetime import datetime
from dataclasses import dataclass
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
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
        if not os.path.exists(self.bpk_dir):
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
            
            months = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            month_id = months[dt.month]
            display_date = f"{dt.day} {month_id} {dt.year}"
            short_date = dt.strftime("%d.%m.%y")
            serial = self._get_next_serial()
            
            filename = f"BPK_{date_str}_{self.store_code}_{serial}.pdf"
            filepath = os.path.join(self.bpk_dir, filename)
            
            # The image is landscape
            c = canvas.Canvas(filepath, pagesize=landscape(A4))
            width, height = landscape(A4)
            
            # Margins
            margin_x = 1 * cm
            margin_y = 1 * cm
            
            # Origin top-left
            def draw_rect(x, y, w, h):
                c.rect(margin_x + x*cm, height - margin_y - y*cm - h*cm, w*cm, h*cm)
                
            def draw_line(x1, y1, x2, y2):
                c.line(margin_x + x1*cm, height - margin_y - y1*cm, margin_x + x2*cm, height - margin_y - y2*cm)

            def draw_str(x, y, text, font="Helvetica", size=10, align="left"):
                c.setFont(font, size)
                if align == "center":
                    c.drawCentredString(margin_x + x*cm, height - margin_y - y*cm, text)
                elif align == "right":
                    c.drawRightString(margin_x + x*cm, height - margin_y - y*cm, text)
                else:
                    c.drawString(margin_x + x*cm, height - margin_y - y*cm, text)

            # Draw Logo Area
            logo_path = os.path.join(BASE_DIR, 'assets', 'kawan_lama_logo.png')
            if os.path.exists(logo_path):
                # Try to draw the actual image
                try:
                    c.drawImage(logo_path, margin_x + 0.5*cm, height - margin_y - 2.5*cm, width=4.5*cm, height=2.0*cm, preserveAspectRatio=True, mask='auto')
                except Exception as e:
                    logging.error(f"Failed to draw logo image: {e}")
                    draw_str(0.5, 1.5, "Kawan Lama.", font="Helvetica-Bold", size=14)
                    draw_str(3.5, 1.5, "GROUP", font="Helvetica", size=8)
            else:
                draw_str(0.5, 1.5, "Kawan Lama.", font="Helvetica-Bold", size=14)
                draw_str(3.5, 1.5, "GROUP", font="Helvetica", size=8)
            
            # Top Header Box Outer Border
            hdr_w_full = (width - margin_x * 2)/cm
            draw_rect(0, 0, hdr_w_full, 2.8)
            
            # Vertical line after logo
            draw_line(5.5, 0, 5.5, 2.8)
            
            # Top Header Box Content
            hdr_x = 5.5
            hdr_w = hdr_w_full - hdr_x
            
            # Title
            draw_str(hdr_x + hdr_w/2, 0.8, "BUKTI PENGELUARAN KAS / BANK", font="Helvetica-Bold", size=16, align="center")
            draw_str(hdr_x + hdr_w - 0.2, 0.4, "Dokumen # :", size=9, align="right")
            draw_str(hdr_x + hdr_w - 0.2, 0.8, "F-SS9.27-01 (01)", font="Helvetica-Bold", size=10, align="right")
            
            # Split line in header
            draw_line(hdr_x, 1.2, hdr_x + hdr_w, 1.2)
            draw_line(hdr_x + hdr_w - 4, 0, hdr_x + hdr_w - 4, 1.2) # Vertical line for dok number
            
            # Checkboxes inside header
            cb_y1 = 1.6
            cb_y2 = 2.1
            cb_y3 = 2.6
            col1_x = hdr_x + 0.5
            col2_x = hdr_x + 8.0
            col3_x = hdr_x + 15.0
            
            def draw_checkbox(x, y, label, checked=False):
                draw_rect(x, y - 0.3, 0.3, 0.3)
                if checked:
                    draw_str(x + 0.15, y - 0.05, "X", font="Helvetica-Bold", size=8, align="center")
                draw_str(x + 0.5, y - 0.05, label, size=9)
            
            draw_checkbox(col1_x, cb_y1, "Aspirasi Hidup Indonesia", False)
            draw_checkbox(col1_x, cb_y2, "Foods Beverages Indonesia", True)
            draw_checkbox(col1_x, cb_y3, "Home Center Indonesia", False)
            
            draw_checkbox(col2_x, cb_y1, "Kawan Lama Inovasi", False)
            draw_checkbox(col2_x, cb_y2, "Kawan Lama Sejahtera", False)
            draw_checkbox(col2_x, cb_y3, "Krisbow Indonesia", False)
            
            draw_checkbox(col3_x, cb_y1, "Tiga Dua Delapan", False)
            draw_checkbox(col3_x, cb_y2, "Toys Games Indonesia", False)
            draw_checkbox(col3_x, cb_y3, "Others : ..............................", False)
            
            # Details Section 1
            dy = 3.5
            draw_str(0, dy, "Dibayarkan ke", size=10)
            draw_str(2.8, dy, ":")
            draw_str(3.3, dy, f"{self.store_code} - {self.store_name}", font="Helvetica-Bold", size=10)
            draw_line(3.3, dy + 0.1, 13, dy + 0.1)
            
            draw_str(0, dy + 0.8, "Tanggal", size=10)
            draw_str(2.8, dy + 0.8, ":")
            draw_str(3.3, dy + 0.8, display_date, font="Helvetica-Bold", size=10)
            draw_line(3.3, dy + 0.9, 13, dy + 0.9)
            
            draw_str(14.5, dy, "WBS/ IO", size=10)
            draw_str(17.5, dy, ":")
            draw_line(18.0, dy + 0.1, 26, dy + 0.1)
            
            draw_str(14.5, dy + 0.8, "Cost Center", size=10)
            draw_str(17.5, dy + 0.8, ":")
            draw_str(18.0, dy + 0.8, f"{self.store_code}2801", font="Helvetica-Bold", size=10)
            draw_line(18.0, dy + 0.9, 26, dy + 0.9)
            
            # Details Section 2 (Box)
            b2_y = 4.8
            b2_h = 1.6
            draw_rect(0, b2_y, (width - 2*margin_x)/cm, b2_h)
            
            draw_str(0.2, b2_y + 0.6, "No. Cek", size=10)
            draw_str(2.8, b2_y + 0.6, ":")
            draw_str(3.3, b2_y + 0.6, entry.check_number, font="Helvetica-Bold", size=10)
            draw_line(3.3, b2_y + 0.7, 13, b2_y + 0.7)
            
            draw_str(0.2, b2_y + 1.3, "Jatuh Tempo", size=10)
            draw_str(2.8, b2_y + 1.3, ":")
            draw_line(3.3, b2_y + 1.4, 13, b2_y + 1.4)
            
            draw_str(14.5, b2_y + 0.6, "Bank", size=10)
            draw_str(17.5, b2_y + 0.6, ":")
            draw_line(18.0, b2_y + 0.7, 26, b2_y + 0.7)
            
            draw_str(14.5, b2_y + 1.3, "A/C", size=10)
            draw_str(17.5, b2_y + 1.3, ":")
            draw_line(18.0, b2_y + 1.4, 26, b2_y + 1.4)
            
            # Main Table
            ty = 6.6
            table_w = (width - 2*margin_x)/cm
            row_h = 0.8
            
            # Table columns (widths)
            col_no = 1.2
            col_rek = 5.0
            col_uraian = table_w - col_no - col_rek - 4.5
            col_jum = 4.5
            
            x_no = 0
            x_rek = col_no
            x_uraian = col_no + col_rek
            x_jum = col_no + col_rek + col_uraian
            
            def draw_row(y_offset, text1, text2, text3, text4, is_bold=False):
                fnt = "Helvetica-Bold" if is_bold else "Helvetica"
                sz = 10 if is_bold else 9
                
                # Borders
                draw_rect(x_no, y_offset, col_no, row_h)
                draw_rect(x_rek, y_offset, col_rek, row_h)
                draw_rect(x_uraian, y_offset, col_uraian, row_h)
                draw_rect(x_jum, y_offset, col_jum, row_h)
                
                # Text
                draw_str(x_no + col_no/2, y_offset + 0.5, text1, font=fnt, size=sz, align="center")
                draw_str(x_rek + col_rek/2, y_offset + 0.5, text2, font=fnt, size=sz, align="center")
                
                if is_bold:
                    draw_str(x_uraian + col_uraian/2, y_offset + 0.5, text3, font=fnt, size=sz, align="center")
                else:
                    draw_str(x_uraian + 0.2, y_offset + 0.5, text3, font=fnt, size=sz)
                
                if text4:
                    draw_str(x_jum + col_jum/2, y_offset + 0.5, text4, font=fnt, size=sz, align="center")
                    
            # Header Row
            # Split Uraian and DEBIT into two lines vertically
            draw_row(ty, "", "", "", "", is_bold=True)
            draw_str(x_no + col_no/2, ty + 0.5, "NO.", font="Helvetica-Bold", size=10, align="center")
            draw_str(x_rek + col_rek/2, ty + 0.4, "NO. REK LAWAN", font="Helvetica-Bold", size=10, align="center")
            draw_str(x_rek + col_rek/2, ty + 0.7, "(DEBIT)", font="Helvetica-Bold", size=10, align="center")
            draw_str(x_uraian + col_uraian/2, ty + 0.5, "U R A I A N", font="Helvetica-Bold", size=10, align="center")
            draw_str(x_jum + col_jum/2, ty + 0.5, "JUMLAH (RP)", font="Helvetica-Bold", size=10, align="center")
            
            # Content Rows
            formatted_amount = f"{entry.amount:,.0f}".replace(',', '.')
            draw_row(ty + row_h, "1", entry.counterparty_account, entry.description.upper(), formatted_amount)
            
            # Empty rows (no row number if no content)
            for i in range(2, 8):
                draw_row(ty + row_h * i, "", "", "", "")
                
            # Footer / Terbilang
            fy = ty + row_h * 8
            
            draw_str(0.2, fy + 0.8, "TERBILANG", font="Helvetica-Bold", size=10)
            draw_str(3.5, fy + 0.8, ":", font="Helvetica-Bold", size=10)
            
            # Gray Box
            c.setFillColorRGB(0.9, 0.9, 0.9) # Light gray
            draw_rect(4, fy + 0.2, x_jum - 4 - 0.5, 1.2)
            c.setFillColorRGB(0, 0, 0)
            
            amount_words = terbilang(int(entry.amount)) + " RUPIAH"
            terbilang_text = f"# {amount_words} #"
            draw_str(4 + (x_jum - 4 - 0.5)/2, fy + 0.9, terbilang_text, font="Helvetica-Bold", size=10, align="center")
            
            # Amount Box
            draw_rect(x_jum, fy + 0.2, col_jum, 1.2)
            draw_str(x_jum + col_jum/2, fy + 0.9, formatted_amount, font="Helvetica-Bold", size=11, align="center")
            
            # Accounting Box
            draw_rect(x_jum, fy + 1.6, col_jum, 0.8)
            draw_str(x_jum + col_jum/2, fy + 2.1, "Accounting", font="Helvetica-Bold", size=10, align="center")
            draw_rect(x_jum, fy + 2.4, col_jum, 2.5) # Empty box for stamp/sign
            
            # Signatures area
            sig_y = fy + 2.0
            sig_w = 4.5
            
            def draw_sig(x, label, is_date=False, employee_info=""):
                draw_str(x + sig_w/2, sig_y, label, size=10, align="center")
                
                if is_date:
                    draw_str(x + 0.5, sig_y + 0.5, f"Tgl.      {short_date}", size=9)
                else:
                    draw_str(x + 0.5, sig_y + 0.5, "Tgl.", size=9)
                
                # Employee info ABOVE the signature line
                if employee_info:
                    draw_str(x + sig_w/2, sig_y + 2.7, employee_info, font="Helvetica-Bold", size=9, align="center")
                
                # Signature line
                draw_line(x + 0.5, sig_y + 3.0, x + sig_w - 0.5, sig_y + 3.0)
            
            draw_sig(0, "Diajukan oleh,", True, entry.diajukan_info)
            draw_sig(5.5, "Disetujui oleh,", False, entry.disetujui_info)
            draw_sig(11, "Diberikan oleh,", False, entry.diberikan_info)
            draw_sig(16.5, "Diterima oleh,", False, entry.diterima_info)
            
            # Finalize
            c.save()
            return filepath
            
        except Exception as e:
            logging.error(f"Error generating BPK PDF: {e}")
            raise e

    def print_pdf(self, filepath: str, parent: QWidget = None):
        import platform
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        
        try:
            if platform.system() == "Windows":
                os.startfile(filepath, "print")
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(filepath))
        except Exception as e:
            logging.error(f"Failed to print PDF: {e}")
            if parent:
                QMessageBox.warning(parent, "Print Error", f"Gagal mencetak dokumen:\n{str(e)}\n\nSilakan buka file secara manual.")
            else:
                raise e
