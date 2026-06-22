"""
line_drawer.py - Interaktif Sanal Cizgi (Virtual Line / Gate) Cizme Araci
==========================================================================
Video uzerinde sol tik ile coklu nokta (polyline) belirleyerek yola dik 
sanal kapilari (gate) tanimlar ve config/lines.json dosyasina kaydeder.

Kontroller:
  - Sol Tik       : Yeni bir nokta ekle
  - Sag Tik       : Son eklenen noktayi geri al (veya cizimi iptal et)
  - 'c' / 'Enter' : Nokta eklemeyi bitir ve kapiyi tamamla (isim iste)
  - 's'           : config/lines.json'a kaydet
  - 'u'           : Son tamamlanan kapiyi geri al (undo)
  - 'q'           : Cik
"""

import cv2
import json
import numpy as np
import os
import ctypes

# 1. High-DPI Awareness (Windows ekran olceklendirme duzeltmesi)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class LineDrawer:
    """
    Video karesi uzerinde interaktif olarak 2-noktali cizgi (gate) tanimlama araci.
    """
    def __init__(self, video_path: str, frame_index: int = 0):
        self.video_path = video_path
        self.frame_index = frame_index
        self.frame = self._get_specific_frame(frame_index)
        
        # State management
        self.lines = []           # [{"name": "...", "points": [[x1,y1], [x2,y2], ...]}, ...]
        self.current_points = []  # O an cizilen kapinin noktalari
        self.mouse_pos = None     # Canli onizleme icin anlık imleç pozisyonu
        self.window_name = "LineDrawer - Virtual Gate Setup"
        
        # --- ROI (Zone) Support ---
        self.draw_mode = "GATE"   # "GATE" veya "ZONE"
        self.zone_data = None     # {"points": [[x1,y1], ...]}
        # --------------------------
        
        # --- AUTO LOAD EXISTING ---
        self._load_existing_data()
        
        # Colors (BGR)
        self.entry_color = (0, 255, 100)    # Giris kapilari: Yesil
        self.exit_color = (0, 80, 255)      # Cikis kapilari: Kirmizi
        self.neutral_color = (255, 200, 0)  # Diger: Mavi
        self.preview_color = (0, 255, 255)  # Onizleme: Sari
        self.point_color = (0, 0, 255)      # Nokta: Kirmizi

    def _load_existing_data(self):
        """Mevcut config dosyalarindan cizimleri yukler."""
        try:
            from src.config_manager import config_manager
            
            # Lines yukle
            lp = config_manager.lines_file or "config/lines.json"
            if os.path.exists(lp):
                with open(lp, 'r', encoding='utf-8') as f:
                    self.lines = json.load(f)
                print(f"[OK] Mevcut {len(self.lines)} kapi yuklendi.")
            
            # Zone yukle
            zp = config_manager.zone_file or "config/zone.json"
            if os.path.exists(zp):
                with open(zp, 'r', encoding='utf-8') as f:
                    self.zone_data = json.load(f)
                print(f"[OK] Mevcut ROI (Zone) yuklendi.")
        except Exception as e:
            print(f"[WARNING] Mevcut veriler yuklenirken hata olustu: {e}")

    def _get_specific_frame(self, index: int):
        """Reads a specific frame from the input video and resizes it to 1024 width."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {self.video_path}")
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise ValueError(f"Could not read frame {index} from: {self.video_path}")
        
        # --- ORIGINAL SCALE USE ---
        # The frame is kept at its original dimension so drawn coordinates
        # perfectly match the original video resolution.
        # -----------------------------
        
        return frame

    def _get_line_color(self, name: str) -> tuple:
        """Kapi isminden renk belirler."""
        name_lower = name.lower()
        if "giris" in name_lower or "entry" in name_lower:
            return self.entry_color
        elif "cikis" in name_lower or "exit" in name_lower:
            return self.exit_color
        return self.neutral_color

    def mouse_callback(self, event, x, y, flags, param):
        """Standard OpenCV mouse callback for drawing lines."""
        # Sol Tik: Nokta ekle
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append([x, y])
            print(f"[NOKTA EKLENDI] ({x}, {y}) — Toplam nokta: {len(self.current_points)}")

        # Sag Tik: Son noktayi geri al (veya komple iptal et)
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.current_points:
                removed = self.current_points.pop()
                print(f"[IPTAL] Son nokta silindi: {removed}")
            else:
                print("[IPTAL] Zaten cizilen nokta yok.")

        # Fare hareketi: Canli onizleme icin pozisyonu takip et
        elif event == cv2.EVENT_MOUSEMOVE:
            self.mouse_pos = (x, y)

    def save_lines(self, output_path: str = None):
        """Saves all defined lines/gates and the zone to JSON files."""
        if self.current_points:
            print("\n[HATA] Hala cizilmekte olan noktalar var! Lutfen 'Enter' ile cizimi onaylayin, sonra 's' ile kaydedin.")
            return

        from src.config_manager import config_manager
        
        # 1. Gates (Lines) Kaydi
        if output_path is None:
            output_path = config_manager.lines_file or "config/lines.json"
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.lines, f, indent=4)
            print(f"\n[OK] {len(self.lines)} kapi '{output_path}' dosyasina kaydedildi.")
        except Exception as e:
            print(f"[ERROR] Gate kayit basarisiz: {e}")

        # 2. Zone (ROI) Kaydi
        zone_path = config_manager.zone_file or "config/zone.json"
        if self.zone_data:
            os.makedirs(os.path.dirname(zone_path), exist_ok=True)
            try:
                with open(zone_path, 'w', encoding='utf-8') as f:
                    json.dump(self.zone_data, f, indent=4)
                print(f"[OK] ROI (Zone) '{zone_path}' dosyasina kaydedildi.")
            except Exception as e:
                print(f"[ERROR] Zone kayit basarisiz: {e}")
        else:
            print("[INFO] Kaydedilecek Zone yok.")


    def _draw_overlay(self):
        """Refreshes the display frame with all annotations."""
        canvas = self.frame.copy()
        
        # 1. Kayitli cizgileri ciz (Polylines)
        for gate in self.lines:
            name = gate["name"]
            pts = gate["points"]
            if len(pts) < 2:
                continue
                
            color = self._get_line_color(name)
            np_pts = np.array(pts, np.int32).reshape((-1, 1, 2))
            
            # Cizgiler
            cv2.polylines(canvas, [np_pts], isClosed=False, color=color, thickness=3, lineType=cv2.LINE_AA)
            
            # Uc ve ara noktalari ciz
            for pt in pts:
                p_tup = tuple(pt)
                cv2.circle(canvas, p_tup, 6, color, -1, lineType=cv2.LINE_AA)
                cv2.circle(canvas, p_tup, 6, (0, 0, 0), 1, lineType=cv2.LINE_AA)
            
            # Isim etiketi (ilk veya orta noktaya yakin bir yere yazalim)
            mid_idx = len(pts) // 2
            label_pos = (pts[mid_idx][0] - 30, pts[mid_idx][1] - 12)
            cv2.putText(canvas, name, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        
        # 1.1. Kayitli Zone'u ciz
        if self.zone_data and self.zone_data.get("points"):
            zpts = np.array(self.zone_data["points"], np.int32).reshape((-1, 1, 2))
            cv2.polylines(canvas, [zpts], isClosed=True, color=(150, 150, 150), thickness=2, lineType=cv2.LINE_AA)
            cv2.putText(canvas, "ZONE (ROI)", (self.zone_data["points"][0][0], self.zone_data["points"][0][1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)

        # 2. O an cizilmekte olan noktalar (Onizleme)
        if self.current_points:
            color = self.point_color if self.draw_mode == "GATE" else (255, 100, 0) # Zone icin Turuncu
            np_curr = np.array(self.current_points, np.int32).reshape((-1, 1, 2))
            is_closed = True if self.draw_mode == "ZONE" else False
            cv2.polylines(canvas, [np_curr], isClosed=is_closed, color=color, thickness=2, lineType=cv2.LINE_AA)
            
            for pt in self.current_points:
                p_tup = tuple(pt)
                cv2.circle(canvas, p_tup, 8, color, -1, lineType=cv2.LINE_AA)
                cv2.circle(canvas, p_tup, 8, (255, 255, 255), 2, lineType=cv2.LINE_AA)
            
            # Fareye dogru esnek onizleme cizgisi (Zone ise son nokta ile ilk noktayi da hayali birlestir)
            if self.mouse_pos is not None:
                last_pt = tuple(self.current_points[-1])
                cv2.line(canvas, last_pt, self.mouse_pos, self.preview_color, 2, lineType=cv2.LINE_AA)
                
                if self.draw_mode == "ZONE" and len(self.current_points) > 1:
                    first_pt = tuple(self.current_points[0])
                    cv2.line(canvas, first_pt, self.mouse_pos, (200, 200, 200), 1, cv2.LINE_AA)
                
                cv2.circle(canvas, self.mouse_pos, 5, self.preview_color, -1, lineType=cv2.LINE_AA)
        
        # 3. Mod Bilgisi
        mode_text = f"MODE: {self.draw_mode}"
        cv2.putText(canvas, mode_text, (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, mode_text, (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1, cv2.LINE_AA)
        
        # 3. Bilgi paneli (Ekrani kapatmamasi icin kaldirildi)
        # Kisa yollar zaten terminalde gosteriliyor.
        
        return canvas

    def run(self):
        """Executes the main visualization loop."""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
        # Frame zaten 1024 oldugu icin direkt gosteriyoruz
        h, w = self.frame.shape[:2]
        cv2.resizeWindow(self.window_name, w, h)
        
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        
        print("\n" + "=" * 50)
        print(f"  LINE DRAWER — Virtual Gate Setup (Polylines)")
        print(f"  Frame: {self.frame_index}")
        print("=" * 50)
        print("Kontroller:")
        print("  - Sol Tik       : Nokta ekle (istediginiz kadar)")
        print("  - Sag Tik       : Son eklenen noktayi geri al")
        print("  - 'c' veya Enter: Cizimi tamamla")
        print("  - 'z'           : GATE / ZONE (ROI) Modu Degistir")
        print("  - 's'           : Kaydet (config/lines.json ve config/zone.json)")
        print("  - 'u'           : Son kapiyi/zone'u geri al (undo)")
        print("  - 'q'           : Cik")
        print("=" * 50 + "\n")

        while True:
            display = self._draw_overlay()
            cv2.imshow(self.window_name, display)
            
            key = cv2.waitKey(30) & 0xFF
            
            # 'c', 'C' veya 'Enter' (13) — Cizimi bitir
            if key in [ord('c'), ord('C'), 13]:
                if len(self.current_points) >= 2:
                    if self.draw_mode == "GATE":
                        gate_name = input("\nBu kapi icin isim girin (ornek: Giris_1): ").strip()
                        if not gate_name:
                            gate_name = f"Gate_{len(self.lines) + 1}"
                        
                        self.lines.append({
                            "name": gate_name,
                            "points": list(self.current_points)
                        })
                        print(f"[OK] Kapi '{gate_name}' ({len(self.current_points)} nokta) kaydedildi.")
                    else:
                        self.zone_data = {"points": list(self.current_points)}
                        print(f"[OK] ROI (Zone) ({len(self.current_points)} nokta) kaydedildi.")
                    
                    self.current_points = []
                else:
                    if len(self.current_points) == 1:
                        print("[WARNING] En az 2 nokta gerekli.")
            
            # 'z' — Mod Degistir
            if key in [ord('z'), ord('Z')]:
                self.draw_mode = "ZONE" if self.draw_mode == "GATE" else "GATE"
                self.current_points = []
                print(f"[*] Mod Degistirildi: {self.draw_mode}")
            
            # 's' — Kaydet
            if key in [ord('s'), ord('S')]:
                self.save_lines()
            
            # 'u' — Undo (son ciziyi geri al)
            elif key in [ord('u'), ord('U')]:
                if self.draw_mode == "GATE" and self.lines:
                    removed = self.lines.pop()
                    print(f"[UNDO] '{removed['name']}' kapisi geri alindi.")
                elif self.draw_mode == "ZONE" and self.zone_data:
                    self.zone_data = None
                    print(f"[UNDO] Zone geri alindi.")
                else:
                    print("[UNDO] Geri alinacak bir sey yok.")
            
            # 'q' — Cik
            elif key in [ord('q'), ord('Q')]:
                break

        cv2.destroyAllWindows()


if __name__ == '__main__':
    import argparse
    import sys
    import os
    
    # Proje kok (root) dizinini bul ve calisma dizinini (CWD) orasi yap
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    os.chdir(project_root)
    sys.path.insert(0, project_root)
    
    from src.config_manager import config_manager
    
    # Config den default video path cek
    default_vid = config_manager.pipeline.video_path
    if not default_vid:
        default_vid = "data/traffic_video.mp4"

    parser = argparse.ArgumentParser(description="Interactive Virtual Line/Gate Drawing Tool")
    parser.add_argument("--video", type=str, default=default_vid, help="Path to video (config'ten cekiyor)")
    parser.add_argument("--frame", type=int, default=0, help="Frame index to start drawing from")
    args = parser.parse_args()
    
    try:
        print(f"[*] VIDEO YUKLENIYOR: {args.video}")
        drawer = LineDrawer(args.video, args.frame)
        drawer.run()
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
