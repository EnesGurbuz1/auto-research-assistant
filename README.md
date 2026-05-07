# 🔬 Otonom Tez Araştırma Asistanı

## Tez Konusu
**Başlık:** Çoklu Ajan (Multi-Agent) Şebeke Yük Pazarlığı
**İngilizce:** Multi-Agent Grid Load Negotiation for EV Charging
**Öğrenci:** Enes

---

## Proje Açıklaması

Bir binadaki veya filodaki şarj olan araçların her birinin kendi dijital ajanı olduğu; bu ajanların kısıtlı şebeke elektriğini paylaşmak için birbirleriyle otonom olarak pazarlık yaptığı bir sistem konusunda kapsamlı literatür taraması yapan otonom araştırma asistanı.

Bu araç, aşağıdaki görevleri tamamen otomatik olarak gerçekleştirir:
- 📚 **Literatür taraması**: Google Scholar, Semantic Scholar, arXiv, Scopus
- 📋 **Patent taraması**: Google Patents, Espacenet, WIPO, TÜRKPATENT
- 📊 **Veri seti keşfi**: Kaggle, Zenodo, HuggingFace, Papers With Code, UCI, IEEE DataPort, OpenML
- 🧪 **Sentez ve gap analizi**: LLM ile boşluk tespiti, trend analizi, aktör haritası
- 📝 **Rapor üretimi**: DOCX (hocanın şablonu) + Markdown formatında haftalık raporlar
- 🤖 **Otomasyon**: Zamanlı taramalar, GitHub sync, daemon modu

---

## Sistem Mimarisi

```
                    ┌─────────────────────┐
                    │   Smart Orchestrator │
                    │   (Görev Planlayıcı) │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
    ┌─────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
    │ Literature │      │   Patent    │      │   Dataset   │
    │   Scout    │      │  Scanner    │      │   Hunter    │
    └─────┬─────┘      └──────┬──────┘      └──────┬──────┘
          │                    │                     │
          └────────────────────┼────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Synthesis Agent    │
                    │  (Sentez & Analiz)  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Report Generator   │
                    │  (Rapor Üretici)    │
                    └─────────────────────┘
```

---

## Ajanlar

| Ajan | Görev |
|------|-------|
| **Smart Orchestrator** | Tüm ajanları koordine eder, görev planlar |
| **Literature Scout** | Google Scholar, Scopus, Semantic Scholar, arXiv'den makale arar |
| **Patent Scanner** | Espacenet, Google Patents, TÜRKPATENT, WIPO'dan patent arar |
| **Dataset Hunter** | Kaggle, UCI, HuggingFace, Zenodo, PWC, IEEE'den veri seti arar |
| **Synthesis Agent** | Gap analizi, trend tespiti, aktör haritası üretir |
| **Report Generator** | Haftalık rapor ve tez önerisi DOCX formatında üretir |

---

## Danışman Direktifleri (Her raporda cevaplanır)
1. Bu alanda çözülmüş ne var, çözülmemiş ne var?
2. Kim çalışıyor, hangi gruplar, hangi şirketler?
3. 2-3 yıl önce ile bugün arasında ne değişti?
4. Survey/review makalelerini öncelikle incele
5. Patentleri incele
6. Veri setlerini MUTLAKA incele
7. Haftalık ilerleme raporu hazırla

---

## Kurulum

### 1. Sanal ortam oluştur ve bağımlılıkları kur

```bash
cd thesis-research-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. API anahtarlarını ayarla

`.env` dosyasını düzenle:

```bash
nano .env
```

| API Key | Gerekli mi? | Nasıl Alınır |
|---------|-------------|--------------|
| `GEMINI_API_KEY` | ✅ Zorunlu | [Google AI Studio](https://aistudio.google.com/apikey) — Ücretsiz |
| `SCOPUS_API_KEY` | ⚠️ Opsiyonel | [Elsevier Dev Portal](https://dev.elsevier.com/) — Kurumsal erişim |
| `GITHUB_TOKEN` | ⚠️ Push için | `gh auth token` veya GitHub Settings → Developer settings |
| `SEMANTIC_SCHOLAR_API_KEY` | ⚠️ Opsiyonel | [S2 API Key](https://www.semanticscholar.org/product/api) — Rate limit artar |
| `SERPAPI_KEY` | ⚠️ Opsiyonel | [SerpAPI](https://serpapi.com/) — Google Scholar bypass |
| `KAGGLE_KEY` + `KAGGLE_USERNAME` | ⚠️ Opsiyonel | [Kaggle Account](https://www.kaggle.com/settings) |

> **Not:** Semantic Scholar, arXiv, Zenodo, HuggingFace, Papers With Code, UCI ve OpenML API'leri **ücretsiz ve key gerektirmez**.

---

## Kullanım

```bash
# Aktive venv
source venv/bin/activate

