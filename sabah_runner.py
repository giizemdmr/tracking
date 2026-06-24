import os
import glob
import subprocess
import yaml
import time

# --- GDOWN KUTUPHANESI ---
try:
    import gdown
except ImportError:
    print("[ERROR] Gerekli kutuphaneler eksik. Lutfen calistirin: pip install gdown")
    exit(1)

# --- AYARLAR ---
DRIVE_FOLDER_ID = "19ECoEW7OM5vJFx-05q7m_6UXJDCAoyXR"
SABAH_DOWNLOAD_DIR = "downloads/sabah"
OUTPUT_DIR = "ciktilar"
CONFIG_PATH = "config/pipeline_config.yaml"

# Beklenen sabah video isimleri (Drive'daki orijinal isimler)
SABAH_VIDEOS_EXPECTED = [
    "20261012070754_000001.MP4",
    "20261012072255_000002.MP4",
    "20261012073755_000003.MP4",
    "20261012075255_000004.MP4",
    "20261012080755_000005.MP4",
    "20261012082255_000006.MP4",
    "20261012083755_000007.MP4",
    "20261012085255_000008.MP4",
]

def update_config(video_path: str, excel_filename: str):
    """pipeline_config.yaml dosyasini dinamik olarak gunceller."""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    if 'pipeline' not in config:
        config['pipeline'] = {}
        
    config['pipeline']['video_path'] = video_path
    config['pipeline']['excel_filename'] = excel_filename
    config['pipeline']['headless_mode'] = True
    
    # Sabah icin lines_4sabah.json kullan
    lines_file = os.path.join(SABAH_DOWNLOAD_DIR, "lines_4sabah.json").replace("\\", "/")
    if os.path.exists(lines_file):
        config['pipeline']['lines_file'] = lines_file
        print(f"[INFO] Cizgi dosyasi: {lines_file}")
    else:
        config['pipeline']['lines_file'] = "config/lines.json"
        print(f"[WARNING] lines_4sabah.json bulunamadi, varsayilan kullanilacak!")
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

def sanitize_filenames(folder):
    """Klasordeki 'adli dosyanin kopyasi' ekini temizle / hard link olustur."""
    exts = [".mp4", ".avi", ".mov", ".MP4", ".AVI", ".MOV", ".json", ".JSON"]
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        new_filename = filename

        if " adlı dosyanın kopyası" in filename:
            new_filename = filename.replace(" adlı dosyanın kopyası", "")
        elif "adlı dosyanın kopyası" in filename:
            new_filename = filename.replace("adlı dosyanın kopyası", "")
        elif "Copy of " in filename:
            new_filename = filename.replace("Copy of ", "")

        # Uzanti ortada kalmis mi?
        for ext in exts:
            if ext in new_filename and not new_filename.endswith(ext):
                idx = new_filename.find(ext)
                new_filename = new_filename[:idx] + ext
                break

        if new_filename != filename:
            new_filepath = os.path.join(folder, new_filename)
            if os.path.exists(filepath) and not os.path.exists(new_filepath):
                try:
                    os.link(filepath, new_filepath)
                    print(f"[INFO] Linklendi: {filename} -> {new_filename}")
                except Exception:
                    try:
                        os.rename(filepath, new_filepath)
                        print(f"[INFO] Rename: {filename} -> {new_filename}")
                    except Exception as e2:
                        print(f"[WARNING] Duzeltme hatasi: {e2}")

