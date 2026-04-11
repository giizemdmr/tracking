import cv2
import threading
import queue
import time
import os
import yaml
import json
import numpy as np
from collections import deque
from types import SimpleNamespace
from typing import Dict, Optional, Tuple, Any

# 1. High-DPI Awareness (Windows ekran ölççeklendirme düzeltmesi)
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# Headless sunucular için GUI bağımlılığını kapat (Vast.ai vb.)
# os.environ["QT_QPA_PLATFORM"] = "offscreen"

from ultralytics import YOLO

from src.reporting import VehicleTracker, ReportGenerator
from src.engine.line_analyzer import LineAnalyzer
from src.config_manager import config_manager

class VideoReader(threading.Thread):
    def __init__(self, config, input_queue: queue.Queue, stop_event: threading.Event) -> None:
        super().__init__(name="VideoReaderThread")
        self.config = config
        self.input_queue: queue.Queue = input_queue
        self.stop_event = stop_event
        self.fps = 30.0
        self.width = 1920
        self.height = 1080
        self.total_frames = 0
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
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        cap.release()

    def run(self) -> None:
        if self.stop_event.is_set(): return
        cap = cv2.VideoCapture(self.config.video_path)
        
        # Kare atlama (vid_stride) parametresi
        stride = getattr(self.config.pipeline, 'vid_stride', 1)
        frame_count = 0
        
        try:
            while cap.isOpened() and not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                if frame_count % stride != 0:
                    continue
                
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
                    
                # NMS ve Tracker parametreleri optimize sekilde (Dinamik Config uzerinden)
                results = model.track(
                    source=frame, 
                    stream=True, 
                    persist=True, 
                    half=self.config.yolo.use_half, 
                    verbose=False, 
                    tracker="config/pipeline_config.yaml", 
                    imgsz=self.config.yolo.input_size,
                    conf=self.config.yolo.confidence_threshold,
                    iou=self.config.yolo.nms_iou, # Kesisim (Overlap) esnekligi
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
    def __init__(self, config, output_queue: queue.Queue, stop_event: threading.Event, fps: float, width: int, height: int, total_frames: int = 0) -> None:
        super().__init__(name="ResultProcessorThread")
        self.config = config
        self.output_queue: queue.Queue = output_queue
        self.stop_event = stop_event
        self.fps = fps
        self.width = width
        self.height = height
        self.total_frames = total_frames
        
        self.frame_count = 0
        self.total_processed_frames = 0
        self.start_time = None  # İlk kare gelene kadar başlatma
        self.current_fps = 0.0

        # Raporlama ve Loglama (Yeni Line/Gate Mimarisi)
        lines_path = os.path.join("config", "lines.json")
        self.line_analyzer = LineAnalyzer(lines_path) if os.path.exists(lines_path) else None
        self.vehicle_tracker = VehicleTracker(self.config)
        self.report_generator = ReportGenerator(self.config)
        self.routes_log = []
        
        # Yorunge (Trajectory) Hafizasi: {track_id: deque([(cx, cy), ...], maxlen=30)}
        self.trajectories: Dict[int, deque] = {}
        
        # --- Pre-compute Line (Gate) Overlay ---
        self.line_overlay = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self.lines_data = []  # [{"name": ..., "points": [[x1,y1],[x2,y2]]}, ...]
        
        lines_path = os.path.join("config", "lines.json")
        if os.path.exists(lines_path):
            try:
                with open(lines_path, 'r', encoding='utf-8') as f:
                    self.lines_data = json.load(f)
                print(f"[OK] {len(self.lines_data)} sanal kapi (gate) yuklendi: {lines_path}")
            except Exception as e:
                print(f"[ERROR] lines.json yuklenemedi: {e}")
        
        # Giris kapilari: Yesil, Cikis kapilari: Kirmizi, Diger: Mavi
        for gate in self.lines_data:
            name = gate.get("name", "")
            pts = gate.get("points", [])
            if len(pts) < 2:
                continue
            
            # Renk secimi: Giris=Yesil, Cikis=Kirmizi, Diger=Mavi
            name_lower = name.lower()
            if "giris" in name_lower or "entry" in name_lower:
                color = (0, 255, 100)   # Yesil
            elif "cikis" in name_lower or "exit" in name_lower:
                color = (0, 80, 255)    # Kirmizi
            else:
                color = (255, 200, 0)   # Mavi
            
            # Coklu Cizgi (Polylines)
            np_pts = np.array(pts, np.int32).reshape((-1, 1, 2))
            cv2.polylines(self.line_overlay, [np_pts], isClosed=False, color=color, thickness=3, lineType=cv2.LINE_AA)
            
            # Uc noktalari (ve ara noktalari) isaretle
            for pt in pts:
                cv2.circle(self.line_overlay, tuple(pt), 6, color, -1, lineType=cv2.LINE_AA)
            
            # Kapi ismini cizginin ortasindaki noktaya yazalim
            mid_idx = len(pts) // 2
            mid_pt = tuple(pts[mid_idx])
            
            cv2.putText(self.line_overlay, name, (mid_pt[0] - 30, mid_pt[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)  # Shadow
            cv2.putText(self.line_overlay, name, (mid_pt[0] - 30, mid_pt[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)       # Text
        
        self.line_mask = np.any(self.line_overlay > 0, axis=-1)
        # ---------------------------------

    def run(self) -> None:
        if self.stop_event.is_set(): return
        
        # Video yazıcı devre dışı bırakıldı (Performans için)
        writer = None
        # output_name = "data/output_live.mp4"
        # os.makedirs("data", exist_ok=True)
        # fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        # writer = cv2.VideoWriter(output_name, fourcc, self.fps, (self.width, self.height))
        
        headless = getattr(self.config.pipeline, 'headless_mode', False)
        if not headless:
            cv2.namedWindow("Canli Takip Sonucu", cv2.WINDOW_NORMAL)
            # Pencereyi video çözünürlüğü ve display_scale'e göre ayarla
            display_w = int(self.width * self.config.display_scale)
            display_h = int(self.height * self.config.display_scale)
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
                        
                        # -- Virtual Line / Gate Kesisim Analizi --
                        cx = (x1 + x2) // 2
                        cy = y2  # Bottom-center (arac tekerlek hizasi)
                        
                        # Yorunge hafizasini guncelle
                        if tid not in self.trajectories:
                            self.trajectories[tid] = deque(maxlen=30)
                        self.trajectories[tid].append((cx, cy))
                        
                        # Arac canlilik (liveness) guncellemesi (yeni eklendi)
                        self.vehicle_tracker.update_liveness(tid, self.total_processed_frames)
                        
                        # Sanal kapi kesisim testi
                        if self.line_analyzer and len(self.trajectories[tid]) >= 2:
                            crossed_gate = self.line_analyzer.check_crossing(
                                track_id=tid,
                                trajectory_points=list(self.trajectories[tid]),
                                current_frame=self.total_processed_frames
                            )
                            if crossed_gate:
                                self.vehicle_tracker.update_zone(tid, crossed_gate, self.total_processed_frames)
                        
                        self.vehicle_tracker.update_type_score(tid, class_name, float(conf), bbox=[x1, y1, x2, y2])


                        # OpenCV Arac Renkleri
                        b, g, r = self.config.get_vehicle_color(class_name)
                        
                        # --- Modern Yörünge (Kuyruk) Çizimi ---
                        if tid in self.trajectories and len(self.trajectories[tid]) > 1:
                            pts = np.array(self.trajectories[tid], np.int32)
                            pts = pts.reshape((-1, 1, 2))
                            cv2.polylines(frame, [pts], isClosed=False, color=(b, g, r), thickness=2, lineType=cv2.LINE_AA)
                        
                        # Sirf Noktasal Isaretleme (FPS max)
                        cv2.circle(frame, (cx, cy), 5, (b, g, r), -1, lineType=cv2.LINE_AA)
                        cv2.circle(frame, (cx, cy), 5, (0, 0, 0), 1, lineType=cv2.LINE_AA)

                        # Minimalist ID, Tur ve Guven Skoru Cizimi
                        label = f"{class_name} %{int(conf*100)}"
                        cv2.putText(frame, label, (cx + 8, cy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
                        cv2.putText(frame, label, (cx + 8, cy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                        cv2.putText(frame, f"ID: {tid}", (cx + 8, cy + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 2, cv2.LINE_AA)
                        cv2.putText(frame, f"ID: {tid}", (cx + 8, cy + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

                # Rotalari Al ve Logla (Stale Buffer kontrolu)
                stale_limit = getattr(self.config.tracking, 'stale_buffer', 200)
                completed_routes = self.vehicle_tracker.get_completed_routes(
                    current_frame=self.total_processed_frames,
                    stale_buffer=stale_limit
                )
                for route in completed_routes:
                    self.report_generator.add_route(route)
                    report_item = route.get_report()
                    print(f"\n[ROTA TAMAMLANDI] {report_item}")
                    self.routes_log.append(report_item)
                    if len(self.routes_log) > 5: self.routes_log.pop(0)
                    
                    # Trajectory ve LineAnalyzer hafizasini temizle
                    tid_done = route.object_id
                    self.trajectories.pop(tid_done, None)
                    if self.line_analyzer:
                        self.line_analyzer.clear_track(tid_done)

                # Ekrana canli rota cizimleri KALDIRILDI (FPS korunumu)

                # OpenCV Pre-computed Line (Gate) Overlay Ekleme
                if self.line_mask is not None and np.any(self.line_mask):
                    frame[self.line_mask] = cv2.addWeighted(frame, 0.30, self.line_overlay, 0.70, 0)[self.line_mask]

                # FPS Hesaplama (vid_stride uyumlu)
                if self.start_time is None:
                    self.start_time = time.time()
                
                self.frame_count += 1
                self.total_processed_frames += 1
                elapsed = time.time() - self.start_time
                
                # Her 1.0 saniyede bir veya 10 karede bir guncelle (Daha akici)
                if elapsed > 1.0:
                    stride = getattr(self.config.pipeline, 'vid_stride', 1)
                    # Isleme FPS'i (Model hizi)
                    proc_fps = self.frame_count / elapsed
                    # Efektif FPS (Videonun tuketilme hizi)
                    self.current_fps = proc_fps * stride
                    
                    self.frame_count = 0
                    self.start_time = time.time()

                    # FPS ve İlerleme (% ve ETA) Hesaplama
                    progress_info = ""
                    if self.total_frames > 0:
                        pct = (self.total_processed_frames * stride / self.total_frames) * 100
                        pct = min(pct, 99.9)
                        
                        if self.current_fps > 0:
                            remaining_frames = self.total_frames - (self.total_processed_frames * stride)
                            eta_sec = remaining_frames / self.current_fps
                            eta_min = int(eta_sec // 60)
                            eta_sec = int(eta_sec % 60)
                            progress_info = f" | PROG: {pct:.1f}% | ETA: {eta_min:02d}:{eta_sec:02d}"

                    self.fps_str = f"SPEED: {self.current_fps:.1f} FPS{progress_info}"
                    
                    # Terminale Dinamik Yazdir (Terminal Progress Bar gibi calisir)
                    # \r sayesinde ayni satiri ezer, terminali spama bogmaz.
                    total_completed = self.report_generator.get_record_count()
                    print(f"\r[TAKIP] {self.fps_str} | TOPLAM GECIS: {total_completed}    ", end="", flush=True)
                
                # Ufak siyah opak panel
                cv2.rectangle(frame, (5, 5), (450, 45), (0, 0, 0), -1)
                # FPS Yazi
                display_fps_str = getattr(self, 'fps_str', 'SPEED: Calculating...')
                cv2.putText(frame, display_fps_str, (12, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(frame, display_fps_str, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 100), 2, cv2.LINE_AA)
                
                # if writer.isOpened(): writer.write(frame)
                
                # Headless Modu Kontrolu (Remote Serverlar icin)
                # YAML'da pipeline: headless_mode: true ise imshow/waitKey atlanir.
                headless = getattr(self.config.pipeline, 'headless_mode', False)
                if not headless:
                    cv2.imshow("Canli Takip Sonucu", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.stop_event.set()
                        break
                
                self.output_queue.task_done()
                
        finally:
            self.report_generator.save_final_report(self.vehicle_tracker)
            self.report_generator.print_statistics(self.total_processed_frames, self.vehicle_tracker.total_vehicles_seen)
            # if writer.isOpened(): writer.release()
            
            # Headless modda pencere kapatma hatasini onle
            if not headless:
                cv2.destroyAllWindows()


def start_pipeline() -> None:
    # 1. Merkezi Config Yukle
    config = config_manager
    
    # Path kontrolu (Sadece bilgilendirme amacli)
    if not os.path.exists(config.video_path):
        print(f"[WARNING] Video dosyasi bulunamadi: {config.video_path}")
    if not os.path.exists(config.model_path):
        print(f"[WARNING] Model dosyasi bulunamadi: {config.model_path}")

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
    processor_thread = ResultProcessor(config, output_queue, stop_event, reader_thread.fps, reader_thread.width, reader_thread.height, reader_thread.total_frames)
    
    reader_thread.start()
    engine_thread.start()
    processor_thread.start()
    
    reader_thread.join()
    engine_thread.join()
    processor_thread.join()
    
    print("\n[OK] Pipeline başarıyla tamamlandı.")

if __name__ == "__main__":
    start_pipeline()
