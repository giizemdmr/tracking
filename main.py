"""
main.py - Canli Izleme Özellikli Asenkron YOLOv8 + BoT-SORT Pipeline

Hardcoded (Sabit) Parametreler:
- Video: D:\tracking\data\traffic_video.mp4
- Model: D:\tracking\models\yolov8.engine
- Proje İçi Sınıflar (Yaya, Bisiklet vs.)

Durdurmak için canlı izleme penceresi açıkken 'q' tuşuna basmanız yeterlidir. Bütün
arkaplan işlemleri asenkron olarak güvenli şekilde temizlenecektir (No Memory Leaks).
"""

import cv2
import threading
import queue
import numpy as np
import time
from typing import Optional, Tuple, Any
from ultralytics import YOLO
from src.reporting import RegionManager, VehicleTracker, ReportGenerator

# ----- KULLANICI PARAMETRELERİ ----- #
VIDEO_SOURCE = r"D:\avm.mp4"
MODEL_WEIGHTS = r"D:\tracking\models\yolov8.engine"
OUTPUT_VIDEO = r"D:\tracking\data\output_live.mp4"

# Kullanıcının tanımladığı tam sınıf isimleri
CLASS_NAMES = {
    0: "Yaya",
    1: "Bisiklet",
    2: "Motosiklet",
    3: "Otomobil",
    4: "Otobus",
    5: "Agir_tasit",
    6: "Panelvan",
    7: "Minibus",
    8: "Kamyonet"
}

# Modern ve Estetik BGR Renk Paleti (Sınıflara Özel)
CLASS_COLORS = {
    0: (146, 98, 240),   # Yaya - Tatlı Mor
    1: (247, 195, 79),   # Bisiklet - Gök Mavisi/Turkuazımsı
    2: (77, 183, 255),   # Motosiklet - Turuncu
    3: (132, 199, 129),  # Otomobil - Fıstık Yeşili
    4: (203, 134, 121),  # Otobus - Çivit Mavisi (İndigo)
    5: (115, 115, 229),  # Agir_tasit - Mat Kırmızı
    6: (225, 208, 77),   # Panelvan - Aqua Mavisi
    7: (200, 104, 186),  # Minibus - Menekşe (Magenta)
    8: (118, 241, 255)   # Kamyonet - Koyu Sarımsı
}

def get_color(cls_id: int):
    """Sınıflara özel hazırlanmış estetik BGR renklerini döndürür. Bulunamazsa gri verir."""
    return CLASS_COLORS.get(cls_id, (128, 128, 128))


class VideoReader(threading.Thread):
    def __init__(self, video_path: str, input_queue: queue.Queue, stop_event: threading.Event) -> None:
        super().__init__(name="VideoReaderThread")
        self.video_path = video_path
        self.input_queue: queue.Queue = input_queue
        self.stop_event = stop_event
        self.fps = 30.0
        self.width = 1920
        self.height = 1080
        self._initialize_video_metadata()

    def _initialize_video_metadata(self) -> None:
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"[!] CRITICAL ERROR: Video dosyasi acilamadi: {self.video_path}")
            self.stop_event.set()
            return
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()

    def run(self) -> None:
        if self.stop_event.is_set(): return
        cap = cv2.VideoCapture(self.video_path)
        try:
            while cap.isOpened() and not self.stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Timeout ile Queue'ya veri yolla (Böylece stop_event bloke olmadan kontrol edilir)
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
                # Sentinel (Sentinel -> TrackerEngine'in okumayı bitirmesi için Bitiş Sinyali)
                self.input_queue.put(None, timeout=1) 
            except:
                pass


class TrackerEngine(threading.Thread):
    def __init__(self, model_path: str, input_queue: queue.Queue, output_queue: queue.Queue, stop_event: threading.Event) -> None:
        super().__init__(name="TrackerEngineThread")
        self.model_path = model_path
        self.input_queue: queue.Queue = input_queue
        self.output_queue: queue.Queue = output_queue
        self.stop_event = stop_event

    def run(self) -> None:
        if self.stop_event.is_set(): return
        try:
            # Type doğrulayıcı ile TensorRT modunu zorla
            model = YOLO(self.model_path, task='detect')
            
            while not self.stop_event.is_set():
                frame = None
                
                # Asılı (Block) kalmayı önlemek için Time-out ile bekleme
                while not self.stop_event.is_set():
                    try:
                        frame = self.input_queue.get(timeout=0.1)
                        break
                    except queue.Empty:
                        pass
                
                # Gelen paket Sentinel (None) ise okuma durmuştur, işlemden çıkılır
                if frame is None or self.stop_event.is_set():
                    if frame is not None: self.input_queue.task_done()
                    break
                    
                # FPS / GPU Darboğazı Engelleyen Tracking Ayarları
                results = model.track(
                    source=frame, 
                    stream=True, 
                    persist=True, 
                    half=True, 
                    verbose=False, 
                    tracker="custom_botsort.yaml",
                    imgsz=1024
                )
                
                for result in results:
                    if self.stop_event.is_set(): break
                    
                    while not self.stop_event.is_set():
                        try:
                            # Saf Orijinal veri, asla engine tarafından kirletilmemiştir (NO DRAW)
                            self.output_queue.put((result.orig_img, result.boxes), timeout=0.1)
                            break
                        except queue.Full:
                            pass
                
                self.input_queue.task_done()
                
        except Exception as e:
            print(f"\n[TrackerEngine] Modelle Baglantili Kritik Hata (Engine Uyusmazligi / Bozuk CUDA): {e}")
            self.stop_event.set()
        finally:
            try:
                # ResultProcessor'a Engine'in durduğunu beyan eder (Sentinel Yollar)
                self.output_queue.put((None, None), timeout=1)
            except:
                pass


