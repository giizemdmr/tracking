"""
async_pipeline.py

Bu modül, GPU'yu %100 kapasiteyle kullanmayı hedefleyen, asenkron Producer-Consumer
mimarisine sahip yüksek performanslı bir YOLOv8 + BoT-SORT video işleme pipeline'ı sağlar.

Modül, üç bağımsız kanaldan (thread) oluşur:
1. VideoReader (Producer): Video dosyasından kareleri okur ve girdi kuyruğuna aktarır.
2. TrackerEngine (Inference): YOLOv8 TensorRT motorunu kullanarak nesne tespiti ve takibi yapar.
3. ResultProcessor (Consumer): Takip sonuçlarını işler, çizimleri yapar ve dışa aktarır.
"""

import cv2
import threading
import queue
import argparse
import numpy as np
from typing import Optional, Tuple, Any
from ultralytics import YOLO


class VideoReader(threading.Thread):
    """
    Video dosyasından kareleri okuyan ve input_queue (Giriş Kuyruğu)'ya besleyen Producer Thread sınıfı.
    
    Kuyruk dolduğunda (maxsize=64) yeni yer açılana kadar asılı kalarak stabiliteyi sağlar (block=True).
    """

    def __init__(self, video_path: str, input_queue: queue.Queue) -> None:
        """
        VideoReader sınıfını başlatır.

        Args:
            video_path (str): İşlenecek kaynak video dosyasının yolu.
            input_queue (queue.Queue): Okunan karelerin aktarılacağı Thread-Safe iletişim kuyruğu.
        """
        super().__init__(name="VideoReaderThread")
        self.video_path = video_path
        self.input_queue: queue.Queue[Optional[np.ndarray]] = input_queue
        
        self.fps: float = 30.0
        self.width: int = 1920
        self.height: int = 1080
        
        # Meta verileri okuma denemesi (Çıktı Videosu İçin Boyut Öğrenme)
        self._initialize_video_metadata()

    def _initialize_video_metadata(self) -> None:
        """Video metadatalarını (çözünürlük, fps) işleme başlamadan önce alır."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError(f"CRITICAL ERROR: Video dosyasi acilamadi: {self.video_path}")
        
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        cap.release()

    def run(self) -> None:
        """Thread başladığında çalışacak ana metot. Video karelerini okur kuyruğa aktarır."""
        cap = cv2.VideoCapture(self.video_path)
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Kuyruk doluysa block=True ile yer açılana kadar işlemi beklemeye alır (Darboğaz önleyici)
                self.input_queue.put(frame, block=True)
                
        except Exception as e:
            print(f"[VideoReader] Beklenmeyen Hata: {e}")
            
        finally:
            cap.release()
            # İşlemin bittiğini bildiren Sentinel Değeri ekleyerek TrackerEngine'in sonsuza dek beklemesini önle
            self.input_queue.put(None, block=True)


class TrackerEngine(threading.Thread):
    """
    Kareleri YOLOv8 + BoT-SORT ile işleyen Çıkarım (Inference) Producer-Consumer Thread sınıfı.
    
    Yalnızca tespit ve takip yapar, hiçbir görsel çizim içermez (annotate = False).
    Çıkan sonuçları (Orijinal Kare, Model Kutuları) Çıkış Kuyruğu'na aktarır.
    """

    def __init__(self, model_path: str, input_queue: queue.Queue, output_queue: queue.Queue) -> None:
        """
        TrackerEngine sınıfını başlatır.
        
        Args:
            model_path (str): YOLOv8 modelinin yolu (Örn: TensorRT .engine dosyası).
            input_queue (queue.Queue): Frame verilerinin alındığı kuyruk.
            output_queue (queue.Queue): Sonuçların işleyici ResultProcessor thread'e iletileceği kuyruk.
        """
        super().__init__(name="TrackerEngineThread")
        self.model_path = model_path
        self.input_queue: queue.Queue[Optional[np.ndarray]] = input_queue
        self.output_queue: queue.Queue[Tuple[Optional[np.ndarray], Any]] = output_queue

    def run(self) -> None:
        """Ana döngü: Girdi kuyruğundan kareyi çeker, izleme yapar, çıkış kuyruğuna iteler."""
        try:
            # task='detect' TensorRT engine kullanırken modelin tipini doğrular.
            model = YOLO(self.model_path, task='detect')
            
            while True:
                frame = self.input_queue.get(block=True)
                
                # Sentinel kontolü: Girdi kuyruğu video bitişini sinyalledi mi?
                if frame is None:
                    self.input_queue.task_done()
                    break
                    
                # İzlemeyi GPU limitinde Gerçekleştir
                # - source=frame: Gelen tek kare okutulur.
                # - stream=True: Asenkron jeneratör modunu tetikler (Bellek optimizasyonu sağlar).
                # - persist=True: Tracker'a gelen karelerin bir bütün dizi olduğunu belirtir (ID tutarlılığı).
                # - half=True: FP16 Hassasiyetinde inference yaparak TensorRT performansını maksimize eder.
                # - verbose=False: Konsol karmaşasını tamamen engeller.
                results = model.track(
                    source=frame,
                    stream=True,
                    persist=True,
                    half=True,       
                    verbose=False,
                    tracker="custom_botsort.yaml"
                )
                
                # KESİN KURAL: Çizim YAPILMAYACAK, sadece saf tracking datası ve orijinal görsel aktarılacak
                for result in results:
                    self.output_queue.put((result.orig_img, result.boxes), block=True)
                    
                # Input kuyruğundan alınan task'ın temizlenmesi
                self.input_queue.task_done()
                
        except Exception as e:
            print(f"[TrackerEngine] Modelle Baglantili Kritik Hata: {e}")
            
        finally:
            # ResultProcessor'a Engine'in işlemi sonlandırdığını (Sentinel) bildir
            self.output_queue.put((None, None), block=True)


class ResultProcessor(threading.Thread):
    """
    Çıktı verilerini işleyen (Consumer), tracking çizimlerini ayrı kanalda yapan 
    ve sonucu kayıpsız .mp4 dosyası olarak sisteme işleyen ana işleyici sınıftır.
    """

    def __init__(self, output_path: str, output_queue: queue.Queue, fps: float, width: int, height: int) -> None:
        """
        ResultProcessor hazırlığını ve bufferlarını tamamlar.
        
        Args:
            output_path (str): Oluşturulacak işlenmiş video dosyasının kaydedileceği yol.
            output_queue (queue.Queue): Engine'den gelen sonuçların asenkron alındığı kuyruk.
            fps (float): Video yazıcısı için orijinal videonun kaynak kare hızı.
            width (int): Video yazıcısı için orijinal genişlik.
            height (int): Video yazıcısı için orijinal yükseklik.
        """
        super().__init__(name="ResultProcessorThread")
        self.output_path = output_path
        self.output_queue: queue.Queue[Tuple[Optional[np.ndarray], Any]] = output_queue
        self.fps = fps
        self.width = width
        self.height = height

    def run(self) -> None:
        """Gelen orijinal frame ve takip box'larını kullanarak render işlemlerini yapar."""
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (self.width, self.height))
        
        if not writer.isOpened():
            print(f"[ResultProcessor] ERROR: Video writer baslatilamadi: {self.output_path}")
            return

        try:
            while True:
                frame, boxes = self.output_queue.get(block=True)
                
                # Sentinel (Bitiş) Sinyali Kontrolü
                if frame is None:
                    self.output_queue.task_done()
                    break
                    
                # Nesne bulunduysa ve Tracker BoT-SORT benzersiz bir ID atamışsa işlemleri tetikle
                if boxes is not None and boxes.id is not None:
                    
                    # TensorRT Engine çıktısını RAM'e al (GPU Darboğazı olmadan çizim yapabilmek için)
                    coords = boxes.xyxy.cpu().numpy()
                    track_ids = boxes.id.cpu().numpy()
                    
                    for coord, track_id in zip(coords, track_ids):
                        x1, y1, x2, y2 = map(int, coord)
                        tid = int(track_id)
                        
                        # Yeşil Bounding Box (Sınır Kutusu) çiz
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # Görsel bütünlük için ID Background (Arka plan) kutusu ve Metni hazırlama
                        label = f"ID: {tid}"
                        (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        
                        cv2.rectangle(frame, (x1, max(0, y1 - 25)), (x1 + text_width, max(0, y1)), (0, 255, 0), -1)
                        cv2.putText(frame, label, (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                # Yeni kareyi kodlanmış dosyaya dök
                writer.write(frame)
                self.output_queue.task_done()
                
        except Exception as e:
            print(f"[ResultProcessor] Render İşlem Hatası: {e}")
            
        finally:
            writer.release()


def start_pipeline(source_vid: str, model_weights: str, output_vid: str) -> None:
    """
    Tüm birimleri (Kuyruk, Sınıf, Thread) başlatan, koordine eden ve bitişini join() ile kontrol eden yapıcı fonksiyon.
    """
    # 1. Thread-Safe Kuyrukları Başlat (GPU'un Frame açlığını giderecek tampon: maxsize=64)
    input_queue: queue.Queue = queue.Queue(maxsize=64)
    output_queue: queue.Queue = queue.Queue(maxsize=64)
    
    # 2. Üretici Sınıfı Ayarla ve Metadataları Çıkar
    print("\n[+] Sistem Baslatiliyor: Thread Baglantilari Kuruluyor...")
    reader_thread = VideoReader(source_vid, input_queue)
    
    fps = reader_thread.fps
    width = reader_thread.width
    height = reader_thread.height
    print(f"|  Video Orijinal Parametreleri: {width}x{height} @ {fps:.2f}FPS")
    
    # 3. Model Engine Tüketici-Üretici (Intermediary) ve Video Renderer Threadlerini Ayarla
    engine_thread = TrackerEngine(model_weights, input_queue, output_queue)
    processor_thread = ResultProcessor(output_vid, output_queue, fps, width, height)
    
    # 4. Asenkron Pipeline Dağıtımını Gerçekleştir
    reader_thread.start()
    print("[+] VideoReader(Producer) Thread Baslatildi. (Kuyruk Dolduruluyor...)")
    
    engine_thread.start()
    print("[+] TrackerEngine(Inference) Thread Baslatildi. (Model .engine Isliyor...)")
    
    processor_thread.start()
    print("[+] ResultProcessor(Consumer) Thread Baslatildi. (Render Basliyor...)")
    
    print("\n>>> Pipeline calisiyor, lutfen gorev tamamlanana kadar bekleyiniz... <<<\n")
    
    # 5. Threadlerin düzgün bir şekilde kapanmasını, RAM'den izole olmasını BEKLE
    reader_thread.join()
    print("[*] (1/3) Kaynak okuma islemi tamamlandi, baglanti kesildi.")
    
    engine_thread.join()
    print("[*] (2/3) Tracking Neural Engine inference'i tamamladi.")
    
    processor_thread.join()
    print("[*] (3/3) Video kayit (Writer Export) islemi kusursuz bitirildi.")
    
    print(f"\n[OK] Tum Asenkron islem basariyla sonlandi. Gorsel Cikti Alindi -> {output_vid}")


def main() -> None:
    """Argüman ayrıştırıcı (argparse) barındıran Production-Ready Giriş Noktası"""
    parser = argparse.ArgumentParser(description="Asynchronous YOLOv8 + BoT-SORT Multi-Threaded Tracking Pipeline")
    parser.add_argument("--source", type=str, required=True, help="Kaynak video dosyasinin Absolute / Relative yolu")
    parser.add_argument("--weights", type=str, required=True, help=".engine (TensorRT) Tensor Weights yolu")
    parser.add_argument("--output", type=str, default="output_tracked.mp4", help="Cikti alinacak islenmis videonun yolu")
    
    args = parser.parse_args()
    start_pipeline(args.source, args.weights, args.output)

if __name__ == "__main__":
    main()
