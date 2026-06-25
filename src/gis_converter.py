import pandas as pd
import glob
import os
import sys
from datetime import datetime
import datetime as dt

def round_time_15min(time_str):
    try:
        t = datetime.strptime(str(time_str), "%H:%M:%S")
        minute = (t.minute // 15) * 15
        t_rounded = t.replace(minute=minute, second=0)
        end_time = t_rounded + dt.timedelta(minutes=15)
        return f"{t_rounded.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    except:
        return "Bilinmiyor"

def get_period(time_str):
    try:
        start_str = time_str.split(' - ')[0]
        h, m = map(int, start_str.split(':'))
        time_val = h + m / 60.0
        
        # Sabah Grubu (06:45 - 09:15 arası çekimler)
        if time_val < 11.0:
            return "SABAH"
        # Öğle Grubu (11:42 - 13:22 arası çekimler)
        elif 11.0 <= time_val < 15.0:
            return "ÖĞLE"
        # Akşam Grubu (15:39 - 19:30 arası çekimler)
        else:
            return "AKŞAM"
    except:
        return ""

def parse_rota(r):
    try:
        parts = str(r).split("->")
        orig = parts[0].strip().split()[-1]
        dest = parts[1].strip().split()[-1]
        return orig, dest
    except:
        return None, None

def main():
    print("[INFO] K01 Referanslı Yeni Excel Raporu (Güncellenmiş) Hazırlanıyor...")
    
    # Varsayılan klasör yolları
    folder = r"d:\tracking\mersankavsagi"
    output_path = r"d:\tracking\mersankavsagi.xlsx"
    
    # Parametre olarak klasör verildiyse onu kullan
    if len(sys.argv) > 1:
        custom_folder = sys.argv[1].strip()
        if os.path.isdir(custom_folder):
            folder = os.path.abspath(custom_folder)
            folder_name = os.path.basename(folder)
            output_path = os.path.join(os.path.dirname(folder), f"{folder_name}.xlsx")
            print(f"[INFO] Belirtilen klasör kullanılıyor: {folder}")
            print(f"[INFO] Çıktı Excel dosyası: {output_path}")
            files = glob.glob(os.path.join(folder, "*_rapor.xlsx"))
        else:
            print(f"[HATA] Belirtilen yol bir klasör değil: {custom_folder}")
            return
    else:
        folder_alt = r"d:\tracking\otogarkavsagi"
        ciktilar_folder = r"d:\tracking\ciktilar"
        
        files = glob.glob(os.path.join(folder, "*_rapor.xlsx"))
        if not files:
            files = glob.glob(os.path.join(ciktilar_folder, "*_rapor.xlsx"))
        if not files:
            files = glob.glob(os.path.join(folder_alt, "*_rapor.xlsx"))
            
    if not files:
        print("[HATA] Excel verisi bulunamadı!")
        return

    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_excel(f))
        except:
            pass

    all_data = pd.concat(dfs, ignore_index=True)
    zaman_col = all_data.columns[0]
    tur_col = all_data.columns[2]
    rota_col = all_data.columns[5]

    # Bisiklet, Motosiklet ve Yayayı kaldır
    exclude_turs = ["bisiklet", "motosiklet", "yaya"]
    all_data = all_data[~all_data[tur_col].str.lower().apply(lambda x: any(e in x for e in exclude_turs))]

    all_data['ZAMAN'] = all_data[zaman_col].apply(round_time_15min)
    all_data['PERİYOT'] = all_data['ZAMAN'].apply(get_period)
    all_data[['Origin', 'Dest']] = all_data[rota_col].apply(lambda x: pd.Series(parse_rota(x)))
    all_data = all_data.dropna(subset=['Origin', 'Dest', 'ZAMAN'])
    
    all_times = sorted(all_data['ZAMAN'].unique())
    all_turs = sorted(all_data[tur_col].unique())
    all_dests = sorted(all_data['Dest'].unique())

    print("[INFO] Matrisler hesaplanıyor...")
    with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
        workbook = writer.book
        header_format1 = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9', 'border': 1})
        header_format2 = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#F2F2F2', 'border': 1})
        cell_format = workbook.add_format({'align': 'center', 'border': 1})
        period_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})

        origins = sorted(all_data['Origin'].unique())
        
        for orig in origins:
            orig_data = all_data[all_data['Origin'] == orig]
            sheet_name = f"{orig}. AKIM"
            worksheet = workbook.add_worksheet(sheet_name)
            
            worksheet.set_column('A:A', 12) # Periyot
            worksheet.set_column('B:B', 18) # Zaman
            
            worksheet.write(0, 0, "PERİYOT", header_format1)
            worksheet.write(0, 1, "ZAMAN", header_format1)
            
            col_idx = 2
            for tur in all_turs:
                start_col = col_idx
                end_col = col_idx + len(all_dests)
                worksheet.merge_range(0, start_col, 0, end_col, tur.upper(), header_format1)
                
                for dest in all_dests:
                    worksheet.write(1, col_idx, f"{orig}-{dest}", header_format2)
                    worksheet.set_column(col_idx, col_idx, 8)
                    col_idx += 1
                
                worksheet.write(1, col_idx, "TOPLAM", header_format2)
                worksheet.set_column(col_idx, col_idx, 10)
                col_idx += 1
                
            row_idx = 2
            current_period = ""
            for t in all_times:
                period = get_period(t)
                worksheet.write(row_idx, 0, period, period_format)
                worksheet.write(row_idx, 1, t, cell_format)
                
                time_data = orig_data[orig_data['ZAMAN'] == t]
                c_idx = 2
                for tur in all_turs:
                    tur_data = time_data[time_data[tur_col] == tur]
                    tur_total = 0
                    
                    for dest in all_dests:
                        count = len(tur_data[tur_data['Dest'] == dest])
                        worksheet.write(row_idx, c_idx, count, cell_format)
                        tur_total += count
                        c_idx += 1
                        
                    worksheet.write(row_idx, c_idx, tur_total, header_format2)
                    c_idx += 1
                
                row_idx += 1
                
        # "ÖZET" Sayfası
        summary_sheet = workbook.add_worksheet("ÖZET")
        summary_sheet.set_column('A:A', 12)
        summary_sheet.set_column('B:B', 15)
        
        # Basit Özet Tablosu
        # Doğru kronolojik sıralama için PERİYOT'u Categorical yap
        period_order = ["SABAH", "ÖĞLE", "AKŞAM"]
        all_data['PERİYOT'] = pd.Categorical(all_data['PERİYOT'], categories=period_order, ordered=True)
        
        summary_df = pd.pivot_table(all_data, index=['PERİYOT', 'ZAMAN'], columns=[tur_col], aggfunc='size', fill_value=0, observed=True)
        summary_df['GENEL TOPLAM'] = summary_df.sum(axis=1)
        
        summary_df.to_excel(writer, sheet_name="ÖZET", startrow=0)
        
        # Gün Sonu Toplamını Ekle
        max_row = len(summary_df) + 1
        summary_sheet.write(max_row, 0, "GÜN SONU", header_format1)
        summary_sheet.write(max_row, 1, "TOPLAMI", header_format1)
        
        # Toplamları sütun bazında topla (A=Periyot, B=Zaman, C...=Türler)
        totals = summary_df.sum()
        for i, val in enumerate(totals):
            summary_sheet.write(max_row, i + 2, val, header_format1)
            
        # --- Yüzdelik Dağılım Grafiği (Pie Chart) ---
        pie_chart = workbook.add_chart({'type': 'pie'})
        
        # Veri Serisi (Türler C'den başlıyor)
        num_turs = len(all_turs)
        # Categories: Tür isimleri (C1, D1, E1...)
        pie_chart.add_series({
            'name': 'Araç Dağılımı (%)',
            'categories': ['ÖZET', 0, 2, 0, 2 + num_turs - 1],
            'values':     ['ÖZET', max_row, 2, max_row, 2 + num_turs - 1],
            'data_labels': {'percentage': True, 'category': True}
        })
        
        pie_chart.set_title({'name': 'Gün İçi Araç Yüzdelik Dağılımı'})
        pie_chart.set_style(10)
        
        # Grafiği J2 hücresine ekle
        summary_sheet.insert_chart('J2', pie_chart)
        
        # --- Zaman Çizgisi Grafiği (Trend) ---
        line_chart = workbook.add_chart({'type': 'line'})
        
        for i in range(num_turs):
            line_chart.add_series({
                'name':       ['ÖZET', 0, i + 2],
                'categories': ['ÖZET', 1, 1, max_row - 1, 1], # Zamanlar
                'values':     ['ÖZET', 1, i + 2, max_row - 1, i + 2],
                'marker':     {'type': 'circle'}
            })
            
        line_chart.set_title({'name': 'Zamana Göre Trafik Trendi'})
        line_chart.set_x_axis({'name': 'Zaman'})
        line_chart.set_y_axis({'name': 'Araç Sayısı'})
        
        # Grafiği J18 hücresine ekle
        summary_sheet.insert_chart('J18', line_chart)

    print(f"\n[BAŞARILI] Excel Dosyası (Bisikletsiz, Sabah/Öğle/Akşam Periyotlu ve Grafikli) Başarıyla Üretildi!")
    print(f"[KAYIT YERİ] {output_path}")

if __name__ == "__main__":
    main()
