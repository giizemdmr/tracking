import os
import subprocess
import shutil
import sys

# Get the base directory (where this script is located)
base_dir = os.path.dirname(os.path.abspath(__file__))
rclone_conf = os.path.join(base_dir, "rclone.conf")
model_dir = os.path.join(base_dir, "model")
model_pt_path = os.path.join(model_dir, "best.pt")

os.makedirs(model_dir, exist_ok=True)

file_id = "1-ynsynHc1-TVVJV6-rE5FuLB4CxANOD9"

print(f"Downloading file ID {file_id} from Google Drive using rclone...")

# Check if rclone is installed
if not shutil.which("rclone"):
    print("[ERROR] 'rclone' bulunamadı! Lütfen sisteminize rclone yükleyin ve PATH ortam değişkenine ekleyin.")
    print("Kurulum kılavuzu için bkz: https://rclone.org/downloads/")
    sys.exit(1)

if not os.path.exists(rclone_conf):
    print(f"[ERROR] '{rclone_conf}' bulunamadı! Lütfen rclone yapılandırma dosyasının yerinde olduğundan emin olun.")
    sys.exit(1)

# Run rclone command to copy file by ID
cmd = [
    "rclone",
    "--config", rclone_conf,
    "backend", "copyid",
    "drive:",
    file_id,
    model_pt_path
]

print(f"Executing: {' '.join(cmd)}")
try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Download completed successfully! Saved to {model_pt_path}")
    else:
        print(f"Error downloading file with rclone:\n{result.stderr}")
        sys.exit(1)
except Exception as e:
    print(f"Failed to execute rclone: {e}")
    sys.exit(1)
