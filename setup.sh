#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Tez Araştırma Asistanı - Kurulum Scripti (Cross-platform)
# ═══════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
OS_TYPE="$(uname -s)"

echo "═══════════════════════════════════════════════════"
echo "  Tez Araştırma Asistanı - Kurulum"
echo "  OS: $OS_TYPE"
echo "═══════════════════════════════════════════════════"

# Python venv oluştur
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] Python sanal ortam oluşturuluyor..."
    python3 -m venv "$VENV_DIR"
else
    echo "[1/4] Sanal ortam zaten mevcut, atlanıyor."
fi

# Aktivasyon
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "ERROR: Sanal ortam oluşturulamadı!"
    exit 1
fi

# Bağımlılıkları yükle
echo "[2/4] Bağımlılıklar yükleniyor..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

# .env dosyasını kontrol et
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "[3/4] UYARI: .env dosyası bulunamadı! .env.example'dan oluşturun."
    echo "        cp .env.example .env"
else
    echo "[3/4] .env dosyası mevcut."
fi

# Dizin yapısını doğrula
echo "[4/4] Dizin yapısı doğrulanıyor..."
for dir in data/papers/pdfs data/papers/scholar_results data/patents data/datasets_catalog data/cache/scholar data/summaries reports/weekly reports/literature_review reports/thesis_proposal logs/agent_runs; do
    mkdir -p "$SCRIPT_DIR/$dir"
done

echo ""
echo "✅ Kurulum tamamlandı!"
echo ""
echo "Kullanım:"
echo "  source .venv/bin/activate"
echo "  python main.py --help"
echo ""

if [ "$OS_TYPE" = "Darwin" ]; then
    echo "📌 macOS Detected: Otomasyonu kurmak için şunu çalıştırın:"
    echo "  bash automation/launchd_setup.sh"
fi
