import os
import sys
import glob
import subprocess
import yaml
import time
import shutil

# --- RCLONE YAPILANDIRMASI ---
if not shutil.which("rclone"):
    print("[ERROR] 'rclone' bulunamadi! Lutfen rclone yukleyin ve PATH ortam degiskenine ekleyin.")
    print("Kurulum kilavuzu: https://rclone.org/downloads/")
    exit(1)

# --- AYARLAR ---
DRIVE_FOLDER_ID = "1WeYhvosemOSYJKh8EkFikcCOvwNElogb"
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "ciktilar"
CONFIG_PATH = "config/pipeline_config.yaml"

def update_config(video_path: str, excel_filename: str):
    """pipeline_config.yaml dosyasini dinamik olarak gunceller."""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    if 'pipeline' not in config:
        config['pipeline'] = {}
        
    config['pipeline']['video_path'] = video_path
    config['pipeline']['excel_filename'] = excel_filename
    config['pipeline']['headless_mode'] = True
    
    # --- YENI: Video ile ayni klasordeki JSON cizgi dosyasini bul ---
    video_dir = os.path.dirname(video_path)
    local_json_files = glob.glob(os.path.join(video_dir, "*.json"))
    
    if not local_json_files:
        print(f"\n[ERROR] '{video_dir}' klasorunde video ile iliskili hicbir cizgi tanim (.json) dosyasi bulunamadi!")
        print("Lutfen video klasorunun icine cizgi tanim dosyasini ekleyin.")
        sys.exit(1)
        
    is_root = not os.path.splitdrive(video_dir)[1].strip("\\/")
    valid_files = []
    for jf in local_json_files:
        jf_name = os.path.basename(jf).lower()
        if "line" in jf_name or "gate" in jf_name:
            valid_files.append(jf)
        elif not is_root:
            valid_files.append(jf)
            
    if not valid_files:
        print(f"\n[ERROR] '{video_dir}' klasorunde gecerli bir cizgi tanim (.json) dosyasi bulunamadi!")
        sys.exit(1)
        
    chosen_json = None
    for jf in valid_files:
        if "line" in os.path.basename(jf).lower():
            chosen_json = jf
            break
    if not chosen_json:
        chosen_json = valid_files[0]
        
    lines_file_to_use = chosen_json.replace("\\", "/")
    print(f"[INFO] Video ile ayni klasorde cizgi dosyasi bulundu: {lines_file_to_use}")
    config['pipeline']['lines_file'] = lines_file_to_use
    
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
        
    def sanitize_download_filenames():
        # --- DOSYA ADLARINI TEMIZLE (Google Drive Türkçe 'adlı dosyanın kopyası' ve 'Copy of' eklerini siler) ---
        print("[INFO] Klasordeki dosya isimleri kontrol edilip temizleniyor...")
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            for filename in files:
                filepath = os.path.join(root, filename)
                new_filename = filename
                
                # Turkce/Ingilizce kopyasi takilarini temizle
                if " adlı dosyanın kopyası" in filename:
                    new_filename = filename.replace(" adlı dosyanın kopyası", "")
                elif "adlı dosyanın kopyası" in filename:
                    new_filename = filename.replace("adlı dosyanın kopyası", "")
                elif "Copy of " in filename:
                    new_filename = filename.replace("Copy of ", "")
                    
                # Eger uzanti dosya adinin ortasinda kaldiysa (ornegin .MP4.kopyasi gibi bir durum varsa veya uzantidan sonra baska karakterler geldiyse)
                exts = [".mp4", ".avi", ".mov", ".MP4", ".AVI", ".MOV"]
                has_ext_inside = False
                for ext in exts:
                    if ext in new_filename and not new_filename.endswith(ext):
                        has_ext_inside = True
                        break
                
                if has_ext_inside:
                    for ext in exts:
                        if ext in new_filename:
                            idx = new_filename.find(ext)
                            new_filename = new_filename[:idx] + ext
                            break
                
                if new_filename != filename:
                    new_filepath = os.path.join(root, new_filename)
                    if os.path.exists(new_filepath):
                        try:
                            os.remove(filepath)
                            print(f"[INFO] Mukerrer veya eski dosya silindi: {filename}")
                        except Exception as e:
                            print(f"[WARNING] Silme hatasi ({filename}): {e}")
                    else:
                        try:
                            os.rename(filepath, new_filepath)
                            print(f"[INFO] Dosya adi duzeltildi: {filename} -> {new_filename}")
                        except Exception as e:
                            print(f"[WARNING] Yeniden adlandirma hatasi ({filename}): {e}")

    # Indirme kontrolunden once mevcut dosyalari temizle ki var olanlari bulabilsin
    sanitize_download_filenames()

    # 2. Videolari İndir (rclone kullanarak indiriyoruz)
    print(f"\n[INFO] Google Drive'daki videolar kontrol ediliyor ve eksik olanlar indiriliyor (Folder ID: {DRIVE_FOLDER_ID})...")
    rclone_conf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rclone.conf")
    if not os.path.exists(rclone_conf):
        print(f"[ERROR] '{rclone_conf}' bulunamadi! Indirme yapilamiyor.")
        return
        
    cmd = [
        "rclone",
        "--config", rclone_conf,
        "copy",
        "drive:",
        DOWNLOAD_DIR,
        "--drive-root-folder-id", DRIVE_FOLDER_ID
    ]
    print(f"[INFO] Komut calistiriliyor: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Indirme sonrasi yeni gelenleri de temizle
            sanitize_download_filenames()
        else:
            print(f"[ERROR] rclone indirme hatasi:\n{result.stderr}")
    except Exception as e:
        print(f"[ERROR] rclone calistirilirken hata olustu: {e}")

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
        
        if os.path.exists(excel_filename) and os.path.getsize(excel_filename) > 5000:
            print(f"[INFO] {video_name} zaten islenmis, geciliyor.")
            continue
            
        print(f"\n[{i}/{len(videos)}] Isleniyor: {video_name}")
        
        # Config'i Guncelle
        update_config(video_path, excel_filename)
        
        # main.py'yi calistir (subprocess kullanarak memory leak onlenir)
        start_time = time.time()
        print(f"[INFO] Pipeline (main.py) baslatiliyor...")
        try:
            # check=False yaparsaniz hata alsa bile diger videoya gecer
            result = subprocess.run([sys.executable, "main.py"], check=False)
            
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
