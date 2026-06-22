import os
from ultralytics import YOLO

def setup_server():
    print("[INFO] Sunucu kurulumu basliyor...")
    
    model_path = "yolov8n.pt"  # Varsayilan veya sizin modeliniz
    
    # Eger model yoksa indir (ultralytics otomatik indirir)
    print(f"[INFO] {model_path} modeli kontrol ediliyor...")
    model = YOLO(model_path)
    
    print("[INFO] Model TensorRT (Engine) formatina cevriliyor. Bu islem bikac dakika surebilir...")
    try:
        # Dynamic axes support, half precision (fp16), and worksapce 4GB
        model.export(format='engine', dynamic=True, half=True, workspace=4)
        print("[OK] TensorRT Engine basariyla olusturuldu!")
    except Exception as e:
        print(f"[ERROR] Engine cevirimi sirasinda hata olustu: {e}")
        print("[WARNING] Sistem TensorRT desteklemiyor olabilir, lutfen CUDA ve TensorRT kurulumlarini kontrol edin.")
        
    print("[OK] Sunucu kurulumu tamamlandi. 'batch_runner.py' yi calistirabilirsiniz.")

if __name__ == "__main__":
    setup_server()
