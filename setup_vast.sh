#!/bin/bash

echo "=== VAST.AI KURULUMU BASLIYOR ==="

# 1. Gerekli Kutuphaneleri Kur
echo "Kutuphaneler yukleniyor..."
pip install ultralytics opencv-python-headless pandas openpyxl gdown pyproj shapely lapx

# 2. Videoyu Google Drive'dan Indir
echo "Test videosu Google Drive'dan indiriliyor..."
gdown "1Q75bU4PlNX4AKMugGk_xYqWhCKjJcc3T" -O video.mp4

# 3. Model Dosyasini Google Drive'dan Indir
echo "Model best.pt Google Drive'dan indiriliyor..."
gdown "1-ynsynHc1-TVVJV6-rE5FuLB4CxANOD9" -O best.pt

# 4. Modeli TensorRT Engine Formatina Cevir
echo "Model TensorRT Engine formatina cevriliyor..."
python3 -c "from ultralytics import YOLO; model = YOLO('best.pt'); model.export(format='engine', half=True, imgsz=1024, workspace=4)"

echo "================================================="
echo "✅ Kurulum, Indirmeler ve TensorRT Donusumu Tamamlandi!"
echo "Sistemi baslatmak icin:"
echo "   python main.py"
echo "================================================="
