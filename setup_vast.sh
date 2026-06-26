#!/bin/bash

echo "=== VAST.AI KURULUMU BASLIYOR ==="

# 1. Gerekli Kutuphaneleri Kur
echo "Kutuphaneler yukleniyor..."
pip install ultralytics opencv-python-headless pandas openpyxl gdown pyproj shapely lapx

# 2. Videoyu Google Drive'dan Indir
echo "Test videosu Google Drive'dan indiriliyor..."
gdown "1Q75bU4PlNX4AKMugGk_xYqWhCKjJcc3T" -O video.mp4

echo "================================================="
echo "✅ Kurulum ve Video Indirme Tamamlandi!"
echo "⚠️ LUTFEN DIKKAT:"
echo "1. 'best.pt' dosyanizi bu klasore (tracking) yukleyin."
echo "2. Yukledikten sonra asagidaki komutu calistirarak modeli TensorRT (engine) formatina cevirin:"
echo "   yolo export model=best.pt format=engine half=True imgsz=1024 workspace=4"
echo "3. Engine dosyasi olustuktan sonra sistemi baslatin:"
echo "   python main.py"
echo "================================================="
