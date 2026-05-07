# 🍎 macOS Setup Guide

## Proje Hakkında
Bu proje daha önce Raspberry Pi üzerinde çalışacak şekilde hazırlanmıştı. Şu anda macOS üzerinde çalışacak şekilde uyarlandı.

---

## ✅ Kurulum Adımları

### 1. Temel Kurulum
```bash
# Proje dizinine git
cd /path/to/oto-research-multi-agent-ev-charging

# setup.sh scriptini çalıştır
bash setup.sh
```

Bu script:
- ✅ Python 3 virtual environment oluşturur (`.venv/`)
- ✅ Gerekli bağımlılıkları yükler
- ✅ Proje dizin yapısını oluşturur
- ✅ .env dosyasını kontrol eder

### 2. .env Dosyası Ayarla
```bash
# Varsa .env.example'dan kopyala
cp .env.example .env

# Açıp API anahtarlarını ekle
# Gerekli: Google Generative AI, Semantic Scholar vb.
nano .env
```

### 3. Projeyi Test Et
```bash
# Virtual environment'ı aktifleştir
source .venv/bin/activate

# Yardım komutlarını görüntüle
python main.py --help

# İlk taramayı yap (test için)
python main.py literature-scout --limit 5
```

---

## 🤖 Otomasyonu Ayarla (İsteğe Bağlı)

macOS'te background görevleri launchd ile yapılandırılır:

```bash
# launchd setup script'ini çalıştır
bash automation/launchd_setup.sh
```

Bu kurarsa aşağıdaki görevleri yapılandırır:
- **Günlük tarama**: Her gün 06:00 → Literatür taraması
- **Haftalık pipeline**: Her Cuma 18:00 → Tam araştırma
- **GitHub sync**: Her Cuma 19:00 → Otomatik commit & push

### Launchd Yönetim Komutları

```bash
# Yüklenmiş görevleri göster
launchctl list | grep thesis-agent

# Görevleri elle çalıştır
launchctl start com.thesis-agent.daily-scan
launchctl start com.thesis-agent.weekly-pipeline
launchctl start com.thesis-agent.github-sync

# Görevleri devre dışı bırak
launchctl unload ~/Library/LaunchAgents/com.thesis-agent.daily-scan.plist

# Tüm görevleri yeniden yükle
launchctl load ~/Library/LaunchAgents/com.thesis-agent.*.plist

# Log dosyalarını görmek için
tail -f data/logs/agent_runs/daily_scan.log
```

---

## 📚 Temel Komutlar

```bash
# Kaynağa aktifleştir
source .venv/bin/activate

# Tam araştırma pipeline'ı (literature + patent + dataset + synthesis)
python main.py full-scan --push

# Sadece literatür taraması
python main.py literature-scout

# Sadece patent taraması
python main.py patent-scanner

# Sadece dataset keşfi
python main.py dataset-hunter

# Haftalık rapor üret (MD + DOCX)
python main.py report

# Danışman soruları (gap analysis, actor map, trend analysis)
python main.py questions

# Tez önerisi taslağı
python main.py proposal

# Daemon modu (arka planda çalış)
python main.py daemon
```

---

## 🛠️ Raspberry Pi → macOS Değişiklikleri

Aşağıdaki dosyalar macOS uyumlu hale getirildi:

### setup.sh
- ✅ OS tespiti eklendi
- ✅ Virtual environment oluşturma iyileştirildi
- ✅ macOS spesifik yönlendirmeler eklendi

### auto_run.sh
- ✅ Hardcoded `/home/adminpi/` yolu kaldırıldı
- ✅ Dinamik path algılaması eklendi
- ✅ `.venv` ve `venv/` her ikisini de destekliyor
- ✅ JSON dosyalarını otomatik bulabiliyor

### automation/cron_setup.sh
- ✅ macOS tespiti eklendi
- ✅ macOS kullanıcılarını `launchd_setup.sh`'e yönlendiriyor

### automation/launchd_setup.sh (YENİ)
- ✅ macOS launchd görevlerini kurulu
- ✅ Cron alternatifi sağlıyor
- ✅ Günlük, haftalık ve senkronizasyon görevleri

### Python kodu
- ✅ Zaten cross-platform (pathlib kullanıyor)
- ✅ Hiçbir değişiklik gerekmedi

---

## 🐛 Sorun Giderme

### Virtual environment bulunamadı
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### .env dosyası yok
```bash
# .env.example'dan oluştur
cp .env.example .env
# API anahtarlarını ekle
```

### Launchd görevler çalışmıyor
```bash
# Log dosyalarını kontrol et
cat ~/Library/LaunchAgents/com.thesis-agent.daily-scan.plist

# Görev ayrıntılarını görüntüle
launchctl dumpstate

# Görevleri manuel test et
source .venv/bin/activate
cd /path/to/project
python main.py full-scan
```

### PDF işleme sorunları
macOS'te bazı PDF kütüphaneleri platform-spesifik bağımlılık gerektirebilir:
```bash
# Homebrew'ü kullanarak sistem bağımlılıklarını kur
brew install poppler
```

---

## 📋 Proje Yapısı

```
.
├── setup.sh                    # Kurulum script'i (macOS uyumlu)
├── auto_run.sh                 # Otomatik çalıştırma (macOS uyumlu)
├── main.py                     # Ana giriş noktası
├── config.yaml                 # Proje konfigürasyonu
├── requirements.txt            # Python bağımlılıkları
├── agents/                     # Araştırma ajanları
│   ├── literature_scout.py     # Literatür taraması
│   ├── patent_scanner.py       # Patent taraması
│   ├── dataset_hunter.py       # Veri seti keşfi
│   └── ...
├── automation/
│   ├── launchd_setup.sh        # macOS otomasyonu (YENİ)
│   ├── cron_setup.sh           # Linux/RPi otomasyonu
│   ├── scheduler.py            # Python scheduler
│   └── github_sync.py          # Git automation
├── tools/                      # Dış API araçları
├── skills/                     # LLM becerileritts
└── data/                       # Tarama sonuçları ve raporlar
```

---

## 🔗 Faydalı Linkler

- [macOS launchd dokumentasyonu](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [Cron vs Launchd karşılaştırması](https://medium.com/swlh/scheduling-tasks-in-macos-e457dca3d4c)
- Proje ana README: [README.md](README.md)

---

## ⚡ Hızlı Başlangıç

```bash
# 1. Kurulum
bash setup.sh

# 2. Virtual environment'ı aktifleştir
source .venv/bin/activate

# 3. .env dosyasını ayarla
cp .env.example .env
# Düzenle ve API anahtarlarını ekle

# 4. İlk test taraması yap
python main.py literature-scout --limit 10

# 5. (İsteğe bağlı) Otomasyonu kur
bash automation/launchd_setup.sh

# 6. Rapor üret
python main.py report

# Bitirme
deactivate
```

---

**Son güncelleme**: 7 Mayıs 2026
**Uyumlu:** macOS 10.15+, Python 3.8+
