#!/bin/bash
# Thesis Research Agent - Auto-Runner Script (Cross-platform: Raspberry Pi / macOS / Linux)
# This script runs synthesis and dataset exploration in a loop until all items are processed.

# Determine script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$SCRIPT_DIR"

# Find the venv - try common locations
if [ -d "$WORKSPACE/.venv/bin" ]; then
    VENV="$WORKSPACE/.venv/bin/activate"
elif [ -d "$WORKSPACE/venv/bin" ]; then
    VENV="$WORKSPACE/venv/bin/activate"
else
    echo "ERROR: Python virtual environment not found!"
    echo "Please run setup.sh first to create the virtual environment."
    exit 1
fi

# Find latest JSON files if not specified
if [ -z "${LIT_JSON:-}" ]; then
    LIT_JSON=$(find "$WORKSPACE/data/papers/scholar_results" -name "literature_scan_*.json" -type f 2>/dev/null | sort -r | head -n1)
fi

if [ -z "${DS_JSON:-}" ]; then
    DS_JSON=$(find "$WORKSPACE/data/datasets_catalog" -name "datasets_*.json" -type f 2>/dev/null | sort -r | head -n1)
fi

if [ -z "$LIT_JSON" ] || [ -z "$DS_JSON" ]; then
    echo "WARNING: Could not find JSON files. Please run the initial scan first."
    echo "Run: python main.py literature-scout"
    exit 1
fi

source "$VENV"

echo "Starting autonomous thesis processing loop..."

while true; do
    echo "[$(date)] Running Synthesis Step..."
    python3 "$WORKSPACE/main.py" run-synthesis "$LIT_JSON"
    SYN_EXIT=$?
    
    echo "[$(date)] Running Dataset Explorer Step..."
    python3 "$WORKSPACE/main.py" run-dataset-explorer "$DS_JSON"
    DS_EXIT=$?
    
    # Check if both scripts finished naturally (e.g., nothing left to process)
    # Note: If the scripts exit with 0 when done, we might need a better check.
    # For now, we loop to be safe as per "never stop" command.
    
    echo "[$(date)] Cycle complete. Sleeping for 10 seconds..."
    sleep 10
done
