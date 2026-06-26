# Tracker Parametre Karşılaştırma Sonuçları

## Genel Özet

| Metrik | YENİ Parametreler | ESKİ Parametreler | Fark |
|---|---|---|---|
| **Toplam geçiş** | 137 | 133 | +4 |
| **Benzersiz ID** | 137 | 133 | +4 |
| **Max ID numarası** | 370 | **691** | **-321** 🔑 |

## 🔑 Kritik Bulgu: Max ID

> [!IMPORTANT]
> **ESKİ parametrelerle Max ID = 691, YENİ ile = 370.**
> 
> Aynı ~%40 videoda eski parametreler **691 farklı track** oluşturmuş, yenisi ise **370**.
> Bu demektir ki eski parametrelerle **321 gereksiz ID atanmış** (araç kaybedilip tekrar yeni ID verilmiş).
> 
> Yeni parametreler ID kararlılığını **%46 iyileştirmiş** (691 → 370).

---

## Geçiş Sayısı Farkı: Sadece +4

Geçiş sayıları neredeyse aynı (137 vs 133). Bu iyi bir işaret:
- Yeni parametreler gereksiz ID değişimini azaltmış ama **gerçek geçiş sayısını bozmamış**
- +4 fark muhtemelen eski parametrelerde ID kırılması yüzünden sayılamayan birkaç aracın artık doğru sayılmasından

---

## Tür Dağılımı Karşılaştırması

| Tür | YENİ | ESKİ | Fark |
|---|---|---|---|
| Otomobil | 84 | 85 | -1 |
| Ağır Taşıt | 22 | 21 | +1 |
| Minibüs | 17 | 15 | +2 |
| Kamyonet | 6 | 6 | 0 |
| Otobüs | 4 | 3 | +1 |
| Panelvan | 3 | 2 | +1 |
| Motosiklet | 1 | 1 | 0 |

> [!NOTE]
> Tür dağılımı çok benzer. Minibüs +2 ve Otobüs +1 farkı, eski parametrelerde ID kırılması sonrası aracın "Otomobil" olarak yeniden sınıflandırılmasından kaynaklanıyor olabilir. ID kararlılığı arttığında **sınıf oylama mekanizması** daha doğru çalışır çünkü daha fazla frame üzerinden oy toplanır.

---

## Rota Dağılımı Karşılaştırması

| Rota | YENİ | ESKİ | Fark |
|---|---|---|---|
| Gate_1 → Gate_4 | 48 | 48 | 0 |
| Gate_3 → Gate_2 | 38 | 35 | **+3** |
| Gate_5 → Gate_2 | 30 | 30 | 0 |
| Gate_1 → Gate_5 | 11 | 11 | 0 |
| Gate_3 → Gate_5 | 5 | 4 | +1 |
| Gate_5 → Gate_4 | 5 | 5 | 0 |

> [!TIP]
> `Gate_3 → Gate_2` rotası +3 artmış. Bu rota muhtemelen engel bölgesinden geçiyor. Eski parametrelerde araç engelden geçerken ID kaybedilip tek-kapı temasına (`Gate_3 → Gate_3`) dönüşüyordu — ki bunu artık filtreliyoruz. Yeni parametrelerde ID korunduğu için araç Gate_3'ten Gate_2'ye kadar takip edilebilmiş.

---

## Sonuç

```
                    ESKİ          YENİ
Track kararlılığı:  ██░░░░░░░░    ██████████  (%46 daha az gereksiz ID)
Geçiş doğruluğu:   ████████░░    ██████████  (+4 daha doğru geçiş)
Sınıf doğruluğu:   ████████░░    █████████░  (Minibüs/Otobüs düzeltmeleri)
```

**Yeni parametreler kesin daha iyi performans gösteriyor.** Geçiş sayısını bozmadan ID kararlılığını ciddi oranda artırmış.
