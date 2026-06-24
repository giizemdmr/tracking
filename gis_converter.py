import os
import sys
import glob
import openpyxl
import pandas as pd
from datetime import datetime, timedelta, time

TEMPLATE_PATH = "K01 (05.11.2022).xlsx"
OUTPUT_PATH = "k01(05.11.2023).xlsx"
INPUT_DIR = "ruspazari"

category_mapping = {
    'otomobil': 'OTOMOBİL',
    'kamyonet': 'KAMYONET',
    'panelvan': 'KAMYONET',
    'minibus': 'T.MİNİBÜS',
    'otobus': 'İETT+HALK',
    'agir_tasit': 'AĞIR TAŞIT'
}

exclude_turs = ["bisiklet", "motosiklet", "yaya"]

def parse_to_time(val):
    if isinstance(val, time):
        return val
    if isinstance(val, datetime):
        return val.time()
    if isinstance(val, str):
        val_str = val.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(val_str, fmt).time()
            except ValueError:
                continue
    return None

def resolve_value(ws, val):
    while isinstance(val, str) and val.startswith('='):
        ref = val[1:]
        val = ws[ref].value
    return val

def get_dest_gate(resolve_val, sheet_name):
    if resolve_val == 'U':
        return f"gate_{sheet_name}"
    elif isinstance(resolve_val, str) and '-' in resolve_val:
        parts = resolve_val.split('-')
        return f"gate_{parts[1].strip()}"
    return None

