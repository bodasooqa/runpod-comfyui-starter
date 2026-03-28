"""Outputs browser: list, view, and download ComfyUI output files."""

import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from services.download_manager import OUTPUT_DIR

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _safe_path(user_path: str) -> str | None:
    """Resolve a user-supplied path and ensure it stays within OUTPUT_DIR."""
    resolved = os.path.realpath(os.path.join(OUTPUT_DIR, user_path))
    if not resolved.startswith(os.path.realpath(OUTPUT_DIR)):
        return None
    return resolved


def _list_files(root: str) -> list[str]:
    items = []
    if not os.path.isdir(root):
        return items
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            items.append(rel)
    items.sort()
    return items


@router.get("/", response_class=HTMLResponse)
async def outputs_page():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = _list_files(OUTPUT_DIR)

    rows = ""
    for f in files:
        full = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(full) if os.path.isfile(full) else 0
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} B"
        rows += (
            f'<tr><td><a href="/outputs/file/{f}" target="_blank">{f}</a></td>'
            f'<td style="text-align:right;color:var(--muted);">{size_str}</td></tr>'
        )

    if not files:
        rows = (
            '<tr><td colspan="2" style="color:var(--muted);text-align:center;">'
            "No output files yet</td></tr>"
        )

    with open(Path(__file__).resolve().parent.parent / "templates" / "outputs.html") as f:
        template = f.read()
    return HTMLResponse(
        template.replace("{{ file_rows }}", rows)
        .replace("{{ file_count }}", str(len(files)))
        .replace("{{ output_dir }}", OUTPUT_DIR)
    )


@router.get("/file/{path:path}")
async def get_file(path: str):
    safe = _safe_path(path)
    if not safe or not os.path.isfile(safe):
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(safe)


@router.get("/download-all")
async def download_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = _list_files(OUTPUT_DIR)
    if not files:
        return HTMLResponse("No files to download", status_code=404)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(OUTPUT_DIR, rel), arcname=rel)
    return FileResponse(tmp.name, filename="comfyui_outputs.zip")
