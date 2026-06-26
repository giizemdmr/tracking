#!/bin/bash
# ==============================================
# GPU PARALEL TEST SCRIPTI
# Kullanim: bash run_test.sh [video_sayisi]
# Ornek:    bash run_test.sh 3   (3 video paralel)
#           bash run_test.sh 6   (6 video paralel)
# ==============================================

MAX_VIDEOS=${1:-1}
LINES_FILE="config/line_sabahkumbasi.json"

echo "================================================="
echo "  GPU PARALEL PERFORMANS TESTI"
echo "  Paralel Video Sayisi: $MAX_VIDEOS"
echo "================================================="

# nvidia-smi bilgisini goster
echo ""
nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader 2>/dev/null
echo ""

PIDS=()

for i in $(seq 1 $MAX_VIDEOS); do
    VIDEO_FILE="video${i}.mp4"
    EXCEL_FILE="rapor_video${i}.xlsx"

    if [ ! -f "$VIDEO_FILE" ]; then
        echo "[UYARI] $VIDEO_FILE bulunamadi, atlaniyor..."
        continue
    fi

    echo "[BASLATILIYOR] Terminal $i: $VIDEO_FILE -> $EXCEL_FILE"
    python3 main.py --video "$VIDEO_FILE" --lines "$LINES_FILE" --excel "$EXCEL_FILE" &
    PIDS+=($!)
    sleep 1
done

echo ""
echo "================================================="
echo "  $MAX_VIDEOS adet video paralel calisiyor."
echo "  Tum islemler bitmesini bekliyoruz..."
echo "  GPU durumunu izlemek icin baska terminalden:"
echo "    watch -n 1 nvidia-smi"
echo "================================================="
echo ""

# Tum islemlerin bitmesini bekle
for PID in "${PIDS[@]}"; do
    wait $PID
done

echo ""
echo "================================================="
echo "✅ TUM PARALEL TESTLER TAMAMLANDI!"
echo "Olusturulan raporlar:"
for i in $(seq 1 $MAX_VIDEOS); do
    EXCEL_FILE="rapor_video${i}.xlsx"
    if [ -f "$EXCEL_FILE" ]; then
        echo "  ✅ $EXCEL_FILE"
    fi
done
echo "================================================="