class ResultProcessor(threading.Thread):
    def __init__(self, output_path: str, output_queue: queue.Queue, stop_event: threading.Event, fps: float, width: int, height: int) -> None:
        super().__init__(name="ResultProcessorThread")
        self.output_path = output_path
        self.output_queue: queue.Queue = output_queue
        self.stop_event = stop_event
        self.fps = fps
        self.width = width
        self.height = height
        
        # FPS Hesaplaması için değişkenler (Yalnızca bu thread'e özel Consumer FPS)
        self.frame_count = 0
        self.start_time = time.time()
        self.current_fps = 0.0

        # Raporlama Bileşenleri
        self.region_manager = RegionManager("bolgeler.json")
        self.vehicle_tracker = VehicleTracker()
        self.report_generator = ReportGenerator("trafik_raporu.xlsx")

    def run(self) -> None:
        if self.stop_event.is_set(): return
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (self.width, self.height))
        
        cv2.namedWindow("Canli Takip Sonucu", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Canli Takip Sonucu", 1280, 720)

        if not writer.isOpened():
            print(f"[ResultProcessor] ERROR: Video writer baslatilamadi, ciktilar sadece izlenebilecek.")

        try:
            while not self.stop_event.is_set():
                item = None
                
                # Asılı Kalma Yok (No block), Timeout ile Stop Sinyali denetleniyor
                while not self.stop_event.is_set():
                    try:
                        item = self.output_queue.get(timeout=0.1)
                        break
                    except queue.Empty:
                        pass
                
                if item is None or item[0] is None or self.stop_event.is_set():
                    if item is not None: self.output_queue.task_done()
                    break
                    
                frame, boxes = item
                
                # Kutu ve ID çizimi
                if boxes is not None and boxes.id is not None:
                    coords = boxes.xyxy.cpu().numpy()
                    track_ids = boxes.id.cpu().numpy()
                    class_ids = boxes.cls.cpu().numpy() if boxes.cls is not None else [0] * len(coords)
                    # Güven Skoru (Threshold) Çekimi
                    confidences = boxes.conf.cpu().numpy() if boxes.conf is not None else [0.0] * len(coords)
                    
                    for coord, track_id, cls_id, conf in zip(coords, track_ids, class_ids, confidences):
                        x1, y1, x2, y2 = map(int, coord)
                        tid = int(track_id)
                        cid = int(cls_id)
                        
                        class_name = CLASS_NAMES.get(cid, "Bilinmeyen")
                        color = get_color(cid) 
                        
                        # 1. Bounding Box (İnce ve Zarif Sınır Kutusu)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1, lineType=cv2.LINE_AA)
                        
                        # 2. Etiket: #{ID} {Sınıf_Adı} [{Threshold}]
                        label = f"#{tid} {class_name} [{conf:.2f}]"
                        
                        # Font Ayarları
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 0.5
                        thickness = 1
                        
                        (text_width, text_height), _ = cv2.getTextSize(label, font, font_scale, thickness)
                        
                        # 3. Yazı Arka Planı (Sınıfın renginde dinamik uzunluk)
                        bg_y1 = max(0, y1 - text_height - 10)
                        bg_y2 = max(0, y1)
                        cv2.rectangle(frame, (x1, bg_y1), (x1 + text_width + 6, bg_y2), color, -1)
                        
                        # 4. Beyaz net yazı (Okunabilir contrast ve LINE_AA Anti-Aliasing ile)
                        cv2.putText(frame, label, (x1 + 3, bg_y2 - 4), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

                        # ------- RAPORLAMA MANTIĞI -------
                        # Bölge Kontrolü
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        current_zone = self.region_manager.point_in_region((cx, cy))
                        self.vehicle_tracker.update_zone(tid, current_zone, self.frame_count)
                        
                        # Tip Skorlama
                        self.vehicle_tracker.update_type_score(tid, class_name, float(conf))

                # Tamamlanmış Rotaları Raporla (Her karede aktif ID listesini yolla)
                active_ids = list(track_ids) if (boxes is not None and boxes.id is not None) else []
                completed_routes = self.vehicle_tracker.get_completed_routes(active_ids)
                for route in completed_routes:
                    self.report_generator.add_route(route)
                    print(f"\n[ROTA TAMAMLANDI] {route.get_report()}")

                # ------- BÖLGELERİ ÇİZ (Görsel Geri Bildirim) -------
                for i, poly in enumerate(self.region_manager.polygons):
                    cv2.polylines(frame, [poly], True, (255, 255, 255), 1, lineType=cv2.LINE_AA)
                    # Bölge İsmi
                    try:
                        M = cv2.moments(poly)
                        if M['m00'] != 0:
                            mcx = int(M['m10'] / M['m00'])
                            mcy = int(M['m01'] / M['m00'])
                            cv2.putText(frame, self.region_manager.names[i], (mcx, mcy), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
                    except: pass

                # ----------- 3. CONSUMER FPS GÖSTERGESİ -----------
                self.frame_count += 1
                elapsed = time.time() - self.start_time
                if elapsed > 1.0:
                    self.current_fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.start_time = time.time()
                
                # Ekranın sol üstüne canlı FPS çizimi
                fps_text = f"FPS: {self.current_fps:.1f}"
                cv2.putText(frame, fps_text, (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)

                # Kayıt etme
                if writer.isOpened():
                    writer.write(frame)
                
                # ------ CANLI İZLEME (LIVE FEED) ------
                cv2.imshow("Canli Takip Sonucu", frame)
                
                # 1ms bekle, kullanıcı 'q' tuşuna basarsa sistemi acil stopla
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\n[!] 'q' tusuna basildi. Pipeline asenkron olarak durduruluyor...")
                    self.stop_event.set()
                    self.output_queue.task_done()
                    break
                
                self.output_queue.task_done()
                
        except Exception as e:
            print(f"[ResultProcessor] Render İşlem Hatası: {e}")
            self.stop_event.set()
        finally:
            # Video bitince veya durdurulunca raporu kaydet
            self.report_generator.save()
            if writer.isOpened(): 
                writer.release()
            cv2.destroyAllWindows()


def start_pipeline() -> None:
    print("-" * 50)
    print(f"[INFO] Video Kaynagi: {VIDEO_SOURCE}")
    print(f"[INFO] Model Engine: {MODEL_WEIGHTS}")
    print("-" * 50)
    
    # 1. Thread-Safe Kuyrukları Başlat (Darboğaza karşı 64 kare RAM izni)
    input_queue = queue.Queue(maxsize=64)
    output_queue = queue.Queue(maxsize=64)
    
    # Tüm modülleri asekron durdurmak için global event (q ile kapanma)
    stop_event = threading.Event()
    
    print("\n[+] Sistem Baslatiliyor: Thread Baglantilari Kuruluyor...")
    reader_thread = VideoReader(VIDEO_SOURCE, input_queue, stop_event)
    
    if stop_event.is_set():
        print("\n[-] Baslatma basarisiz. Lutfen kaynaktaki dosyalarin varligini kontol edin.")
        return
        
    fps = reader_thread.fps
    width = reader_thread.width
    height = reader_thread.height
    print(f"|  Video Orijinal Parametreleri: {width}x{height} @ {fps:.2f}FPS")
    
    engine_thread = TrackerEngine(MODEL_WEIGHTS, input_queue, output_queue, stop_event)
    processor_thread = ResultProcessor(OUTPUT_VIDEO, output_queue, stop_event, fps, width, height)
    
    reader_thread.start()
    engine_thread.start()
    processor_thread.start()
    
    print("\n>>> Pipeline calisiyor, Canli izleme ekrani aciliyor... <<<")
    print("      (Durdurmak icin acilan pencere uzerindeyken 'q' tusuna basin)\n")
    
    # Thread kilitlenmeleri 'timeout' eklendiği için artık olmayacak.
    # Güvenli kapanış (Graceful Shutdown) mekanizması ile bekleniyor:
    reader_thread.join()
    print("[*] (1/3) Kaynak okuma islemi tamamladi/durduruldu.")
    
    engine_thread.join()
    print("[*] (2/3) Tracking Neural Engine kapandi.")
    
    processor_thread.join()
    print("[*] (3/3) Result Processor Gorsellestirmeyi Kapatti.")
    
    print(f"\n[OK] Pipeline basariyla kapandi. Cikti videonuz:\n -> {OUTPUT_VIDEO}")


if __name__ == "__main__":
    start_pipeline()
