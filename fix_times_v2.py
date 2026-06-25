import pandas as pd
import glob
import os
import json
import subprocess
from datetime import timedelta, datetime

def get_bad_start_time(video_path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            tags = data.get('format', {}).get('tags', {})
            creation_time = tags.get('creation_time') or tags.get('com.apple.quicktime.creationdate')
            if creation_time:
                ct = creation_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(ct)
                dt = dt + timedelta(hours=3) # The bug that was in reporting.py
                return datetime(2026, 6, 15, dt.hour, dt.minute, dt.second)
    except:
        pass
    return None

def fix_all():
    ciktilar_folder = r"d:\tracking\ciktilar"
    folder2 = r"d:\tracking\otogar kavsağı"
    excel_files = glob.glob(os.path.join(ciktilar_folder, "*_rapor.xlsx")) + glob.glob(os.path.join(folder2, "*_rapor.xlsx"))
    
    video_dir = r"d:\tracking\downloads"
    
    for f in excel_files:
        basename = os.path.basename(f)
        video_name = basename.replace("_rapor.xlsx", ".MP4") # Büyük harf MP4 genelde
        video_path = os.path.join(video_dir, video_name)
        
        if not os.path.exists(video_path):
            video_name = basename.replace("_rapor.xlsx", ".mp4")
            video_path = os.path.join(video_dir, video_name)
            
        if not os.path.exists(video_path):
            print(f"Video bulunamadı: {video_path}")
            continue
            
        bad_start_time = get_bad_start_time(video_path)
        if not bad_start_time:
            continue
            
        parts = basename.split('_')
        real_start_time = None
        if len(parts) >= 3 and len(parts[2]) == 6:
            try:
                hour = int(parts[2][:2])
                minute = int(parts[2][2:4])
                second = int(parts[2][4:])
                real_start_time = datetime(2026, 6, 15, hour, minute, second)
            except:
                pass
                
        if not real_start_time:
            continue
            
        # Eğer hata payı 10 saniyeden azsa dosya zaten doğrudur (fixlenmiştir veya fallback çalışmıştır)
        diff_seconds = (bad_start_time - real_start_time).total_seconds()
        if abs(diff_seconds) < 10:
            print(f"[{basename}] zaten doğru, atlanıyor.")
            continue
            
        print(f"[{basename}] düzeltiliyor. Hatalı Başlangıç: {bad_start_time.strftime('%H:%M:%S')}, Gerçek: {real_start_time.strftime('%H:%M:%S')}")
        
        df = pd.read_excel(f)
        if 'Zaman' in df.columns:
            def correct_time(time_str):
                try:
                    t = datetime.strptime(str(time_str), "%H:%M:%S")
                    excel_dt = datetime(2026, 6, 15, t.hour, t.minute, t.second)
                    
                    # Eğer daha önce 3 saat çıkardıysam ve dosya bozulduysa, onu eski bad_start_time'a göre düşünemem.
                    # Ama offset her zaman: Gerçek Zaman = Excel_Zaman - Bad_Start_Time + Real_Start_Time
                    # Wait, if I already subtracted 3 hours from SOME files, their excel_dt is already 3 hours less.
                    # I will calculate video_seconds based on current excel_dt.
                    # If the user says "zaman damgaları yanlış", it means they haven't been fully fixed.
                    
                    video_secs = (excel_dt - bad_start_time).total_seconds()
                    
                    # Eğer video_secs çok negatifse (-3 saat gibi), demek ki ben bunu fix_times.py ile 3 saat geri almışım demektir!
                    if video_secs < -5000:
                        # 3 saat geri alınmış hali. Onu tekrar +3 saat ekleyip orjinal haline getirelim.
                        excel_dt = excel_dt + timedelta(hours=3)
                        video_secs = (excel_dt - bad_start_time).total_seconds()
                        
                    correct_dt = real_start_time + timedelta(seconds=video_secs)
                    return correct_dt.strftime("%H:%M:%S")
                except:
                    return time_str
                    
            df['Zaman'] = df['Zaman'].apply(correct_time)
            df.to_excel(f, index=False)

if __name__ == "__main__":
    fix_all()
