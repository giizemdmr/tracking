"""
ZoneAnalyzer — Birleşik Bölge Analiz Motoru
============================================
İki kritik koruma mekanizmasını tek bir sınıfta birleştirir:

1. KALMAN OCCLUSION GUARD (main.py kaynaklı):
   - Güven skoru (conf) < 0.40 → YOLO tespiti güvenilmez, Kalman state kullan.
   - BBox yüksekliği aniden %80'in altına düştü → Kısmi kapanma var, Kalman state kullan.
   - Kalman state vektörü: mean[:4] = [cx, cy, aspect_ratio, height]

2. QUANTUM LEAP GUARD (main_pipeline.py kaynaklı):
   - Düşük FPS'te hızlı araçlar bölgeyi atlayabilir.
   - Önceki frame ile şu anki frame arasına Shapely LineString çizilir.
   - Bu çizgi herhangi bir zone poligonuyla kesişiyorsa, araç o bölgeden geçmiş demektir.

Mimari:
   VisionEngine → detections + kalman_states → ZoneAnalyzer.determine_zone() → zone_name
"""

import json
import logging
from typing import Dict, Tuple, Optional, Any, List

from shapely.geometry import Polygon, Point, LineString
from shapely.prepared import prep

from src.config_manager import config_manager

logger = logging.getLogger(__name__)


