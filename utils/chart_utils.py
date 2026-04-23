# chart_utils.py
import pandas as pd
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from datetime import datetime
from utils.constants import COL_ARTICLE_NAME, COL_QUANTITY, COL_NET_PRICE

plt.style.use('seaborn-v0_8-pastel')
plt.rcParams.update({'font.size': 8, 'font.family': 'Segoe UI', 'figure.autolayout': True})

def create_all_charts(report_data, payments_df, transactions_df, db_manager, config_manager):
    """
    Membuat semua objek Figure untuk setiap grafik dan mengembalikannya dalam dictionary.
    """
    charts = {}
    site_code = config_manager.get_config().get('site_code')

    try:
        charts["Perbandingan Sales vs Target"] = plot_sales_vs_target(db_manager, config_manager, site_code)
        charts["Perbandingan Ojol vs Instore"] = plot_ojol_vs_instore(report_data)
        charts["SSG MTD vs Last Year"] = plot_ssg_mtd(report_data)
        charts["Sales All Channel"] = plot_sales_all_channel(report_data)
        charts["Tren Sales Harian"] = plot_daily_sales_trend(payments_df)
        charts["Top Menu Harian"] = plot_top_menu_daily(transactions_df)
        charts["LTB (Large, Topping, Bundling)"] = plot_ltb(report_data)
    except Exception as e:
        logging.error(f"Gagal membuat salah satu grafik: {e}", exc_info=True)
        # Jika ada error, kita tetap kembalikan chart yang berhasil dibuat
    
    return charts
    
def plot_sales_vs_target(db_manager, config_manager, site_code):
    """Grafik 1: Perbandingan Nett Sales vs Target Bulanan."""
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_title('Perbandingan Nett Sales vs Target Bulanan')

    all_history = db_manager.get_all_history_for_site(site_code)
    if not all_history:
        ax.text(0.5, 0.5, 'Tidak ada data histori untuk ditampilkan', ha='center', va='center')
    else:
        df = pd.DataFrame(all_history)
        df['tanggal'] = pd.to_datetime(df['tanggal'])
        df['tahun_bulan'] = df['tanggal'].dt.to_period('M')
        monthly_sales = df.groupby('tahun_bulan')['net_sales'].sum()
        monthly_targets_config = config_manager.get_monthly_targets()
        month_labels = [period.strftime('%b %Y') for period in monthly_sales.index]
        sales_values = monthly_sales.values
        target_values = [monthly_targets_config.get(period.month, 0) for period in monthly_sales.index]
        x = range(len(month_labels))
        ax.bar([i - 0.2 for i in x], sales_values, width=0.4, label='Actual Nett Sales', color='#42A5F5')
        ax.bar([i + 0.2 for i in x], target_values, width=0.4, label='Target Sales', color='#FFA726')
        ax.set_ylabel('Nett Sales (Rp)')
        ax.set_xticks(x)
        ax.set_xticklabels(month_labels, rotation=45, ha="right")
        ax.legend()
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val/1e6)}Jt" if val >= 1e6 else f"{int(val/1e3)}Rb"))
    
    fig.tight_layout()
    return fig

def plot_ojol_vs_instore(report_data):
    """Grafik 2: Perbandingan Ojol vs Instore (MTD)."""
    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    sales_ojol = report_data.get('mtd_sales_ojol', 0)
    sales_instore = report_data.get('mtd_sales_instore', 0)
    
    if sales_ojol + sales_instore == 0:
        ax.text(0.5, 0.5, 'Tidak ada data penjualan Ojol atau Instore', ha='center', va='center')
    else:
        labels = ['Instore', 'Ojol']
        sizes = [sales_instore, sales_ojol]
        ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=['#66BB6A', '#FFCA28'])
        ax.axis('equal')
    
    ax.set_title('Kontribusi Sales MTD: Ojol vs Instore')
    return fig

