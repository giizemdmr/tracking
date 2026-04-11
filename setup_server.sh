#!/bin/bash
# ==========================================
# TRAFFIC PIPELINE - LINUX/VAST.AI SETUP
# ==========================================

echo "[INFO] Sistemi güncelliyorum..."
apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 zip unzip tmux

echo "[INFO] Gerekli Python kütüphanelerini kuruyorum..."
pip install --upgrade pip
pip install -r requirements.txt

# Eger kosede opencv-python kaldiysa kaldirip headless kuralim (Sunucuda cokmesini onler)
pip uninstall -y opencv-python opencv-python-headless
pip install opencv-python-headless

echo "[INFO] TensorRT kutuphanelerini kuruyorum (YOLO hizlandirma icin)..."
pip install tensorrt

echo "=========================================="
echo "[BAŞARILI] Kurulum tamamlandi!"
echo ""
echo "!!! ÇOK ÖNEMLİ TENSORRT UYARISI !!!"
echo "Windows'ta kullandiginiz 'yolov8.engine' dosyasi Linux sunucuda CALISMAZ!"
echo "Lutfen 'yolov8.pt' (orijinal pytorch modelinizi) sunucuya yukleyin ve asagidaki kodu calistirin:"
echo ""
echo "   yolo export model=models/yolov8.pt format=engine half=True"
echo ""
echo "Bu komut sunucudaki ekran kartina (Orn: RTX 4090) ozel yeni bir .engine dosyasi uretir."
echo "=========================================="
