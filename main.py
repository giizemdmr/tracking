import cv2
import threading
import queue
import time
import os
import yaml
import numpy as np
from types import SimpleNamespace
from typing import Optional, Tuple, Any
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

from src.reporting import RegionManager, VehicleTracker, ReportGenerator

# D:\config.py referansindan arac renkleri (BGR)
VEHICLE_COLORS = {
    "yaya": (128, 128, 128),
    "bisiklet": (255, 255, 0),
    "motosiklet": (255, 0, 255),
    "otomobil": (0, 255, 0),
    "minivan": (180, 105, 255),
    "otobus": (255, 0, 0),
    "kamyon": (0, 0, 255),
    "tir": (0, 0, 180),
    "pikap": (0, 165, 255),
    "panelvan": (200, 150, 100),
    "minibus": (0, 255, 255),
    "kamyonet": (128, 0, 255),
    "arac": (200, 200, 200),
}

def get_vehicle_color(vehicle_type: str) -> tuple:
    """Arac tipine gore BGR renk dondurur."""
    v_type_lower = vehicle_type.lower()
    for key, color in VEHICLE_COLORS.items():
        if key in v_type_lower:
            return color
    return VEHICLE_COLORS["arac"]

def load_config(yaml_path: str) -> SimpleNamespace:
    """YAML dosyasini okur, D:\\config.py varsayilanlari ile birlestirir."""
    defaults = {
        "video_path": "avm.mp4",
        "model_path": r"D:\tracking\models\yolov8.engine",
        "regions_file": "bolgeler.json",
        "excel_filename": "trafik_raporu_yogunburc.xlsx",
        "headless_mode": False,
        "skip_frames": 4,
        "display_scale": 1.0,
        "confidence_threshold": 0.25,
        "nms_threshold": 0.70, # Perspektif yığılması icin artirildı (Eski deger: 0.45). Kesisim toleransi yukseltilerek araclari yutmasi engellendi.
        "input_size": 1024,
        "use_half": True,
        "track_thresh": 0.5,
        "track_buffer": 120,
        "match_thresh": 0.7,
        "max_disappeared": 50,
        "max_distance": 500,
        "zone_entry_frames": 3,
        "zone_change_frames": 5,
        "min_route_zone_duration": 15,
    }
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        defaults.update(data)
        print(f"[OK] Config yuklendi: {yaml_path}")
    except Exception as e:
        print(f"[WARN] YAML okunamadi ({e}), varsayilan degerler kullaniliyor.")
    
    cfg = SimpleNamespace(**defaults)
    cfg.get_vehicle_color = get_vehicle_color
    return cfg