def plot_ssg_mtd(report_data):
    """Grafik 3: Perbandingan Sales MTD vs MTD Tahun Lalu."""
    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    # --- PERBAIKAN: Ambil data langsung dari report_data ---
    mtd_nett_sales = report_data.get('mtd_nett_sales', 0)
    ly_nett_mtd = report_data.get('ly_nett_mtd', 0)
    
    labels = ['MTD Tahun Lalu', 'MTD Saat Ini']
    values = [ly_nett_mtd, mtd_nett_sales]
    
    bars = ax.bar(labels, values, color=['#BDBDBD', '#7986CB'])
    ax.set_ylabel('Nett Sales (Rp)')
    ax.set_title('Perbandingan Sales MTD vs Tahun Lalu (SSG MTD)')
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val/1e6)}Jt"))
    
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height/1e6)} Jt', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    return fig

def plot_sales_all_channel(report_data):
    """Grafik 4: Pie chart Sales untuk semua channel."""
    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    channels = {
        'Instore': report_data.get('mtd_sales_instore', 0),
        'GoBiz': report_data.get('mtd_sales_gobiz', 0),
        'GrabFood': report_data.get('mtd_sales_grab', 0),
        'ShopeeFood': report_data.get('mtd_sales_shopeefood', 0),
        'FNB Order': report_data.get('mtd_fnb_order_sales', 0)
    }
    
    # Saring channel yang penjualannya > 0
    sales_data = {label: value for label, value in channels.items() if value > 0}
    
    if not sales_data:
        ax.text(0.5, 0.5, 'Tidak ada data penjualan per channel', ha='center', va='center')
    else:
        ax.pie(sales_data.values(), labels=sales_data.keys(), autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        
    ax.set_title('Kontribusi Penjualan MTD per Channel')
    return fig

def plot_daily_sales_trend(payments_df):
    """Grafik 5: Tren sales harian dalam bulan berjalan."""
    fig = Figure(figsize=(8, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    if payments_df.empty or 'Tanggal' not in payments_df.columns:
        ax.text(0.5, 0.5, 'Tidak ada data harian untuk ditampilkan', ha='center', va='center')
    else:
        daily_sales = payments_df.groupby('Tanggal')['Amount'].sum() / 1.1 # Nett Sales
        ax.plot(daily_sales.index, daily_sales.values, marker='o', linestyle='-')
        ax.set_ylabel('Nett Sales (Rp)')
        ax.set_xlabel('Tanggal')
        ax.grid(True, linestyle='--', alpha=0.6)
        fig.autofmt_xdate() # Rotasi tanggal otomatis
        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val/1e6)}Jt"))
        
    ax.set_title('Tren Penjualan Nett Harian (Periode Terfilter)')
    return fig

def plot_top_menu_daily(transactions_df):
    """Grafik 6: Tren menu paling banyak terjual (harian)."""
    fig = Figure(figsize=(8, 4.5), dpi=100)
    ax = fig.add_subplot(111)
    
    latest_date = transactions_df['Created Date'].max().date()
    daily_trx = transactions_df[transactions_df['Created Date'].dt.date == latest_date]
    
    if daily_trx.empty:
        ax.text(0.5, 0.5, 'Tidak ada data transaksi harian', ha='center', va='center')
    else:
        top_5 = daily_trx.groupby(COL_ARTICLE_NAME)[COL_QUANTITY].sum().nlargest(5).sort_values()
        ax.barh(top_5.index, top_5.values, color='#81C784')
        ax.set_xlabel('Kuantitas Terjual')
        for index, value in enumerate(top_5):
            ax.text(value, index, f' {value}')
            
    ax.set_title(f'Top 5 Menu Terlaris (Qty) - {latest_date.strftime("%d %b %Y")}')
    fig.tight_layout()
    return fig

def plot_ltb(report_data):
    """Grafik 7: Perbandingan LTB (Large, Topping, Bundling)."""
    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    large_qty = report_data.get('mtd_qty_large', 0)
    topping_qty = report_data.get('mtd_qty_topping', 0)
    bundling_sales = report_data.get('mtd_ouast_sales', 0)
    
    labels = ['Large (Qty)', 'Topping (Qty)']
    values = [large_qty, topping_qty]
    
    # Hanya tambahkan Bundling jika datanya ada
    if bundling_sales > 0:
        labels.append('Bundling (Sales)')
        values.append(bundling_sales)
    
    bars = ax.bar(labels, values, color=['#29B6F6', '#FFEE58', '#EF5350'])
    ax.set_ylabel('Jumlah / Nilai (Rp)')
    ax.set_title('Perbandingan LTB (MTD)')
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height):,}', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    return fig