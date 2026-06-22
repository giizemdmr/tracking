import os
import yaml
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
        
    config['pipeline']['model_path'] = model_engine_path.replace("\\", "/")
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    print(f"[OK] {CONFIG_PATH} icindeki model_path '{model_engine_path}' olarak guncellendi.")

def setup_server():
    print("="*50)
    print(" SUNUCU MODEL & ORTAM KURULUMU")
    print("="*50)
    
    os.makedirs("model", exist_ok=True)
    model_pt_path = "model/best.pt"
    default_drive_id = "1IsKjin4PwSXt-ASymIJzJ9zORqO14k8k"
    
    # 1. Model Dosyasi Kontrolu / Indirme
    if not os.path.exists(model_pt_path):
        print(f"\n[INFO] '{model_pt_path}' bulunamadi. Google Drive'dan otomatik indiriliyor...")
        
        try:
            import gdown
            print(f"[INFO] Varsayilan Model ID '{default_drive_id}' indiriliyor...")
            gdown.download(id=default_drive_id, output=model_pt_path, quiet=False)
        except Exception as e:
            print(f"[WARNING] Otomatik indirme basarisiz oldu: {e}")
            print("Modeli manuel olarak baska bir linkten indirmek ister misiniz?")
            
            drive_input = input("\nGoogle Drive Dosya ID veya Linkini girin (Vazgecmek/Manuel yuklemek icin bos birakin): ").strip()
            
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
                try:
                    import gdown
                    gdown.download(id=drive_id, output=model_pt_path, quiet=False)
                except Exception as ex:
                    print(f"[ERROR] Indirme basarisiz: {ex}")
                    
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
        engine_path = model.export(format='engine', dynamic=True, half=True, workspace=4)
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
