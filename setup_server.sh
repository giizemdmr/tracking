#!/bin/bash
# ==========================================
# TRAFFIC PIPELINE - LINUX/VAST.AI ZERO-TOUCH SETUP
# ==========================================

echo "[INFO] Klasor yapisi hazirlaniyor..."
mkdir -p models

echo "[INFO] Sistem kutuphaneleri kuruluyor..."
apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 zip unzip tmux

echo "[INFO] Python bagimliliklari yukleniyor..."
pip install --upgrade pip
pip install gdown opencv-python-headless ultralytics shapely openpyxl PyYAML numpy
pip install nvidia-tensorrt==8.6.1

echo "[INFO] Video dosyasi Drive'dan cekiliyor..."
gdown 1wEsuJAP7rF9ocwTb-SAlmxspjvq9d-zy -O deneme2.mp4

# Kutuphane uyuşmazlığını önlemek için yolu dışa aktar
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/lib/x86_64-linux-gnu

echo "=========================================="
echo "[BASARILI] Kurulum ve Video Indirme Tamamlandi!"
echo ""
echo "SIRADAKI ADIMLAR:"
echo "1. 'best.pt' modelinizi 'models/' klasorune kopyalayin."
echo "2. 'yolo export model=models/best.pt format=engine half=True' komutunu calistirin."
echo "3. 'python main.py' ile sistemi ucurun."
echo "=========================================="
