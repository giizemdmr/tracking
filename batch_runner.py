import os
import glob
import subprocess
import yaml
import time
import shutil

# --- GDOWN KUTUPHANESI ---
try:
    import gdown
except ImportError:
    print("[ERROR] Gerekli kütüphaneler eksik. Lütfen çalıştırın: pip install gdown")
    exit(1)

# --- AYARLAR ---
DRIVE_FOLDER_ID = "1pO2FAxvEHw-cYQZuvVrPZ3sZNKtgY9U2"
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "ciktilar"
CONFIG_PATH = "config/pipeline_config.yaml"

def update_config(video_path: str, excel_filename: str):
    """pipeline_config.yaml dosyasini dinamik olarak gunceller."""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    config['video_path'] = video_path
    config['reporting']['excel_filename'] = excel_filename
    
    # Sunucu ortaminda calisirken headless_mode'un acik olmasini garanti et
    config['reporting']['headless_mode'] = True
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        
def main():
    print("="*50)
    print(" BATCH RUNNER: Google Drive Video Otomasyonu")
    print("="*50)
    
    # 1. Klasorleri Olustur
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    # 2. Videolari İndir (gdown kullanarak public klasorden klasor olarak cekiyoruz)
    print(f"\n[INFO] Google Drive'dan videolar indiriliyor (Folder ID: {DRIVE_FOLDER_ID})...")
    gdown.download_folder(id=DRIVE_FOLDER_ID, output=DOWNLOAD_DIR, quiet=False, use_cookies=False)
    
    # 3. İnen Videolari Bul
    video_extensions = ["*.mp4", "*.avi", "*.mov", "*.MP4", "*.AVI", "*.MOV"]
    videos = []
    for ext in video_extensions:
        videos.extend(glob.glob(os.path.join(DOWNLOAD_DIR, "**", ext), recursive=True))
        
    if not videos:
        print("[WARNING] Işlenecek video bulunamadi!")
        return
        
    print(f"[OK] Toplam {len(videos)} adet video bulundu. Islem sirasina aliniyor...")
    
    # 4. Videolari Sirayla Isle
    for i, video_path in enumerate(videos, 1):
        video_name = os.path.basename(video_path)
        base_name, _ = os.path.splitext(video_name)
        
        # Excel ciktisi "ciktilar/" klasorunun icine kaydedilecek
        excel_filename = os.path.join(OUTPUT_DIR, f"{base_name}_rapor.xlsx")
        # pipeline_config.yaml yollari relative kabul edebilir, o yuzden / ile birlestirdik
        excel_filename = excel_filename.replace("\\", "/")
        
        print(f"\n[{i}/{len(videos)}] Isleniyor: {video_name}")
        
        # Config'i Guncelle
        update_config(video_path, excel_filename)
        
        # main.py'yi calistir (subprocess kullanarak memory leak onlenir)
        start_time = time.time()
        print(f"[INFO] Pipeline (main.py) baslatiliyor...")
        try:
            # check=False yaparsaniz hata alsa bile diger videoya gecer
            result = subprocess.run(["python", "main.py"], check=False)
            
            if result.returncode == 0:
                print(f"[OK] {video_name} analizi bitti! (Süre: {time.time()-start_time:.1f}sn)")
                print(f"[INFO] Rapor {excel_filename} konumuna kaydedildi.")
                
                # (Opsiyonel) Disk dolmasin diye islenen videoyu silebiliriz
                # os.remove(video_path)
            else:
                print(f"[ERROR] {video_name} islenirken main.py coktu!")
                
        except Exception as e:
            print(f"[ERROR] Calistirma hatasi: {e}")
            
    print("\n" + "="*50)
    print("[OK] TÜM VİDEOLARIN İŞLEMİ TAMAMLANDI!")
    print("="*50)

if __name__ == "__main__":
    main()
