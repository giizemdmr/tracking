import os
import time
import subprocess

local_dir = os.path.abspath("fidangor")
os.makedirs(local_dir, exist_ok=True)

remote_path = "root@69.176.92.106:/workspace/tracking/ciktilar/."
port = "50171"

print("="*60)
print(" FIDANGOR RAPOR SENKRONİZASYON ARACI")
print("="*60)
print(f"Hedef Klasör: {local_dir}")
print("Yeni raporlar sunucuda oluştukça otomatik olarak buraya indirilecek...")
print("Durdurmak için Ctrl+C tuşlarına basabilirsiniz.\n")

known_files = set(os.listdir(local_dir))

while True:
    try:
        # Run scp to pull new files
        cmd = ["scp", "-P", port, "-r", remote_path, local_dir]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Check for new files
        current_files = set(os.listdir(local_dir))
        new_files = current_files - known_files
        
        if new_files:
            for nf in new_files:
                print(f"[YENİ RAPOR GELDİ]: {nf}")
            known_files = current_files
            
    except KeyboardInterrupt:
        print("\nSenkronizasyon sonlandırıldı.")
        break
    except Exception as e:
        print(f"[HATA] Senkronizasyon sırasında hata oluştu: {e}")
        
    time.sleep(10)
