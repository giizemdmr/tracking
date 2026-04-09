"""
zone_helper.py - Profesyonel Bölge (Zone) Çizim Aracı

Bu araç, videonun ilk karesini açarak farenizle bölgeler (poligonlar) çizmenizi sağlar.
Çizilen bölgeler otomatik olarak 'bolgeler.json' dosyasına kaydedilir ve
'main.py' bu dosyayı okuyarak takibi gerçekleştirir.

Kullanım:
1. Sol tık: Nokta ekle
2. Sağ tık: Bölgeyi kapat (Poligonu tamamla)
3. 's' tuşu: Bölgeleri kaydet ve çık
4. 'r' tuşu: Son çizilen bölgeyi sil
5. 'q' tuşu: Kaydetmeden çık
"""

import cv2
import numpy as np
import json
import os

# ==========================================
# AYARLAR (Burayı videonuza göre güncelleyin)
# ==========================================
VIDEO_PATH = r"D:\avm.mp4" 
SAVE_FILE = "bolgeler.json"
DISPLAY_SCALE = 1 

# ==========================================
# ÇİZİM DEĞİŞKENLERİ
# ==========================================
current_points = []
polygons = []
zone_names = []

def mouse_callback(event, x, y, flags, param):
    global current_points, polygons, zone_names
    scale = param
    
    # Koordinatları orijinal boyutuna geri ölçeklendir
    real_x = int(x / scale)
    real_y = int(y / scale)
    
    if event == cv2.EVENT_LBUTTONDOWN:
        current_points.append((real_x, real_y))
        print(f"[+] Nokta eklendi: ({real_x}, {real_y})")
        
    elif event == cv2.EVENT_RBUTTONDOWN:
        if len(current_points) >= 3:
            pts = np.array(current_points, np.int32)
            polygons.append(pts)
            name = str(len(polygons))
            zone_names.append(name)
            print(f"[OK] Bölge {name} kaydedildi! ({len(current_points)} nokta)")
            current_points = []
        else:
            print("[!] Hata: Bir poligon oluşturmak için en az 3 nokta gereklidir.")

def save_to_json(filename):
    """Bölgeleri JSON formatında kaydeder."""
    data = {
        "polygons": [poly.tolist() for poly in polygons],
        "names": zone_names
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"\n✅ {len(polygons)} adet bölge '{filename}' dosyasına başarıyla kaydedildi!")

def load_existing_polygons(filename):
    """Var olan bölgeleri dosyadan yükle."""
    global polygons, zone_names
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            polygons = [np.array(p, np.int32) for p in data.get("polygons", [])]
            zone_names = data.get("names", [])
            print(f"[OK] {len(polygons)} adet eski bölge yüklendi. Silmek için 'r' tuşunu kullanabilirsiniz.")
        except:
            print("[!] Eski bölge dosyası okunamadı, temiz sayfa açılıyor.")

def main():
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Hata: Video dosyası bulunamadı: {VIDEO_PATH}")
        return

    # Önce eski bölgeleri yükle
    load_existing_polygons(SAVE_FILE)

    cap = cv2.VideoCapture(VIDEO_PATH)
    # 30. saniyeye git
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(30 * fps))
    
    ret, frame = cap.read()
    if not ret:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    cap.release()

    if not ret:
        print("❌ Hata: Video karesi okunamadı.")
        return

    h, w = frame.shape[:2]
    # Ekran boyutuna sığması için ölçekleme
    dw, dh = int(w * DISPLAY_SCALE), int(h * DISPLAY_SCALE)
    frame_resized = cv2.resize(frame, (dw, dh))

    cv2.namedWindow("Bolge Cizici - AI Optimize")
    cv2.setMouseCallback("Bolge Cizici - AI Optimize", mouse_callback, DISPLAY_SCALE)

    print("\n" + "="*50)
    print("🎨 BÖLGE ÇİZİM ARACI")
    print("="*50)
    print(">> Sol Tık: Köşe noktası koy")
    print(">> Sağ Tık: Poligonu bitir (Bölgeyi kaydet)")
    print(">> 'r' Tuşu: SON ÇİZİLEN BÖLGEYİ SİL")
    print(">> 's' Tuşu: DOSYAYA KAYDET VE ÇIK ✅")
    print(">> 'q' Tuşu: İptal et (Kaydetmez) 🛑")
    print("="*50 + "\n")

    while True:
        display_img = frame_resized.copy()
        overlay = display_img.copy()

        # Bölgeleri çiz
        for i, poly in enumerate(polygons):
            scaled_poly = (poly * DISPLAY_SCALE).astype(np.int32)
            cv2.fillPoly(overlay, [scaled_poly], (0, 255, 0))
            cv2.polylines(display_img, [scaled_poly], True, (0, 255, 0), 2, cv2.LINE_AA)
            
            M = cv2.moments(scaled_poly)
            if M['m00'] != 0:
                cx = int(M['m10'] / M['m00'])
                cy = int(M['m01'] / M['m00'])
                cv2.putText(display_img, zone_names[i], (cx, cy), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 0), 3)
                cv2.putText(display_img, zone_names[i], (cx, cy), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

        cv2.addWeighted(overlay, 0.4, display_img, 0.6, 0, display_img)

        # Çizilmekte olan noktalar
        if len(current_points) > 0:
            pts = np.array([(int(p[0]*DISPLAY_SCALE), int(p[1]*DISPLAY_SCALE)) for p in current_points], np.int32)
            cv2.polylines(display_img, [pts], False, (0, 0, 255), 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(display_img, tuple(p), 5, (0, 0, 255), -1)

        cv2.imshow("Bolge Cizici - AI Optimize", display_img)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            save_to_json(SAVE_FILE)
            break
        elif key == ord('r'):
            if polygons:
                polygons.pop()
                zone_names.pop()
                print("↶ Son bölge silindi.")
        elif key == ord('q'):
            print("🛑 Kaydetmeden çıkıldı.")
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
