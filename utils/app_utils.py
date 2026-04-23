import re

#def get_base_article_name(full_name: str) -> str:
#    """Mengekstrak nama dasar dari artikel, menghapus info ukuran dan suhu."""
#    if not isinstance(full_name, str):
#        return ""
#    base = full_name.replace('CT ', '').strip()
#    base = re.sub(r'\s*-\s*(Cold|Hot|Large|Regular|Small|Cup|Popcan).*$', '', base, flags=re.IGNORECASE).strip()
#    return base
def get_base_article_name(full_name: str) -> str:
    """
    Membersihkan nama artikel secara agresif untuk pengelompokan laporan.
    Menghilangkan:
    1. Kode awalan (CT, PC, dll).
    2. Ukuran (L, R, Large, Regular, Small).
    3. Suhu (Hot, Cold, Ice).
    4. Tanda baca pemisah (-, (), []).
    """
    if not isinstance(full_name, str):
        return str(full_name)
        
    # 1. Normalisasi: Ubah ke Huruf Besar untuk memudahkan pencarian
    name = full_name.upper()
    
    # 2. Daftar kata kunci yang dianggap "SAMPAH" (Varian/Ukuran/Kode)
    # Urutkan dari yang terpanjang agar tidak salah potong (misal: "LARGE" dulu, baru "L")
    keywords_to_remove = [
        r'\bLARGE\b', r'\bREGULAR\b', r'\bSMALL\b', r'\bMEDIUM\b',
        r'\bHOT\b', r'\bCOLD\b', r'\bICE\b', r'\bPANAS\b', r'\bDINGIN\b',
        r'\bXXL\b', r'\bXL\b', 
        r'\b\(L\)\b', r'\b\(M\)\b', r'\b\(S\)\b', r'\b\(R\)\b', # (L), (R) di tengah kalimat
        r'\bCT\b', r'\bPC\b', # Kode awalan umum (CT=Chatime?, PC=Popcan?)
        r'\bLS\b', # Less Sugar?
        r'\bNO ICE\b', r'\bLESS ICE\b'
    ]
    
    # 3. Hapus kata kunci tersebut dari string
    for pattern in keywords_to_remove:
        name = re.sub(pattern, '', name)

    # 4. Pembersihan Lanjutan (Regex)
    # Hapus karakter dalam kurung di akhir: "MENU (L)" -> "MENU"
    name = re.sub(r'\s*\(.*?\)$', '', name)
    
    # Hapus huruf ukuran tunggal di akhir string: "MENU L" -> "MENU"
    # (Hati-hati: \bL\b berarti huruf L yang berdiri sendiri)
    name = re.sub(r'\s+\b[LMRS]\b$', '', name) 

    # 5. Bersihkan tanda baca sisa (misal: "MENU - - ")
    # Ganti tanda hubung, kurung, dll dengan spasi
    name = re.sub(r'[-–_()\[\]]', ' ', name)
    
    # 6. Rapikan Spasi (Hapus spasi ganda dan spasi di ujung)
    name = re.sub(r'\s+', ' ', name).strip()
    
    # 7. Kembalikan ke format Judul (Title Case) agar rapi di laporan
    return name.title()

def format_article_name_short(full_name: str) -> str:
    """Memformat nama artikel menjadi versi singkat, contoh: 'Choco Mousse (L)'."""
    if not isinstance(full_name, str):
        return ""
        
    base_name = get_base_article_name(full_name)
    size_code = ''
    
    name_lower = full_name.lower()
    if 'large' in name_lower:
        size_code = '(L)'
    elif 'regular' in name_lower:
        size_code = '(R)'
    elif 'small' in name_lower:
        size_code = '(S)'
    # --- PENAMBAHAN: Logika untuk Popcan ---
    elif 'popcan' in name_lower:
        size_code = '(PC)'
        
    return f'{base_name} {size_code}'.strip()

def trim_article_name(full_name: str) -> str:
    if not isinstance(full_name, str):
        return ""
    parts = full_name.split(' - ')
    main_menu = parts[0].strip()
    lower_full_name = full_name.lower()
    if 'large' in lower_full_name:
        return f"{main_menu} (L)"
    elif 'regular' in lower_full_name:
        return f"{main_menu} (R)"
    elif 'small' in lower_full_name:
        return f"{main_menu} (S)"
    else:
        return main_menu

def calculate_ac(sales, tc):
    if not isinstance(sales, (int, float)) or not isinstance(tc, (int, float)):
        return 0.0
    return sales / tc if tc > 0 else 0.0

def calculate_growth(current, previous):
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    if previous > 0:
        return (current - previous) / previous
    if previous == 0 and current > 0:
        return 9.99 
    if previous == 0 and current == 0:
        return 0.0
    return None