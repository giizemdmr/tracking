import pandas as pd
import glob
import os
from datetime import timedelta, datetime

def parse_filename_time(basename):
    parts = basename.split('_')
    if len(parts) >= 3 and len(parts[2]) == 6:
        try:
            hour = int(parts[2][:2])
            minute = int(parts[2][2:4])
            second = int(parts[2][4:])
            return datetime(2026, 6, 15, hour, minute, second)
        except:
            pass
    return None

def fix_all():
    ciktilar_folder = r"d:\tracking\ciktilar"
    folder2 = r"d:\tracking\otogar kavsağı"
    files = glob.glob(os.path.join(ciktilar_folder, "*_rapor.xlsx")) + glob.glob(os.path.join(folder2, "*_rapor.xlsx"))
    
    # Tüm dosyaları sıraya diz
    files = sorted(files)
    
    for i, f in enumerate(files):
        basename = os.path.basename(f)
        real_start_time = parse_filename_time(basename)
        if not real_start_time:
            continue
            
        # End_Time'ı bul
        if i + 1 < len(files):
            next_basename = os.path.basename(files[i+1])
            end_time = parse_filename_time(next_basename)
        else:
            # Son video için varsayılan 25 dakika
            end_time = real_start_time + timedelta(minutes=25)
            
        if not end_time:
            end_time = real_start_time + timedelta(minutes=25)
            
        bad_start_time = end_time + timedelta(hours=3)
        
        df = pd.read_excel(f)
        if 'Zaman' not in df.columns or len(df) == 0:
            continue
            
        first_time_str = str(df['Zaman'].iloc[0])
        try:
            ft = datetime.strptime(first_time_str, "%H:%M:%S")
            first_row_time = datetime(2026, 6, 15, ft.hour, ft.minute, ft.second)
            
            # Eğer bu dosya benim önceki script ile "kısmen" düzeltildiyse (3 saat çıkardıysam)
            # Onun first_row_time'ı 3 saat geri gelmiştir. Onu tekrar +3 saat ileri alıp orjinal bad_start_time ile işlem yapalım.
            diff_from_bad = (first_row_time - bad_start_time).total_seconds()
            
            was_partially_fixed = False
            if diff_from_bad < -10000: # Demek ki 3 saat çıkarılmış (yaklaşık -10800 saniye)
                was_partially_fixed = True
                print(f"[{basename}] Daha önce kısmen düzeltilmiş. Tam matematiksel düzeltme uygulanıyor...")
            else:
                # Zaten düzeltilmemişse, first_row_time bad_start_time'a çok yakın olmalı (0-60 saniye)
                # Eğer already correct ise (gerçek saate yakınsa), dokunma!
                if abs((first_row_time - real_start_time).total_seconds()) < 600:
                    print(f"[{basename}] Zaten tamamen doğru, atlanıyor.")
                    continue
            
            def correct_time(time_str):
                try:
                    t = datetime.strptime(str(time_str), "%H:%M:%S")
                    excel_dt = datetime(2026, 6, 15, t.hour, t.minute, t.second)
                    
                    if was_partially_fixed:
                        excel_dt = excel_dt + timedelta(hours=3)
                        
                    # Gerçek Zaman = Excel_Zaman - Bad_Start_Time + Real_Start_Time
                    video_secs = (excel_dt - bad_start_time).total_seconds()
                    
                    # Eğer video_secs negatifse (örn -10) sıfıra yuvarla
                    if video_secs < 0:
                        video_secs = 0
                        
                    correct_dt = real_start_time + timedelta(seconds=video_secs)
                    return correct_dt.strftime("%H:%M:%S")
                except:
                    return time_str
                    
            df['Zaman'] = df['Zaman'].apply(correct_time)
            df.to_excel(f, index=False)
            print(f"[{basename}] Kusursuz şekilde fixlendi!")
            
        except Exception as e:
            print(f"Hata: {e} - Dosya: {f}")

if __name__ == "__main__":
    fix_all()
