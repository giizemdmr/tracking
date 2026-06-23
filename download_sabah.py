import os
import gdown

SABAH_DIR = "downloads/sabah"
os.makedirs(SABAH_DIR, exist_ok=True)

files = {
    "20260615070812_000002.MP4": "1MNGVA25-j9Yb7QZy9rWK2I6q7_Kw976J",
    "20260615072313_000003.MP4": "1zJBxFxUIWZQ1ai52YuHSyqX9nVvrSzU2",
    "20260615072313_000004.MP4": "1QfJENBq2HpkTFI0PVWLJU--VFb73yZaW",
    "20260615072313_000005.MP4": "1e1u7xBzEJRFsGuqPubiEtohI3IMZWcfK",
    "20260615072313_000006.MP4": "1rt23mWkEs4By0Qz2lTPs7Tae7OJMA6eb",
    "20260615072313_000007.MP4": "1vNts4z_z3VALOO7nnUpW7VqdczQ8j8ub",
    "20260615072313_000008.MP4": "1_DkCnfiJj3DU5U91DKnyP52cJMr3tyFZ",
    "20260615072313_000009.MP4": "1GjoBZ9xExsyYwyfcSWVReDDGwvb2Qijw",
    "lines_ruspazarsabah.json": "1QuxOh0yIqOtSeQiDUpYOEq7JXv9Hc799"
}

print("="*60)
print(" SABAH VIDEOLARI INDIRME YARDIMCISI")
print("="*60)

for filename, file_id in files.items():
    output_path = os.path.join(SABAH_DIR, filename)
    if os.path.exists(output_path):
        print(f"[INFO] {filename} zaten mevcut, indirme atlaniyor.")
        continue
        
    print(f"\n[INFO] {filename} indiriliyor (ID: {file_id})...")
    try:
        gdown.download(id=file_id, output=output_path, quiet=False)
        print(f"[OK] {filename} basariyla indirildi.")
    except Exception as e:
        print(f"[ERROR] {filename} indirilemedi: {e}")

print("\nIslem tamamlandi.")
