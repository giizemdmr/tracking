import os
import yaml
import shutil
import subprocess
from ultralytics import YOLO

CONFIG_PATH = "config/pipeline_config.yaml"

def update_pipeline_model_path(model_engine_path: str):
    """pipeline_config.yaml dosyasindaki model_path degerini gunceller."""
    if not os.path.exists(CONFIG_PATH):
        print(f"[WARNING] {CONFIG_PATH} bulunamadi, model_path guncellenemedi.")
        return
        
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
        
    if 'pipeline' not in config:
        config['pipeline'] = {}
        
    config['pipeline']['model_path'] = str(model_engine_path).replace("\\", "/")
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    print(f"[OK] {CONFIG_PATH} icindeki model_path '{model_engine_path}' olarak guncellendi.")

CORRECT_MODEL_MD5 = "9b204c836ff159db13562654ca31ef6d"  # Dogru best.pt MD5 hash

def verify_model_md5(path):
    """Modelin MD5 hashini hesaplar ve dogru olup olmadigini kontrol eder."""
    import hashlib
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    actual = h.hexdigest()
    if actual == CORRECT_MODEL_MD5:
        print(f"[OK] Model MD5 dogrulandi: {actual}")
        return True
    else:
        print(f"[WARNING] Model MD5 HATALI! Beklenen: {CORRECT_MODEL_MD5}, Bulunan: {actual}")
        print("[WARNING] Bu yanlis/eski bir model dosyasidir. Silinip yeniden indirilecek.")
        return False

def setup_server():
    print("="*50)
    print(" SUNUCU MODEL & ORTAM KURULUMU")
    print("="*50)
    
    os.makedirs("model", exist_ok=True)
    model_pt_path = "model/best.pt"
    correct_drive_id = "1-ynsynHc1-TVVJV6-rE5FuLB4CxANOD9"  # Dogru model ID
    
    # 1. Model Dosyasi Kontrolu / Indirme
    # Eger dosya varsa MD5 kontrol et — yanlis model olabilir (repodaki eski model gibi)
    if os.path.exists(model_pt_path):
        if not verify_model_md5(model_pt_path):
            os.remove(model_pt_path)
            print(f"[INFO] Yanlis model silindi. Dogru model indiriliyor...")
    
    if not os.path.exists(model_pt_path):
        print(f"\n[INFO] '{model_pt_path}' bulunamadi. Google Drive'dan rclone ile otomatik indiriliyor...")
        
        rclone_conf = "rclone.conf"
        if shutil.which("rclone") and os.path.exists(rclone_conf):
            try:
                print(f"[INFO] Dogru Model ID '{correct_drive_id}' indiriliyor...")
                cmd = [
                    "rclone",
                    "--config", rclone_conf,
                    "backend", "copyid",
                    "drive:",
                    correct_drive_id,
                    model_pt_path
                ]
                print(f"[INFO] Komut calistiriliyor: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    if os.path.exists(model_pt_path):
                        verify_model_md5(model_pt_path)
                else:
                    print(f"[WARNING] rclone ile indirme basarisiz oldu:\n{result.stderr}")
            except Exception as e:
                print(f"[WARNING] rclone calistirilirken hata olustu: {e}")
        else:
            if not shutil.which("rclone"):
                print("[WARNING] Sistemde 'rclone' kurulu degil!")
            if not os.path.exists(rclone_conf):
                print(f"[WARNING] '{rclone_conf}' bulunamadi!")
                
        if not os.path.exists(model_pt_path):
            print("\nModeli manuel olarak baska bir Drive ID veya Linkiyle indirmek ister misiniz?")
            drive_input = input("Google Drive Dosya ID veya Linkini girin (Vazgecmek icin bos birakin): ").strip()
            
            if drive_input:
                if "drive.google.com" in drive_input:
                    parts = drive_input.split("/d/")
                    if len(parts) > 1:
                        drive_id = parts[1].split("/")[0]
                    else:
                        drive_id = drive_input
                else:
                    drive_id = drive_input
                    
                print(f"[INFO] Belirtilen Google Drive ID '{drive_id}' kullanilarak tekrar deneniyor...")
                if shutil.which("rclone") and os.path.exists(rclone_conf):
                    try:
                        cmd = [
                            "rclone",
                            "--config", rclone_conf,
                            "backend", "copyid",
                            "drive:",
                            drive_id,
                            model_pt_path
                        ]
                        subprocess.run(cmd, check=True)
                        if os.path.exists(model_pt_path):
                            verify_model_md5(model_pt_path)
                    except Exception as ex:
                        print(f"[ERROR] Indirme basarisiz: {ex}")
                else:
                    print("[ERROR] rclone veya rclone.conf eksik oldugundan manuel indirme baslatilamadi.")
                    
    # Eger hala model.pt yoksa default/fallback olarak yolov8n kullanabiliriz
    if not os.path.exists(model_pt_path):
        print(f"\n[WARNING] '{model_pt_path}' bulunamadigi icin varsayilan 'yolov8n.pt' kullanilacak.")
        model_pt_path = "yolov8n.pt"
        
    print(f"\n[INFO] '{model_pt_path}' yukleniyor...")
    model = YOLO(model_pt_path)
    
    print("\n[INFO] Model TensorRT (Engine) formatina cevriliyor...")
    print("Bu islem GPU performansina bagli olarak birkac dakika surebilir...")
    
    try:
        # Dynamic axes support, half precision (fp16), and workspace 4GB
        engine_path = model.export(format='engine', dynamic=True, half=True, workspace=4, imgsz=1024)
        print(f"\n[OK] TensorRT Engine basariyla olusturuldu: {engine_path}")
        
        # pipeline_config.yaml dosyasindaki model_path'i guncelle
        update_pipeline_model_path(engine_path)
        
    except Exception as e:
        print(f"\n[ERROR] Engine cevirimi sirasinda hata olustu: {e}")
        print("[WARNING] Sistem TensorRT/CUDA desteklemiyor olabilir.")
        print("[INFO] pipeline_config.yaml dosyasini .pt modelini kullanacak sekilde ayarliyoruz...")
        update_pipeline_model_path(model_pt_path)
        
    print("\n" + "="*50)
    print("[OK] Sunucu kurulumu tamamlandi. 'batch_runner.py' yi calistirabilirsiniz.")
    print("="*50)

if __name__ == "__main__":
    setup_server()
