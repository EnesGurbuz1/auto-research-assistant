# Tez Araştırma Asistanı - Teknik Açıklama

## 1. Projenin Teknik Amacı
Bu sistem, tez araştırma sürecini otomatikleştiren çok ajanlı bir araştırma pipeline'ıdır.
Temel hedef, belirli bir tez konusu için:

1. Literatürü toplamak
2. Patentleri taramak
3. Veri seti kaynaklarını bulmak
4. Tüm bulguları sentezlemek
5. Haftalık akademik rapora dönüştürmek

Bu akış insan müdahalesini azaltacak şekilde komut satırı ve zamanlayıcı üzerinden çalışır.

## 2. Kullanılan Teknolojiler

1. Programlama dili: Python
2. CLI: Click
3. Konfigürasyon: YAML
4. Ortam değişkenleri: python-dotenv (.env)
5. HTTP istemcisi: httpx
6. Web parse: BeautifulSoup
7. Loglama: Loguru
8. Terminal UI: Rich
9. LLM entegrasyonu: Google Gemini (google-generativeai)
10. Retry/backoff: tenacity
11. Rapor üretimi: Markdown + python-docx + docxtpl + HTML
12. Zamanlama: schedule

## 3. Mimari Mantık
Sistem monolitik değil, rol bazlı uzman ajanlardan oluşur.
Mimari, tek bir merkez orchestrator üzerinden çalışan modüler bir agent-pipeline modelidir.

### Katmanlar

1. Komut katmanı: Kullanıcı komutlarını alır ve pipeline tetikler.
2. Orkestrasyon katmanı: Hangi ajanın ne zaman çalışacağını yönetir.
3. Veri toplama katmanı: Dış kaynaklardan ham araştırma verisi toplar.
4. Sentez katmanı: Ham veriyi akademik içgörüye dönüştürür.
5. Doğrulama katmanı: Üretilen iddiaları kaynaklara karşı denetler.
6. Raporlama katmanı: Sonucu md/docx/html rapora çevirir.
7. Operasyon katmanı: Zamanlama, artımlı çalışma ve git senkronu yapar.

## 4. Ajanlar ve Görev Dağılımı

1. Literature Scout
- Akademik kaynak tarar.
- Birden fazla sağlayıcıdan sonuç toplar.
- Sonuçları tekilleştirir.

2. Patent Scanner
- Patent kaynaklarını sorgular.
- Sonuçları normalize eder.

3. Dataset Hunter
- Veri seti platformlarını tarar.
- Sorgu varyantlarıyla kapsama alanını artırır.
- Sonuçları tekilleştirir.

4. Synthesis Agent
- Gap analizi üretir.
- Aktör haritası çıkarır.
- Trend analizi üretir.
- Veri seti uygunluğu değerlendirir.
- Araştırma soruları önerir.

5. Report Generator
- Sentez çıktısını haftalık rapora dönüştürür.
- Aynı içeriği birden fazla formatta dışa verir.
- Güvenilirlik skoru ve kaynakça ekler.

## 5. Pipeline Sıralaması
Tam tarama (full pipeline) şu sırayla çalışır:

1. Literatür taraması
2. Patent taraması
3. Veri seti taraması
4. Sentez üretimi
5. Fact-check
6. Credibility score hesaplama
7. Rapor üretimi
8. Çalışma logunun kaydı

Bunu kısa pseudo-akış olarak düşün:

```text
collect(literature, patent, dataset)
-> synthesize(insights)
-> verify(claims)
-> score(credibility)
-> report(md, docx, html)
-> log(run)
```

## 6. LLM Kullanım Mantığı
LLM erişimi tek bir ortak arayüzde toplanır.
Bu tasarımın amacı, tüm ajanların aynı kalite ve hata yönetimi standardını kullanmasıdır.

### Uygulanan prensipler

1. Role özel system prompt kullanımı
2. Düşük sıcaklık ile daha deterministik üretim
3. JSON formatına zorlanan çıktı
4. Parse hatasında temizleme ve kurtarma denemesi
5. Model/failure durumunda retry + fallback

Bu sayede ajanlar serbest metin yerine işlenebilir yapılandırılmış veri üretir.

## 7. Veri İşleme Stratejisi

1. Her aşama çıktısı JSON olarak kaydedilir.
2. Ham sonuçlar ve sentez sonuçları ayrı tutulur.
3. Artımlı modda önceki sonuçlarla karşılaştırma yapılır.
4. Uygun yerlerde deduplikasyon uygulanır.
5. Uzun süreçler için state dosyaları tutulur.

Bu yaklaşımın sonucu:
- İzlenebilirlik artar
- Hata sonrası kaldığı yerden devam kolaylaşır
- Yeniden üretilebilirlik korunur

## 8. Doğrulama ve Güvenilirlik Modeli
Sistem sadece içerik üretmez, kalite kontrol de uygular.

1. Fact-check aşaması
- İddialar ilgili kaynaklarla karşılaştırılır.
- Her iddiaya durum etiketi verilir.

2. Credibility score aşaması
- Doğrulama dağılımı
- Kaynak çeşitliliği
- Atıf derinliği
- İç tutarlılık

Bu bileşenlerden birleşik bir güvenilirlik puanı üretilir.

## 9. Raporlama Mantığı
Raporlar akademik iletişime uygun bir formatta hazırlanır.

1. Haftalık faaliyet özeti
2. Bulgular özeti
3. Kilit çalışmalar
4. Patent ve veri seti durumu
5. Açık sorular
6. Sonraki hafta planı
7. Kaynakça
8. Güvenilirlik özeti

Çıktılar çok formatlıdır:

1. Markdown: hızlı okuma ve versiyon kontrol için
2. DOCX: danışman paylaşımı için
3. HTML: hızlı görsel önizleme için

## 10. Operasyon ve Süreklilik
Sistem iki kullanım moduna uygundur:

1. Manuel mod
- Komut bazlı çalıştırma
- Adım adım kontrol

2. Otomatik mod
- Zamanlanmış görevler
- Günlük artımlı tarama
- Haftalık rapor üretimi
- Periyodik git senkronu

Bu yapı, araştırmayı tek seferlik script olmaktan çıkarıp sürekli çalışan bir araştırma altyapısına dönüştürür.

## 11. Tasarımın Özeti
Teknik olarak bu proje:

1. Modüler ajan mimarisi kullanır
2. Çok kaynaklı veri toplama uygular
3. LLM'i kontrolsüz metin üretimi için değil, yapılandırılmış analiz için kullanır
4. Doğrulama + skorlama ile kalite katmanı ekler
5. Otomasyon ile süreci sürdürülebilir hale getirir

Kısacası sistem, "arama yapan script" değil; "toplayan + düşünen + doğrulayan + raporlayan" bir araştırma pipeline'ıdır.
