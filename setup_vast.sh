#!/bin/bash

echo "=== VAST.AI KURULUMU BASLIYOR ==="

# 1. Gerekli Kutuphaneleri Kur
echo "Kutuphaneler yukleniyor..."
pip install ultralytics opencv-python-headless pandas openpyxl gdown pyproj shapely lapx

# 2. Videolari Google Drive'dan Indir
echo ""
echo "=== 6 ADET TEST VIDEOSU INDIRILIYOR ==="

gdown "1Q75bU4PlNX4AKMugGk_xYqWhCKjJcc3T" -O video1.mp4
echo "[1/6] video1.mp4 indirildi."

gdown "1Fn5Iz9dVMYJEfsoJRk9y35b7j9FiIgdE" -O video2.mp4
echo "[2/6] video2.mp4 indirildi."

gdown "1zmOWv8MwV9m7zXRu2t0uNDHiAHdBbNkj" -O video3.mp4
echo "[3/6] video3.mp4 indirildi."

gdown "17PjQXjC9p20FLfLTfTCqoM9sRc4zDlRI" -O video4.mp4
echo "[4/6] video4.mp4 indirildi."

gdown "1jpDqrxQ7gnWA4Bw_PAQzbDlYXeMzqQRZ" -O video5.mp4
echo "[5/6] video5.mp4 indirildi."

gdown "1TpdvBBGxyihODysYluqDwD9QU-qiOKXP" -O video6.mp4
echo "[6/6] video6.mp4 indirildi."

echo ""
echo "=== TUM VIDEOLAR INDIRILDI ==="

# 3. Model Dosyasini Google Drive'dan Indir
echo ""
echo "Model best.pt Google Drive'dan indiriliyor..."
gdown "1-ynsynHc1-TVVJV6-rE5FuLB4CxANOD9" -O best.pt

# 4. Modeli TensorRT Engine Formatina Cevir
echo "Model TensorRT Engine formatina cevriliyor..."
python3 -c "from ultralytics import YOLO; model = YOLO('best.pt'); model.export(format='engine', half=True, imgsz=1024, workspace=4)"

echo ""
echo "================================================="
echo "✅ Kurulum, Indirmeler ve TensorRT Donusumu Tamamlandi!"
echo ""
echo "KULLANIM:"
echo "  Tek video calistirmak icin:"
echo "    python3 main.py --video video1.mp4 --excel rapor1.xlsx"
echo ""
echo "  Paralel GPU testi icin (ornek: 3 video ayni anda):"
echo "    bash run_test.sh 3"
echo ""
echo "  Tum 6 videoyu paralel calistirmak icin:"
echo "    bash run_test.sh 6"
echo "================================================="
