# GPU Performans Tahmini — DELL R760xs Sunucu

## Mevcut Sistem (Referans)
- **Yerel bilgisayar**: 60 FPS efektif (vid_stride=2 → ~30 inference/s)
- **Model**: best.engine (TensorRT FP16, ~137 MB)
- **imgsz**: 1024
- **Pipeline**: BotSort tracking + detection

---

## GPU Karşılaştırma Tablosu

| Özellik | RTX 4090 | L40 | L40S |
|---|---|---|---|
| **Mimari** | Ada Lovelace | Ada Lovelace | Ada Lovelace |
| **CUDA Cores** | 16,384 | 18,176 | 18,176 |
| **Tensor Cores** | 512 (4th gen) | 568 (4th gen) | 568 (4th gen) |
| **VRAM** | 24 GB GDDR6X | 48 GB GDDR6 ECC | 48 GB GDDR6 ECC |
| **Bellek Bant Genişliği** | 1,008 GB/s | 864 GB/s | 864 GB/s |
| **FP16 Tensor Perf.** | ~330 TOPS | ~181 TOPS | ~362 TOPS |
| **TDP** | 450W | 300W | 350W |
| **Form Faktör** | 3-slot consumer | Dual-slot datacenter | Dual-slot datacenter |
| **Datacenter Lisans** | ❌ Yasak | ✅ Evet | ✅ Evet |

---

## FPS Tahmini (imgsz=1024, TensorRT FP16, BotSort)

```
Hesaplama Mantığı:
  - Yerel PC = 60 efektif FPS (vid_stride=2) → 30 inference/s
  - GPU TOPS oranı + bellek bant genişliği + headless bonus ile ölçekleme
  - Sunucu headless modda çalışacak → cv2.imshow yükü yok (+%5-8)
  - Xeon Silver 4510 single-thread performansı consumer CPU'dan düşük (-~%10)
```

| GPU | Tahmini İnference/s | Efektif FPS (stride=2) | Yerel PC'ye Göre |
|---|---|---|---|
| **Yerel PC (referans)** | ~30 | ~60 | 1.0x |
| **RTX 4090** | ~55-65 | **~110-130** | ~2.0x |
| **L40** | ~38-45 | **~76-90** | ~1.4x |
| **L40S** | ~52-60 | **~104-120** | ~1.8x |

### Neden L40 < L40S < 4090?

```
FP16 Tensor Performansı (TOPS):
  L40:   ████████░░░░░░░░░  181 TOPS
  4090:  ████████████████░  330 TOPS
  L40S:  █████████████████  362 TOPS

Bellek Bant Genişliği (GB/s):
  L40:   ████████░░  864 GB/s
  L40S:  ████████░░  864 GB/s
  4090:  ██████████  1,008 GB/s
```

- **L40**: FP16 tensor performansı düşük (181 TOPS). Nvidia bunu **rendering ve inference** için optimize etmiş, saf FP16'da geri kalıyor.
- **L40S**: L40'ın **"supercharged"** versiyonu. FP16 tensor 2x artırılmış (362 TOPS). AI inference için optimize.
- **4090**: En yüksek bellek bant genişliği (1,008 GB/s) — büyük imgsz'lerde avantaj. Ama datacenter'da kullanılamaz.

---

## ⚡ Güç Tüketimi Analizi (DELL R760xs: 2x700W PSU)

```
Sunucu Base Güç Tüketimi (GPU hariç):
  2x Xeon Silver 4510  : ~260W
  64GB DDR5             : ~30W
  1x SAS 10K disk       : ~15W
  Network + iDRAC + Fan : ~45W
  ─────────────────────────────
  Toplam Base           : ~350W
```

| Senaryo | GPU TDP | Toplam Çekim | Tek PSU (700W) | Sonuç |
|---|---|---|---|---|
| **RTX 4090** | 450W | ~800W | ❌ Aşıyor | ⚠️ Redundancy YOK |
| **L40** | 300W | ~650W | ✅ 650/700 | ✅ Tam redundancy |
| **L40S** | 350W | ~700W | ⚠️ 700/700 | ⚠️ Sınırda |

> [!WARNING]
> **RTX 4090** ile sistem tek PSU'dan beslenemez (800W > 700W). Redundancy kaybolur ve güç sıkıntısı riski oluşur.

---

## 🔧 Fiziksel Uyumluluk

| GPU | R760xs'e Sığar mı? | Not |
|---|---|---|
| **RTX 4090** | ❌ **SIĞMAZ** | 3-slot consumer soğutucu, 2U rack'e fiziksel olarak sığmaz |
| **L40** | ✅ Sığar | Dual-slot, passive cooling, datacenter form factor |
| **L40S** | ✅ Sığar | Dual-slot, passive cooling, datacenter form factor |

> [!CAUTION]
> **RTX 4090 bu sunucuya fiziksel olarak takılamaz.** 2U rack server'a sadece dual-slot passive-cooled datacenter GPU'lar sığar. 4090'ın 3-slot fan soğutucusu 2U kasaya girmez. Ayrıca NVIDIA lisans politikası consumer GPU'ların datacenter kullanımını yasaklar.

---

## Sonuç ve Öneri

| GPU | FPS | Güç | Uyumluluk | Tavsiye |
|---|---|---|---|---|
| **RTX 4090** | ⭐⭐⭐ ~120 | ❌ | ❌ Sığmaz | ❌ Bu sunucu için uygun değil |
| **L40** | ⭐⭐ ~83 | ✅ | ✅ | ✅ Bütçe dostu, kararlı |
| **L40S** | ⭐⭐⭐ ~112 | ⚠️ | ✅ | ⭐ **En iyi seçim** |

> [!TIP]
> **L40S önerisi:** Mevcut 60 FPS'ten ~112 FPS'e çıkarsınız (**~1.8x hızlanma**). Datacenter uyumlu, 48GB VRAM (gelecekte daha büyük modeller için yeterli), ECC bellek (kararlılık). Güç tüketimi sınırda ama kabul edilebilir.
>
> **L40 alternatifi:** Daha düşük FPS (~83) ama güç konusunda rahat ve daha uygun fiyatlı.