def download_missing_sabah_videos():
    """Drive'dan eksik sabah videolarini indir."""
    os.makedirs(SABAH_DOWNLOAD_DIR, exist_ok=True)
    
    # Mevcut dosyalari temizle
    sanitize_filenames(SABAH_DOWNLOAD_DIR)
    
    # Hangi videolar eksik?
    missing = []
    for vname in SABAH_VIDEOS_EXPECTED:
        local_path = os.path.join(SABAH_DOWNLOAD_DIR, vname)
        if not os.path.exists(local_path):
            missing.append(vname)
    
    if not missing:
        print("[OK] Tum sabah videolari zaten mevcut, indirme atlanıyor.")
        return
    
    print(f"\n[INFO] Eksik {len(missing)} video Drive'dan indiriliyor...")
    print(f"[INFO] Drive Folder ID: {DRIVE_FOLDER_ID}")
    
    try:
        print("[INFO] Drive klasor listesi aliniyor...")
        drive_files = gdown.download_folder(
            id=DRIVE_FOLDER_ID,
            output="downloads",
            quiet=True,
            use_cookies=False,
            skip_download=True
        )
        print(f"[INFO] Drive'da toplam {len(drive_files)} dosya bulundu.")
        
        for f in drive_files:
            if not f.id:
                continue
            
            file_name = os.path.basename(f.path)
            # Drive'daki kopyasi adini temiz isme donustur
            clean_name = file_name
            if " adlı dosyanın kopyası" in file_name:
                clean_name = file_name.replace(" adlı dosyanın kopyası", "")
            elif "Copy of " in file_name:
                clean_name = file_name.replace("Copy of ", "")
            
            # Uzanti temizle
            exts = [".mp4", ".avi", ".mov", ".MP4", ".AVI", ".MOV"]
            for ext in exts:
                if ext in clean_name and not clean_name.endswith(ext):
                    idx = clean_name.find(ext)
                    clean_name = clean_name[:idx] + ext
                    break
            
            # Sadece sabah klasorunun dosyalari
            folder_in_drive = os.path.dirname(f.path).lower()
            if "sabah" not in folder_in_drive:
                continue
            
            if clean_name not in missing:
                continue
                
            local_path = os.path.join(SABAH_DOWNLOAD_DIR, clean_name)
            drive_path = os.path.join("downloads", f.path)
            
            print(f"[INDIR] {clean_name} indiriliyor...")
            try:
                gdown.download(id=f.id, output=drive_path, quiet=False, use_cookies=False)
                # Temiz isimle link olustur
                if os.path.exists(drive_path) and not os.path.exists(local_path):
                    try:
                        os.link(drive_path, local_path)
                    except Exception:
                        os.rename(drive_path, local_path)
                print(f"[OK] {clean_name} indirildi.")
            except Exception as e:
                print(f"[ERROR] {clean_name} indirilemedi: {e}")
                
    except Exception as e:
        print(f"[ERROR] Drive listesi alinamadi: {e}")
    finally:
        sanitize_filenames(SABAH_DOWNLOAD_DIR)

def main():
    print("="*55)
    print(" SABAH RUNNER: Sabah Videolarini Isle (000001-000008)")
    print("="*55)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Eksik videolari indir
    download_missing_sabah_videos()
    
    # 2. Sabah videolarini bul
    video_extensions = ["*.mp4", "*.avi", "*.mov", "*.MP4", "*.AVI", "*.MOV"]
    videos = []
    for ext in video_extensions:
        videos.extend(glob.glob(os.path.join(SABAH_DOWNLOAD_DIR, ext)))
    videos = sorted(list(set(videos)))
    
    if not videos:
        print("[WARNING] Sabah klasorunde islenecek video bulunamadi!")
        return
    
    print(f"\n[OK] Sabah klasorunde {len(videos)} video bulundu.")
    
    # 3. Her videoyu isle - raporu varsa atla
    skipped = 0
    processed = 0
    for i, video_path in enumerate(videos, 1):
        video_name = os.path.basename(video_path)
        base_name, _ = os.path.splitext(video_name)
        excel_filename = os.path.join(OUTPUT_DIR, f"{base_name}_rapor.xlsx").replace("\\", "/")
        
        # Rapor zaten varsa atla
        if os.path.exists(excel_filename):
            print(f"\n[{i}/{len(videos)}] ATLANDI (rapor mevcut): {video_name}")
            skipped += 1
            continue
        
        print(f"\n[{i}/{len(videos)}] Isleniyor: {video_name}")
        
        update_config(video_path.replace("\\", "/"), excel_filename)
        
        start_time = time.time()
        print(f"[INFO] Pipeline (main.py) baslatiliyor...")
        try:
            result = subprocess.run(["python", "main.py"], check=False)
            elapsed = time.time() - start_time
            if result.returncode == 0:
                print(f"[OK] {video_name} analizi tamamlandi! (Sure: {elapsed:.1f}sn)")
                print(f"[INFO] Rapor: {excel_filename}")
                processed += 1
            else:
                print(f"[ERROR] {video_name} islenirken main.py hata verdi! (returncode={result.returncode})")
        except Exception as e:
            print(f"[ERROR] Calistirma hatasi: {e}")
    
    print("\n" + "="*55)
    print(f"[OK] SABAH ISLEMI TAMAMLANDI!")
    print(f"     Islenen  : {processed} video")
    print(f"     Atlanan  : {skipped} video (zaten raporlandi)")
    print(f"     Toplam   : {len(videos)} video")
    print("="*55)

if __name__ == "__main__":
    main()
