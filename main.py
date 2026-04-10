import cv2
import threading
import queue
import time
import os
import yaml
import numpy as np
from types import SimpleNamespace
from typing import Optional, Tuple, Any
from ultralytics import YOLO

from src.reporting import RegionManager, VehicleTracker, ReportGenerator
from src.engine.zone_analyzer import ZoneAnalyzer
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
        self.region_manager = RegionManager(self.config)  # Sadece cizim icin
        # Birlesik Zone Analizi (Kalman Occlusion Guard + Quantum Leap)
        zones_path = os.path.join("config", "zones.json")
        self.zone_analyzer = ZoneAnalyzer(zones_path, cache_threshold=8.0) if os.path.exists(zones_path) else None
        self.vehicle_tracker = VehicleTracker(self.config)
        self.report_generator = ReportGenerator(self.config)
        self.routes_log = []
        
        # --- Pre-compute Zone Overlay ---
        self.zone_fill_overlay = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        for i, poly in enumerate(self.region_manager.polygons):
            # Acik sari renk dolgu (BGR: 150, 255, 255)
            cv2.fillPoly(self.zone_fill_overlay, [poly], (150, 255, 255))
            cv2.polylines(self.zone_fill_overlay, [poly], True, (0, 200, 200), 2, lineType=cv2.LINE_AA)
            
            M = cv2.moments(poly)
            if M['m00'] != 0:
                mcx, mcy = int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])
                cv2.putText(self.zone_fill_overlay, str(self.region_manager.names[i]), (mcx - 15, mcy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
            
        self.zone_mask = np.any(self.zone_fill_overlay > 0, axis=-1)
        # ---------------------------------

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
                        
                        # -- Birlesik Zone Analizi (Kalman Guard + Quantum Leap) --
                        bbox = (x1, y1, x2, y2)
                        
                        if self.zone_analyzer:
                            # ZoneAnalyzer: Kalman rescue + LineString trajectory icsel olarak uygulanir
                            current_zone = self.zone_analyzer.determine_zone(
                                bbox=bbox, track_id=tid, conf=float(conf),
                                kalman_states=kalman_states
                            )
                            # Gorsellestirme icin kurtarilmis (cx, cy) noktasini al
                            cx, cy, _ = self.zone_analyzer.get_rescued_point(
                                bbox, tid, float(conf), kalman_states
                            )
                            cx, cy = int(cx), int(cy)
                        else:
                            # Fallback: ZoneAnalyzer yoksa eski RegionManager kullan
                            cx, cy = (x1 + x2) // 2, y2
                            current_zone = self.region_manager.point_in_region((cx, cy))

                        self.vehicle_tracker.update_zone(tid, current_zone)
                        self.vehicle_tracker.update_type_score(tid, class_name, float(conf))


                        # OpenCV Arac Renkleri
                        b, g, r = self.config.get_vehicle_color(class_name)
                        
                        # Sirf Noktasal Isaretleme (FPS max)
                        cv2.circle(frame, (cx, cy), 5, (b, g, r), -1, lineType=cv2.LINE_AA)
                        cv2.circle(frame, (cx, cy), 5, (0, 0, 0), 1, lineType=cv2.LINE_AA)

                        # Minimalist ID Cizimi (Gozlem icin)
                        cv2.putText(frame, str(tid), (cx + 8, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2, cv2.LINE_AA)
                        cv2.putText(frame, str(tid), (cx + 8, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                # Rotalari Al ve Logla
                active_ids = list(track_ids) if (boxes is not None and boxes.id is not None) else []
                completed_routes = self.vehicle_tracker.get_completed_routes(active_ids)
                for route in completed_routes:
                    self.report_generator.add_route(route)
                    report_item = route.get_report()
                    print(f"\n[ROTA TAMAMLANDI] {report_item}")
                    self.routes_log.append(report_item)
                    if len(self.routes_log) > 5: self.routes_log.pop(0)

                # Ekrana canli rota cizimleri KALDIRILDI (FPS korunumu)

                # OpenCV Pre-computed Zone Overlay Ekleme (Sadece Saydam Dolgu)
                if self.zone_mask is not None and np.any(self.zone_mask):
                    frame[self.zone_mask] = cv2.addWeighted(frame, 0.80, self.zone_fill_overlay, 0.20, 0)[self.zone_mask]

                # FPS Hesaplama
                self.frame_count += 1
                self.total_processed_frames += 1
                elapsed = time.time() - self.start_time
                if elapsed > 1.0:
                    self.current_fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.start_time = time.time()

                # Sadece FPS Sayaci (Ultra Sade)
                fps_str = f"{self.current_fps:.1f} FPS"
                
                # Ufak siyah opak panel
                cv2.rectangle(frame, (5, 5), (140, 45), (0, 0, 0), -1)
                # FPS Yazi
                cv2.putText(frame, fps_str, (12, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(frame, fps_str, (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 100), 2, cv2.LINE_AA)
                
                if writer.isOpened(): writer.write(frame)
                cv2.imshow("Canli Takip Sonucu", frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.stop_event.set()
                    break
                
                self.output_queue.task_done()
                
        finally:
            self.report_generator.save_final_report(self.vehicle_tracker)
            self.report_generator.print_statistics(self.total_processed_frames, self.vehicle_tracker.total_vehicles_seen)
            if writer.isOpened(): writer.release()
            cv2.destroyAllWindows()


def start_pipeline() -> None:
    # 1. Merkezi Config Yukle
    config = config_manager
    
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
