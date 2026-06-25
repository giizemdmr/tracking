import pandas as pd
import glob
import os
from datetime import timedelta, datetime

def fix_all():
    ciktilar_folder = r"d:\tracking\ciktilar"
    folder2 = r"d:\tracking\otogar kavsağı"
    files = glob.glob(os.path.join(ciktilar_folder, "*_rapor.xlsx")) + glob.glob(os.path.join(folder2, "*_rapor.xlsx"))
    
    for f in files:
        basename = os.path.basename(f) # e.g. 2026_0615_185920_023_rapor.xlsx
        parts = basename.split('_')
        
        # Dosya adındaki gerçek saati bulalım
        real_start_time = None
        if len(parts) >= 3 and len(parts[2]) == 6:
            try:
                hour = int(parts[2][:2])
                minute = int(parts[2][2:4])
                second = int(parts[2][4:])
                real_start_time = datetime(2026, 6, 15, hour, minute, second)
            except:
                pass
                
        df = pd.read_excel(f)
        if 'Zaman' in df.columns and len(df) > 0 and real_start_time:
            first_time_str = str(df['Zaman'].iloc[0])
            try:
                ft = datetime.strptime(first_time_str, "%H:%M:%S")
                # Yıl ay gün uyduralım karşılaştırmak için
                first_row_time = datetime(2026, 6, 15, ft.hour, ft.minute, ft.second)
                
                # Eğer ilk satırın saati, dosya ismindeki saatten yaklaşık 3 saat ileriyse:
                diff = (first_row_time - real_start_time).total_seconds()
                
                # 2.5 ile 3.5 saat arası (10800 saniye = 3 saat)
                if 9000 < diff < 12000:
                    print(f"Hatalı dosya tespit edildi: {basename}. 3 saat çıkarılıyor...")
                    def sub_3_hours(time_str):
                        try:
                            t = datetime.strptime(str(time_str), "%H:%M:%S")
                            new_t = t - timedelta(hours=3)
                            return new_t.strftime("%H:%M:%S")
                        except:
                            return time_str
                    
                    df['Zaman'] = df['Zaman'].apply(sub_3_hours)
                    df.to_excel(f, index=False)
                else:
                    print(f"Dosya zaten doğru saatte: {basename} (Fark: {diff} saniye)")
            except Exception as e:
                print(f"Hata: {e} - Dosya: {f}")

if __name__ == "__main__":
    fix_all()
