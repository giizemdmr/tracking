"""
reporting.py - Raporlama ve Analiz Modülü
Bu modül, araçların bölgeler arası geçişlerini takip eder ve Excel raporu oluşturur.
D:\\report_generator.py referans alinarak yazilmistir.
"""

import cv2
import numpy as np
import json
import openpyxl
from openpyxl.styles import Font, PatternFill
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import os



class RegionManager:
    """JSON dosyasından bölgeleri yükler ve nokta kontrolü yapar."""
    def __init__(self, config):
        self.config = config
        self.polygons = []
        self.names = []
        self._load_regions()

    def _load_regions(self) -> None:
        if not os.path.exists(self.config.regions_file):
            print(f"[ERROR] Bolge dosyasi bulunamadi: {self.config.regions_file}")
            return
            
        try:
            with open(self.config.regions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            polys = data.get("polygons", [])
            names = data.get("names", [])
            
            for p, n in zip(polys, names):
                self.polygons.append(np.array(p, np.int32))
                self.names.append(n)
            
            print(f"[OK] {len(self.polygons)} bolge '{self.config.regions_file}' dosyasindan yuklendi.")
        except Exception as e:
            print(f"[ERROR] Bolgeler yuklenirken hata: {e}")

    def point_in_region(self, point: Tuple[int, int]) -> Optional[str]:
        """Verilen noktanın hangi bölgede olduğunu döndürür."""
        for i, poly in enumerate(self.polygons):
            if cv2.pointPolygonTest(poly, (float(point[0]), float(point[1])), False) >= 0:
                return self.names[i]
        return None

class VehicleRoute:
    """Bir aracın izlediği rota bilgilerini tutar."""
    def __init__(self, object_id: int):
        self.object_id = object_id
        self.vehicle_type = "Bilinmiyor"
        self.route = []  # Bölge isimleri listesi
        self.start_time = datetime.now()
        self.last_update = datetime.now()
        self.entry_zone = None
        self.exit_zone = None
        self.is_completed = False
        
    def add_zone(self, zone_name: str) -> bool:
        """Yeni bir bölge ekler, eğer ardışık değilse."""
        if not self.route or self.route[-1] != zone_name:
            self.route.append(zone_name)
            self.last_update = datetime.now()
            if len(self.route) == 1:
                self.entry_zone = zone_name
            return True
        return False

    def complete(self) -> bool:
        """Rotayı tamamlar (En az 2 farklı bölge geçilmişse gecerlidir)."""
        if len(self.route) >= 2:
            self.entry_zone = self.route[0]
            self.exit_zone = self.route[-1]
            self.is_completed = True
            return True
        return False

    def get_report(self) -> str:
        """Excel ve konsol için rapor metni üretir."""
        return f"{self.object_id} idli {self.vehicle_type} {self.entry_zone} ten girdi {self.exit_zone} ten cikti"

    def get_route_string(self) -> str:
        """Tam rotayı string olarak döndürür."""
        return " → ".join(self.route)

class VehicleTracker:
    """Tüm araçların ömür döngüsünü ve bölge geçişlerini yönetir."""
    def __init__(self, config):
        self.config = config
        self.active_vehicles: Dict[int, VehicleRoute] = {}
        self.type_stats: Dict[int, Dict[str, float]] = {} # ID -> {type: total_conf}
        self.total_vehicles_seen = 0

    def update_zone(self, object_id: int, zone_name: Optional[str]) -> None:
        if zone_name is None:
            return
            
        if object_id not in self.active_vehicles:
            self.active_vehicles[object_id] = VehicleRoute(object_id)
            self.total_vehicles_seen += 1
            
        self.active_vehicles[object_id].add_zone(zone_name)

    def update_type_score(self, object_id: int, vehicle_type: str, confidence: float) -> None:
        """En güvenilir araç tipini belirlemek için %70 üzeri skorları toplayarak hesap tutar."""
        if object_id not in self.type_stats:
            self.type_stats[object_id] = {'high_conf': {}, 'all': {}}
            
        # 1. Eger confidence %70 üzerinde ise, bu gercek ve kaliteli bir despıt tespittir.
        # Formul geregi: Toplam Skor = Frame Sayisi x Confidence degerlerinin kümülatif toplamı
        if confidence >= 0.70:
            self.type_stats[object_id]['high_conf'][vehicle_type] = self.type_stats[object_id]['high_conf'].get(vehicle_type, 0) + confidence
        
        # 2. Her ihtimale karsi (hicbiri 0.70 uzeri cikmazsa fallback icin) normal listeyi de tut
        self.type_stats[object_id]['all'][vehicle_type] = self.type_stats[object_id]['all'].get(vehicle_type, 0) + confidence

    def get_best_type(self, object_id: int) -> str:
        """Önce %70 üzeri kesin kayıtlara bakar, en yüksek toplam skoru alana galibiyeti verir."""
        if object_id in self.type_stats:
            high_scores = self.type_stats[object_id]['high_conf']
            fallback_scores = self.type_stats[object_id]['all']
            
            # Eğer %70 üzeri tek bir tespiti dahi varsa, o gruba ait skor liderini sec!
            if high_scores:
                return max(high_scores, key=high_scores.get)
            # Arac 100 frame boyunca gozuktu ama asla 0.70 skoruna cikamadiysa (sis, karanlik vs)
            elif fallback_scores:
                return max(fallback_scores, key=fallback_scores.get)
                
        return "Bilinmiyor"

    def get_completed_routes(self, current_active_ids: List[int]) -> List[VehicleRoute]:
        """Ekrandan kaybolan araçların rotalarını döndürür ve temizler."""
        completed = []
        ids_to_remove = []
        
        for tid, route in self.active_vehicles.items():
            if tid not in current_active_ids:
                # Araç artık ekranda değilse
                if route.complete():
                    route.vehicle_type = self.get_best_type(tid)
                    completed.append(route)
                ids_to_remove.append(tid)
                
        for tid in ids_to_remove:
            if tid in self.active_vehicles: del self.active_vehicles[tid]
            if tid in self.type_stats: del self.type_stats[tid]
            
        return completed


class ReportGenerator:
    """
    Trafik analiz raporlarını Excel formatında oluşturur.
    
    Araç geçişlerini kaydeder ve Excel dosyasına yazar.
    D:\\report_generator.py mantığı birebir uygulanmıştır.
    
    Attributes:
        config: Uygulama konfigürasyonu
        records: Rapor kayıtları listesi
    """
    
    def __init__(self, config):
        """
        ReportGenerator başlatıcısı.
        
        Args:
            config: Uygulama konfigürasyonu
        """
        self.config = config
        self.records: List[List] = []
    
    def add_route(self, route: 'VehicleRoute') -> None:
        """
        Tamamlanmış bir rota ekler.
        
        Args:
            route: VehicleRoute nesnesi
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_text = route.get_report()
        route_string = route.get_route_string()
        
        record = [
            timestamp,
            report_text,
            route.object_id,
            route.vehicle_type,
            route.entry_zone,
            route.exit_zone,
            route_string
        ]
        
        self.records.append(record)
    
    def add_record(
        self,
        object_id: int,
        vehicle_type: str,
        entry_zone: str,
        exit_zone: str,
        full_route: List[str]
    ) -> None:
        """
        Manuel olarak kayıt ekler.
        
        Args:
            object_id: Araç ID'si
            vehicle_type: Araç tipi
            entry_zone: Giriş bölgesi
            exit_zone: Çıkış bölgesi
            full_route: Tam rota listesi
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        route_string = " → ".join(full_route)
        report_text = f"{object_id} idli {vehicle_type} {entry_zone} ten girdi {exit_zone} ten cikti"
        
        record = [
            timestamp,
            report_text,
            object_id,
            vehicle_type,
            entry_zone,
            exit_zone,
            route_string
        ]
        
        self.records.append(record)

    def get_record_count(self) -> int:
        """Kayıt sayısını döndürür."""
        return len(self.records)
    
    def save_final_report(self, tracker: 'VehicleTracker') -> bool:
        """
        Video sonunda aktif kalan tüm araçların rotalarını 'boş tespit listesi' ile zorla (-flush) 
        kapatarak rapora ekler ve projeyi kaydeder.
        """
        print("\n[INFO] Video sonlandi. Yarim kalan rotalar kapatiliyor...")
        
        # Tracker'a 'ekranda hicbir target yok ([])' diyerek aktiflerin hepsini bitirt.
        flushed_routes = tracker.get_completed_routes([])
        for route in flushed_routes:
            self.add_route(route)
            print(f"[FLUSH TAMAMLANDI] {route.get_report()}")
            
        return self.save()

    def save(self) -> bool:
        """
        Raporu Excel dosyasına kaydeder.
        
        Returns:
            True eğer başarılı, False eğer hata oluşursa
        """
        print("\n[INFO] Excel raporu olusturuluyor...")
        
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Trafik Raporu"
            
            # Başlıklar
            headers = [
                "Tarih/Saat",
                "Olay Raporu",
                "ID",
                "Tür",
                "Giriş",
                "Çıkış",
                "Tam Rota"
            ]
            ws.append(headers)
            
            # Başlık stili
            header_font = Font(bold=True)
            header_fill = PatternFill(
                start_color="FFFF00",
                end_color="FFFF00",
                fill_type="solid"
            )
            
            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
            
            # Veri satırları
            for record in self.records:
                ws.append(record)
            
            # Sütun genişlikleri
            ws.column_dimensions['A'].width = 20
            ws.column_dimensions['B'].width = 60
            ws.column_dimensions['C'].width = 8
            ws.column_dimensions['D'].width = 15
            ws.column_dimensions['E'].width = 10
            ws.column_dimensions['F'].width = 10
            ws.column_dimensions['G'].width = 30
            
            # Kaydet
            wb.save(self.config.excel_filename)
            print(f"[OK] {len(self.records)} kayit yazildi: {self.config.excel_filename}")
            
            return True
            
        except PermissionError:
            print(f"[ERROR] Dosya erisim hatasi: {self.config.excel_filename}")
            print("   Dosya baska bir program tarafindan acik olabilir.")
            return False
            
        except Exception as e:
            print(f"[ERROR] Excel hatasi: {e}")
            return False
    
    def print_statistics(self, frame_count: int, vehicle_count: int = 0) -> None:
        """
        İstatistikleri konsola yazdırır.
        
        Args:
            frame_count: Toplam frame sayısı
            vehicle_count: Tespit edilen toplam araç sayısı
        """
        print("\n" + "=" * 60)
        print("[STATS] ISTATISTIKLER")
        print("=" * 60)
        print(f"Toplam Frame: {frame_count}")
        print(f"Tespit Edilen Araç: {vehicle_count}")
        print(f"Raporlanan Geçiş: {len(self.records)}")
        print("=" * 60)
    
    def clear(self) -> None:
        """Tüm kayıtları temizler."""
        self.records.clear()
