#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Cron Setup - Otomatik görevleri ayarla (Linux/Raspberry Pi)
# For macOS, use launchd_setup.sh instead
# ═══════════════════════════════════════════════════
set -euo pipefail

OS_TYPE="$(uname -s)"

if [ "$OS_TYPE" = "Darwin" ]; then
    echo "❌ macOS detected!"
    echo ""
    echo "macOS'te crontab yerine launchd kullanın:"
    echo "  bash automation/launchd_setup.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"

echo "═══════════════════════════════════════════════════"
echo "  Tez Araştırma Asistanı - Cron Kurulumu"
echo "  (Linux / Raspberry Pi)"
echo "═══════════════════════════════════════════════════"

# Crontab girişleri
CRON_ENTRIES=(
    # Günlük literatür taraması - her gün 06:00
    "0 6 * * * cd $PROJECT_DIR && $PYTHON -c 'from agents.literature_scout import LiteratureScout; import yaml; config=yaml.safe_load(open(\"config.yaml\")); s=LiteratureScout(config, __import__(\"pathlib\").Path(\".\").resolve()); s.run_incremental()' >> $PROJECT_DIR/logs/agent_runs/daily_scan.log 2>&1"
    
    # Haftalık tam pipeline - her Cuma 18:00
    "0 18 * * 5 cd $PROJECT_DIR && $PYTHON main.py full >> $PROJECT_DIR/logs/agent_runs/weekly_pipeline.log 2>&1"
    
    # Haftalık GitHub sync - her Cuma 19:00
    "0 19 * * 5 cd $PROJECT_DIR && $PYTHON -c 'from automation.github_sync import GitHubSync; import yaml; config=yaml.safe_load(open(\"config.yaml\")); g=GitHubSync(config, __import__(\"pathlib\").Path(\".\").resolve()); g.commit_and_push()' >> $PROJECT_DIR/logs/agent_runs/github_sync.log 2>&1"
)

echo "Aşağıdaki cron görevleri eklenecek:"
echo ""
for entry in "${CRON_ENTRIES[@]}"; do
    echo "  $entry"
    echo ""
done

read -p "Devam edilsin mi? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Mevcut crontab'ı yedekle
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || true
    
    # Yeni girdileri ekle
    (crontab -l 2>/dev/null; echo ""; echo "# === Tez Araştırma Asistanı ==="; for entry in "${CRON_ENTRIES[@]}"; do echo "$entry"; done) | crontab -
    
    echo "✅ Cron görevleri eklendi!"
    echo ""
    echo "Mevcut crontab:"
    crontab -l
else
    echo "İptal edildi."
fi
