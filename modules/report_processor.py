import pandas as pd
from datetime import datetime, date, timedelta
import logging
import calendar
import json
import re
from utils.app_utils import format_article_name_short, get_base_article_name
from dateutil.relativedelta import relativedelta
from utils.constants import (
    MOP_CODE_GOBIZ, MOP_CODE_GRAB, MOP_CODE_SHOPEEFOOD, OJOL_MOP_CODES,
    LARGE_CUP_KEYWORDS, REGULAR_CUP_KEYWORDS, TOPPING_KEYWORD, OUAST_KEYWORD,
    COL_RECEIPT_NO, COL_CREATED_DATE, COL_AMOUNT, COL_MOP_NAME, COL_MOP_CODE,
    COL_ARTICLE_NAME, COL_NET_PRICE, COL_QUANTITY, COL_PROMOTION_NAME,
    COL_PROMOTION_AMOUNT, COL_SITE_CODE, COL_CHANNEL, COL_MERCHANDISE_NAME,
    COL_PRODUCT_GROUP_NAME, NO_DATA_FOR_SECTION, NO_DATA_TO_PROCESS_FILTERED,
    FNB_ORDER_MOP_CODES, POP_CAN_KEYWORDS, LIMITED_MENU_KEYWORDS, PROMO_CALC_BY_ITEM, 
    PROMO_CALC_BY_RECEIPT, REPORT_TEMPLATE_FILE
)