def main():
    print("="*60)
    print(" GIS CONVERTER: Excel Toplu Düzenleme & Zaman Kaydırma")
    print("="*60)

    # 1. Uzak sunucu ciktilarini (excel dosyalarini) yukle
    files = glob.glob(os.path.join(INPUT_DIR, "*.xlsx"))
    if not files:
        print(f"[ERROR] '{INPUT_DIR}' klasörü içinde excel dosyası bulunamadı!")
        return

    print(f"[INFO] '{INPUT_DIR}' klasöründen {len(files)} adet rapor okunuyor...")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_excel(f))
        except Exception as e:
            print(f"[WARNING] {os.path.basename(f)} okunamadı: {e}")

    if not dfs:
        print("[ERROR] Hiçbir veri okunamadı!")
        return

    all_data = pd.concat(dfs, ignore_index=True)
    print(f"[INFO] Toplam {len(all_data)} satır veri birleştirildi.")

    # Bisiklet, Motosiklet ve Yayayı kaldır
    all_data = all_data[~all_data['Tür'].str.lower().apply(lambda x: any(e in str(x).lower() for e in exclude_turs))]
    print(f"[INFO] Bisiklet, motosiklet ve yaya filtrelemesinden sonra {len(all_data)} satır kaldı.")

    # Saatleri 3 saat 15 dakika geriye kaydır
    def shift_time(t_val):
        if pd.isna(t_val):
            return None
        try:
            t_parsed = datetime.strptime(str(t_val).strip(), "%H:%M:%S")
            t_shifted = t_parsed - timedelta(hours=3, minutes=15)
            return t_shifted.time()
        except Exception:
            try:
                t_parsed = datetime.strptime(str(t_val).strip(), "%H:%M")
                t_shifted = t_parsed - timedelta(hours=3, minutes=15)
                return t_shifted.time()
            except Exception:
                return None

    all_data['shifted_time'] = all_data['Zaman'].apply(shift_time)
    all_data = all_data.dropna(subset=['shifted_time'])
    print(f"[INFO] Zaman kaydırma ve filtreleme tamamlandı.")

    # 2. Şablon Excel Dosyasını Yükle
    if not os.path.exists(TEMPLATE_PATH):
        print(f"[ERROR] Şablon dosya bulunamadı: {TEMPLATE_PATH}")
        return

    print(f"[INFO] Şablon dosyalar yükleniyor (Okuma & Yazma): {TEMPLATE_PATH}")
    wb_eval = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    wb_save = openpyxl.load_workbook(TEMPLATE_PATH, data_only=False)

    # Üst Bilgi Güncelleme
    if 'ÜST_BİLGİ' in wb_save.sheetnames:
        ws_info = wb_save['ÜST_BİLGİ']
        # D30 hücresine çekim tarihini 2026-06-15 olarak yaz
        ws_info['D30'] = datetime(2026, 6, 15)
        print(f"[INFO] ÜST_BİLGİ çekim tarihi 15.06.2026 olarak güncellendi.")

    stream_sheets = ['1', '2', '3', '4', '5', '6']
    
    # 3. Her Akım Sayfası için Temizlik ve Yazma
    for sheet_name in stream_sheets:
        if sheet_name not in wb_save.sheetnames:
            continue
        
        ws_eval = wb_eval[sheet_name]
        ws_save = wb_save[sheet_name]
        print(f"\n[*] Akım Sayfası İşleniyor: {sheet_name}. AKIM")

        # A. Önce mevcut şablon verilerini sıfırla (Böylece eski veriler kalmaz)
        # Peak hour rows: Sabah (8-17), Öğle (20-23), Akşam (26-35)
        # Data columns: 4 to 45 (D to AS)
        data_rows = list(range(8, 18)) + list(range(20, 24)) + list(range(26, 36))
        for r in data_rows:
            for c in range(4, 46):
                ws_save.cell(row=r, column=c).value = None

        # B. Sütunların hangi araç tipine ve hedef kapıya karşılık geldiğini analiz et (ws_eval üzerinden)
        col_mappings = {} # col_idx -> (vehicle_class, dest_gate_name)
        current_vehicle = None
        for c in range(4, 46):
            v_val = ws_eval.cell(row=6, column=c).value
            if v_val is not None:
                current_vehicle = str(v_val).strip()
            
            d_val = ws_eval.cell(row=7, column=c).value
            dest_gate = get_dest_gate(d_val, sheet_name)
            
            if current_vehicle and dest_gate:
                col_mappings[c] = (current_vehicle, dest_gate)
        
        # C. Akım verisini filtrele (Giriş Kapısı == Gate_X)
        sheet_gate_name = f"gate_{sheet_name}"
        orig_data = all_data[all_data['Giriş Kapısı'].str.lower().str.strip() == sheet_gate_name]
        
        # D. Hücreleri doldur
        for r in data_rows:
            # Zaman aralığını al (ws_eval üzerinden)
            start_t = parse_to_time(ws_eval.cell(row=r, column=2).value)
            end_t = parse_to_time(ws_eval.cell(row=r, column=3).value)
            
            if start_t is None or end_t is None:
                continue
            
            # Bu zaman aralığına düşen veriyi filtrele
            time_data = orig_data[(orig_data['shifted_time'] >= start_t) & (orig_data['shifted_time'] < end_t)]
            
            for c in range(4, 46):
                if c not in col_mappings:
                    continue
                
                vehicle_class, dest_gate = col_mappings[c]
                
                # Taşıt sınıfı ve hedef kapıya göre eşleşen kayıtları say
                match_count = 0
                for idx, row in time_data.iterrows():
                    row_tur = str(row['Tür']).lower().strip()
                    row_dest = str(row['Çıkış Kapısı']).lower().strip()
                    
                    mapped_class = category_mapping.get(row_tur)
                    if mapped_class == vehicle_class and row_dest == dest_gate:
                        match_count += 1
                
                # Değer 0'dan büyükse hücreye yaz, yoksa None bırak (boş gözüksün)
                if match_count > 0:
                    ws_save.cell(row=r, column=c).value = match_count

    # 4. Excel formüllerinin otomatik hesaplanmasını zorunlu kıl
    wb_save.calculation.calcMode = 'auto'
    wb_save.calculation.forceFullCalc = True
    wb_save.calculation.fullCalcOnLoad = True

    # 5. Kaydet
    print(f"\n[INFO] Rapor kaydediliyor: {OUTPUT_PATH}")
    wb_save.save(OUTPUT_PATH)
    print(f"[BAŞARILI] Tüm veriler toplu olarak düzenlendi ve {OUTPUT_PATH} dosyasına yazıldı!")

if __name__ == "__main__":
    main()
