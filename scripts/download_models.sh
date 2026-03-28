#!/bin/bash
# download_models.sh — Download model presets defined in presets.json.
#
# Usage:
#   bash /scripts/download_models.sh PRESET1,PRESET2,...
#
# Reads preset definitions from /opt/services/presets.json via a Python helper.
# Downloads files with wget, skips existing, prints structured progress.
# Called by start.sh when PRESET_DOWNLOAD env var is set.

set -euo pipefail

PRESETS_JSON="${PRESETS_JSON:-/opt/services/presets.json}"
COMFYUI_DIR="${COMFYUI_DIR:-/workspace/runpod-slim/ComfyUI}"
MODELS_DIR="${COMFYUI_DIR}/models"

if [ $# -eq 0 ] || [ -z "$1" ]; then
    echo "Usage: $0 PRESET1,PRESET2,..."
    exit 1
fi

REQUESTED="$1"

extract_preset_files() {
    python3 -c "
import json, sys

presets_file = sys.argv[1]
requested = sys.argv[2].split(',')

with open(presets_file) as f:
    data = json.load(f)

for pid in requested:
    pid = pid.strip()
    if pid.startswith('_') or pid not in data:
        print(f'UNKNOWN:{pid}', file=sys.stderr)
        continue
    preset = data[pid]
    for entry in preset.get('files', []):
        url = entry['url']
        folder = entry.get('folder', 'diffusion_models')
        filename = entry.get('filename', '')
        print(f'{url}\t{folder}\t{filename}')
" "$PRESETS_JSON" "$REQUESTED"
}

download_if_missing() {
    local url="$1"
    local dest_dir="$2"
    local custom_filename="$3"
    local current_num="$4"
    local total_num="$5"

    local filename
    if [ -n "$custom_filename" ]; then
        filename="$custom_filename"
    else
        filename=$(basename "${url%%\?*}")
    fi
    local filepath="$dest_dir/$filename"

    mkdir -p "$dest_dir"

    if [ -f "$filepath" ] && [ -s "$filepath" ]; then
        echo "  [$current_num/$total_num] SKIP (exists): $filename"
        return 0
    fi

    echo "  [$current_num/$total_num] Downloading: $filename"

    local tmpdir="${COMFYUI_DIR}/.tmp_downloads"
    mkdir -p "$tmpdir"
    local tmpfile="$tmpdir/${filename}.part"

    if wget -q --show-progress -O "$tmpfile" "$url" 2>&1; then
        mv -f "$tmpfile" "$filepath"
        echo "  [$current_num/$total_num] OK: $filename"
        return 0
    else
        echo "  [$current_num/$total_num] FAILED: $filename" >&2
        rm -f "$tmpfile"
        return 1
    fi
}

echo "=== Preset Model Downloader ==="
echo "Requested presets: $REQUESTED"
echo "Models directory: $MODELS_DIR"
echo ""

FILE_LIST=$(extract_preset_files 2>&1 1>/tmp/_dm_files.txt && cat /tmp/_dm_files.txt || cat /tmp/_dm_files.txt)
UNKNOWN_LINES=$(echo "$FILE_LIST" | grep "^UNKNOWN:" || true)
FILE_LINES=$(cat /tmp/_dm_files.txt 2>/dev/null || true)
rm -f /tmp/_dm_files.txt

if [ -n "$UNKNOWN_LINES" ]; then
    echo "$UNKNOWN_LINES" | while read -r line; do
        pid="${line#UNKNOWN:}"
        echo "WARNING: Unknown preset '$pid', skipping."
    done
    echo ""
fi

if [ -z "$FILE_LINES" ]; then
    echo "No files to download. Check preset names and presets.json."
    exit 0
fi

TOTAL=$(echo "$FILE_LINES" | wc -l | tr -d ' ')
echo "Total files to process: $TOTAL"
echo ""

CURRENT=0
DOWNLOADED=0
SKIPPED=0
FAILED=0

while IFS=$'\t' read -r url folder custom_filename; do
    [ -z "$url" ] && continue
    CURRENT=$((CURRENT + 1))
    dest_dir="$MODELS_DIR/$folder"

    if download_if_missing "$url" "$dest_dir" "$custom_filename" "$CURRENT" "$TOTAL"; then
        filepath="$dest_dir/${custom_filename:-$(basename "${url%%\?*}")}"
        if [ -f "$filepath" ]; then
            # Determine if it was skipped or downloaded by checking the output
            DOWNLOADED=$((DOWNLOADED + 1))
        else
            SKIPPED=$((SKIPPED + 1))
        fi
    else
        FAILED=$((FAILED + 1))
    fi
done <<< "$FILE_LINES"

echo ""
echo "=== Download Summary ==="
echo "Processed: $CURRENT/$TOTAL"
echo "Downloaded/Skipped: $((CURRENT - FAILED))"
echo "Failed: $FAILED"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
