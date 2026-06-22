"""
LineAnalyzer — Sanal Çizgi Kesişim Motoru (Core Logic)
=======================================================
Aracın yörüngesinin (trajectory) sanal kapıları (gates) kesip kesmediğini
Shapely LineString intersection algoritması ile belirler.

Mimari:
    StateMemory.trajectory_history → LineAnalyzer.check_crossing() → crossed gate name

Kullanılan Geometri:
    - Araç yörüngesi: Son N bottom-center noktasından oluşan LineString
    - Kapı çizgisi  : 2 uç noktadan (A, B) oluşan LineString
    - Kesişim testi : trajectory.intersects(gate_line) → bool

Çift Sayma Koruması:
    - Her track_id için hangi kapıları zaten geçtiği kaydedilir
    - Aynı kapı bir track için sadece 1 kez raporlanır
"""

import json
import logging
from typing import Dict, List, Optional, Set, Tuple, Any

from shapely.geometry import LineString
from shapely.prepared import prep

logger = logging.getLogger(__name__)


class LineAnalyzer:
    """
    Sanal çizgi kesişim analiz sınıfı.

    Girdi:
        - Araç yörüngesi: [(cx, cy), (cx, cy), ...] — bottom-center noktaları
    Çıktı:
        - Kesişen kapının adı (str) veya None
    """

    def __init__(self, lines_json_path: str = "config/lines.json"):
        """
        Args:
            lines_json_path: Sanal kapı tanımlarının bulunduğu JSON dosyasının yolu.
        """
        # Kapı geometrileri: {name: LineString}
        self.gates: Dict[str, LineString] = {}
        self.prepared_gates: Dict[str, Any] = {}   # Shapely prepared (hızlı intersection)
        self.gate_names_ordered: List[str] = []

        # Çift Sayma ve Titreme (Flickering) Koruması (20-frame cooldown)
        # {track_id: {gate_name: last_crossed_frame}}
        self._last_crossings: Dict[int, Dict[str, int]] = {}

        # İstatistikler
        self.total_crossings: int = 0

        self._load_gates(lines_json_path)

    # ══════════════════════════════════════════════════════════
    # KAPI YÜKLEME
    # ══════════════════════════════════════════════════════════

    def _load_gates(self, json_path: str) -> None:
        """lines.json'dan kapı çizgilerini yükler, Shapely LineString veya MultiLineString oluşturur."""
        from shapely.geometry import MultiLineString
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            temp_lines: Dict[str, List[LineString]] = {}

            for gate_data in data:
                name = gate_data.get("name")
                points = gate_data.get("points")

                if not name or not points or len(points) < 2:
                    logger.warning(f"Geçersiz kapı verisi atlandı: {gate_data}")
                    continue

                line = LineString(points)
                if not line.is_valid or line.is_empty:
                    logger.warning(f"Kapı '{name}' geçersiz geometri — atlandı.")
                    continue

                # Aynı isimdeki çizgileri grupla
                if name not in temp_lines:
                    temp_lines[name] = []
                    self.gate_names_ordered.append(name) # Sadece ilk gördüğümüzde sıraya ekle
                
                temp_lines[name].append(line)
                logger.info(f"Kapı parçası yüklendi: '{name}' → {points[0]} ... {points[-1]} ({len(points)} nokta)")

            # Gruplanan çizgileri kaydet
            for name, lines_list in temp_lines.items():
                if len(lines_list) == 1:
                    geom = lines_list[0]
                else:
                    # Aynı isimde birden fazla çizgi varsa birleştir
                    geom = MultiLineString(lines_list)
                    logger.info(f"Kapı '{name}' toplam {len(lines_list)} parçadan (MultiLineString) oluşturuldu.")
                
                self.gates[name] = geom
                self.prepared_gates[name] = prep(geom)

            logger.info(f"Toplam {len(self.gates)} eşsiz kapı başarıyla yüklendi.")

        except FileNotFoundError:
            logger.error(f"Lines JSON bulunamadı: {json_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Lines JSON parse hatası: {e}")
        except Exception as e:
            logger.error(f"Kapı yükleme hatası: {e}")

    # ══════════════════════════════════════════════════════════
    # ANA KESİŞİM FONKSİYONLARI
    # ══════════════════════════════════════════════════════════

    def check_crossing(
        self,
        track_id: int,
        trajectory_points: List[Tuple[int, int]],
        current_frame: int
    ) -> Optional[str]:
        """
        Aracın yörüngesinin herhangi bir kapıyı kesip kesmediğini kontrol eder.

        Sadece SON 2 NOKTAYI (son segment) kontrol eder.
        → Performans optimizasyonu + yalnızca "şu an geçiş oldu mu?" sorusunu yanıtlar.

        Titreme (Flickering) Koruması:
        → Aynı araç aynı kapıyı tekrar 20 frame geçemez (cooldown).

        Args:
            track_id:           Araç takip ID'si
            trajectory_points:  [(cx, cy), ...] bottom-center noktaları (min 2 gerekli)
            current_frame:      Cooldown kontrolü için güncel frame sayısı

        Returns:
            Kesişen kapının adı (str) veya None
        """
        if not self.gates or len(trajectory_points) < 2:
            return None

        # Son segment: trajectory'nin son 2 noktası
        segment = LineString([trajectory_points[-2], trajectory_points[-1]])

        if segment.is_empty or not segment.is_valid:
            return None

        if track_id not in self._last_crossings:
            self._last_crossings[track_id] = {}

        for gate_name in self.gate_names_ordered:
            # 20-frame cooldown kontrolü
            last_frame = self._last_crossings[track_id].get(gate_name, -999)
            if current_frame - last_frame < 20:
                continue

            prepared_gate = self.prepared_gates[gate_name]
            if prepared_gate.intersects(segment):
                # KESIŞİM BULUNDU! Cooldown'ı başlat.
                self._last_crossings[track_id][gate_name] = current_frame
                self.total_crossings += 1
                logger.info(f"[CROSSING] Track {track_id} → '{gate_name}' kapısını geçti! (Frame: {current_frame})")
                return gate_name

        return None

    def check_all_crossings(
        self,
        track_id: int,
        trajectory_points: List[Tuple[int, int]],
        current_frame: int
    ) -> List[str]:
        if not self.gates or len(trajectory_points) < 2:
            return []

        segment = LineString([trajectory_points[-2], trajectory_points[-1]])

        if segment.is_empty or not segment.is_valid:
            return []

        if track_id not in self._last_crossings:
            self._last_crossings[track_id] = {}

        crossed = []
        for gate_name in self.gate_names_ordered:
            last_frame = self._last_crossings[track_id].get(gate_name, -999)
            if current_frame - last_frame < 20:
                continue

            prepared_gate = self.prepared_gates[gate_name]
            if prepared_gate.intersects(segment):
                self._last_crossings[track_id][gate_name] = current_frame
                self.total_crossings += 1
                crossed.append(gate_name)
                logger.info(f"[CROSSING] Track {track_id} → '{gate_name}' kapısını geçti! (Frame: {current_frame})")

        return crossed

    def get_crossed_gates(self, track_id: int) -> List[str]:
        """Bir track'in şimdiye kadar geçtiği (cooldown kaydedilen) kapıları döndürür."""
        if track_id in self._last_crossings:
            return list(self._last_crossings[track_id].keys())
        return []

    # ══════════════════════════════════════════════════════════
    # TRACK TEMİZLİĞİ
    # ══════════════════════════════════════════════════════════

    def clear_track(self, track_id: int) -> None:
        """Track silindiğinde cooldown sözlüğünü temizler."""
        self._last_crossings.pop(track_id, None)

    def clear_all(self) -> None:
        """Tüm track geçmişlerini sıfırlar."""
        self._last_crossings.clear()
        self.total_crossings = 0

    # ══════════════════════════════════════════════════════════
    # BİLGİ & DEBUG
    # ══════════════════════════════════════════════════════════

    def get_gate_names(self) -> List[str]:
        """Yükleme sırasına göre kapı isimlerini döndürür."""
        return list(self.gate_names_ordered)

    def __repr__(self) -> str:
        return (
            f"LineAnalyzer("
            f"gates={len(self.gates)}, "
            f"active_tracks={len(self._last_crossings)}, "
            f"total_crossings={self.total_crossings})"
        )


