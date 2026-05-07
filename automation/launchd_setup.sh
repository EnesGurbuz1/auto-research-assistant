#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Tez Araştırma Asistanı - macOS launchd Kurulumu
# ═══════════════════════════════════════════════════
# macOS'te background görevleri launchd ile yapılandırır
# (Unix/Linux'teki crontab yerine)
# ═══════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"
PLIST_DIR="$HOME/Library/LaunchAgents"

# OS kontrolü
OS_TYPE="$(uname -s)"
if [ "$OS_TYPE" != "Darwin" ]; then
    echo "❌ Bu script sadece macOS'te çalışır!"
    exit 1
fi

echo "═══════════════════════════════════════════════════"
echo "  Tez Araştırma Asistanı - macOS launchd Kurulumu"
echo "═══════════════════════════════════════════════════"
echo ""

# Virtual environment kontrolü
if [ ! -f "$PYTHON" ]; then
    echo "❌ ERROR: Virtual environment bulunamadı!"
    echo "   Lütfen önce setup.sh'i çalıştırın"
    exit 1
fi

echo "✅ Virtual environment bulundu: $VENV_DIR"
echo ""

# LaunchAgents dizini oluştur
mkdir -p "$PLIST_DIR"

# 1. Günlük literatür taraması (her gün 06:00)
create_daily_scan_plist() {
    local plist="$PLIST_DIR/com.thesis-agent.daily-scan.plist"
    
    cat > "$plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.thesis-agent.daily-scan</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>PYTHON_PATH</string>
        <string>-c</string>
        <string>
import sys
sys.path.insert(0, "PROJECT_PATH")
from agents.literature_scout import LiteratureScout
import yaml
from pathlib import Path
config = yaml.safe_load(open("PROJECT_PATH/config.yaml"))
scout = LiteratureScout(config, Path("PROJECT_PATH"))
scout.run_incremental()
        </string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>PROJECT_PATH</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>PROJECT_PATH/logs/agent_runs/daily_scan.log</string>
    
    <key>StandardErrorPath</key>
    <string>PROJECT_PATH/logs/agent_runs/daily_scan_error.log</string>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF
    
    # Placeholder'ları değiştir
    sed -i '' "s|PYTHON_PATH|$PYTHON|g" "$plist"
    sed -i '' "s|PROJECT_PATH|$PROJECT_DIR|g" "$plist"
    
    echo "✅ Daily scan plist oluşturuldu: $plist"
}

# 2. Haftalık tam pipeline (her Cuma 18:00)
create_weekly_pipeline_plist() {
    local plist="$PLIST_DIR/com.thesis-agent.weekly-pipeline.plist"
    
    cat > "$plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.thesis-agent.weekly-pipeline</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>PYTHON_PATH</string>
        <string>PROJECT_PATH/main.py</string>
        <string>full</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>PROJECT_PATH</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>DayOfWeek</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>PROJECT_PATH/logs/agent_runs/weekly_pipeline.log</string>
    
    <key>StandardErrorPath</key>
    <string>PROJECT_PATH/logs/agent_runs/weekly_pipeline_error.log</string>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF
    
    # Placeholder'ları değiştir
    sed -i '' "s|PYTHON_PATH|$PYTHON|g" "$plist"
    sed -i '' "s|PROJECT_PATH|$PROJECT_DIR|g" "$plist"
    
    echo "✅ Weekly pipeline plist oluşturuldu: $plist"
}

# 3. Haftalık GitHub sync (her Cuma 19:00)
create_github_sync_plist() {
    local plist="$PLIST_DIR/com.thesis-agent.github-sync.plist"
    
    cat > "$plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.thesis-agent.github-sync</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>PYTHON_PATH</string>
        <string>-c</string>
        <string>
import sys
sys.path.insert(0, "PROJECT_PATH")
from automation.github_sync import GitHubSync
import yaml
from pathlib import Path
config = yaml.safe_load(open("PROJECT_PATH/config.yaml"))
sync = GitHubSync(config, Path("PROJECT_PATH"))
sync.commit_and_push()
        </string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>PROJECT_PATH</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>DayOfWeek</key>
        <integer>5</integer>
        <key>Hour</key>
        <integer>19</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>PROJECT_PATH/logs/agent_runs/github_sync.log</string>
    
    <key>StandardErrorPath</key>
    <string>PROJECT_PATH/logs/agent_runs/github_sync_error.log</string>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF
    
    # Placeholder'ları değiştir
    sed -i '' "s|PYTHON_PATH|$PYTHON|g" "$plist"
    sed -i '' "s|PROJECT_PATH|$PROJECT_DIR|g" "$plist"
    
    echo "✅ GitHub sync plist oluşturuldu: $plist"
}

# Plist dosyalarını oluştur
echo "📝 Plist dosyaları oluşturuluyor..."
create_daily_scan_plist
create_weekly_pipeline_plist
create_github_sync_plist

echo ""
echo "═══════════════════════════════════════════════════"
echo "📋 Kurulacak görevler:"
echo "═══════════════════════════════════════════════════"
echo "1. Günlük tarama      → Her gün 06:00"
echo "2. Haftalık pipeline  → Her Cuma 18:00"
echo "3. GitHub sync        → Her Cuma 19:00"
echo ""

read -p "📌 Görevleri yüklemek ve etkinleştirmek istiyorum? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "⏳ Görevler yükleniyor..."
    
    launchctl load "$PLIST_DIR/com.thesis-agent.daily-scan.plist"
    echo "✅ Daily scan yüklendi"
    
    launchctl load "$PLIST_DIR/com.thesis-agent.weekly-pipeline.plist"
    echo "✅ Weekly pipeline yüklendi"
    
    launchctl load "$PLIST_DIR/com.thesis-agent.github-sync.plist"
    echo "✅ GitHub sync yüklendi"
    
    echo ""
    echo "✅ Tüm görevler başarıyla kuruldu!"
    echo ""
    echo "📚 Yönetim Komutları:"
    echo "  Durumu görüntüle:"
    echo "    launchctl list | grep thesis-agent"
    echo ""
    echo "  Manuel olarak çalıştır:"
    echo "    launchctl start com.thesis-agent.daily-scan"
    echo "    launchctl start com.thesis-agent.weekly-pipeline"
    echo "    launchctl start com.thesis-agent.github-sync"
    echo ""
    echo "  Görevleri devre dışı bırak:"
    echo "    launchctl unload ~/Library/LaunchAgents/com.thesis-agent.daily-scan.plist"
    echo "    launchctl unload ~/Library/LaunchAgents/com.thesis-agent.weekly-pipeline.plist"
    echo "    launchctl unload ~/Library/LaunchAgents/com.thesis-agent.github-sync.plist"
    echo ""
else
    echo "❌ İptal edildi. Plist dosyaları oluşturuldu ama yüklenmedi."
    echo "   Daha sonra yüklemek için:"
    echo "   launchctl load ~/Library/LaunchAgents/com.thesis-agent.*.plist"
fi

echo ""