class VideoReader(threading.Thread):
    def __init__(self, config, input_queue: queue.Queue, stop_event: threading.Event) -> None:
        super().__init__(name="VideoReaderThread")
        self.config = config
        self.input_queue: queue.Queue = input_queue
        self.stop_event = stop_event
        self.fps = 30.0
        self.width = 1920
        self.height = 1080
        self._initialize_video_metadata()

    def _initialize_video_metadata(self) -> None:
        cap = cv2.VideoCapture(self.config.video_path)
        if not cap.isOpened():
            print(f"[!] CRITICAL ERROR: Video dosyasi acilamadi: {self.config.video_path}")
            self.stop_event.set()
            return
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()

    def run(self) -> None:
        if self.stop_event.is_set(): return
        cap = cv2.VideoCapture(self.config.video_path)
        try:
            while cap.isOpened() and not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break
                
                while not self.stop_event.is_set():
                    try:
                        self.input_queue.put(frame, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        except Exception as e:
            print(f"[VideoReader] Beklenmeyen Hata: {e}")
        finally:
            cap.release()
            try:
                self.input_queue.put(None, timeout=1) 
            except:
                pass


class TrackerEngine(threading.Thread):
    def __init__(self, config, input_queue: queue.Queue, output_queue: queue.Queue, stop_event: threading.Event) -> None:
        super().__init__(name="TrackerEngineThread")
        self.config = config
        self.input_queue: queue.Queue = input_queue
        self.output_queue: queue.Queue = output_queue
        self.stop_event = stop_event

    def run(self) -> None:
        if self.stop_event.is_set(): return
        try:
            model = YOLO(self.config.model_path, task='detect')
            
            while not self.stop_event.is_set():
                frame = None
                while not self.stop_event.is_set():
                    try:
                        frame = self.input_queue.get(timeout=0.1)
                        break
                    except queue.Empty:
                        pass
                
                if frame is None or self.stop_event.is_set():
                    if frame is not None: self.input_queue.task_done()
                    break
                    
                # Botsort parametrelerini direkt YAML'dan okuyoruz
                # NMS ve Tracker parametreleri optimize sekilde (TRT uzerinden sifir latency islemleri)
                results = model.track(
                    source=frame, 
                    stream=True, 
                    persist=True, 
                    half=self.config.use_half, 
                    verbose=False, 
                    tracker="config/botsort_traffic.yaml", 
                    imgsz=self.config.input_size,
                    conf=self.config.confidence_threshold,
                    iou=self.config.nms_threshold, # Kesisim (Overlap) esnekligi
                    agnostic_nms=False # OTO, OTOBUS'u yutmasin diye class spesifik kalmali
                )
                
                for result in results:
                    if self.stop_event.is_set(): break
                    while not self.stop_event.is_set():
                        try:
                            kalman_states = {}
                            if hasattr(model, 'predictor') and model.predictor is not None:
                                if hasattr(model.predictor, 'trackers') and len(model.predictor.trackers) > 0:
                                    bt_tracker = model.predictor.trackers[0]
                                    for t in getattr(bt_tracker, 'tracked_stracks', []) + getattr(bt_tracker, 'lost_stracks', []):
                                        kalman_states[int(t.track_id)] = t.mean[:4].copy()
                                        
                            # Model isimlerini ve 8 boyutlu state tabanlarini kuyruk ile gönder
                            self.output_queue.put((result.orig_img, result.boxes, result.names, kalman_states), timeout=0.1)
                            break
                        except queue.Full:
                            pass
                
                self.input_queue.task_done()
                
        except Exception as e:
            print(f"\n[TrackerEngine] Modelle Baglantili Kritik Hata: {e}")
            self.stop_event.set()
        finally:
            try:
                self.output_queue.put((None, None, None, None), timeout=1)
            except:
                pass


class ResultProcessor(threading.Thread):
    def __init__(self, config, output_queue: queue.Queue, stop_event: threading.Event, fps: float, width: int, height: int) -> None:
        super().__init__(name="ResultProcessorThread")
        self.config = config
        self.output_queue: queue.Queue = output_queue
        self.stop_event = stop_event
        self.fps = fps
        self.width = width
        self.height = height
        
        self.frame_count = 0
        self.total_processed_frames = 0
        self.start_time = time.time()
        self.current_fps = 0.0

        # Raporlama ve Loglama (Yeni merkezi Config ile)
        self.region_manager = RegionManager(self.config)
        self.vehicle_tracker = VehicleTracker(self.config)
        self.report_generator = ReportGenerator(self.config)
        self.routes_log = []
        
        # Pillow modern font onyukleme
        try:
            self.font = ImageFont.truetype("Arial.ttf", 14)
            self.font_large = ImageFont.truetype("Arial.ttf", 26)
            self.font_mid = ImageFont.truetype("Arial.ttf", 16)
        except IOError:
            self.font = ImageFont.load_default()
            self.font_large = ImageFont.load_default()
            self.font_mid = ImageFont.load_default()

    def run(self) -> None:
        if self.stop_event.is_set(): return
        
        output_name = "data/output_live.mp4"
        os.makedirs("data", exist_ok=True)
        
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(output_name, fourcc, self.fps, (self.width, self.height))
        
        cv2.namedWindow("Canli Takip Sonucu", cv2.WINDOW_NORMAL)
        display_w = int(1280 * self.config.display_scale)
        display_h = int(720 * self.config.display_scale)
        cv2.resizeWindow("Canli Takip Sonucu", display_w, display_h)

        try:
            while not self.stop_event.is_set():
                item = None
                while not self.stop_event.is_set():
                    try:
                        item = self.output_queue.get(timeout=0.1)
                        break
                    except queue.Empty:
                        pass
                
                if item is None or item[0] is None or self.stop_event.is_set():
                    if item is not None: self.output_queue.task_done()
                    break
                    
                frame, boxes, model_names, kalman_states = item
                
                # Pillow (PIL) cizimleri icin bos bir RGBA (overlay) katmani olustur
                overlay = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                # Cizim islemleri
                if boxes is not None and boxes.id is not None:
                    coords = boxes.xyxy.cpu().numpy()
                    track_ids = boxes.id.cpu().numpy()
                    class_ids = boxes.cls.cpu().numpy() if boxes.cls is not None else [0] * len(coords)
                    confidences = boxes.conf.cpu().numpy() if boxes.conf is not None else [0.0] * len(coords)
                    
                    for coord, track_id, cls_id, conf in zip(coords, track_ids, class_ids, confidences):
                        x1, y1, x2, y2 = map(int, coord)
                        tid = int(track_id)
                        cid = int(cls_id)
                        class_name = model_names.get(cid, "Arac")
                        
                        # -- Kalman State Rescue (Occlusion Guard) --
                        cx, cy = (x1 + x2) // 2, y2 
                        current_h = y2 - y1
                        
                        if tid in kalman_states:
                            k_x, k_y, k_a, k_h = kalman_states[tid]
                            # Eger YOLO kutusu Kalman'in gercek fiziksel boyut beklentisinden aniden %20+ kuculduyse
                            # (Bir seyin arkasina girip alti kesildiyse) veya Guven skoru ani dustuyse -> KAPANMA VAR!
                            if current_h < (k_h * 0.80) or conf < 0.40:
                                # YOLO koordinatlarini COPE AT. 
                                # Tracker'in hiz ve yon vektorunden(ivme) gelen State ([x, y, a, h]) degerleriyle SANAL 'cy' olustur!
                                cx = int(k_x)
                                cy = int(k_y + (k_h / 2))

                        # Guncellenmis/Korunmus (Rescue) Noktayla Zone Analizini Yap
                        current_zone = self.region_manager.point_in_region((cx, cy))
                        self.vehicle_tracker.update_zone(tid, current_zone)
                        self.vehicle_tracker.update_type_score(tid, class_name, float(conf))

                        # Eger arac hicbir zoneda degilse ekranda cizme (FPS ve gereksiz kalabalik optimizasyonu)
                        if current_zone is None:
                            continue
                        
                        # OpenCV BGR rengini RGB'ye cevir (ImageDraw icin)
                        b, g, r = self.config.get_vehicle_color(class_name)
                        rgb_color = (r, g, b)
                        bg_color = (r, g, b, 150) # saydamlik ekli rgb
                        
                        # Ince ve zarif bounding box YERINE sadece bottom-center nokta cizimi (Nokta Modu)
                        # -1 ici dolu, siyah dis cizgiyle modern gorunum
                        cv2.circle(frame, (cx, cy), 5, (b, g, r), -1, lineType=cv2.LINE_AA)
                        cv2.circle(frame, (cx, cy), 5, (0, 0, 0), 1, lineType=cv2.LINE_AA)
                        
                        # Etiket
                        label = f"id {tid} {class_name}"
                        left, top, right, bottom = draw.textbbox((0, 0), label, font=self.font)
                        tw, th = right - left, bottom - top
                        
                        pad_x, pad_y = 6, 4
                        
                        # Noktanin uzerine ortalayarak yerlestir (X: merkez, Y: top - bosluk)
                        text_x = cx - (tw // 2)
                        text_y = cy - th - 18
                        
                        bg_rect = [text_x - pad_x, text_y - pad_y, text_x + tw + pad_x, text_y + th + pad_y]
                        
                        draw.rounded_rectangle(bg_rect, radius=5, fill=bg_color)
                        draw.text((text_x, text_y), label, font=self.font, fill=(255, 255, 255, 255))

                # Rotalari Al ve Logla
                active_ids = list(track_ids) if (boxes is not None and boxes.id is not None) else []
                completed_routes = self.vehicle_tracker.get_completed_routes(active_ids)
                for route in completed_routes:
                    self.report_generator.add_route(route)
                    report_item = route.get_report()
                    print(f"\n[ROTA TAMAMLANDI] {report_item}")
                    self.routes_log.append(report_item)
                    if len(self.routes_log) > 5: self.routes_log.pop(0)

                # UI Cizimleri (Sag Ust Loglar)
                for i, log_text in enumerate(reversed(self.routes_log)):
                    cv2.putText(frame, log_text, (self.width - 500, 50 + (i * 35)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2, cv2.LINE_AA)

                # Bolgeleri Ciz (Saydam Dolgulu)
                zone_overlay = frame.copy()
                for i, poly in enumerate(self.region_manager.polygons):
                    # Acik sari renk dolgu (BGR: 150, 255, 255)
                    cv2.fillPoly(zone_overlay, [poly], (150, 255, 255))
                    cv2.polylines(frame, [poly], True, (0, 255, 255), 1, lineType=cv2.LINE_AA)
                
                # Sadece %20 opaklikla saydamlik (arka planin cok net gorunmesi icin)
                cv2.addWeighted(zone_overlay, 0.20, frame, 0.80, 0, frame)

                for i, poly in enumerate(self.region_manager.polygons):
                    M = cv2.moments(poly)
                    if M['m00'] != 0:
                        mcx, mcy = int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])
                        # Modern stroke tekniği ile yazım
                        cv2.putText(frame, f"Zone {self.region_manager.names[i]}", (mcx - 25, mcy), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
                        cv2.putText(frame, f"Zone {self.region_manager.names[i]}", (mcx - 25, mcy), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

                # FPS Hesaplamasi
                self.frame_count += 1
                self.total_processed_frames += 1
                elapsed = time.time() - self.start_time
                if elapsed > 1.0:
                    self.current_fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.start_time = time.time()

                # Modern FPS / Threshold Paneli (Pillow ile)
                fps_str = f"{self.current_fps:.1f} FPS"
                conf_str = f"Threshold: {self.config.confidence_threshold:.2f}"
                
                # Panel arka plani
                draw.rounded_rectangle([15, 15, 180, 85], radius=8, fill=(0, 0, 0, 180))
                # Yazilar (Drop shadow hissi ile modern)
                draw.text((26, 26), fps_str, font=self.font_large, fill=(0, 0, 0, 255))
                draw.text((25, 25), fps_str, font=self.font_large, fill=(0, 255, 100, 255))
                
                draw.text((26, 61), conf_str, font=self.font_mid, fill=(0, 0, 0, 255))
                draw.text((25, 60), conf_str, font=self.font_mid, fill=(255, 255, 255, 255))

                # Tum OpenCV cizimleri tamamlandiktan sonra resmi PIL'a cevirip overlay'i ekle
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_frame).convert('RGBA')
                pil_img.paste(overlay, (0, 0), overlay)
                
                # RGB olarak geri OpenCV'ye dondur
                frame = cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)
                
                if writer.isOpened(): writer.write(frame)
                cv2.imshow("Canli Takip Sonucu", frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.stop_event.set()
                    break
                
                self.output_queue.task_done()
                
        finally:
            self.report_generator.save()
            self.report_generator.print_statistics(self.total_processed_frames)
            if writer.isOpened(): writer.release()
            cv2.destroyAllWindows()


def start_pipeline() -> None:
    # 1. Config Yukle
    config = load_config("config/botsort_traffic.yaml")
    
    # User yollarini koruyalim (D:\avm.mp4 vb.)
    # Eger YAML'da yoksa veya gecersiz ise varsayilanlari setle
    if not os.path.exists(config.video_path):
        config.video_path = r"D:\avm.mp4"
    if not os.path.exists(config.model_path):
        config.model_path = r"D:\tracking\models\yolov8.engine"

    print("-" * 50)
    print(f"[INFO] Video Kaynagi: {config.video_path}")
    print(f"[INFO] Model Engine: {config.model_path}")
    print("-" * 50)
    
    input_queue = queue.Queue(maxsize=64)
    output_queue = queue.Queue(maxsize=64)
    stop_event = threading.Event()
    
    reader_thread = VideoReader(config, input_queue, stop_event)
    if stop_event.is_set(): return
        
    engine_thread = TrackerEngine(config, input_queue, output_queue, stop_event)
    processor_thread = ResultProcessor(config, output_queue, stop_event, reader_thread.fps, reader_thread.width, reader_thread.height)
    
    reader_thread.start()
    engine_thread.start()
    processor_thread.start()
    
    reader_thread.join()
    engine_thread.join()
    processor_thread.join()
    
    print("\n[OK] Pipeline başarıyla tamamlandı.")

if __name__ == "__main__":
    start_pipeline()
