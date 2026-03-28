"""Preset downloader: browse available presets and download model bundles."""

import asyncio
import json
import os
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from services.download_manager import (
    MODELS_DIR,
    TaskStatus,
    download_manager,
)

router = APIRouter(prefix="/presets", tags=["presets"])

PRESETS_FILE = Path(__file__).resolve().parent.parent / "presets.json"


def _load_presets() -> dict:
    if not PRESETS_FILE.exists():
        return {}
    with open(PRESETS_FILE) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


@router.get("/", response_class=HTMLResponse)
async def presets_page():
    presets = _load_presets()
    cards_html = ""
    for pid, info in presets.items():
        cards_html += (
            f'<div class="preset-card" data-preset="{pid}" '
            f"onclick=\"togglePreset('{pid}')\">"
            f'<div class="preset-name">{info.get("name", pid)}</div>'
            f'<div class="preset-desc">{info.get("description", "")}</div>'
            f'<div class="preset-info">'
            f'Size: {info.get("size", "?")} · Time: {info.get("time", "?")}'
            f"</div></div>"
        )

    if not presets:
        cards_html = (
            '<p style="color:var(--muted);">'
            "No presets configured. Edit "
            "<code>services/presets.json</code> to add presets.</p>"
        )

    with open(Path(__file__).resolve().parent.parent / "templates" / "presets.html") as f:
        template = f.read()
    return HTMLResponse(template.replace("{{ preset_cards }}", cards_html))


@router.post("/download")
async def download_presets(presets: str = Form(...)):
    preset_ids = [p.strip() for p in presets.split(",") if p.strip()]
    all_presets = _load_presets()

    files_to_download = []
    unknown = []
    for pid in preset_ids:
        preset = all_presets.get(pid)
        if not preset:
            unknown.append(pid)
            continue
        for entry in preset.get("files", []):
            folder = entry.get("folder", "diffusion_models")
            files_to_download.append({
                "url": entry["url"],
                "dest_dir": os.path.join(MODELS_DIR, folder),
                "filename": entry.get("filename"),
            })

    if not files_to_download:
        msg = "No files to download."
        if unknown:
            msg += f" Unknown presets: {', '.join(unknown)}"
        return {"message": msg}

    task = download_manager.create_task()
    task.status = TaskStatus.RUNNING
    task.message = f"Starting download: {', '.join(preset_ids)} ({len(files_to_download)} files)"

    asyncio.create_task(_run_preset_download(task, files_to_download, preset_ids))

    msg = f"Download started: {', '.join(preset_ids)} ({len(files_to_download)} files)"
    if unknown:
        msg += f" | Unknown presets skipped: {', '.join(unknown)}"
    return {"message": msg, "task_id": task.task_id}


async def _run_preset_download(task, files, preset_ids):
    await download_manager.download_multiple(files, task)


@router.get("/status/{task_id}")
async def preset_status(task_id: str):
    task = download_manager.get_task(task_id)
    if not task:
        return {"status": "not_found", "message": "Task not found"}
    return task.to_dict()