# Tam araştırma taraması
python main.py full-scan

# Tam tarama + GitHub push
python main.py full-scan --push

# Günlük artımlı tarama
python main.py incremental

# Haftalık rapor (md + docx)
python main.py report

# Danışman hocanın 3 sorusunu cevapla
python main.py questions

# Tez önerisi taslağı
python main.py proposal

# 7/24 otomatik çalışma
python main.py daemon

# Durum göster
python main.py status

# Rapor şablonunu analiz et
python main.py analyze-template

# Araçları test et
python main.py test-tools

# Sadece literatür
python main.py literature

# Sadece patent
python main.py patent

# Sadece veri seti
python main.py datasets

# Sadece sentez
python main.py synthesize
```

---

## Dizin Yapısı

```
thesis-research-agent/
├── main.py                    # CLI giriş noktası
├── config.yaml                # Ana konfigürasyon
├── requirements.txt           # Python bağımlılıkları
├── .env                       # API anahtarları (gitignore)
├── .gitignore
├── README.md
├── setup.sh                   # Kurulum scripti
│
├── agents/                    # Ajan modülleri
│   ├── llm_interface.py       # Google Gemini API wrapper
│   ├── orchestrator.py        # Temel orkestrasyon
│   ├── smart_orchestrator.py  # Akıllı pipeline yönetimi
│   ├── literature_scout.py    # Akademik arama ajanı
│   ├── patent_scanner.py      # Patent tarama ajanı
│   ├── dataset_hunter.py      # Veri seti keşif ajanı
│   ├── synthesis_agent.py     # Sentez ve gap analizi
│   └── report_generator.py    # Rapor üretim ajanı
│
├── tools/                     # Araç modülleri
│   ├── scholar_search.py      # Google Scholar API
│   ├── scopus_search.py       # Scopus API
│   ├── semantic_scholar_api.py # Semantic Scholar API
│   ├── arxiv_search.py        # arXiv API
│   ├── patent_search.py       # Çoklu patent arama
│   ├── dataset_search.py      # Çoklu veri seti arama
│   ├── pdf_downloader.py      # PDF indirme
│   ├── pdf_parser.py          # PDF metin çıkarma
│   └── docx_report.py         # DOCX rapor üretimi
│
├── skills/                    # Beceri modülleri
│   ├── gap_analysis.py        # Boşluk tespiti
│   ├── trend_detection.py     # Trend analizi
│   ├── paper_summarizer.py    # Makale özetleme
│   ├── comparison_matrix.py   # Karşılaştırma tablosu
│   ├── citation_network.py    # Atıf ağı analizi
│   └── research_question_gen.py # Araştırma sorusu üretimi
│
├── prompts/                   # LLM sistem promptları
│   ├── orchestrator_system.md
│   ├── literature_scout_system.md
│   ├── patent_scanner_system.md
│   ├── dataset_hunter_system.md
│   ├── synthesis_system.md
│   └── report_generator_system.md
│
├── automation/                # Otomasyon
│   ├── scheduler.py           # Zamanlayıcı
│   ├── github_sync.py         # Git otomasyonu
│   └── cron_setup.sh          # Cron kurulumu
│
├── templates/                 # Şablonlar
│   └── rapor_template.docx    # Hocanın rapor şablonu
│
├── data/                      # Veriler (gitignore hariç)
│   ├── papers/
│   │   ├── scholar_results/   # JSON arama sonuçları
│   │   └── pdfs/              # İndirilen PDF'ler
│   ├── patents/               # Patent sonuçları
│   ├── datasets_catalog/      # Veri seti kataloğu
│   ├── summaries/             # Sentez sonuçları
│   └── cache/                 # Arama cache'i
│
├── reports/                   # Üretilen raporlar
│   ├── weekly/                # Haftalık raporlar (.md + .docx)
│   └── thesis_proposal/       # Tez önerisi taslakları
│
└── logs/                      # Log dosyaları
    └── agent_runs/            # Çalışma logları
```

---

## Otomasyon Zamanlaması

| Zamanlama | Görev |
|-----------|-------|
| Her Pazartesi 02:00 | Tam araştırma taraması |
| Her gün 08:00 | Artımlı tarama (yeni yayınlar) |
| Her Cuma 20:00 | Haftalık rapor üretimi |
| Her 30 dakika | GitHub otomatik sync |

Daemon modunda çalıştırmak için:
```bash
nohup python main.py daemon > logs/daemon.log 2>&1 &
```

---

## Lisans
Özel kullanım — Enes'in yüksek lisans tez araştırması için.
