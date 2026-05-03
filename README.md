# Repot.in — Sales Report Dashboard for Aurora

<p align="center">
  <img src="screenshot.png" alt="Repot.in Dashboard" width="800"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-5.1.1-blue?style=flat-square" alt="Version"/>
  <img src="https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square&logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/UI-PyQt5-green?style=flat-square" alt="PyQt5"/>
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square&logo=windows" alt="Platform"/>
  <img src="https://img.shields.io/badge/license-Private-red?style=flat-square" alt="License"/>
</p>

> Aplikasi desktop manajemen dan analitik laporan penjualan harian untuk toko ritel yang menggunakan sistem POS **Aurora**. Repot.in menyederhanakan proses pelaporan dari input CSV mentah hingga laporan siap kirim — lengkap dengan dashboard real-time, cetak BPK, analisis promo, dan banyak lagi.

---

## Fitur Utama

| Modul | Deskripsi |
|---|---|
| 📈 **Dashboard** | Ringkasan performa harian & MTD dengan indikator forecast vs. actuals |
| 📋 **Sales Report** | Generate laporan penjualan dari file CSV Aurora secara otomatis |
| 🔄 **Sync Aurora** | Scrape & download laporan langsung dari portal web Aurora |
| 💰 **Kas & Tips** | Pencatatan kas masuk/keluar dan manajemen tips karyawan |
| 📦 **Order Barang** | Manajemen dan tracking permintaan order ke warehouse |
| 🗑️ **Waste Conversion** | Konversi dan pencatatan waste produk dengan resep konfigurasi |
| 🧾 **BPK Generator** | Cetak Bukti Pengeluaran Kas (BPK) dalam format PDF otomatis |
| 📅 **Edspayed** | Kalkulator dan tracker tanggal kedaluwarsa produk |
| 💧 **Minum (Periode)** | Tracker konsumsi minuman per periode shift |
| ☁️ **Upload Google Sheet** | Sinkronisasi data laporan ke Google Spreadsheet |
| 📢 **Broadcast System** | Notifikasi dan pengumuman real-time dari developer |
| 📝 **Notes & Todo List** | Catatan dan daftar tugas internal per outlet |
| 💬 **Feedback** | Kirim laporan bug atau request fitur langsung ke Google Sheets |

---

## Screenshots

<table>
  <tr>
    <td align="center"><img src="screenshot.png" alt="Dashboard Utama" width="350"/><br/><sub>Dashboard Utama</sub></td>
    <td align="center"><img src="screenshot_sidebar_expanded.png" alt="Sidebar Expanded" width="350"/><br/><sub>Sidebar Expanded</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshot_kastips.png" alt="Kas & Tips" width="350"/><br/><sub>Kas & Tips</sub></td>
    <td align="center"><img src="screenshot_todo_list.png" alt="Todo List" width="350"/><br/><sub>Todo List</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="screenshot_notes.png" alt="Notes" width="350"/><br/><sub>Notes</sub></td>
    <td align="center"><img src="screenshot_marquee.png" alt="Marquee Info" width="350"/><br/><sub>Marquee Info</sub></td>
  </tr>
</table>

---

## Arsitektur Proyek

```
repot.in/
├── main_app.py              # Entry point & controller utama (QMainWindow)
│
├── modules/                 # Business logic & backend
│   ├── report_processor.py  # Pemrosesan data CSV & kalkulasi laporan
│   ├── database_manager.py  # SQLite local database (kas, tips, dll)
│   ├── order_db_manager.py  # Database order barang
│   ├── aurora_scraper.py    # Web scraper portal Aurora (PyQt WebEngine)
│   ├── config_manager.py    # Manajemen konfigurasi (INI + JSON)
│   ├── bpk_generator.py     # Generator PDF Bukti Pengeluaran Kas
│   ├── feedback_manager.py  # Pengiriman feedback ke Google Sheets
│   ├── workers.py           # QThread workers (file import, GSheet upload)
│   ├── notification_manager.py
│   ├── broadcast_manager.py
│   ├── asset_manager.py
│   ├── chat_it_fetcher.py
│   └── validation_manager.py
│
├── ui/                      # Tampilan antarmuka (PyQt5)
│   ├── ui_components.py     # Komponen UI utama (sidebar, dashboard cards)
│   ├── dashboard_tab.py     # Tab Dashboard dengan grafik & KPI
│   ├── sales_report_tab.py  # Tab laporan penjualan
│   ├── bpk_tab.py           # Tab manajemen BPK
│   ├── bpk_dialog.py        # Dialog cetak & pratinjau BPK
│   ├── order_tab_ui.py      # Tab order barang
│   ├── waste_conversion_tab.py
│   ├── minum_tab.py
│   ├── dialogs.py           # Dialog-dialog (config, kalkulator, log, dll)
│   ├── downloader_dialog.py
│   ├── feedback_dialog.py
│   ├── notes_dialog.py
│   └── todo_dialog.py
│
├── utils/                   # Utilitas & konstanta
│   ├── constants.py         # Konstanta global (path, versi, nama kolom)
│   ├── employee_utils.py    # Manajemen data karyawan & autentikasi
│   ├── chart_utils.py       # Utilitas pembuatan grafik (Matplotlib)
│   ├── app_utils.py
│   └── app_settings_utils.py
│
├── config/                  # File konfigurasi runtime
│   ├── app_settings.ini     # Konfigurasi utama aplikasi
│   ├── report_templates.json
│   ├── waste_recipes.json
│   ├── edspayed_data.json
│   └── placeholders.json
│
├── assets/                  # Aset statis
│   ├── images/              # Ikon, logo, splash screen
│   └── styles/              # Tema QSS (light & dark)
│
├── data/                    # Data runtime (SQLite, log, JSON)
├── downloads/               # File master data yang diunduh
└── version.json             # Metadata versi untuk auto-update checker
```

