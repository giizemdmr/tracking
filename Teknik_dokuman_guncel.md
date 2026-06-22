# AIPTIMIZE TEKNİK DÖKÜMAN

## 1. Sistemin Amacı ve Genel Kapsam

* **Akıllı Trafik Analizi:** Sistem; trafik mühendisliği, planlama ve veri analitiği ihtiyaçlarına yanıt vermek üzere tasarlanmış bulut tabanlı (SaaS) bir akıllı trafik analiz platformudur.
* **Otomatik Analiz:** Platformun temel amacı; kullanıcıların trafik akışını içeren video kayıtlarını sisteme yükleyerek, insan müdahalesine gerek kalmaksızın otomatik video analizi yaptırabilmesini ve bu verileri anlamlı istatistiksel raporlara dönüştürebilmesini sağlamaktır.
* **Esnek Hizmet:** Bireysel, Şirket ve Belediye (Kamu) olmak üzere farklı kullanıcı profillerine hizmet verebilecek ölçeklenebilir bir mimariye sahiptir.

---

## 2. SaaS Altyapısı ve Video Yükleme Süreci

* **Web Tabanlı Erişim (SaaS):** Sistem tamamen bulut tabanlı bir çözüm olarak sunulur. Son kullanıcıların sistemi kullanabilmesi için herhangi bir yerel sunucu kurulumuna, özel grafik kartı (GPU) donanımına veya yerel yazılım lisansına ihtiyacı yoktur. Güncel bir web tarayıcısı ve internet bağlantısı yeterlidir.
* **Kesintisiz Video Yükleme (Chunked Upload):** Yüksek çözünürlüklü ve büyük boyutlu trafik videolarının sisteme aktarımı sırasında internet kesintilerinden etkilenmemek amacıyla parçalı yükleme teknolojisi kullanılır. Video yükleme aşamasında ilerleme durumu kullanıcıya anlık olarak gösterilir.
* **Asenkron İşleme:** Kullanıcılar videolarını yükledikten sonra, video arka planda bağımsız bir analiz servisi tarafından asenkron olarak işlenir. Kullanıcıların tarayıcıyı açık tutmasına gerek yoktur; analiz tamamlandığında sonuçlar sisteme yansıtılır.

---

## 3. Yapay Zeka ve Görüntü İşleme Yetenekleri

* **Araç Tespiti ve Sınıflandırma:** Yapay zeka motoru, video akışındaki nesneleri yüksek doğrulukla tespit eder ve sınıflandırır. Sistem aşağıdaki nesne sınıflarını tanımaktadır:
  1. Yaya
  2. Bisiklet
  3. Motosiklet
  4. Otomobil
  5. Otobüs
  6. Ağır Taşıt (Kamyon vb.)
  7. Panelvan
  8. Minibüs
  9. Kamyonet
* **Araç Takibi (Object Tracking):** Tespit edilen araçlar video boyunca kimlik (ID) değiştirmeden ve kaybolmadan izlenir. Araçların birbirini kapattığı durumlarda dahi akıllı tahmin algoritmalarıyla takip kesintisiz sürdürülür.
* **Sanal Kapılar (Çizgi Geçiş Analizi):** Yol üzerine tanımlanan sanal çizgiler/kapılar (Giriş ve Çıkış hatları) aracılığıyla araçların hangi yönden gelip hangi yöne gittiği (Origin-Destination) belirlenir. Araçların çizgiden geçerken titreme veya anlık gecikmeler nedeniyle mükerrer (çift) sayılmasını engelleyen akıllı bir filtreleme koruması bulunur.
* **Bölge Filtreleme (ROI):** Kullanıcılar tarafından tanımlanan analiz bölgesi dışındaki hareketli cisimler elenerek sadece ilgilenilen bölge içerisindeki trafik verileri işlenir ve gereksiz sayımların önüne geçilir.
* **Alan Ağırlıklı Sınıf Kararı:** Araçların türü belirlenirken, kameraya en yakın (en net görülen) ve en yüksek güvenilirlikteki tespitler baz alınarak sınıflandırma hataları otomatik olarak düzeltilir.

---

## 4. Çıktı Formatları ve Raporlama

Analiz tamamlandığında sistem kullanıcılara iki temel formatta çıktı sunar:

### A. Excel Raporu (.xlsx)
Kullanıcıların bilgisayarlarına indirebilecekleri, doğrudan kullanıma hazır ve biçimlendirilmiş detaylı trafik raporudur. Excel dökümanı şu kolonları içerir:
* **Tarih/Saat:** Araç geçişinin gerçekleştiği zaman bilgisi.
* **Olay Raporu:** Geçişin kısa metinsel özeti.
* **ID:** Aracın sistem tarafından atanan benzersiz takip numarası.
* **Tür:** Sınıflandırılan araç tipi (örn: Otomobil, Otobüs).
* **Giriş:** Aracın ilk tespit edildiği/girdiği sanal kapı.
* **Çıkış:** Aracın sistemden çıktığı/terk ettiği sanal kapı.
* **Tam Rota:** Aracın izlediği tüm sanal kapıların kronolojik sırası (örn: Giriş-A -> Çıkış-B).

> [!TIP]
> Video sona erdiğinde, analizi henüz bitmemiş veya ekrandan çıkmamış aktif durumdaki tüm araçların rotaları otomatik olarak kapatılarak Excel raporuna dahil edilir. Böylece hiçbir veri kaybı yaşanmaz.

### B. Ham Veri Formatı (JSON)
Sistemin arka planda ürettiği ham veri çıktısıdır. Bu format, platformun diğer kurumsal yazılımlarla veya veri tabanlarıyla entegrasyonunu sağlamak amacıyla kullanılır.

---

## 5. Abonelik ve Ödeme Yönetimi

* **Müşteri Grupları:** Platform; Bireysel, Kurumsal ve Belediye olmak üzere üç temel hiyerarşik müşteri tipini destekler ve her profile özel dinamik fiyatlandırma politikaları sunar.
* **Abonelik Modelleri:** Belirli bir kotaya ve süreye tabi olan "Tekrarlayan" veya esnek kullanıma uygun "Tek Seferlik" abonelik paketleri mevcuttur.
* **Kota Takibi:** Kullanıcılar, tanımlı paketlerindeki toplam video yükleme limitlerini (saat bazında) ve anlık kota tüketimlerini kullanıcı arayüzü üzerinden şeffaf bir şekilde izleyebilirler.
* **Otomatik Kontrol:** Süresi dolan veya kullanım kotasını dolduran abonelikler sistem tarafından otomatik olarak tespit edilerek pasifleştirilir.