class ReportProcessor:
    def __init__(self, payments_df, transactions_df, target_value, config_site_code, db_manager):
        self.payments_df = payments_df.copy() if payments_df is not None else pd.DataFrame()
        self.transactions_df = transactions_df.copy() if transactions_df is not None else pd.DataFrame()
        
        # --- FIX: Konversi target_value ke Float agar tidak Error TypeError ---
        try:
            # Bersihkan string dari karakter non-numerik (jika ada) kecuali titik/koma desimal
            if isinstance(target_value, str):
                # Asumsi input standar python (dot for decimal)
                clean_target = target_value.replace(',', '') # Hapus pemisah ribuan jika ada
                self.target_value = float(clean_target)
            else:
                self.target_value = float(target_value)
        except (ValueError, TypeError):
            logging.warning(f"Target value '{target_value}' invalid. Set to 0.")
            self.target_value = 0.0
        # ----------------------------------------------------------------------

        self.config_site_code = config_site_code
        self.db_manager = db_manager
        self.results = {} 
        
        # Default Preferences
        self.article_filter_text = ""
        self.selected_articles_pref = []
        self.is_grouped_view = False
        self.selected_promos_pref = []

    def _get_daily_or_latest_date_data(self, custom_date=None):
        if self.payments_df.empty or 'Tanggal' not in self.payments_df.columns or self.payments_df['Tanggal'].isnull().all():
            return pd.DataFrame(), pd.DataFrame(), None

        if custom_date:
            try:
                # Ensure custom_date is a datetime.date object
                if isinstance(custom_date, str):
                    target_date = pd.to_datetime(custom_date).date()
                else:
                    target_date = custom_date # Assume it's already a date/datetime object
            except Exception as e:
                logging.error(f"Invalid custom_date format: {e}")
                target_date = datetime.now().date()
        else:
             target_date = datetime.now().date()
             
        # Check if the exact target date exists
        daily_payments = self.payments_df[self.payments_df['Tanggal'] == target_date]
        used_date = target_date
        
        # If no data for target date (e.g. today has no sales yet or custom date has no sales), fallback to latest date IN THE SET.
        if daily_payments.empty:
            latest_date = self.payments_df['Tanggal'].max()
            if pd.isna(latest_date): return pd.DataFrame(), pd.DataFrame(), None
            daily_payments = self.payments_df[self.payments_df['Tanggal'] == latest_date]
            used_date = latest_date
            
        daily_transactions = pd.DataFrame()
        if not daily_payments.empty and not self.transactions_df.empty and COL_RECEIPT_NO in self.transactions_df.columns:
            daily_transactions = self.transactions_df[self.transactions_df[COL_RECEIPT_NO].isin(daily_payments[COL_RECEIPT_NO])]
        return daily_payments, daily_transactions, used_date
        
    def set_article_filter(self, filter_text):
        """Menyimpan text filter artikel dari input user."""
        self.article_filter_text = filter_text

    def set_article_preferences(self, selected_articles, is_grouped):
        """Menyimpan preferensi artikel yang dipilih user."""
        self.selected_articles_pref = selected_articles
        self.is_grouped_view = is_grouped

    def set_promo_preferences(self, selected_promos):
        """Menyimpan preferensi promo."""
        self.selected_promos_pref = selected_promos
    
    def _calculate_all_quantity_metrics(self, df):
        """
        Menghitung Sales Quantity berdasarkan kategori (Large, Regular, Topping, dll).
        Menggunakan MASTER DATA DATABASE untuk akurasi 100%.
        """
        if df.empty:
            return { k: 0 for k in ['large', 'regular', 'small', 'topping', 'foods', 'merch', 'snack', 'gb', 'popcan', 'total_sold_cup', 'combined_large_popcan', 'combined_regular_small'] }
                     
        calc_df = df.copy()
        
        # 1. AMBIL MAPPING DARI DB (AKURASI 100%)
        # Format: {'Nama Artikel': 'L', 'Nama Artikel 2': 'R', ...}
        size_map = self.db_manager.get_product_size_map()

        # 2. JIKA MASTER DATA KOSONG, GUNAKAN LOGIKA LAMA (FALLBACK)
        if not size_map:
            logging.info("Master Size Map kosong. Menggunakan metode fallback (keyword matching).")
            return self._calculate_metrics_fallback(calc_df)

        # 3. MAPPING (DATABASE CENTRIC)
        # Normalisasi nama artikel di DF agar match dengan Key di Dictionary DB
        calc_df['normalized_name'] = calc_df[COL_ARTICLE_NAME].astype(str).str.strip()
        
        # Map nama artikel ke Size (L/R/S) menggunakan dictionary dari DB
        calc_df['master_size'] = calc_df['normalized_name'].map(size_map).fillna('UNK')

        # Override Pop Can & Gede Banget (Extra Large) agar direkam sebagai 'L' (Large)
        if COL_MERCHANDISE_NAME in calc_df.columns:
            mask_popcan_xl = calc_df[COL_MERCHANDISE_NAME].astype(str).str.contains('Pop Can|Extra Large|Gede Banget', case=False, na=False, regex=True)
            calc_df.loc[mask_popcan_xl, 'master_size'] = 'L'

        # Hitung Qty berdasarkan Size Master
        qty_large = calc_df[calc_df['master_size'] == 'L'][COL_QUANTITY].sum()
        qty_regular = calc_df[calc_df['master_size'] == 'R'][COL_QUANTITY].sum()
        qty_small = calc_df[calc_df['master_size'] == 'S'][COL_QUANTITY].sum()

        # 4. LOGIKA PELENGKAP (DARI RAW DATA)
        # Untuk Topping & Popcan, kita tetap percaya data POS (Raw) 
        # karena Master Data Excel biasanya hanya fokus ke Size minuman.

        # Topping (Cek Product Group Name)
        qty_topping = 0
        if COL_PRODUCT_GROUP_NAME in calc_df.columns:
            # Cari yang mengandung kata 'Topping' (Case Insensitive)
            mask_topping = calc_df[COL_PRODUCT_GROUP_NAME].astype(str).str.contains('Topping', case=False, na=False)
            qty_topping = calc_df.loc[mask_topping, COL_QUANTITY].sum()

        # Popcan (Cek Merchandise Name)
        qty_popcan = 0
        if COL_MERCHANDISE_NAME in calc_df.columns:
             mask_popcan = calc_df[COL_MERCHANDISE_NAME].astype(str).str.contains('Pop Can', case=False, na=False)
             qty_popcan = calc_df.loc[mask_popcan, COL_QUANTITY].sum()

        metrics = {
            'large': qty_large,
            'regular': qty_regular,
            'small': qty_small,
            'topping': qty_topping,
            'popcan': qty_popcan,
            'foods': 0, 'merch': 0, 'snack': 0, 'gb': 0,
            
            # Kombinasi (Sesuai kebutuhan laporan)
            'combined_large_popcan': qty_large,
            'combined_regular_small': qty_regular + qty_small,
            'total_sold_cup': qty_large + qty_regular + qty_small
        }

        return metrics

    def _calculate_metrics_fallback(self, df):
        """Metode lama (Keyword Matching) sebagai cadangan jika belum import master data."""
        calc_df = df.copy()
        
        for col in [COL_MERCHANDISE_NAME, COL_PRODUCT_GROUP_NAME, 'Department Name']:
            if col in calc_df.columns:
                calc_df[col] = calc_df[col].astype(str).str.strip()

        # Logic Lama
        mask_large = calc_df[COL_MERCHANDISE_NAME].astype(str).str.contains('Large|Pop Can|Extra Large|Gede Banget', case=False, na=False, regex=True) & (calc_df['Department Name'] == 'Chatime')
        mask_regular = calc_df[COL_MERCHANDISE_NAME].astype(str).str.contains('Regular|Butterfly Cup', case=False, na=False, regex=True) & (calc_df['Department Name'] == 'Chatime')
        mask_small = calc_df[COL_MERCHANDISE_NAME].astype(str).str.contains('Small', case=False, na=False, regex=True) & (calc_df['Department Name'] == 'Chatime')
        mask_topping = (calc_df[COL_PRODUCT_GROUP_NAME] == 'Topping')
        mask_popcan = (calc_df[COL_MERCHANDISE_NAME] == 'Pop Can')

        metrics = {
            'large': calc_df.loc[mask_large, COL_QUANTITY].sum(),
            'regular': calc_df.loc[mask_regular, COL_QUANTITY].sum(),
            'small': calc_df.loc[mask_small, COL_QUANTITY].sum(),
            'topping': calc_df.loc[mask_topping, COL_QUANTITY].sum(),
            'popcan': calc_df.loc[mask_popcan, COL_QUANTITY].sum(),
            'foods': 0, 'merch': 0, 'snack': 0, 'gb': 0
        }
        
        metrics['combined_large_popcan'] = metrics['large']
        metrics['combined_regular_small'] = metrics['regular'] + metrics['small']
        metrics['total_sold_cup'] = metrics['large'] + metrics['regular'] + metrics['small']

        return metrics
    
    def _calculate_mop_summary(self, df_payments, site_code, sales_date_str):
        if df_payments.empty or COL_MOP_NAME not in df_payments.columns or COL_AMOUNT not in df_payments.columns: 
            return f"Tidak ada data untuk tanggal tersebut."
            
        mop = df_payments.groupby(COL_MOP_NAME)[COL_AMOUNT].sum().reset_index().sort_values(by=COL_AMOUNT, ascending=False).reset_index(drop=True)
        mop['No'] = mop.index + 1
        
        # Format the text with proper spacing and alignment
        text = f"Site       : {site_code}\n"
        text += f"Sales Date : {sales_date_str}\n"
        text += "---\n\n"
        
        gross_sales = mop[COL_AMOUNT].sum()
        nett_sales = gross_sales / 1.1
        service_charge = gross_sales - nett_sales
        
        for _, r in mop.iterrows():
            text += f"{int(r['No'])}. {r[COL_MOP_NAME]}: {r[COL_AMOUNT]:,.0f}\n"
            
        text += "\n---\n"
        text += f"Gross Sales: {gross_sales:,.0f}\n"
        text += f"Service Charge: {service_charge:,.0f}\n"
        text += f"Nett Sales: {nett_sales:,.0f}"
        
        return text

    def _contains_any(self, text, keywords):
        if pd.isna(text): return False
        return any(keyword.lower() in text.lower() for keyword in keywords)
    
    def _calculate_promo_summary_by_item(self, df_transactions):
        req_cols = [COL_PROMOTION_NAME, COL_NET_PRICE, COL_RECEIPT_NO]
        if df_transactions.empty or not all(c in df_transactions.columns for c in req_cols):
            return pd.DataFrame()

        promo_df = df_transactions.dropna(subset=[COL_PROMOTION_NAME])
        if promo_df.empty:
            return pd.DataFrame()

        summary = promo_df.groupby(COL_PROMOTION_NAME).agg(
            sales=(COL_NET_PRICE, 'sum'),
            qty=(COL_RECEIPT_NO, 'nunique')
        ).reset_index()
        return summary

    def _calculate_promo_summary_by_receipt(self, df_transactions, df_payments):
        req_tx_cols = [COL_PROMOTION_NAME, COL_RECEIPT_NO]
        req_pay_cols = [COL_RECEIPT_NO, COL_AMOUNT]

        if df_transactions.empty or df_payments.empty or \
           not all(c in df_transactions.columns for c in req_tx_cols) or \
           not all(c in df_payments.columns for c in req_pay_cols):
            return pd.DataFrame()

        promo_transactions = df_transactions.dropna(subset=[COL_PROMOTION_NAME])
        if promo_transactions.empty:
            return pd.DataFrame()
            
        promo_receipt_map = promo_transactions[[COL_RECEIPT_NO, COL_PROMOTION_NAME]].drop_duplicates()
        receipt_totals = df_payments.groupby(COL_RECEIPT_NO)[COL_AMOUNT].sum().reset_index()
        merged_data = pd.merge(promo_receipt_map, receipt_totals, on=COL_RECEIPT_NO, how='left')

        final_summary = merged_data.groupby(COL_PROMOTION_NAME).agg(
            sales=(COL_AMOUNT, 'sum'),
            qty=(COL_RECEIPT_NO, 'nunique')
        ).reset_index()
        
        return final_summary

    def _calculate_other_sales_metrics(self, df_transactions, df_payments):
        metrics = {
            'topping': 0, 'topping_ojol': 0, 'topping_instore': 0,
            'ouast_sales': 0, 'ouast_sales_ojol': 0, 'ouast_sales_instore': 0,
            'instore_sales': 0, 'tc_instore': 0,
            'ojol_sales': 0, 'tc_ojol': 0,
            'fnb_order_sales': 0, 'tc_fnb_order': 0,
            'gobiz_sales': 0, 'tc_gobiz': 0,
            'grab_sales': 0, 'tc_grab': 0,
            'shopeefood_sales': 0, 'tc_shopeefood': 0,
            'tc_total': 0,
        }

        # ---------- Transaksi ----------
        tx_required_cols = [COL_PRODUCT_GROUP_NAME, COL_QUANTITY, COL_NET_PRICE, COL_CHANNEL]
        if not df_transactions.empty and all(col in df_transactions.columns for col in tx_required_cols):
            topping_mask = df_transactions[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(TOPPING_KEYWORD, case=False, na=False)
            ouast_mask = df_transactions[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(OUAST_KEYWORD, case=False, na=False)

            metrics['topping'] = df_transactions.loc[topping_mask, COL_QUANTITY].sum()
            metrics['ouast_sales'] = df_transactions.loc[ouast_mask, COL_NET_PRICE].sum()

            if COL_CHANNEL in df_transactions.columns:
                ojol_tx = df_transactions[df_transactions[COL_CHANNEL] == 'Ojol']
                instore_tx = df_transactions[df_transactions[COL_CHANNEL] != 'Ojol']
                
                metrics['topping_ojol'] = ojol_tx.loc[ojol_tx[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(TOPPING_KEYWORD, case=False, na=False), COL_QUANTITY].sum()
                metrics['topping_instore'] = instore_tx.loc[instore_tx[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(TOPPING_KEYWORD, case=False, na=False), COL_QUANTITY].sum()

                metrics['ouast_sales_ojol'] = ojol_tx.loc[ojol_tx[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(OUAST_KEYWORD, case=False, na=False), COL_NET_PRICE].sum()
                metrics['ouast_sales_instore'] = instore_tx.loc[instore_tx[COL_PRODUCT_GROUP_NAME].fillna('').str.contains(OUAST_KEYWORD, case=False, na=False), COL_NET_PRICE].sum()


        # ---------- Pembayaran ----------
        pay_required_cols = [COL_MOP_CODE, COL_AMOUNT, COL_RECEIPT_NO]
        if not df_payments.empty and all(col in df_payments.columns for col in pay_required_cols):
            metrics['tc_total'] = df_payments[COL_RECEIPT_NO].nunique()

            excluded_mops = OJOL_MOP_CODES + FNB_ORDER_MOP_CODES
            instore_payments = df_payments[~df_payments[COL_MOP_CODE].isin(excluded_mops)]
            metrics['instore_sales'] = instore_payments[COL_AMOUNT].sum()
            metrics['tc_instore'] = instore_payments[COL_RECEIPT_NO].nunique()

            ojol_payments = df_payments[df_payments[COL_MOP_CODE].isin(OJOL_MOP_CODES)]
            metrics['ojol_sales'] = ojol_payments[COL_AMOUNT].sum()
            metrics['tc_ojol'] = ojol_payments[COL_RECEIPT_NO].nunique()

            fnb_order_payments = df_payments[df_payments[COL_MOP_CODE].isin(FNB_ORDER_MOP_CODES)]
            metrics['fnb_order_sales'] = fnb_order_payments[COL_AMOUNT].sum()
            metrics['tc_fnb_order'] = fnb_order_payments[COL_RECEIPT_NO].nunique()

            for code, name in [(MOP_CODE_GOBIZ,'gobiz'),(MOP_CODE_GRAB,'grab'),(MOP_CODE_SHOPEEFOOD,'shopeefood')]:
                subset = df_payments[df_payments[COL_MOP_CODE]==code]
                metrics[f'{name}_sales'] = subset[COL_AMOUNT].sum()
                metrics[f'tc_{name}'] = subset[COL_RECEIPT_NO].nunique()
        
        return metrics
        
    def _generate_daily_summaries(self):
        payments_df = self.payments_df
        transactions_df = self.transactions_df
        
        if payments_df.empty or 'Tanggal' not in payments_df.columns:
            return []
        
        source_site_code = transactions_df[COL_SITE_CODE].iloc[0] if not transactions_df.empty and COL_SITE_CODE in transactions_df.columns else self.config_site_code

        summaries = []
        unique_dates = sorted(payments_df['Tanggal'].dropna().unique())
        
        for dt in unique_dates:
            day_pay = payments_df[payments_df['Tanggal'] == dt]
            day_trx = transactions_df[transactions_df[COL_RECEIPT_NO].isin(day_pay[COL_RECEIPT_NO])]
            
            if day_pay.empty:
                continue

            qty_metrics = self._calculate_all_quantity_metrics(day_trx)
            other_metrics = self._calculate_other_sales_metrics(day_trx, day_pay)

            summaries.append({
                'tanggal': dt,
                'site_code': source_site_code,
                'net_sales': float((other_metrics.get('instore_sales', 0) + other_metrics.get('ojol_sales', 0) + other_metrics.get('fnb_order_sales', 0)) / 1.1),
                'tc': int(day_pay[COL_RECEIPT_NO].nunique()),
                'large_cups': int(qty_metrics.get('large', 0)),
                'toping': int(qty_metrics.get('topping', 0)),
                'ouast_sales': float(other_metrics.get('ouast_sales_instore', 0) + other_metrics.get('ouast_sales_ojol', 0))
            })
            
        return summaries

    def regenerate_new_series_outputs(self, day_trx, day_net, mtd_nett_sales, new_series_prefs):
        """
        new_series_prefs format:
        [
            {
                "group_name": "Brown Sugar Series",
                "articles": ["Art 1", "Art 2"],
                "format": "Grouped", # or "Detailed"
                "metrics": {"qty_today": True, "qty_mtd": True, "sales_today": False, "sales_mtd": False, "contrib": False}
            },
            ...
        ]
        """
        new_series_outputs = {
            'contribution_today_df': pd.DataFrame(),
            'contribution_mtd_df': pd.DataFrame(),
            'new_series_text_block': ""
        }

        if not new_series_prefs:
            return new_series_outputs

        all_selected_articles = []
        for grp in new_series_prefs:
            all_selected_articles.extend(grp.get("articles", []))
            
        all_selected_articles = list(set(all_selected_articles))

        # 1. Master Dataframes of selected articles
        contrib_today_df = day_trx[day_trx[COL_ARTICLE_NAME].isin(all_selected_articles)] if not day_trx.empty else pd.DataFrame()
        contrib_mtd_df = self.transactions_df[self.transactions_df[COL_ARTICLE_NAME].isin(all_selected_articles)]
        
        if contrib_today_df.empty and contrib_mtd_df.empty:
            return new_series_outputs

        # Buat Aggregasi MTD & Today secara keseluruhan untuk tabel GUI di App (Mirip aslinya)
        agg_today = contrib_today_df.groupby(COL_ARTICLE_NAME, as_index=False).agg(Quantity=(COL_QUANTITY, 'sum'), Net_Price=(COL_NET_PRICE, 'sum')) if not contrib_today_df.empty else pd.DataFrame(columns=[COL_ARTICLE_NAME, 'Quantity', 'Net_Price'])
        agg_mtd = contrib_mtd_df.groupby(COL_ARTICLE_NAME, as_index=False).agg(Quantity=(COL_QUANTITY, 'sum'), Net_Price=(COL_NET_PRICE, 'sum')) if not contrib_mtd_df.empty else pd.DataFrame(columns=[COL_ARTICLE_NAME, 'Quantity', 'Net_Price'])
        
        # Hitung Unique Transaction (TC)
        agg_today_tc = contrib_today_df.groupby(COL_ARTICLE_NAME, as_index=False).agg(tc_today=(COL_RECEIPT_NO, 'nunique')) if not contrib_today_df.empty and COL_RECEIPT_NO in contrib_today_df.columns else pd.DataFrame(columns=[COL_ARTICLE_NAME, 'tc_today'])
        agg_mtd_tc = contrib_mtd_df.groupby(COL_ARTICLE_NAME, as_index=False).agg(tc_mtd=(COL_RECEIPT_NO, 'nunique')) if not contrib_mtd_df.empty and COL_RECEIPT_NO in contrib_mtd_df.columns else pd.DataFrame(columns=[COL_ARTICLE_NAME, 'tc_mtd'])
        
        new_series_outputs['contribution_today_df'] = agg_today
        new_series_outputs['contribution_mtd_df'] = agg_mtd

        # Gabungkan untuk mempermudah perhitungan Report Text
        summary_master_df = pd.merge(
            agg_today.rename(columns={'Quantity': 'qty_today', 'Net_Price': 'sales_today'}),
            agg_mtd.rename(columns={'Quantity': 'qty_mtd', 'Net_Price': 'sales_mtd'}),
            on=COL_ARTICLE_NAME,
            how='outer'
        ).fillna(0)
        
        summary_master_df = pd.merge(summary_master_df, agg_today_tc, on=COL_ARTICLE_NAME, how='outer').fillna(0)
        summary_master_df = pd.merge(summary_master_df, agg_mtd_tc, on=COL_ARTICLE_NAME, how='outer').fillna(0)

        # 2. Build the Text Block Loop per Group
        text_block = ""
        for grp in new_series_prefs:
            grp_name = grp.get("group_name", "Unknown Group")
            grp_articles = grp.get("articles", [])
            grp_format = grp.get("format", "Grouped")
            metrics = grp.get("metrics", {})
            
            show_qty_today = metrics.get("qty_today", True)
            show_qty_mtd = metrics.get("qty_mtd", True)
            show_tc_today = metrics.get("tc_today", False)
            show_tc_mtd = metrics.get("tc_mtd", False)
            show_sales_today = metrics.get("sales_today", False)
            show_sales_mtd = metrics.get("sales_mtd", False)
            show_contrib = metrics.get("contrib", False)

            # Filter data khusus grup ini
            grp_df = summary_master_df[summary_master_df[COL_ARTICLE_NAME].isin(grp_articles)].copy()
            if grp_df.empty:
                continue

            if grp_format == "Grouped":
                # Totalkan semua item dalam grup ini menjadi 1 baris
                total_qty_today = grp_df['qty_today'].sum()
                total_qty_mtd = grp_df['qty_mtd'].sum()
                total_tc_today = grp_df['tc_today'].sum()
                total_tc_mtd = grp_df['tc_mtd'].sum()
                total_sales_today = grp_df['sales_today'].sum()
                total_sales_mtd = grp_df['sales_mtd'].sum()
                
                text_block += f"{grp_name}\n"
                
                # Dynamic Metrics Formatting
                if show_qty_today and show_qty_mtd:
                    text_block += f"  - SC    : {int(total_qty_today):,} | {int(total_qty_mtd):,}\n"
                elif show_qty_today: text_block += f"  - SC    : {int(total_qty_today):,}\n"
                elif show_qty_mtd: text_block += f"  - SC MTD: {int(total_qty_mtd):,}\n"
                
                if show_tc_today and show_tc_mtd:
                    text_block += f"  - TC    : {int(total_tc_today):,} | {int(total_tc_mtd):,}\n"
                elif show_tc_today: text_block += f"  - TC    : {int(total_tc_today):,}\n"
                elif show_tc_mtd: text_block += f"  - TC MTD: {int(total_tc_mtd):,}\n"

                if show_sales_today and show_sales_mtd:
                    text_block += f"  - Sales : {total_sales_today:,.0f} | {total_sales_mtd:,.0f}\n"
                elif show_sales_today: text_block += f"  - Sales : {total_sales_today:,.0f}\n"
                elif show_sales_mtd: text_block += f"  - Sales MTD: {total_sales_mtd:,.0f}\n"

                if show_contrib:
                    contrib_today_pct = (total_sales_today / day_net) * 100 if day_net > 0 else 0
                    contrib_mtd_pct = (total_sales_mtd / mtd_nett_sales) * 100 if mtd_nett_sales > 0 else 0
                    text_block += f"  - Contrib%: {contrib_today_pct:.1f}% | {contrib_mtd_pct:.1f}%\n"

            else:
                # Mode Detailed (Rincian per item dalam grup)
                text_block += f"-- {grp_name} --\n"
                grp_df = grp_df.sort_values(by='sales_today', ascending=False)
                for _, row in grp_df.iterrows():
                    qty_tdy = row['qty_today']; qty_mtd = row['qty_mtd']
                    tc_tdy = row['tc_today']; tc_mtd = row['tc_mtd']
                    sls_tdy = row['sales_today']; sls_mtd = row['sales_mtd']
                    
                    short_name = format_article_name_short(row[COL_ARTICLE_NAME])
                    text_block += f" {short_name}\n"
                    
                    if show_qty_today and show_qty_mtd:
                        text_block += f"  - SC    : {int(qty_tdy):,} | {int(qty_mtd):,}\n"
                    elif show_qty_today: text_block += f"  - SC    : {int(qty_tdy):,}\n"
                    elif show_qty_mtd: text_block += f"  - SC MTD: {int(qty_mtd):,}\n"
                    
                    if show_tc_today and show_tc_mtd:
                        text_block += f"  - TC    : {int(tc_tdy):,} | {int(tc_mtd):,}\n"
                    elif show_tc_today: text_block += f"  - TC    : {int(tc_tdy):,}\n"
                    elif show_tc_mtd: text_block += f"  - TC MTD: {int(tc_mtd):,}\n"

                    if show_sales_today and show_sales_mtd:
                        text_block += f"  - Sales : {sls_tdy:,.0f} | {sls_mtd:,.0f}\n"
                    elif show_sales_today: text_block += f"  - Sales : {sls_tdy:,.0f}\n"
                    elif show_sales_mtd: text_block += f"  - Sales MTD: {sls_mtd:,.0f}\n"
                    
                    if show_contrib:
                        contrib_today_pct = (sls_tdy / day_net) * 100 if day_net > 0 else 0
                        contrib_mtd_pct = (sls_mtd / mtd_nett_sales) * 100 if mtd_nett_sales > 0 else 0
                        text_block += f"  - Contrib%: {contrib_today_pct:.1f}% | {contrib_mtd_pct:.1f}%\n"

        new_series_outputs['new_series_text_block'] = text_block
        return new_series_outputs
    
    def process(self, template_name="Default Template", config_data={}, selected_promos=None, new_series_prefs=None, promo_calc_method=PROMO_CALC_BY_ITEM, custom_tw_date=None, promo_metrics=None, promo_groups=None):
        # --- 0. PRE-CHECKS ---
        if self.payments_df.empty or ('Tanggal' not in self.payments_df.columns or self.payments_df['Tanggal'].isnull().all()):
            self.results['data_filtered_empty'] = True
            return self.results

        # --- 1. FILTER TRANSAKSI (SEARCH) ---
        if self.article_filter_text:
            search_term = self.article_filter_text.lower()
            if COL_ARTICLE_NAME in self.transactions_df.columns:
                self.transactions_df = self.transactions_df[
                    self.transactions_df[COL_ARTICLE_NAME].astype(str).str.lower().str.contains(search_term)
                ]

        sbd_site_code = self.transactions_df[COL_SITE_CODE].iloc[0] if COL_SITE_CODE in self.transactions_df.columns and not self.transactions_df.empty else "N/A"

        # --- 2. GET DAILY DATA ---
        day_pay, day_trx, day_date = self._get_daily_or_latest_date_data(custom_tw_date)
        self.results['day_trx'] = day_trx
        self.results['day_date'] = day_date
        day_date_str = day_date.strftime('%d-%m-%Y') if day_date else "N/A"
        
        min_date = self.payments_df['Tanggal'].min()
        max_date = self.payments_df['Tanggal'].max()
        
        # --- 3. CALCULATE METRICS (QTY & SALES) ---
        # Kita butuh ini untuk mendapatkan 'total_sold_cup' guna perhitungan %
        mtd_qty_metrics = self._calculate_all_quantity_metrics(self.transactions_df)
        day_qty_metrics = self._calculate_all_quantity_metrics(day_trx)
        
        COL_CHANNEL = 'channel'
        if COL_CHANNEL in self.transactions_df.columns:
            mtd_qty_instore = self._calculate_all_quantity_metrics(self.transactions_df[self.transactions_df[COL_CHANNEL] != 'Ojol'])
        else:
            mtd_qty_instore = mtd_qty_metrics
            
        if COL_CHANNEL in day_trx.columns:
            day_qty_instore = self._calculate_all_quantity_metrics(day_trx[day_trx[COL_CHANNEL] != 'Ojol'])
        else:
            day_qty_instore = day_qty_metrics
        
        mtd_other_metrics = self._calculate_other_sales_metrics(self.transactions_df, self.payments_df)
        day_others = self._calculate_other_sales_metrics(day_trx, day_pay)
        
        # --- 4. SALES FIGURES ---
        mtd_gross = mtd_other_metrics['instore_sales'] + mtd_other_metrics['ojol_sales'] + mtd_other_metrics['fnb_order_sales']
        mtd_nett_sales = mtd_gross / 1.1
        mtd_tc = mtd_other_metrics.get('tc_total', mtd_other_metrics['tc_instore'] + mtd_other_metrics['tc_ojol'] + mtd_other_metrics['tc_fnb_order'])
        
        day_gross = day_others['instore_sales'] + day_others['ojol_sales'] + day_others['fnb_order_sales']
        day_net = day_gross / 1.1
        day_tc = day_others.get('tc_total', day_others['tc_instore'] + day_others['tc_ojol'] + day_others['tc_fnb_order'])
        
        # --- 5. TARGET & DELTA (Dynamic Weekday/Weekend) ---
        ach = (mtd_nett_sales / self.target_value) * 100 if self.target_value > 0 else 0
        
        ref_date = custom_tw_date if custom_tw_date else (max_date if pd.notna(max_date) else datetime.now())
        days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]
        std_ach = (ref_date.day / days_in_month) * 100 if ref_date else 0
        ssg = ach - std_ach
        
        # Hitung poin weight untuk membagi budget target  
        weekday_weight = float(config_data.get('weekday_weight', 1.0))
        weekend_weight = float(config_data.get('weekend_weight', 1.8604651))
        
        weekdays_count, weekends_count = 0, 0
        for day in range(1, days_in_month + 1):
            if date(ref_date.year, ref_date.month, day).weekday() < 5:
                weekdays_count += 1
            else:
                weekends_count += 1
                
        total_weight_points = (weekdays_count * weekday_weight) + (weekends_count * weekend_weight)
        value_per_point = self.target_value / total_weight_points if total_weight_points > 0 else 0
        
        actual_target_weekday = value_per_point * weekday_weight
        actual_target_weekend = value_per_point * weekend_weight
        
        # Tentukan target harian berdasarkan hari H
        if ref_date.weekday() < 5:
            target_harian = actual_target_weekday
        else:
            target_harian = actual_target_weekend
            
        target_mtd = target_harian * ref_date.day
        
        delta_today = day_net - target_harian
        delta_mtd = mtd_nett_sales - target_mtd
        
        # --- 6. HISTORICAL DATA (LW, LM, LY) ---
        lw_nett = 0; lm_nett = 0; ly_nett = 0
        lw_history = {}
        lm_history = {}
        ly_history = {}

        if day_date and self.db_manager:
            date_lw = day_date - timedelta(days=7)
            date_lm = day_date - timedelta(days=28)
            date_ly = day_date - relativedelta(years=1)
            
            def get_hist_detail(h_date):
                h_pay = self.db_manager.get_payments_dataframe(h_date, h_date, self.config_site_code)
                h_trx = self.db_manager.get_transactions_dataframe(h_date, h_date, self.config_site_code)
                if h_pay.empty or h_trx.empty: return {}
                
                h_others = self._calculate_other_sales_metrics(h_trx, h_pay)
                instore_sales = h_others.get('instore_sales', 0)
                ojol_sales = h_others.get('ojol_sales', 0)
                h_gross = instore_sales + ojol_sales + h_others.get('fnb_order_sales', 0)
                h_tc = h_others.get('tc_total', h_others.get('tc_instore', 0) + h_others.get('tc_ojol', 0))
                h_net = h_gross / 1.1

                return {
                    'nett': h_net, 'tc': h_tc, 'ac': (h_net / h_tc) if h_tc > 0 else 0,
                    'instore_nett': instore_sales / 1.1,
                    'instore_tc': h_others.get('tc_instore', 0),
                    'instore_ac': (instore_sales / 1.1) / h_others.get('tc_instore', 1) if h_others.get('tc_instore', 0) > 0 else 0,
                    'ojol_nett': ojol_sales / 1.1,
                    'ojol_tc': h_others.get('tc_ojol', 0),
                    'ojol_ac': (ojol_sales / 1.1) / h_others.get('tc_ojol', 1) if h_others.get('tc_ojol', 0) > 0 else 0,
                    'ouast_nett': h_others.get('ouast_sales_instore', 0) + h_others.get('ouast_sales_ojol', 0),
                    'ouast_instore_nett': h_others.get('ouast_sales_instore', 0)
                }

            lw_history = get_hist_detail(date_lw)
            lm_history = get_hist_detail(date_lm)
            ly_history = get_hist_detail(date_ly)

            lw_nett = lw_history.get('nett', 0)
            lm_nett = lm_history.get('nett', 0)
            ly_nett = ly_history.get('nett', 0)

        from utils.app_utils import calculate_growth 
        ach_diff = ach - std_ach
        growth_lw_pct = calculate_growth(day_net, lw_nett) or 0
        growth_lm_pct = calculate_growth(day_net, lm_nett) or 0
        ssg_new = calculate_growth(day_net, ly_nett) or 0
        
        lm_nett_mtd = 0; ly_nett_mtd = 0
        lm_mtd_detail = {}
        ly_mtd_detail = {}
        if pd.notna(min_date) and pd.notna(max_date) and self.db_manager:
            start_date_lm = min_date - relativedelta(months=1)
            end_date_lm = max_date - relativedelta(months=1)
            start_date_ly = min_date - relativedelta(years=1)
            end_date_ly = max_date - relativedelta(years=1)

            ly_nett_mtd = self.db_manager.get_total_sales_for_period(start_date_ly, end_date_ly, self.config_site_code)
            lm_nett_mtd = self.db_manager.get_total_sales_for_period(start_date_lm, end_date_lm, self.config_site_code)

            def _get_period_detail(start_d, end_d):
                """Query dan hitung metrik detail untuk suatu periode tanggal."""
                try:
                    p_pay = self.db_manager.get_payments_dataframe(start_d, end_d, self.config_site_code)
                    p_trx = self.db_manager.get_transactions_dataframe(start_d, end_d, self.config_site_code)
                    if p_pay.empty or p_trx.empty:
                        return {}
                    p_oth = self._calculate_other_sales_metrics(p_trx, p_pay)
                    p_gross = p_oth.get('instore_sales', 0) + p_oth.get('ojol_sales', 0) + p_oth.get('fnb_order_sales', 0)
                    p_net = p_gross / 1.1
                    p_tc = p_oth.get('tc_total', p_oth.get('tc_instore', 0) + p_oth.get('tc_ojol', 0) + p_oth.get('tc_fnb_order', 0))
                    p_ins_nett = p_oth.get('instore_sales', 0) / 1.1
                    p_ins_tc = p_oth.get('tc_instore', 0)
                    return {
                        'nett': p_net, 'tc': p_tc,
                        'ac': p_net / p_tc if p_tc > 0 else 0,
                        'instore_nett': p_ins_nett, 'instore_tc': p_ins_tc,
                        'instore_ac': p_ins_nett / p_ins_tc if p_ins_tc > 0 else 0,
                        'ouast_nett': p_oth.get('ouast_sales_instore', 0) + p_oth.get('ouast_sales_ojol', 0),
                        'ouast_instore_nett': p_oth.get('ouast_sales_instore', 0),
                    }
                except Exception as e:
                    import logging; logging.warning(f"Period detail calc failed: {e}")
                    return {}

            lm_mtd_detail = _get_period_detail(start_date_lm, end_date_lm)
            ly_mtd_detail = _get_period_detail(start_date_ly, end_date_ly)

        growth_lm_mtd_pct = calculate_growth(mtd_nett_sales, lm_nett_mtd) or 0
        ssg_mtd = calculate_growth(mtd_nett_sales, ly_nett_mtd) or 0
        
        def safe_div(numerator, denominator): return (numerator / denominator) * 100 if denominator > 0 else 0.0

        # --- 7. CONSTRUCT ALL_DATA DICTIONARY ---
        from modules.config_manager import ConfigManager
        config_mgr = ConfigManager()
        target_tc, target_sc, target_large, target_topping, target_spunbond, target_ouast = 0, 0, 0, 0, 0, 0
        if day_date:
            month_year_str = day_date.strftime("%Y-%m")
            metrics = config_mgr.get_monthly_metric_targets(month_year_str)
            if metrics:
                is_weekend = day_date.weekday() >= 5
                target_tc = metrics.get('tc_we' if is_weekend else 'tc_wd', 0)
                target_sc = metrics.get('sc_we' if is_weekend else 'sc_wd', 0)
                target_large = metrics.get('large_we' if is_weekend else 'large_wd', 0)
                target_topping = metrics.get('topping_we' if is_weekend else 'topping_wd', 0)
                target_spunbond = metrics.get('spunbond_we' if is_weekend else 'spunbond_wd', 0)
                target_ouast = metrics.get('ouast_we' if is_weekend else 'ouast_wd', 0)

        bulan_indo = {
            "January": "Januari", "February": "Februari", "March": "Maret",
            "April": "April", "May": "Mei", "June": "Juni",
            "July": "Juli", "August": "Agustus", "September": "September",
            "October": "Oktober", "November": "November", "December": "Desember"
        }
        day_date_full_id = f"{day_date.strftime('%d')} {bulan_indo.get(day_date.strftime('%B'), day_date.strftime('%B'))} {day_date.strftime('%Y')}" if day_date else "N/A"
        day_date_mon_id = bulan_indo.get(day_date.strftime("%B"), day_date.strftime('%B')) if day_date else "N/A"
        
        all_data = {
            "site_code": self.config_site_code, "store_name": config_data.get('store_name', ''),
            "day_date_full": day_date_full_id,
            "day_date_month": day_date_mon_id,
            "target_bulanan": self.target_value, "target_weekday": actual_target_weekday, "target_weekend": actual_target_weekend,
            "target_tc": target_tc, "target_sc": target_sc, "target_large": target_large,
            "target_topping": target_topping, "target_spunbond": target_spunbond, "target_ouast": target_ouast,
            
            "std_ach": std_ach, "ach": ach, "ach_diff": ach_diff, "ssg": ssg_new, "ssg_mtd": ssg_mtd,
            "lw_nett": lw_nett, "growth_lw_pct": growth_lw_pct, "lm_nett": lm_nett, "growth_lm_pct": growth_lm_pct,
            "ly_nett": ly_nett, "lm_nett_mtd": lm_nett_mtd, "growth_lm_mtd_pct": growth_lm_mtd_pct, "ly_nett_mtd": ly_nett_mtd,

            "mtd_gross": mtd_gross, "mtd_nett_sales": mtd_nett_sales, "day_gross": day_gross, "day_net": day_net,
            "mtd_tc": mtd_tc, "day_tc": day_tc, "mtd_ac": mtd_nett_sales / mtd_tc if mtd_tc > 0 else 0, "day_ac": day_net / day_tc if day_tc > 0 else 0,
            "day_ouast_pct": safe_div(day_others['ouast_sales'], day_net), 
            "mtd_ouast_pct": safe_div(mtd_other_metrics['ouast_sales'], mtd_nett_sales),
            
            "day_qty_large": day_qty_metrics['large'], "mtd_qty_large": mtd_qty_metrics['large'],
            "day_qty_regular": day_qty_metrics['regular'], "mtd_qty_regular": mtd_qty_metrics['regular'],
            "day_qty_small": day_qty_metrics['small'], "mtd_qty_small": mtd_qty_metrics['small'],
            "day_total_sc": day_qty_metrics['total_sold_cup'], "mtd_total_sc": mtd_qty_metrics['total_sold_cup'],
            "day_qty_topping": day_qty_metrics['topping'], "mtd_qty_topping": mtd_qty_metrics['topping'],
            "day_qty_foods": day_qty_metrics['foods'], "mtd_qty_foods": mtd_qty_metrics['foods'],
            "day_qty_merch": day_qty_metrics['merch'], "mtd_qty_merch": mtd_qty_metrics['merch'],
            "day_qty_snack": day_qty_metrics['snack'], "mtd_qty_snack": mtd_qty_metrics['snack'],
            "day_qty_gb": day_qty_metrics['gb'], "mtd_qty_gb": mtd_qty_metrics['gb'],
            "day_qty_popcan": day_qty_metrics['popcan'], "mtd_qty_popcan": mtd_qty_metrics['popcan'],
            "day_ouast_sales": float(day_others.get('ouast_sales_instore', 0) + day_others.get('ouast_sales_ojol', 0)),
            "mtd_ouast_sales": float(mtd_other_metrics.get('ouast_sales_instore', 0) + mtd_other_metrics.get('ouast_sales_ojol', 0)),
            
            "day_pct_large": safe_div(day_qty_metrics['large'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_large": safe_div(mtd_qty_metrics['large'], mtd_qty_metrics['total_sold_cup']),
            "day_pct_regular": safe_div(day_qty_metrics['regular'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_regular": safe_div(mtd_qty_metrics['regular'], mtd_qty_metrics['total_sold_cup']),
            "day_pct_small": safe_div(day_qty_metrics['small'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_small": safe_div(mtd_qty_metrics['small'], mtd_qty_metrics['total_sold_cup']),
            "day_pct_topping": safe_div(day_qty_metrics['topping'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_topping": safe_div(mtd_qty_metrics['topping'], mtd_qty_metrics['total_sold_cup']),
            "day_pct_foods": safe_div(day_qty_metrics['foods'], day_net),
            "mtd_pct_foods": safe_div(mtd_qty_metrics['foods'], mtd_nett_sales),
            "day_pct_snack": safe_div(day_qty_metrics['snack'], day_tc),
            "mtd_pct_snack": safe_div(mtd_qty_metrics['snack'], mtd_tc),
            "day_pct_gb": safe_div(day_qty_metrics['gb'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_gb": safe_div(mtd_qty_metrics['gb'], mtd_qty_metrics['total_sold_cup']),
            "day_pct_popcan": safe_div(day_qty_metrics['popcan'], day_qty_metrics['total_sold_cup']),
            "mtd_pct_popcan": safe_div(mtd_qty_metrics['popcan'], mtd_qty_metrics['total_sold_cup']),

            "day_sales_instore": day_others['instore_sales'] / 1.1, "mtd_sales_instore": mtd_other_metrics['instore_sales'] / 1.1,
            "day_tc_instore": day_others['tc_instore'], "mtd_tc_instore": mtd_other_metrics['tc_instore'],
            "day_ac_instore": (day_others['instore_sales'] / 1.1) / day_others['tc_instore'] if day_others['tc_instore'] > 0 else 0,
            "mtd_ac_instore": (mtd_other_metrics['instore_sales'] / 1.1) / mtd_other_metrics['tc_instore'] if mtd_other_metrics['tc_instore'] > 0 else 0,
            "day_sales_ojol": day_others['ojol_sales'] / 1.1, "mtd_sales_ojol": mtd_other_metrics['ojol_sales'] / 1.1,
            "day_tc_ojol": day_others['tc_ojol'], "mtd_tc_ojol": mtd_other_metrics['tc_ojol'],
            "day_ac_ojol": (day_others['ojol_sales'] / 1.1) / day_others['tc_ojol'] if day_others['tc_ojol'] > 0 else 0,
            "mtd_ac_ojol": (mtd_other_metrics['ojol_sales'] / 1.1) / mtd_other_metrics['tc_ojol'] if mtd_other_metrics['tc_ojol'] > 0 else 0,
            "day_fnb_order_sales": day_others['fnb_order_sales'] / 1.1, "mtd_fnb_order_sales": mtd_other_metrics['fnb_order_sales'] / 1.1,
            "day_tc_fnb_order": day_others['tc_fnb_order'], "mtd_tc_fnb_order": mtd_other_metrics['tc_fnb_order'],
            "day_ac_fnb_order": (day_others['fnb_order_sales'] / 1.1) / day_others['tc_fnb_order'] if day_others['tc_fnb_order'] > 0 else 0,
            "mtd_ac_fnb_order": (mtd_other_metrics['fnb_order_sales'] / 1.1) / mtd_other_metrics['tc_fnb_order'] if mtd_other_metrics['tc_fnb_order'] > 0 else 0,
            "day_sales_gobiz": day_others.get('gobiz_sales', 0) / 1.1, "mtd_sales_gobiz": mtd_other_metrics.get('gobiz_sales', 0) / 1.1,
            "day_tc_gobiz": day_others.get('tc_gobiz', 0), "mtd_tc_gobiz": mtd_other_metrics.get('tc_gobiz', 0),
            "day_sales_grab": day_others.get('grab_sales', 0) / 1.1, "mtd_sales_grab": mtd_other_metrics.get('grab_sales', 0) / 1.1,
            "day_tc_grab": day_others.get('tc_grab', 0), "mtd_tc_grab": mtd_other_metrics.get('tc_grab', 0),
            "day_sales_shopeefood": day_others.get('shopeefood_sales', 0) / 1.1, "mtd_sales_shopeefood": mtd_other_metrics.get('shopeefood_sales', 0) / 1.1,
            "day_tc_shopeefood": day_others.get('tc_shopeefood', 0), "mtd_tc_shopeefood": mtd_other_metrics.get('tc_shopeefood', 0),

            "day_sales_instore_pct": safe_div(day_others['instore_sales'], day_gross), "mtd_sales_instore_pct": safe_div(mtd_other_metrics['instore_sales'], mtd_gross),
            "day_tc_instore_pct": safe_div(day_others['tc_instore'], day_tc), "mtd_tc_instore_pct": safe_div(mtd_other_metrics['tc_instore'], mtd_tc),
            "day_sales_ojol_pct": safe_div(day_others['ojol_sales'], day_gross), "mtd_sales_ojol_pct": safe_div(mtd_other_metrics['ojol_sales'], mtd_gross),
            "day_tc_ojol_pct": safe_div(day_others['tc_ojol'], day_tc), "mtd_tc_ojol_pct": safe_div(mtd_other_metrics['tc_ojol'], mtd_tc),
            "day_fnb_order_sales_pct": safe_div(day_others.get('fnb_order_sales', 0), day_gross), "mtd_fnb_order_sales_pct": safe_div(mtd_other_metrics.get('fnb_order_sales', 0), mtd_gross),
            "day_tc_fnb_order_pct": safe_div(day_others.get('tc_fnb_order', 0), day_tc), "mtd_tc_fnb_order_pct": safe_div(mtd_other_metrics.get('tc_fnb_order', 0), mtd_tc),
            "day_gobiz_sales_pct": safe_div(day_others.get('gobiz_sales', 0), day_gross), "mtd_gobiz_sales_pct": safe_div(mtd_other_metrics.get('gobiz_sales', 0), mtd_gross),
            "day_grab_sales_pct": safe_div(day_others.get('grab_sales', 0), day_gross), "mtd_grab_sales_pct": safe_div(mtd_other_metrics.get('grab_sales', 0), mtd_gross),
            "day_shopeefood_sales_pct": safe_div(day_others.get('shopeefood_sales', 0), day_gross), "mtd_shopeefood_sales_pct": safe_div(mtd_other_metrics.get('shopeefood_sales', 0), mtd_gross),
            "day_combined_large_popcan": day_qty_metrics['combined_large_popcan'],
            "mtd_combined_large_popcan": mtd_qty_metrics['combined_large_popcan'],
            "day_combined_regular_small": day_qty_metrics['combined_regular_small'],
            "mtd_combined_regular_small": mtd_qty_metrics['combined_regular_small'],
            "target_harian": target_harian,
            "target_mtd": target_mtd,
            "delta_today": delta_today,
            "delta_mtd": delta_mtd,
            
            # --- NEW METRICS FOR REPORT SALES TEMPLATE ---
            # Instore Cup Sales
            "day_instore_sold_cup": day_qty_instore['total_sold_cup'], "mtd_instore_sold_cup": mtd_qty_instore['total_sold_cup'],
            "day_instore_large": day_qty_instore['large'], "mtd_instore_large": mtd_qty_instore['large'],
            "day_instore_pct_large": safe_div(day_qty_instore['large'], day_qty_instore['total_sold_cup']),
            "mtd_instore_pct_large": safe_div(mtd_qty_instore['large'], mtd_qty_instore['total_sold_cup']),
            "day_instore_reguler": day_qty_instore['regular'], "mtd_instore_reguler": mtd_qty_instore['regular'],
            "day_instore_pct_reguler": safe_div(day_qty_instore['regular'], day_qty_instore['total_sold_cup']),
            "mtd_instore_pct_reguler": safe_div(mtd_qty_instore['regular'], mtd_qty_instore['total_sold_cup']),
            "day_instore_topping": day_qty_instore['topping'], "mtd_instore_topping": mtd_qty_instore['topping'],
            "day_instore_pct_topping": safe_div(day_qty_instore['topping'], day_qty_instore['total_sold_cup']),
            "mtd_instore_pct_topping": safe_div(mtd_qty_instore['topping'], mtd_qty_instore['total_sold_cup']),
            
            # OUAST Additional metrics
            "day_ouast_instore_nett": day_others.get('ouast_sales_instore', 0),
            "mtd_ouast_instore_nett": mtd_other_metrics.get('ouast_sales_instore', 0),
            "day_ouast_instore_pct": safe_div(day_others.get('ouast_sales_instore', 0), day_others.get('instore_sales', 1) / 1.1) if day_others.get('instore_sales', 0) > 0 else 0,
            "mtd_ouast_instore_pct": safe_div(mtd_other_metrics.get('ouast_sales_instore', 0), mtd_other_metrics.get('instore_sales', 1) / 1.1) if mtd_other_metrics.get('instore_sales', 0) > 0 else 0,
            
            # Historical Comparison (Detailed)
            "lw_ac": lw_history.get('ac', 0), "lm_ac": lm_history.get('ac', 0), "ly_ac": ly_history.get('ac', 0),
            "lw_tc": lw_history.get('tc', 0), "lm_tc": lm_history.get('tc', 0), "ly_tc": ly_history.get('tc', 0),
            "lw_instore_nett": lw_history.get('instore_nett', 0), "lm_instore_nett": lm_history.get('instore_nett', 0), "ly_instore_nett": ly_history.get('instore_nett', 0),
            "lw_instore_ac": lw_history.get('instore_ac', 0), "lm_instore_ac": lm_history.get('instore_ac', 0), "ly_instore_ac": ly_history.get('instore_ac', 0),
            "lw_instore_tc": lw_history.get('instore_tc', 0), "lm_instore_tc": lm_history.get('instore_tc', 0), "ly_instore_tc": ly_history.get('instore_tc', 0),
            "lw_ojol_nett": lw_history.get('ojol_nett', 0), "lm_ojol_nett": lm_history.get('ojol_nett', 0), "ly_ojol_nett": ly_history.get('ojol_nett', 0),
            "lw_ojol_ac": lw_history.get('ojol_ac', 0), "lm_ojol_ac": lm_history.get('ojol_ac', 0), "ly_ojol_ac": ly_history.get('ojol_ac', 0),
            "lw_ojol_tc": lw_history.get('ojol_tc', 0), "lm_ojol_tc": lm_history.get('ojol_tc', 0), "ly_ojol_tc": ly_history.get('ojol_tc', 0),
            "lw_ouast_nett": lw_history.get('ouast_nett', 0), "lm_ouast_nett": lm_history.get('ouast_nett', 0), "ly_ouast_nett": ly_history.get('ouast_nett', 0),
            "lw_ouast_instore_nett": lw_history.get('ouast_instore_nett', 0), "lm_ouast_instore_nett": lm_history.get('ouast_instore_nett', 0), "ly_ouast_instore_nett": ly_history.get('ouast_instore_nett', 0),

            "lw_pct_growth_nett": calculate_growth(day_net, lw_history.get('nett', 0)) or 0,
            "lw_pct_growth_instore_nett": calculate_growth(day_others.get('instore_sales', 0)/1.1, lw_history.get('instore_nett', 0)) or 0,
            "lw_pct_growth_ojol_nett": calculate_growth(day_others.get('ojol_sales', 0)/1.1, lw_history.get('ojol_nett', 0)) or 0,
            "lw_pct_growth_ouast_nett": calculate_growth(day_others.get('ouast_sales_instore', 0) + day_others.get('ouast_sales_ojol', 0), lw_history.get('ouast_nett', 0)) or 0,
            "lw_pct_growth_ouast_instore_nett": calculate_growth(day_others.get('ouast_sales_instore', 0), lw_history.get('ouast_instore_nett', 0)) or 0,
            
            "lm_pct_growth_nett": calculate_growth(day_net, lm_history.get('nett', 0)) or 0,
            "lm_pct_growth_instore_nett": calculate_growth(day_others.get('instore_sales', 0)/1.1, lm_history.get('instore_nett', 0)) or 0,
            "lm_pct_growth_ojol_nett": calculate_growth(day_others.get('ojol_sales', 0)/1.1, lm_history.get('ojol_nett', 0)) or 0,
            "lm_pct_growth_ouast_nett": calculate_growth(day_others.get('ouast_sales_instore', 0) + day_others.get('ouast_sales_ojol', 0), lm_history.get('ouast_nett', 0)) or 0,
            "lm_pct_growth_ouast_instore_nett": calculate_growth(day_others.get('ouast_sales_instore', 0), lm_history.get('ouast_instore_nett', 0)) or 0,
            
            "ly_pct_growth_nett": calculate_growth(day_net, ly_history.get('nett', 0)) or 0,
            "ly_pct_growth_instore_nett": calculate_growth(day_others.get('instore_sales', 0)/1.1, ly_history.get('instore_nett', 0)) or 0,
            "ly_pct_growth_ojol_nett": calculate_growth(day_others.get('ojol_sales', 0)/1.1, ly_history.get('ojol_nett', 0)) or 0,
            "ly_pct_growth_ouast_nett": calculate_growth(day_others.get('ouast_sales_instore', 0) + day_others.get('ouast_sales_ojol', 0), ly_history.get('ouast_nett', 0)) or 0,
            "ly_pct_growth_ouast_instore_nett": calculate_growth(day_others.get('ouast_sales_instore', 0), ly_history.get('ouast_instore_nett', 0)) or 0,

            # --- AC per Sub-Channel Ojol (Harian & MTD) ---
            "day_ac_grab": (day_others.get('grab_sales', 0) / 1.1) / day_others.get('tc_grab', 1) if day_others.get('tc_grab', 0) > 0 else 0,
            "mtd_ac_grab": (mtd_other_metrics.get('grab_sales', 0) / 1.1) / mtd_other_metrics.get('tc_grab', 1) if mtd_other_metrics.get('tc_grab', 0) > 0 else 0,
            "day_ac_gobiz": (day_others.get('gobiz_sales', 0) / 1.1) / day_others.get('tc_gobiz', 1) if day_others.get('tc_gobiz', 0) > 0 else 0,
            "mtd_ac_gobiz": (mtd_other_metrics.get('gobiz_sales', 0) / 1.1) / mtd_other_metrics.get('tc_gobiz', 1) if mtd_other_metrics.get('tc_gobiz', 0) > 0 else 0,
            "day_ac_shopeefood": (day_others.get('shopeefood_sales', 0) / 1.1) / day_others.get('tc_shopeefood', 1) if day_others.get('tc_shopeefood', 0) > 0 else 0,
            "mtd_ac_shopeefood": (mtd_other_metrics.get('shopeefood_sales', 0) / 1.1) / mtd_other_metrics.get('tc_shopeefood', 1) if mtd_other_metrics.get('tc_shopeefood', 0) > 0 else 0,

            # --- Growth % LW: AC & TC ---
            "lw_pct_growth_ac": calculate_growth(day_net / day_tc if day_tc > 0 else 0, lw_history.get('ac', 0)) or 0,
            "lw_pct_growth_tc": calculate_growth(day_tc, lw_history.get('tc', 0)) or 0,
            "lw_pct_growth_instore_ac": calculate_growth((day_others.get('instore_sales', 0) / 1.1) / day_others.get('tc_instore', 1) if day_others.get('tc_instore', 0) > 0 else 0, lw_history.get('instore_ac', 0)) or 0,
            "lw_pct_growth_instore_tc": calculate_growth(day_others.get('tc_instore', 0), lw_history.get('instore_tc', 0)) or 0,
            "lw_pct_growth_ojol_ac": calculate_growth((day_others.get('ojol_sales', 0) / 1.1) / day_others.get('tc_ojol', 1) if day_others.get('tc_ojol', 0) > 0 else 0, lw_history.get('ojol_ac', 0)) or 0,
            "lw_pct_growth_ojol_tc": calculate_growth(day_others.get('tc_ojol', 0), lw_history.get('ojol_tc', 0)) or 0,

            # --- Growth % LM: AC & TC ---
            "lm_pct_growth_ac": calculate_growth(day_net / day_tc if day_tc > 0 else 0, lm_history.get('ac', 0)) or 0,
            "lm_pct_growth_tc": calculate_growth(day_tc, lm_history.get('tc', 0)) or 0,
            "lm_pct_growth_instore_ac": calculate_growth((day_others.get('instore_sales', 0) / 1.1) / day_others.get('tc_instore', 1) if day_others.get('tc_instore', 0) > 0 else 0, lm_history.get('instore_ac', 0)) or 0,
            "lm_pct_growth_instore_tc": calculate_growth(day_others.get('tc_instore', 0), lm_history.get('instore_tc', 0)) or 0,
            "lm_pct_growth_ojol_ac": calculate_growth((day_others.get('ojol_sales', 0) / 1.1) / day_others.get('tc_ojol', 1) if day_others.get('tc_ojol', 0) > 0 else 0, lm_history.get('ojol_ac', 0)) or 0,
            "lm_pct_growth_ojol_tc": calculate_growth(day_others.get('tc_ojol', 0), lm_history.get('ojol_tc', 0)) or 0,

            # --- Growth % LY: AC & TC ---
            "ly_pct_growth_ac": calculate_growth(day_net / day_tc if day_tc > 0 else 0, ly_history.get('ac', 0)) or 0,
            "ly_pct_growth_tc": calculate_growth(day_tc, ly_history.get('tc', 0)) or 0,
            "ly_pct_growth_instore_ac": calculate_growth((day_others.get('instore_sales', 0) / 1.1) / day_others.get('tc_instore', 1) if day_others.get('tc_instore', 0) > 0 else 0, ly_history.get('instore_ac', 0)) or 0,
            "ly_pct_growth_instore_tc": calculate_growth(day_others.get('tc_instore', 0), ly_history.get('instore_tc', 0)) or 0,
            "ly_pct_growth_ojol_ac": calculate_growth((day_others.get('ojol_sales', 0) / 1.1) / day_others.get('tc_ojol', 1) if day_others.get('tc_ojol', 0) > 0 else 0, ly_history.get('ojol_ac', 0)) or 0,
            "ly_pct_growth_ojol_tc": calculate_growth(day_others.get('tc_ojol', 0), ly_history.get('ojol_tc', 0)) or 0,

            # --- Daily SR, SA, Ach Diff & Date Format tambahan ---
            "day_sr": (day_net / target_harian * 100) if target_harian > 0 else 0,
            "day_sa": 100.0,
            "day_ach_diff": ((day_net / target_harian * 100) - 100) if target_harian > 0 else 0,
            "day_date_mmddyy": day_date.strftime('%m/%d/%y') if day_date else "N/A",

            # --- LM MTD Detailed (dari query DB periode LM) ---
            "lm_mtd_tc": lm_mtd_detail.get('tc', 0),
            "lm_mtd_ac": lm_mtd_detail.get('ac', 0),
            "lm_mtd_instore_nett": lm_mtd_detail.get('instore_nett', 0),
            "lm_mtd_instore_tc": lm_mtd_detail.get('instore_tc', 0),
            "lm_mtd_instore_ac": lm_mtd_detail.get('instore_ac', 0),
            "lm_mtd_ouast_nett": lm_mtd_detail.get('ouast_nett', 0),
            "lm_mtd_ouast_instore_nett": lm_mtd_detail.get('ouast_instore_nett', 0),
            # Growth MTD vs LM MTD: AC, TC, Instore, OUAST
            "growth_lm_mtd_ac": calculate_growth(mtd_nett_sales / mtd_tc if mtd_tc > 0 else 0, lm_mtd_detail.get('ac', 0)) or 0,
            "growth_lm_mtd_tc": calculate_growth(mtd_tc, lm_mtd_detail.get('tc', 0)) or 0,
            "growth_lm_mtd_instore_nett": calculate_growth(mtd_other_metrics['instore_sales'] / 1.1, lm_mtd_detail.get('instore_nett', 0)) or 0,
            "growth_lm_mtd_instore_ac": calculate_growth((mtd_other_metrics['instore_sales'] / 1.1) / mtd_other_metrics['tc_instore'] if mtd_other_metrics['tc_instore'] > 0 else 0, lm_mtd_detail.get('instore_ac', 0)) or 0,
            "growth_lm_mtd_instore_tc": calculate_growth(mtd_other_metrics['tc_instore'], lm_mtd_detail.get('instore_tc', 0)) or 0,
            "growth_lm_mtd_ouast_nett": calculate_growth(float(mtd_other_metrics.get('ouast_sales_instore', 0) + mtd_other_metrics.get('ouast_sales_ojol', 0)), lm_mtd_detail.get('ouast_nett', 0)) or 0,
            "growth_lm_mtd_ouast_instore_nett": calculate_growth(float(mtd_other_metrics.get('ouast_sales_instore', 0)), lm_mtd_detail.get('ouast_instore_nett', 0)) or 0,

            # --- LY MTD Detailed (dari query DB periode LY) ---
            "ly_mtd_tc": ly_mtd_detail.get('tc', 0),
            "ly_mtd_ac": ly_mtd_detail.get('ac', 0),
            "ly_mtd_instore_nett": ly_mtd_detail.get('instore_nett', 0),
            "ly_mtd_instore_tc": ly_mtd_detail.get('instore_tc', 0),
            "ly_mtd_instore_ac": ly_mtd_detail.get('instore_ac', 0),
            "ly_mtd_ouast_nett": ly_mtd_detail.get('ouast_nett', 0),
            "ly_mtd_ouast_instore_nett": ly_mtd_detail.get('ouast_instore_nett', 0),
            # SSG MTD: AC, TC, Instore, OUAST
            "ssg_mtd_ac": calculate_growth(mtd_nett_sales / mtd_tc if mtd_tc > 0 else 0, ly_mtd_detail.get('ac', 0)) or 0,
            "ssg_mtd_tc": calculate_growth(mtd_tc, ly_mtd_detail.get('tc', 0)) or 0,
            "ssg_mtd_instore_nett": calculate_growth(mtd_other_metrics['instore_sales'] / 1.1, ly_mtd_detail.get('instore_nett', 0)) or 0,
            "ssg_mtd_instore_ac": calculate_growth((mtd_other_metrics['instore_sales'] / 1.1) / mtd_other_metrics['tc_instore'] if mtd_other_metrics['tc_instore'] > 0 else 0, ly_mtd_detail.get('instore_ac', 0)) or 0,
            "ssg_mtd_instore_tc": calculate_growth(mtd_other_metrics['tc_instore'], ly_mtd_detail.get('instore_tc', 0)) or 0,
            "ssg_mtd_ouast_nett": calculate_growth(float(mtd_other_metrics.get('ouast_sales_instore', 0) + mtd_other_metrics.get('ouast_sales_ojol', 0)), ly_mtd_detail.get('ouast_nett', 0)) or 0,
            "ssg_mtd_ouast_instore_nett": calculate_growth(float(mtd_other_metrics.get('ouast_sales_instore', 0)), ly_mtd_detail.get('ouast_instore_nett', 0)) or 0,
        }
        
        self.results['processor'] = self
        self.results['day_qty_metrics'] = day_qty_metrics
        self.results['mtd_qty_metrics'] = mtd_qty_metrics

        # --- 8. PROMO CALCULATION ---
        # Selalu hitung KEDUA versi agar setiap grup bisa pick metode-nya sendiri.
        # Versi global (promo_calc_method) tetap digunakan untuk merged_promo_df utama
        # yang dipakai di flat-list / backward-compat mode.
        promo_by_receipt_mtd   = self._calculate_promo_summary_by_receipt(self.transactions_df, self.payments_df)
        promo_by_receipt_today = self._calculate_promo_summary_by_receipt(day_trx, day_pay)
        promo_by_item_mtd      = self._calculate_promo_summary_by_item(self.transactions_df)
        promo_by_item_today    = self._calculate_promo_summary_by_item(day_trx)

        def _merge_promo(df_mtd, df_today):
            """Rename + outer-merge dua DataFrame promo."""
            if not df_mtd.empty:   df_mtd   = df_mtd.rename(columns={'sales': 'sales_mtd',   'qty': 'qty_mtd'})
            if not df_today.empty: df_today = df_today.rename(columns={'sales': 'sales_today', 'qty': 'qty_today'})
            if not df_mtd.empty and not df_today.empty:
                return pd.merge(df_mtd, df_today, on=COL_PROMOTION_NAME, how='outer').fillna(0)
            elif not df_mtd.empty:
                m = df_mtd.copy(); m['sales_today'] = 0; m['qty_today'] = 0; return m
            elif not df_today.empty:
                m = df_today.copy(); m['sales_mtd'] = 0; m['qty_mtd'] = 0; return m
            return pd.DataFrame()

        merged_by_receipt = _merge_promo(promo_by_receipt_mtd, promo_by_receipt_today)
        merged_by_item    = _merge_promo(promo_by_item_mtd,    promo_by_item_today)

        # Untuk flat-list / backward compat: gunakan metode global
        if promo_calc_method == PROMO_CALC_BY_RECEIPT:
            merged_promo_df = merged_by_receipt
        else:
            merged_promo_df = merged_by_item

        # Simpan keduanya agar regenerate_promo_block_text bisa akses per-grup
        self.results['merged_promo_by_receipt'] = merged_by_receipt
        self.results['merged_promo_by_item']    = merged_by_item
        self.results['merged_promo_df'] = merged_promo_df
        self.results['all_promotions_list'] = merged_promo_df[COL_PROMOTION_NAME].unique().tolist() if not merged_promo_df.empty else []
        
        # --- 9. NEW SERIES CALCULATION (Handled entirely by regenerate_new_series_outputs now) ---
        self.results['contribution_today_df'] = pd.DataFrame()
        self.results['contribution_mtd_df'] = pd.DataFrame()

        # --- 10. GENERATE TEXT BLOCKS ---
        promo_text_block = self.regenerate_promo_block_text(
            self.results['merged_promo_df'], selected_promos, day_net, mtd_nett_sales,
            promo_metrics=promo_metrics, promo_groups=promo_groups,
            merged_by_receipt=self.results.get('merged_promo_by_receipt', pd.DataFrame()),
            merged_by_item=self.results.get('merged_promo_by_item', pd.DataFrame()),
        )
        new_series_outputs = self.regenerate_new_series_outputs(day_trx, day_net, mtd_nett_sales, new_series_prefs)
        
        # Populate the shared top-level dfs for the table UI
        if not new_series_outputs.get('contribution_today_df').empty:
            self.results['contribution_today_df'] = new_series_outputs.get('contribution_today_df')
        if not new_series_outputs.get('contribution_mtd_df').empty:
            self.results['contribution_mtd_df'] = new_series_outputs.get('contribution_mtd_df')
        # --- 11. DATABASE SAVING ---
        daily_summaries = self._generate_daily_summaries()
        if self.db_manager and daily_summaries:
            self.db_manager.upsert_daily_history(daily_summaries)
            # self.db_manager.save_bulk_raw_data(self.transactions_df, self.payments_df) # Optional: Sudah di main_app

        self.results['main_report_text'] = self.regenerate_main_report_text(
            template_name, all_data, promo_text_block, new_series_outputs.get('new_series_text_block', '')
        )

        # --- 12. PREPARE UI TABLE DATA (FIXED & MIRRORED FOR TODAY) ---
        
        # A. Payments
        if 'Order No' not in self.payments_df.columns: self.payments_df['Order No'] = ''
        payment_cols = ['Amount', 'Order No', 'Receipt No', 'MOP Code', 'MOP Name', 'Tanggal'] # Pastikan Tanggal ada
        existing_payment_cols = [col for col in payment_cols if col in self.payments_df.columns]
        self.results['sales_by_payment_df'] = self.payments_df[existing_payment_cols]
        
        # B. MENU SUMMARY MTD (KODE ANDA)
        if not self.transactions_df.empty:
            menu_summary_df = self.transactions_df.groupby(COL_ARTICLE_NAME).agg(
                Qty=(COL_QUANTITY, 'sum'), 
                Sales=(COL_NET_PRICE, 'sum')
            ).reset_index().sort_values(by='Qty', ascending=False)
            
            total_sold_cups = mtd_qty_metrics.get('total_sold_cup', 1)
            if total_sold_cups == 0: total_sold_cups = 1
            
            menu_summary_df['%'] = (menu_summary_df['Qty'] / total_sold_cups) * 100
            self.results['menu_summary_df'] = menu_summary_df[[COL_ARTICLE_NAME, 'Qty', '%', 'Sales']]
        else:
            self.results['menu_summary_df'] = pd.DataFrame()

        # C. MENU SUMMARY TODAY (MIRRORED LOGIC AGAR FITUR TODAY JALAN)
        if not day_trx.empty:
            menu_today_df = day_trx.groupby(COL_ARTICLE_NAME).agg(
                Qty=(COL_QUANTITY, 'sum'), 
                Sales=(COL_NET_PRICE, 'sum')
            ).reset_index().sort_values(by='Qty', ascending=False)
            
            total_sold_today = day_qty_metrics.get('total_sold_cup', 1)
            if total_sold_today == 0: total_sold_today = 1
            
            menu_today_df['%'] = (menu_today_df['Qty'] / total_sold_today) * 100
            self.results['menu_summary_today_df'] = menu_today_df[[COL_ARTICLE_NAME, 'Qty', '%', 'Sales']]
        else:
            self.results['menu_summary_today_df'] = pd.DataFrame()

        # --- NEW: GENERATE AUTO ANALYSIS FOR BSCD BUSINESS REVIEW ---
        # Fetch LW data safely from DB
        lw_net_val = 0
        lw_large_val = 0
        lw_tc_val = 0
        lw_topping_val = 0
        
        if self.db_manager:
            lw_date = day_date - timedelta(days=7) if day_date else None
            if lw_date:
                 lw_data_row = self.db_manager.get_history_for_date(lw_date, sbd_site_code)
                 if lw_data_row:
                     lw_net_val = lw_data_row.get('net_sales', 0)
                     lw_large_val = lw_data_row.get('large_cups', 0)
                     lw_tc_val = lw_data_row.get('tc', 0)
                     lw_topping_val = lw_data_row.get('toping', 0)
                     
        all_data['auto_analysis_text'] = self._generate_auto_analysis(
            day_net, day_qty_metrics.get('large', 0),
            lw_net_val, lw_large_val,
            merged_promo_df, # Provide the merged dataframe to find top promo today
            today_tc=day_tc,
            lw_tc=lw_tc_val,
            today_topping=day_qty_metrics.get('topping', 0),
            lw_topping=lw_topping_val
        )

        # --- 13. FINALIZE ---
        self.results.update(all_data)
        
        site_list = config_data.get('site_list', [])
        store_name = config_data.get('store_name', '')
        
        # Coba cari nama toko dari site_list jika store_name kosong atau memakai referensi site_code yang berbeda
        if not store_name or config_data.get('site_code') != sbd_site_code:
            for site in site_list:
                if str(site.get('Kode Site')) == str(sbd_site_code):
                    store_name = site.get('Nama Toko', '')
                    break
                    
        if store_name and store_name not in sbd_site_code:
             site_display = f"{sbd_site_code} - {store_name}"
        else:
             site_display = sbd_site_code
            
        day_date_fmt = day_date.strftime('%d %b %Y') if day_date else "N/A"
        self.results['mop_today_text'] = self._calculate_mop_summary(day_pay, site_display, day_date_fmt)
        
        # Define date strings before referencing them
        min_date_str = min_date.strftime('%d-%m-%Y') if pd.notna(min_date) else "N/A"
        max_date_str = max_date.strftime('%d-%m-%Y') if pd.notna(max_date) else "N/A"
        
        self.results['min_date_str'] = min_date_str
        self.results['max_date_str'] = max_date_str
        self.results['daily_used_date_str'] = day_date.strftime('%d-%m-%Y') if day_date else "N/A" 
        
        date_range_str = f"{min_date_str} s/d {max_date_str}" if min_date_str != "N/A" else "N/A"
        self.results['mop_mtd_text'] = self._calculate_mop_summary(self.payments_df, site_display, date_range_str)
        self.results['sbd_site_code'] = sbd_site_code

        return self.results
    
    def regenerate_promo_block_text(self, merged_promo_df, selected_promos, day_net, mtd_nett_sales,
                                     promo_metrics=None, promo_groups=None,
                                     merged_by_receipt=None, merged_by_item=None):
        promo_text_block = ""
        if merged_promo_df is None: merged_promo_df = pd.DataFrame()
        if merged_by_receipt is None: merged_by_receipt = merged_promo_df
        if merged_by_item    is None: merged_by_item    = merged_promo_df
        if merged_promo_df.empty and merged_by_receipt.empty and merged_by_item.empty:
            return promo_text_block

        # --- MODE GROUPED: iterate per group, aggregate promos ---
        if promo_groups:
            for grp in promo_groups:
                grp_name = grp.get("group_name", "Promo Group")
                grp_promos = grp.get("promos", [])
                metrics = grp.get("metrics", {})
                if not grp_promos:
                    continue

                show_qty_today  = metrics.get("qty_today",  True)
                show_qty_mtd    = metrics.get("qty_mtd",    True)
                show_sales_today = metrics.get("sales_today", True)
                show_sales_mtd   = metrics.get("sales_mtd",   True)
                show_contrib    = metrics.get("contrib",    True)

                # Pilih DataFrame sesuai metode kalkulasi grup ini
                grp_method = grp.get("calc_method", "by_item")  # default by_item
                if grp_method == PROMO_CALC_BY_RECEIPT:
                    source_df = merged_by_receipt
                else:
                    source_df = merged_by_item

                if source_df.empty:
                    source_df = merged_promo_df  # fallback ke default

                grp_data = source_df[source_df[COL_PROMOTION_NAME].isin(grp_promos)]
                if grp_data.empty:
                    continue

                total_qty_today   = int(grp_data.get('qty_today',   pd.Series([0])).sum())
                total_qty_mtd     = int(grp_data.get('qty_mtd',     pd.Series([0])).sum())
                total_sales_today = grp_data.get('sales_today', pd.Series([0])).sum()
                total_sales_mtd   = grp_data.get('sales_mtd',   pd.Series([0])).sum()

                promo_text_block += f"{grp_name}\n"

                if show_qty_today and show_qty_mtd:
                    promo_text_block += f"  - TC    : {total_qty_today:,} | {total_qty_mtd:,}\n"
                elif show_qty_today:
                    promo_text_block += f"  - TC    : {total_qty_today:,}\n"
                elif show_qty_mtd:
                    promo_text_block += f"  - TC MTD: {total_qty_mtd:,}\n"

                if show_sales_today and show_sales_mtd:
                    promo_text_block += f"  - Sales : {total_sales_today:,.0f} | {total_sales_mtd:,.0f}\n"
                elif show_sales_today:
                    promo_text_block += f"  - Sales : {total_sales_today:,.0f}\n"
                elif show_sales_mtd:
                    promo_text_block += f"  - Sales MTD: {total_sales_mtd:,.0f}\n"

                if show_contrib:
                    contrib_today_pct = (float(total_sales_today) / float(day_net)) * 100 if float(day_net) > 0 else 0
                    contrib_mtd_pct = (float(total_sales_mtd) / float(mtd_nett_sales)) * 100 if float(mtd_nett_sales) > 0 else 0
                    promo_text_block += f"  - Contrib%: {contrib_today_pct:.1f}% | {contrib_mtd_pct:.1f}%\n"

            return promo_text_block

        # --- FALLBACK: flat promo list (backward compatible) ---
        if not selected_promos:
            return promo_text_block

        if not promo_metrics:
            promo_metrics = {"qty_today": True, "qty_mtd": True, "sales_today": True, "sales_mtd": True, "contrib": True}

        show_qty_today = promo_metrics.get("qty_today", True)
        show_qty_mtd = promo_metrics.get("qty_mtd", True)
        show_sales_today = promo_metrics.get("sales_today", True)
        show_sales_mtd = promo_metrics.get("sales_mtd", True)
        show_contrib = promo_metrics.get("contrib", True)

        selected_promo_data = merged_promo_df[merged_promo_df[COL_PROMOTION_NAME].isin(selected_promos)]
        
        for _, promo_row in selected_promo_data.iterrows():
            qty_today = int(promo_row.get('qty_today', 0))
            qty_mtd = int(promo_row.get('qty_mtd', 0))
            sales_today = promo_row.get('sales_today', 0)
            sales_mtd = promo_row.get('sales_mtd', 0)
            
            promo_text_block += f"{promo_row[COL_PROMOTION_NAME]}\n"

            if show_qty_today and show_qty_mtd:
                promo_text_block += f"  - TC    : {qty_today:,} | {qty_mtd:,}\n"
            elif show_qty_today:
                promo_text_block += f"  - TC    : {qty_today:,}\n"
            elif show_qty_mtd:
                promo_text_block += f"  - TC MTD: {qty_mtd:,}\n"

            if show_sales_today and show_sales_mtd:
                promo_text_block += f"  - Sales : {sales_today:,.0f} | {sales_mtd:,.0f}\n"
            elif show_sales_today:
                promo_text_block += f"  - Sales : {sales_today:,.0f}\n"
            elif show_sales_mtd:
                promo_text_block += f"  - Sales MTD: {sales_mtd:,.0f}\n"

            if show_contrib:
                contrib_today_pct = (float(sales_today) / float(day_net)) * 100 if float(day_net) > 0 else 0
                contrib_mtd_pct = (float(sales_mtd) / float(mtd_nett_sales)) * 100 if float(mtd_nett_sales) > 0 else 0
                promo_text_block += f"  - Contrib%: {contrib_today_pct:.1f}% | {contrib_mtd_pct:.1f}%\n"
            
        return promo_text_block
    
    def _generate_auto_analysis(self, today_net, today_large, lw_net, lw_large, summary_by_promo, today_tc=0, lw_tc=0, today_topping=0, lw_topping=0):
        import random
        try:
            # 1. Analisa Sales
            sales_growth = 0
            if lw_net > 0:
                sales_growth = ((today_net - lw_net) / lw_net) * 100
            sales_status = "naik" if sales_growth > 0 else "turun" if sales_growth < 0 else "stabil"
            sales_diff = abs(today_net - lw_net)
            
            # 2. Analisa Cup Large
            large_growth = 0
            if lw_large > 0:
                large_growth = ((today_large - lw_large) / lw_large) * 100
            large_status = "naik" if large_growth > 0 else "turun" if large_growth < 0 else "stabil"
            
            # 3. Analisa TC, AC, Topping
            tc_growth = ((today_tc - lw_tc) / lw_tc) * 100 if lw_tc > 0 else 0
            tc_status = "naik" if tc_growth > 0 else "turun" if tc_growth < 0 else "stabil"
            
            today_ac = today_net / today_tc if today_tc > 0 else 0
            lw_ac = lw_net / lw_tc if lw_tc > 0 else 0
            ac_growth = ((today_ac - lw_ac) / lw_ac) * 100 if lw_ac > 0 else 0
            ac_status = "naik" if ac_growth > 0 else "turun" if ac_growth < 0 else "stabil"
            
            topping_growth = ((today_topping - lw_topping) / lw_topping) * 100 if lw_topping > 0 else 0
            topping_status = "naik" if topping_growth > 0 else "turun" if topping_growth < 0 else "stabil"
            
            # 4. Cari Promo Tertinggi (Abaikan nan/empty)
            top_promo_name = "-"
            top_promo_sales = 0
            top_promo_contrib = 0
            
            if summary_by_promo is not None and not summary_by_promo.empty:
                # Filter out 'nan' strings
                valid_promos = summary_by_promo[~summary_by_promo[COL_PROMOTION_NAME].astype(str).str.strip().str.lower().isin(['nan', 'none', 'null', ''])]
                if not valid_promos.empty:
                    if 'sales_today' in valid_promos.columns:
                        top_promo_idx = valid_promos['sales_today'].idxmax()
                        top_row = valid_promos.loc[top_promo_idx]
                        
                        if top_row.get('sales_today', 0) > 0:
                            top_promo_name = str(top_row[COL_PROMOTION_NAME])
                            top_promo_sales = float(top_row.get('sales_today', 0))
                            if today_net > 0:
                                top_promo_contrib = (top_promo_sales / today_net) * 100
                    elif 'sales' in valid_promos.columns:
                         top_promo_idx = valid_promos['sales'].idxmax()
                         top_row = valid_promos.loc[top_promo_idx]
                         if top_row.get('sales', 0) > 0:
                            top_promo_name = str(top_row[COL_PROMOTION_NAME])
                            top_promo_sales = float(top_row.get('sales', 0))
                            if today_net > 0:
                                top_promo_contrib = (top_promo_sales / today_net) * 100
                            
            # 5. Susun Teks Natural Language yang Variatif
            text = "💡 Auto-Analysis:\n"
            
            if today_net == 0 and lw_net == 0:
                 return text + "Belum ada cukup data transaksi untuk dianalisa."
                 
            # Template Variasi
            large_templates_up = [
                f"• Penjualan Cup Large kita mencatat kenaikan sebesar {abs(large_growth):.1f}%, mencapai {int(today_large)} cup dibanding periode minggu lalu.",
                f"• Volume Cup Large hari ini naik {abs(large_growth):.1f}% menjadi {int(today_large)} cup dibanding minggu sebelumnya.",
                f"• Terdapat peningkatan {abs(large_growth):.1f}% pada penjualan Cup Large, dengan total {int(today_large)} cup terjual di hari ini."
            ]
            
            large_templates_down = [
                f"• Penjualan Cup Large saat ini mengalami penurunan {abs(large_growth):.1f}%, bertengger di angka {int(today_large)} cup jika dibandingkan minggu lalu.",
                f"• Cup Large hari ini turun {abs(large_growth):.1f}% menjadi {int(today_large)} cup dibanding performa minggu sebelumnya.",
                f"• Terjadi kontraksi sebesar {abs(large_growth):.1f}% pada seles Cup Large hari ini ({int(today_large)} cup) berbanding dengan minggu lalu."
            ]
            
            large_templates_stable = [
                f"• Kinerja volume Cup Large terpantau stabil di angka {int(today_large)} cup.",
                f"• Penjualan Cup Large hari ini konstan/stabil di {int(today_large)} cup tanpa ada perubahan signifikan dari minggu lalu.",
                f"• Di segmen Cup Large, volume hari ini bertahan di titik stabil {int(today_large)} cup."
            ]
            
            promo_templates = [
                f"• Sebagai catatan promosi, '{top_promo_name}' memberikan sumbangsih tertinggi sebesar {top_promo_contrib:.1f}% dari total sales (Rp {top_promo_sales:,.0f}).",
                f"• Dari sisi penawaran, '{top_promo_name}' menjadi kontributor terbesar dengan penetrasi mencapai {top_promo_contrib:.1f}% terhadap sales harian (Rp {top_promo_sales:,.0f}).",
                f"• Terdapat dominasi dari promo '{top_promo_name}' yang menduduki {top_promo_contrib:.1f}% bauran transaksi promosi hari ini (Rp {top_promo_sales:,.0f})."
            ]
            
            sales_templates_up = [
                f"• Di sisi performa global, kita menutup hari dengan kenaikan Gross Sales sebesar {abs(sales_growth):.1f}% (tumbuh Rp {sales_diff:,.0f}) dibanding minggu lalu.",
                f"• Secara agregat, pendapatan kita naik {abs(sales_growth):.1f}% (terdapat extra Rp {sales_diff:,.0f}) dibandingkan hari yang sama di minggu lalu.",
                f"• Momentum positif terlihat dari total sales harian yang merangkak naik {abs(sales_growth):.1f}% (selisih Rp {sales_diff:,.0f}) vs minggu lalu."
            ]
            
            sales_templates_down = [
                f"• Secara garis besar, total Sales hari ini mengalami sedikit penurunan sebesar {abs(sales_growth):.1f}% (sekitar Rp {sales_diff:,.0f}) dibanding minggu lalu.",
                f"• Jika dilihat dari total pendapatan agregat, kita tertinggal {abs(sales_growth):.1f}% (minus Rp {sales_diff:,.0f}) dari pencapaian minggu sebelumnya.",
                f"• Peforma global pendapatan kita hari ini terkoreksi {abs(sales_growth):.1f}% (turun Rp {sales_diff:,.0f}) vs minggu lalu."
            ]
            
            sales_templates_stable = [
                f"• Secara makro, pencapaian Sales hari ini identik/stabil seperti persentase performa minggu yang lalu.",
                f"• Perolehan Gross Sales secara keseluruhan menunjukkan konsistensi yang sangat stabil dari minggu sebelumnya.",
            ]
            
            # Extra Metrics Bullet
            extra_bullets = []
            if tc_status == "naik":
                extra_bullets.append(f"• Trafik pelanggan (TC) menanjak positif {abs(tc_growth):.1f}% mencapai {int(today_tc)} struk belanja.")
            elif tc_status == "turun":
                extra_bullets.append(f"• Jumlah struk transaksi (TC) menurun {abs(tc_growth):.1f}% ke angka {int(today_tc)} pelanggan.")
                
            if ac_status == "naik":
                extra_bullets.append(f"• Rata-rata belanja per struk (Average Check) menguat {abs(ac_growth):.1f}%, di level Rp {today_ac:,.0f}.")
            elif ac_status == "turun":
                extra_bullets.append(f"• Sales rata-rata per struk (Average Check) tertekan {abs(ac_growth):.1f}% di angka Rp {today_ac:,.0f}.")
                
            if topping_status == "naik":
                extra_bullets.append(f"• Pencapaian Topping ikut berkontribusi positif, tumbuh {abs(topping_growth):.1f}% menjadi {int(today_topping)} porsi.")
            elif topping_status == "turun":
                extra_bullets.append(f"• Penjualan add-ons Topping melemah {abs(topping_growth):.1f}% ({int(today_topping)} porsi).")

            # Paragraf 1: Analisis Large Cup
            if large_status == "naik":
                text += random.choice(large_templates_up) + "\n"
            elif large_status == "turun":
                text += random.choice(large_templates_down) + "\n"
            else:
                text += random.choice(large_templates_stable) + "\n"

            # Point Tambahan: Promo dipindah sejajar dengan poin-poin terpisah
            if top_promo_name != "-":
                 text += random.choice(promo_templates) + "\n"
                 
            # Paragraf 2: Analisis Net Sales Keseluruhan
            if sales_status == "naik":
                 text += random.choice(sales_templates_up) + "\n"
            elif sales_status == "turun":
                 text += random.choice(sales_templates_down) + "\n"
            else:
                 text += random.choice(sales_templates_stable) + "\n"
                 
            # Paragraf 3: Highlight Ekstra (maksimal 2 agar tidak kepanjangan)
            if extra_bullets:
                 chosen_bullets = random.sample(extra_bullets, min(2, len(extra_bullets)))
                 for b in chosen_bullets:
                     text += f"{b}\n"

            return text.strip()
            
        except Exception as e:
            logging.error(f"Error pada _generate_auto_analysis: {e}", exc_info=True)
            return "Gagal membuat analisa otomatis saat ini."
    
    def get_bscd_data(self, db_manager, config_manager, custom_tw_date=None):
        target_date = custom_tw_date if custom_tw_date else (self.results.get('day_date') or date.today())
        site_code = self.config_site_code
        store_name = config_manager.get_store_name(site_code)
        
        if not target_date or not site_code:
            return None

        full_config = config_manager.get_config()
        monthly_targets = config_manager.get_monthly_targets()
        
        target_bulanan = monthly_targets.get(target_date.month, 0)
        
        weekday_weight = float(full_config.get('weekday_weight', 1.0))
        weekend_weight = float(full_config.get('weekend_weight', 1.86))
        
        try:
            year, month = target_date.year, target_date.month
            days_in_month = calendar.monthrange(year, month)[1]
            weekdays, weekends = 0, 0
            for day in range(1, days_in_month + 1):
                d = date(year, month, day)
                if d.weekday() < 5: weekdays += 1
                else: weekends += 1
            
            total_weight_points = (weekdays * weekday_weight) + (weekends * weekend_weight)
            value_per_point = target_bulanan / total_weight_points if total_weight_points > 0 else 0
            
            is_target_date_weekend = target_date.weekday() >= 5
            target_sales_harian = (value_per_point * weekend_weight) if is_target_date_weekend else (value_per_point * weekday_weight)
        except Exception as e:
            logging.error(f"Gagal menghitung target harian dinamis: {e}")
            target_sales_harian = 0

        date_tw = target_date
        date_lw = target_date - timedelta(days=7)
        date_lm = target_date - timedelta(days=28)
        
        data_tw = db_manager.get_history_for_date(date_tw, site_code)
        data_lw = db_manager.get_history_for_date(date_lw, site_code)
        data_lm = db_manager.get_history_for_date(date_lm, site_code)
        
        def ac(s, t): return s / t if t and t > 0 else 0.0
        def gr(c, p):
            if isinstance(p, (int, float)) and isinstance(c, (int, float)) and p > 0: return (c - p) / p
            if p == 0 and c > 0: return 9.99
            return 0.0 if p == 0 and c == 0 else None

        tw, lw, lm = {}, {}, {}
        # Keys as they exist in `daily_sales` DB table columns
        metrics = ['net_sales','tc','large_cups','toping','ouast_sales']
        for m in metrics:
            for d, s in [(tw, data_tw), (lw, data_lw), (lm, data_lm)]:
                v = s.get(m, 0) if s else 0
                try: d[m] = float(v)
                except (ValueError, TypeError): d[m] = 0.0
        
        tw['ac'], lw['ac'], lm['ac'] = ac(tw.get('net_sales',0),tw.get('tc',0)), ac(lw.get('net_sales',0),lw.get('tc',0)), ac(lm.get('net_sales',0),lm.get('tc',0))
        
        # (Override logic removed per user request: strictly load from DB)
        
        mtd_net = self.results.get('mtd_nett_sales', 0)
        mtd_tc = self.results.get('mtd_tc', 0)
        
        mtd_metrics = {
            'netsales_mtd': self.results.get('mtd_nett_sales', 0), 
            'tc_mtd': self.results.get('mtd_tc', 0), 
            'ac_mtd': self.results.get('mtd_ac', 0),
            'large_mtd': self.results.get('mtd_qty_large', 0),
            'toping_mtd': self.results.get('mtd_qty_topping', 0),
            'ouast_mtd': self.results.get('mtd_ouast_sales', 0)
        }
        
        output = {
            'targets': {'sales': target_sales_harian, 'other': 7},
            'site_code': site_code,
            'store_name': store_name,
            'date_tw': date_tw, 'date_lw': date_lw, 'date_lm': date_lm,
            'data_tw': data_tw, 'data_lw': data_lw, 'data_lm': data_lm,
            'mtd_metrics': mtd_metrics
        }
        
        for prefix, data_dict in [('tw', tw), ('lw', lw), ('lm', lm)]:
            for metric, value in data_dict.items():
                ui_key = metric.replace('_sales','').replace('_cups','')
                if ui_key == 'toping': ui_key = 'topping'
                output[f"{ui_key}_{prefix}"] = value

        for metric in metrics + ['ac']:
            ui_key = metric.replace('_sales','').replace('_cups','');
            if ui_key == 'toping': ui_key = 'topping'
            output[f"{ui_key}_lw_growth"] = gr(tw.get(metric,0), lw.get(metric,0))
            output[f"{ui_key}_lm_growth"] = gr(tw.get(metric,0), lm.get(metric,0))
            
        return {**output, **mtd_metrics}

    def regenerate_main_report_text(self, template_name, all_data_source, promo_text_block, new_series_text_block):
        try:
            with open(REPORT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                templates = json.load(f)
            
            # Pre-format dictionary values so they appear correctly even if user uses bare {placholder}
            formatted_data = {}
            # Keys dengan nilai DECIMAL (0-1) dari calculate_growth — harus dicek PERTAMA
            # sebelum cek currency, karena key seperti 'lw_pct_growth_nett' mengandung '_nett'
            # yang akan salah terdeteksi sebagai currency jika cek dilakukan belakangan.
            DECIMAL_GROWTH_KEYS = ('pct_growth', 'growth_lw', 'growth_lm', 'growth_ly',
                                   'growth_lm_mtd', 'growth_ly_mtd', 'ssg')
            CURRENCY_KEYS = ('_gross', '_sales', 'target', 'delta_',
                             'lw_nett', 'lm_nett', 'ly_nett',
                             'lw_ac', 'lm_ac', 'ly_ac',
                             'lw_tc', 'lm_tc', 'ly_tc',
                             'lw_instore', 'lm_instore', 'ly_instore',
                             'lw_ojol', 'lm_ojol', 'ly_ojol',
                             'lw_ouast', 'lm_ouast', 'ly_ouast',
                             'lm_mtd_', 'ly_mtd_',
                             'day_net', 'mtd_nett', 'mtd_gross',
                             'day_ouast', 'mtd_ouast')

            for k, v in all_data_source.items():
                if isinstance(v, (int, float)):
                    # 1. Growth decimal keys — HARUS PERTAMA (sebelum currency!)
                    if any(x in k for x in DECIMAL_GROWTH_KEYS):
                        # Nilai 9.99 adalah sentinel "tidak ada data historis"
                        if abs(v) >= 9.9:
                            formatted_data[k] = "N/A"
                        else:
                            pct_val = v * 100
                            formatted_data[k] = f"{pct_val:.1f}%" if pct_val != 0 else "0%"
                    # 2. Currency / monetary values
                    elif any(x in k for x in CURRENCY_KEYS):
                        formatted_data[k] = f"{v:,.0f}".replace(',', '.')
                    # 3. Percentage values sudah range 0-100 (ach, std_ach, _pct, dll.)
                    elif any(x in k for x in ('_pct', 'ach', 'day_sr', 'day_sa', 'day_ach_diff')):
                        formatted_data[k] = f"{v:.1f}%" if v != 0 else "0%"
                    # 4. Quantities / TC / AC
                    elif any(x in k for x in ('_qty', '_tc', '_ac', 'total_sc', 'combined_',
                                               '_cup', '_large', '_reguler', '_topping')):
                        formatted_data[k] = f"{v:,.0f}".replace(',', '.')
                    else:
                        formatted_data[k] = v
                else:
                    formatted_data[k] = v
            
            template = templates.get(template_name, templates.get("Default Template", {}))
            report_lines = []
            
            for line_format in template.get('structure', []):
                if "{promo_block}" in line_format:
                    if promo_text_block:
                        report_lines.append(promo_text_block.strip())
                elif "{new_series_block}" in line_format:
                    if new_series_text_block:
                        report_lines.append(new_series_text_block.strip())
                else:
                    try:
                        # Fallback for old templates that might still have format specifiers like {day_net:,.0f}
                        # which will crash if we pass a formatted string. We clean them on the fly.
                        import re
                        clean_line_format = re.sub(r'\{([^{}:]+):[^}]+\}', r'{\1}', line_format)
                        report_lines.append(clean_line_format.format(**formatted_data))
                    except KeyError as e:
                        logging.warning(f"Placeholder tidak ditemukan saat regenerasi: {e}")
                        report_lines.append(line_format.replace("{" + str(e.args[0]) + "}", "{N/A}").replace("{" + str(e.args[0]), "{N/A}", 1))
                    except ValueError as e:
                        logging.error(f"ValueError formatting line '{line_format}' -> '{clean_line_format}': {e}")
                        report_lines.append(line_format)
            
            return "\n".join(report_lines)
        except Exception as e:
            logging.error(f"Gagal me-regenerasi template laporan: {e}", exc_info=True)
            return f"Error: Gagal memuat template, pastikan file template tersedia atau silakan buat template."