class ZoneAnalyzer:
    """
    Birleşik bölge analiz sınıfı.

    Girdi:
        - YOLO bounding box (x1, y1, x2, y2)
        - Güven skoru (conf)
        - track_id
        - Kalman state geçmişi {track_id: mean[:4]}

    Çıktı:
        - Aracın bulunduğu zone adı (str) veya None
    """

    # ── Occlusion Guard Eşikleri (ConfigManager uzerinden dinamik) ──
    # CONF_RESCUE_THRESH: float = 0.40       
    # HEIGHT_DROP_RATIO: float = 0.80        

    # ── Spatial Cache Eşiği ──
    MIN_MOVEMENT_PX: float = 2.0           # Bu pikselden az hareket → önceki sonucu tekrar kullan

    def __init__(self, zones_json_path: str, cache_threshold: float = 8.0):
        """
        Args:
            zones_json_path: zones.json dosyasının yolu.
            cache_threshold: Bölge kontrolünü tetiklemek için minimum piksel hareketi.
                             (Eski cache sistemi ile uyumlu parametre — artık MIN_MOVEMENT_PX kullanıyor)
        """
        # Bölge geometrileri
        self.zones: Dict[str, Polygon] = {}
        self.prepared_zones: Dict[str, Any] = {}   # Shapely prepared (2x hızlı containment)
        self.zone_names_ordered: List[str] = []     # Yükleme sırasına göre isimler

        # Track bazlı geçmiş: {track_id: (cx, cy)}
        self._prev_positions: Dict[int, Tuple[float, float]] = {}

        # Track bazlı önceki yükseklik: {track_id: bbox_height}
        self._prev_heights: Dict[int, float] = {}

        # Spatial cache: {track_id: (last_cx, last_cy, last_zone_result)}
        self._result_cache: Dict[int, Tuple[float, float, Optional[str]]] = {}

        # İstatistikler
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Cache threshold'u ayarla
        if cache_threshold > 0:
            self.MIN_MOVEMENT_PX = cache_threshold

        self._load_zones(zones_json_path)

    # ══════════════════════════════════════════════════════════
    # ZONE YÜKLEME
    # ══════════════════════════════════════════════════════════

    def _load_zones(self, json_path: str) -> None:
        """zones.json'dan poligonları yükler, Shapely Polygon + prepared geometry oluşturur."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for zone_data in data:
                name = zone_data.get("name")
                points = zone_data.get("points")

                if not name or not points or len(points) < 3:
                    logger.warning(f"Geçersiz zone verisi atlandı: {zone_data}")
                    continue

                poly = Polygon(points)
                if not poly.is_valid:
                    # Geçersiz poligonu düzeltmeye çalış (self-intersection vb.)
                    poly = poly.buffer(0)
                    logger.warning(f"Zone '{name}' geçersiz poligon — buffer(0) ile düzeltildi.")

                self.zones[name] = poly
                self.prepared_zones[name] = prep(poly)
                self.zone_names_ordered.append(name)
                logger.info(f"Zone yüklendi: '{name}' ({len(points)} köşe, alan={poly.area:.0f}px²)")

            logger.info(f"Toplam {len(self.zones)} zone başarıyla yüklendi.")

        except FileNotFoundError:
            logger.error(f"Zones JSON bulunamadı: {json_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Zones JSON parse hatası: {e}")
        except Exception as e:
            logger.error(f"Zone yükleme hatası: {e}")

    # ══════════════════════════════════════════════════════════
    # ANA ANALİZ FONKSİYONU
    # ══════════════════════════════════════════════════════════

    def determine_zone(
        self,
        bbox: Tuple[float, float, float, float],
        track_id: int,
        conf: float = 1.0,
        kalman_states: Optional[Dict[int, Any]] = None
    ) -> Optional[str]:
        """
        Aracın hangi bölgede olduğunu kesin olarak belirler.

        İşlem Sırası:
            1. Bottom-center noktasını hesapla (cx, cy)
            2. Kalman Occlusion Guard: Gerekirse noktayı Kalman state ile değiştir
            3. Spatial Cache: Az hareket varsa önceki sonucu döndür
            4. Point-in-Polygon: Kurtarılmış nokta bir zone'un içinde mi?
            5. Quantum Leap: Önceki frame ile bu frame arasındaki LineString
               herhangi bir zone ile kesişiyor mu?

        Args:
            bbox:          (x1, y1, x2, y2) YOLO bounding box koordinatları
            track_id:      Araç takip ID'si
            conf:          YOLO güven skoru [0.0 - 1.0]
            kalman_states: {track_id: [cx, cy, aspect_ratio, height]} Kalman state dict

        Returns:
            Zone adı (str) veya None (hiçbir bölgede değil)
        """
        if not self.zones:
            return None

        x1, y1, x2, y2 = bbox
        current_h = y2 - y1

        # ── Adım 1: Ham bottom-center noktası ──
        cx = (x1 + x2) / 2.0
        cy = float(y2)  # Bottom-center (araç tekerlek hizası)

        # ── Adım 2: KALMAN OCCLUSION GUARD ──
        rescued = False
        
        # ── MERKEZİ CONFIG MANAGER KULLANIMI ──
        conf_rescue_thresh = config_manager.tracking.kalman_rescue_conf
        height_drop_ratio = config_manager.tracking.kalman_drop_height_ratio
        
        if kalman_states and track_id in kalman_states:
            k_state = kalman_states[track_id]
            k_x, k_y, k_a, k_h = k_state[0], k_state[1], k_state[2], k_state[3]

            # Koşul A: BBox yüksekliği aniden çok küçüldü (kısmi kapanma)
            height_collapsed = current_h < (k_h * height_drop_ratio)

            # Koşul B: Güven skoru çok düşük (YOLO kararsız)
            low_confidence = conf < conf_rescue_thresh

            # Koşul C: Önceki yükseklik bilgisi varsa, ani düşüşü kontrol et
            sudden_shrink = False
            if track_id in self._prev_heights:
                prev_h = self._prev_heights[track_id]
                if prev_h > 0 and current_h < (prev_h * height_drop_ratio):
                    sudden_shrink = True

            if height_collapsed or low_confidence or sudden_shrink:
                # YOLO koordinatlarını bırak → Kalman tahminini kullan
                cx = float(k_x)
                cy = float(k_y + (k_h / 2.0))  # Kalman center + yarı yükseklik = bottom-center
                rescued = True

        # Yükseklik geçmişini güncelle (rescued olmayan gerçek YOLO ölçümü)
        if not rescued:
            self._prev_heights[track_id] = current_h

        # ── Adım 3: SPATIAL CACHE (mikro-optimizasyon) ──
        if track_id in self._result_cache:
            cached_cx, cached_cy, cached_zone = self._result_cache[track_id]
            dx = cx - cached_cx
            dy = cy - cached_cy
            dist_sq = dx * dx + dy * dy
            if dist_sq < (self.MIN_MOVEMENT_PX * self.MIN_MOVEMENT_PX):
                self._cache_hits += 1
                return cached_zone

        self._cache_misses += 1

        # ── Adım 4: POINT-IN-POLYGON TESTİ ──
        point = Point(cx, cy)
        result: Optional[str] = None

        for name in self.zone_names_ordered:
            prepared_poly = self.prepared_zones[name]
            if prepared_poly.contains(point):
                result = name
                break

        # ── Adım 5: QUANTUM LEAP GUARD (LineString Intersection) ──
        # Eğer nokta hiçbir zone'un içinde değilse AMA önceki frame'den bu frame'e
        # çizilen çizgi bir zone'u kesiyorsa → araç o zone'dan geçmiş demektir.
        if result is None and track_id in self._prev_positions:
            prev_cx, prev_cy = self._prev_positions[track_id]

            # Sadece gerçekten hareket ettiyse LineString oluştur
            if abs(cx - prev_cx) > 0.5 or abs(cy - prev_cy) > 0.5:
                trajectory = LineString([(prev_cx, prev_cy), (cx, cy)])

                for name in self.zone_names_ordered:
                    prepared_poly = self.prepared_zones[name]
                    if prepared_poly.intersects(trajectory):
                        result = name
                        break

        # ── Geçmişi Güncelle ──
        self._prev_positions[track_id] = (cx, cy)
        self._result_cache[track_id] = (cx, cy, result)

        return result

    # ══════════════════════════════════════════════════════════
    # GERİYE DÖNÜK UYUMLULUK (main_pipeline.py check_zones çağrısı)
    # ══════════════════════════════════════════════════════════

    def check_zones(
        self,
        bbox: Tuple[float, float, float, float],
        track_id: int,
        kalman_states: Optional[Dict[int, Any]] = None,
        conf: float = 1.0
    ) -> Optional[str]:
        """
        main_pipeline.py ile geriye dönük uyumlu wrapper.
        Dahili olarak determine_zone() fonksiyonunu çağırır.
        """
        return self.determine_zone(
            bbox=bbox,
            track_id=track_id,
            conf=conf,
            kalman_states=kalman_states
        )

    # ══════════════════════════════════════════════════════════
    # TRACK TEMİZLİĞİ
    # ══════════════════════════════════════════════════════════

    def clear_cache(self, track_id: int) -> None:
        """Ölen/kaybolan track'in tüm geçmiş verilerini temizler."""
        self._prev_positions.pop(track_id, None)
        self._prev_heights.pop(track_id, None)
        self._result_cache.pop(track_id, None)

    def clear_all(self) -> None:
        """Tüm track geçmişlerini sıfırlar (video değişimi vb.)."""
        self._prev_positions.clear()
        self._prev_heights.clear()
        self._result_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    # ══════════════════════════════════════════════════════════
    # İSTATİSTİKLER
    # ══════════════════════════════════════════════════════════

    def get_cache_stats(self) -> Tuple[int, int]:
        """Spatial cache istatistikleri: (hit, miss)."""
        return self._cache_hits, self._cache_misses

    def reset_cache_stats(self) -> None:
        """Cache sayaçlarını sıfırlar (periyodik profiler raporları için)."""
        self._cache_hits = 0
        self._cache_misses = 0

    def get_active_track_count(self) -> int:
        """Geçmişte pozisyon kaydı olan aktif track sayısı."""
        return len(self._prev_positions)

    # ══════════════════════════════════════════════════════════
    # DEBUG & YARDIMCI
    # ══════════════════════════════════════════════════════════

    def get_zone_names(self) -> List[str]:
        """Yükleme sırasına göre zone isimlerini döndürür."""
        return list(self.zone_names_ordered)

    def get_rescued_point(
        self,
        bbox: Tuple[float, float, float, float],
        track_id: int,
        conf: float,
        kalman_states: Optional[Dict[int, Any]] = None
    ) -> Tuple[float, float, bool]:
        """
        Debug: Kalman rescue uygulanmış (cx, cy) ve rescue durumunu döndürür.
        Görselleştirme katmanında kullanılabilir.

        Returns:
            (cx, cy, was_rescued)
        """
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = float(y2)
        current_h = y2 - y1
        rescued = False

        if kalman_states and track_id in kalman_states:
            k_state = kalman_states[track_id]
            k_x, k_y, k_a, k_h = k_state[0], k_state[1], k_state[2], k_state[3]

            conf_rescue_thresh = config_manager.tracking.kalman_rescue_conf
            height_drop_ratio = config_manager.tracking.kalman_drop_height_ratio

            height_collapsed = current_h < (k_h * height_drop_ratio)
            low_confidence = conf < conf_rescue_thresh

            if height_collapsed or low_confidence:
                cx = float(k_x)
                cy = float(k_y + (k_h / 2.0))
                rescued = True

        return cx, cy, rescued

    def __repr__(self) -> str:
        return (
            f"ZoneAnalyzer("
            f"zones={len(self.zones)}, "
            f"active_tracks={len(self._prev_positions)}, "
            f"cache_hits={self._cache_hits}, "
            f"cache_misses={self._cache_misses})"
        )


