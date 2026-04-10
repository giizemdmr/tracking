set -e
echo "Updating apt and installing dependencies..."
apt-get update > /dev/null
apt-get install -y libgl1 libglib2.0-0 > /dev/null

echo "Setting up repository..."
rm -rf /root/tracking
mkdir -p /root/tracking
tar -xf /root/tracking.tar -C /root/tracking

echo "Setting up virtual environment..."
python3 -m venv /root/tracking/venv
source /root/tracking/venv/bin/activate
pip install --upgrade pip > /dev/null
pip install opencv-python numpy ultralytics shapely openpyxl > /dev/null

echo "Moving assets to tracking directory..."
mkdir -p /root/tracking/models
mv /root/best.pt /root/tracking/models/best.pt || true
mv "/root/2026-04-09 17-51-58.mp4" /root/tracking/video.mp4 || true
mv /root/zones.json /root/tracking/config/zones.json || true
cp /root/tracking/config/zones.json /root/tracking/bolgeler.json || true

echo "Updating pipeline_config.yaml to match remote paths..."
sed -i 's|C:\\\\Users\\\\W11\\\\Videos\\\\2026-04-09 17-51-58.mp4|/root/tracking/video.mp4|g' /root/tracking/config/pipeline_config.yaml
sed -i 's|D:\\\\tracking\\\\models\\\\yolov8.engine|/root/tracking/models/best.engine|g' /root/tracking/config/pipeline_config.yaml

echo "Exporting model to TensorRT Engine..."
yolo export model=/root/tracking/models/best.pt format=engine half=True imgsz=1024 workspace=4

echo "Initialization Complete"
