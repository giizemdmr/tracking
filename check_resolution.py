import cv2
import glob
import os
import json

print("Checking video resolutions...")
videos = glob.glob("downloads/**/*.mp4", recursive=True) + glob.glob("downloads/**/*.MP4", recursive=True)
if not videos:
    print("No videos found in downloads")
else:
    for v in videos[:3]:
        cap = cv2.VideoCapture(v)
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"Video: {os.path.basename(v)} | Resolution: {w}x{h}")
        cap.release()

# List line JSON files
print("\nChecking line configurations in config/ ...")
for jf in glob.glob("config/lines_*.json"):
    with open(jf, "r") as f:
        data = json.load(f)
    print(f"\nFile: {os.path.basename(jf)}")
    for item in data:
        name = item.get("name")
        points = item.get("points")
        print(f"  Line {name}: points={points}")