# ══════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    MOCK_JSON = "zones_test_tmp.json"
    mock_data = [
        {"name": "Kuzey", "points": [[100, 100], [400, 100], [400, 400], [100, 400]]},
        {"name": "Guney", "points": [[500, 500], [800, 500], [800, 800], [500, 800]]}
    ]

    try:
        with open(MOCK_JSON, "w") as f:
            json.dump(mock_data, f)

        analyzer = ZoneAnalyzer(MOCK_JSON, cache_threshold=5.0)
        print(f"\n{analyzer}\n")

        # Test 1: Nokta Kuzey bölgesinde
        z1 = analyzer.determine_zone((150, 150, 250, 350), track_id=1, conf=0.85)
        print(f"Test 1 (Kuzey içi): {z1} — Beklenen: Kuzey [OK]" if z1 == "Kuzey" else f"FAIL: {z1}")

        # Test 2: Aynı track, az hareket → cache hit
        z2 = analyzer.determine_zone((152, 152, 252, 352), track_id=1, conf=0.85)
        print(f"Test 2 (Cache hit): {z2} — Beklenen: Kuzey [OK]" if z2 == "Kuzey" else f"FAIL: {z2}")

        # Test 3: Büyük hareket → Güney bölgesine
        z3 = analyzer.determine_zone((550, 550, 650, 750), track_id=1, conf=0.90)
        print(f"Test 3 (Guney): {z3} — Beklenen: Guney [OK]" if z3 == "Guney" else f"FAIL: {z3}")

        # Test 4: Kalman Rescue — düşük güven
        kalman = {2: [250.0, 250.0, 0.5, 200.0]}
        z4 = analyzer.determine_zone((240, 240, 260, 260), track_id=2, conf=0.25, kalman_states=kalman)
        print(f"Test 4 (Kalman rescue, conf<0.40): {z4} — Beklenen: Kuzey [OK]" if z4 == "Kuzey" else f"FAIL: {z4}")

        # Test 5: Quantum Leap — iki frame arası kesişim
        # Track 3: Kuzey'in dışından başlat
        _ = analyzer.determine_zone((50, 50, 80, 80), track_id=3, conf=0.90)
        # Track 3: Kuzey'in diğer tarafına atla (çizgi Kuzey'i keser)
        z5 = analyzer.determine_zone((450, 450, 480, 480), track_id=3, conf=0.90)
        print(f"Test 5 (Quantum Leap): {z5} — Beklenen: Kuzey [OK]" if z5 == "Kuzey" else f"FAIL: {z5}")

        # Test 6: check_zones geriye uyumluluk
        z6 = analyzer.check_zones((600, 600, 700, 700), track_id=4, conf=0.80)
        print(f"Test 6 (check_zones compat): {z6} — Beklenen: Guney [OK]" if z6 == "Guney" else f"FAIL: {z6}")

        # Test 7: get_rescued_point debug
        cx, cy, was_rescued = analyzer.get_rescued_point(
            (240, 240, 260, 260), track_id=99, conf=0.20, kalman_states={99: [300.0, 300.0, 0.6, 180.0]}
        )
        print(f"Test 7 (Rescue debug): cx={cx:.0f}, cy={cy:.0f}, rescued={was_rescued}")

        # İstatistikler
        hits, misses = analyzer.get_cache_stats()
        print(f"\nCache stats: hits={hits}, misses={misses}")
        print(f"Active tracks: {analyzer.get_active_track_count()}")
        print(f"\n{analyzer}")

        # Temizlik testi
        analyzer.clear_cache(1)
        print(f"Track 1 temizlendi. Active: {analyzer.get_active_track_count()}")

    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(MOCK_JSON):
            os.remove(MOCK_JSON)