# ══════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    import tempfile

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # ─── Test kapıları oluştur ───
    test_gates = [
        {"name": "Giris_1", "points": [[100, 200], [400, 200]]},   # Yatay çizgi y=200
        {"name": "Cikis_1", "points": [[100, 600], [400, 600]]},   # Yatay çizgi y=600
        {"name": "Lateral",  "points": [[500, 100], [500, 700]]}    # Dikey çizgi x=500
    ]

    test_json = os.path.join(os.path.dirname(__file__), "_test_lines.json")
    try:
        with open(test_json, 'w') as f:
            json.dump(test_gates, f)

        analyzer = LineAnalyzer(test_json)
        print(f"\n{analyzer}\n")

        # --- Test 1: Arac yukaridan asagi hareket -> Giris_1'i keser ---
        traj1 = [(250, 150), (250, 180), (250, 210)]  # y=200 cizgisini geciyor
        result1 = analyzer.check_crossing(track_id=1, trajectory_points=traj1)
        print(f"Test 1 (yorunge y=200'u keser): {result1}")
        assert result1 == "Giris_1", f"FAIL: Beklenen 'Giris_1', gelen '{result1}'"
        print("  PASSED")

        # --- Test 2: Ayni track tekrar ayni kapiyi kesmemeli (cift sayma korumasi) ---
        traj2 = [(250, 210), (250, 190)]  # Geri donuyor ama Giris_1 zaten sayildi
        result2 = analyzer.check_crossing(track_id=1, trajectory_points=traj2)
        print(f"Test 2 (cift sayma korumasi): {result2}")
        assert result2 is None, f"FAIL: Cift sayma oldu! Gelen '{result2}'"
        print("  PASSED")

        # --- Test 3: Farkli track ayni kapiyi kesebilmeli ---
        traj3 = [(300, 150), (300, 250)]
        result3 = analyzer.check_crossing(track_id=2, trajectory_points=traj3)
        print(f"Test 3 (farkli track, ayni kapi): {result3}")
        assert result3 == "Giris_1", f"FAIL: Beklenen 'Giris_1', gelen '{result3}'"
        print("  PASSED")

        # --- Test 4: Hicbir kapiyi kesmeyen yorunge ---
        traj4 = [(50, 50), (80, 80)]
        result4 = analyzer.check_crossing(track_id=3, trajectory_points=traj4)
        print(f"Test 4 (kesisim yok): {result4}")
        assert result4 is None, f"FAIL: Beklenen None, gelen '{result4}'"
        print("  PASSED")

        # --- Test 5: Tek noktali trajectory -> None (en az 2 nokta gerekli) ---
        result5 = analyzer.check_crossing(track_id=4, trajectory_points=[(200, 200)])
        print(f"Test 5 (tek nokta): {result5}")
        assert result5 is None, f"FAIL: Beklenen None, gelen '{result5}'"
        print("  PASSED")

        # --- Test 6: check_all_crossings -- tek segmentte 2 kapiyi birden keser ---
        traj6 = [(250, 100), (250, 700)]  # Uzun dusey segment, hem y=200 hem y=600'u keser
        result6 = analyzer.check_all_crossings(track_id=5, trajectory_points=traj6)
        print(f"Test 6 (coklu kesisim): {result6}")
        assert "Giris_1" in result6 and "Cikis_1" in result6, f"FAIL: {result6}"
        print("  PASSED")

        # --- Test 7: get_crossed_gates ---
        gates_1 = analyzer.get_crossed_gates(1)
        print(f"Test 7 (track 1 gectigi kapilar): {gates_1}")
        assert "Giris_1" in gates_1, f"FAIL: {gates_1}"
        print("  PASSED")

        # --- Test 8: clear_track ---
        analyzer.clear_track(1)
        gates_after = analyzer.get_crossed_gates(1)
        print(f"Test 8 (track 1 temizlendi): {gates_after}")
        assert gates_after == [], f"FAIL: {gates_after}"
        print("  PASSED")

        print(f"\n{analyzer}")
        print(f"\n[OK] Tum testler basarili!")

    finally:
        if os.path.exists(test_json):
            os.remove(test_json)
