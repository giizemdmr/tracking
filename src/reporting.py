"""
reporting.py - Profesyonel Trafik Raporlama Modülü

Bu modül, araçların bölgeler (zone) arasındaki hareketlerini takip eder,
en doğru araç tipini belirler ve sonuçları Excel formatında dışa aktarır.
"""

import json
import cv2
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set

@dataclass
class VehicleRoute:
    """Tamamlanmış bir araç rotasını temsil eder."""
    object_id: int
    vehicle_type: str
    entry_zone: str
    exit_zone: str
    full_route: List[str]

    def get_route_string(self) -> str:
        return " -> ".join(self.full_route)

    def get_report(self) -> str:
        return f"ID:{self.object_id} | {self.vehicle_type} | {self.entry_zone} -> {self.exit_zone}"

class RegionManager:
    """Bölge tanımlarını yönetir ve nokta kontrolü yapar."""
    def __init__(self, regions_file: str):
        self.regions_file = regions_file
        self.polygons: List[np.ndarray] = []
        self.names: List[str] = []
        self._load_regions()

    def _load_regions(self) -> None:
        try:
            with open(self.regions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # bolgeler.json formatına göre (PalyeTracking_Test formatı)
            polys = data.get("polygons", [])
            names = data.get("names", [])
            
            for p, n in zip(polys, names):
                self.polygons.append(np.array(p, np.int32))
                self.names.append(n)
            
            print(f"[OK] {len(self.polygons)} bolge '{self.regions_file}' dosyasindan yuklendi.")
        except Exception as e:
            print(f"[ERROR] Bolge yukleme hatasi: {e}")

    def point_in_region(self, point: Tuple[int, int]) -> Optional[str]:
        for i, poly in enumerate(self.polygons):
            if cv2.pointPolygonTest(poly, point, False) >= 0:
                return self.names[i]
        return None

class VehicleTracker:
    """Araç lifecycle ve rota takibi yapar."""
    def __init__(self):
        self.routes: Dict[int, List[str]] = {}
        self.route_timestamps: Dict[int, List[int]] = {}
        self.type_scores: Dict[int, Dict[str, float]] = {}
        self.consecutive_frames: Dict[int, int] = {}
        self.last_seen_zone: Dict[int, Optional[str]] = {}
        self.last_seen_frame: Dict[int, int] = {}
        self.processed_ids: Set[int] = set()

        # Ayarlar (Config'den devralınan mantık)
        self.zone_entry_frames = 3
        self.zone_change_frames = 5
        self.min_route_zone_duration = 15

    def update_type_score(self, object_id: int, v_type: str, confidence: float):
        if object_id not in self.type_scores:
            self.type_scores[object_id] = {}
        self.type_scores[object_id][v_type] = self.type_scores[object_id].get(v_type, 0.0) + confidence

    def get_best_type(self, object_id: int) -> str:
        if object_id in self.type_scores and self.type_scores[object_id]:
            return max(self.type_scores[object_id], key=self.type_scores[object_id].get)
        return "Unknown"

    def update_zone(self, object_id: int, zone: Optional[str], frame_count: int):
        if object_id not in self.routes:
            self.routes[object_id] = []
            self.route_timestamps[object_id] = []
            self.consecutive_frames[object_id] = 0
            self.last_seen_zone[object_id] = None
        
        self.last_seen_frame[object_id] = frame_count

        if zone is None:
            self.consecutive_frames[object_id] = 0
            return

        if zone == self.last_seen_zone[object_id]:
            self.consecutive_frames[object_id] += 1
        else:
            self.consecutive_frames[object_id] = 1
            self.last_seen_zone[object_id] = zone

        required = self.zone_entry_frames if not self.routes[object_id] else self.zone_change_frames
        if self.consecutive_frames[object_id] >= required:
            if not self.routes[object_id] or self.routes[object_id][-1] != zone:
                self.routes[object_id].append(zone)
                self.route_timestamps[object_id].append(frame_count)

    def get_completed_routes(self, active_ids: List[int]) -> List[VehicleRoute]:
        completed = []
        for v_id in list(self.routes.keys()):
            if v_id not in active_ids and v_id not in self.processed_ids:
                route = self.routes[v_id]
                # Temizleme (Transit geçişleri eleme)
                clean_route = self._clean_route(v_id)
                
                if len(clean_route) >= 2 and clean_route[0] != clean_route[-1]:
                    completed.append(VehicleRoute(
                        object_id=v_id,
                        vehicle_type=self.get_best_type(v_id),
                        entry_zone=clean_route[0],
                        exit_zone=clean_route[-1],
                        full_route=clean_route
                    ))
                    self.processed_ids.add(v_id)
        return completed

    def _clean_route(self, v_id: int) -> List[str]:
        route = self.routes[v_id]
        ts = self.route_timestamps[v_id]
        if len(route) < 3: return route
        
        cleaned = [route[0]]
        for i in range(1, len(route)-1):
            duration = ts[i+1] - ts[i]
            if duration >= self.min_route_zone_duration:
                cleaned.append(route[i])
        cleaned.append(route[-1])
        
        # Ardışık tekrarları sil
        final = [cleaned[0]]
        for z in cleaned[1:]:
            if z != final[-1]: final.append(z)
        return final

class ReportGenerator:
    """Excel raporlarını oluşturur."""
    def __init__(self, filename: str):
        self.filename = filename
        self.records = []

    def add_route(self, route: VehicleRoute):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = [
            timestamp,
            route.get_report(),
            route.object_id,
            route.vehicle_type,
            route.entry_zone,
            route.exit_zone,
            route.get_route_string()
        ]
        self.records.append(record)

    def save(self):
        if not self.records:
            print("[INFO] Raporlanacak veri yok.")
            return
        
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Trafik Raporu"
            
            headers = ["Tarih/Saat", "Olay", "ID", "Tür", "Giriş", "Çıkış", "Tam Rota"]
            ws.append(headers)
            
            # Stil
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
            
            for r in self.records:
                ws.append(r)
            
            wb.save(self.filename)
            print(f"[OK] Rapor kaydedildi: {self.filename} ({len(self.records)} kayit)")
        except Exception as e:
            print(f"[ERROR] Excel kayit hatasi: {e}")