---

## Cara Menjalankan (Development)

### Prasyarat

- Python **3.10+**
- Windows 10/11 (karena integrasi printer dan PyQt5 WebEngine)

### Instalasi

```bash
# 1. Clone repository
git clone https://github.com/jsteds/repot.in.git
cd repot.in

# 2. Buat virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependensi
pip install -r requirements.txt
```

### Menjalankan Aplikasi

```bash
python main_app.py
```

---

## 📦 Dependensi Utama

| Library | Kegunaan |
|---|---|
| `PyQt5` | Framework UI desktop |
| `PyQtWebEngine` | Web scraping Aurora via embedded browser |
| `pandas` | Pemrosesan dan analisis data CSV |
| `matplotlib` | Visualisasi grafik dashboard |
| `reportlab` / `fpdf2` | Generasi dokumen PDF (BPK) |
| `requests` | HTTP calls (feedback, broadcast, update check) |
| `openpyxl` | Baca/tulis file Excel (master data) |

> ⚠️ File `requirements.txt` tidak disertakan di repo ini. Lihat daftar import di `main_app.py` dan subfolder untuk daftar lengkap.

---

## Konfigurasi Pertama Kali

1. **Jalankan aplikasi** → akan muncul dialog perjanjian EULA.
2. Buka menu **File → Konfigurasi** (Ctrl+,) untuk mengisi:
   - `Site Code` — kode outlet Anda
   - `Google Sheet ID` — untuk fitur upload laporan (opsional)
   - Konfigurasi printer BPK
3. Buka menu **File → Unduh File Online** untuk mengunduh asset pendukung (template, ikon, dll) dari Google Drive.

---

## Alur Penggunaan Harian

```
1. Buka Repot.in
      ↓
2. Import Data:
   - [Otomatis] File → Sync Data Aurora  ← scrape langsung dari web Aurora
   - [Manual]   File → Import Data CSV   ← pilih file dari komputer
      ↓
3. Laporan otomatis di-generate di tab Sales Report
      ↓
4. Salin laporan → paste ke grup WhatsApp / media lain
      ↓
5. (Opsional) Upload ke Google Sheet via tombol ☁
```

---

## Fitur BPK (Bukti Pengeluaran Kas)

- Input nama karyawan, nominal, dan keperluan
- Generate PDF berformat A4 (emulasi continuous form)
- Dukungan printer: **Foxit PDF Reader**, **SumatraPDF**, atau printer sistem default
- Mendukung cetak ulang dengan pilihan printer

---

## Sistem Auto-Update

Aplikasi secara otomatis memeriksa versi terbaru melalui URL yang dikonfigurasi di `version.json`. Jika versi baru tersedia, notifikasi akan muncul dengan tautan unduh ke Google Drive.

```
Versi Saat Ini: 5.1.1
URL Checker   : Google Drive (via version.json)
Download      : https://drive.google.com/drive/folders/1rwyOpgKzgOpoJvAG-b0yPxETG09O81ma
```

---

## Tema Antarmuka

Repot.in mendukung dua tema:

| Tema | Cara Aktifkan |
|---|---|
| ☀️ Terang (Light) | Menu Tampilan → Tema Terang |
| 🌙 Gelap (Dark) | Menu Tampilan → Tema Gelap |

File tema QSS dapat diunduh/diperbarui melalui fitur **Unduh File Online**.

---

## Feedback & Bug Report

Gunakan menu **Bantuan → Kirim Feedback / Lapor Bug** di dalam aplikasi. Feedback akan langsung terkirim ke Google Sheets developer. Jika offline, data tersimpan secara lokal dan dikirim otomatis saat koneksi pulih.

---

## 👥 Kontributor

- **[@jsteds](https://github.com/jsteds)** — Lead Developer
- **[@e001red-coder](https://github.com/e001red-coder)** — Co-Developer

---

## 📄 Lisensi

Proyek ini bersifat **privat** dan digunakan secara internal. Distribusi tanpa izin tidak diperkenankan.

---

<p align="center">
  Dibuat dengan ❤️ untuk memudahkan pekerjaan tim operasional citemmm :p
</p>
