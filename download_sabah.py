import os
import gdown

SABAH_DIR = "downloads/sabah"
os.makedirs(SABAH_DIR, exist_ok=True)

print("="*60)
print(" YENI SABAH VIDEOLARI INDIRME YARDIMCISI")
print("="*60)

try:
    gdown.download_folder(id="1edge4k0E-g-nrK1JUYV6nECJ4IT7FUfs", output=SABAH_DIR, quiet=False, use_cookies=False)
    print("\n[OK] Sabah klasörü indirme işlemi tamamlandı.")
except Exception as e:
    print(f"\n[ERROR] İndirme sırasında bir hata oluştu: {e}")
