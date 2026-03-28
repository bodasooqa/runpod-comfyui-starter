"""CivitAI LoRA downloader with async download and auto-unzip."""

import asyncio
import os
import re
import time
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from services.download_manager import (
    MODELS_DIR,
    CHUNK_SIZE,
    PROGRESS_UPDATE_BYTES,
    TaskStatus,
    download_manager,
    unzip_and_remove,
)

router = APIRouter(prefix="/civitai", tags=["civitai"])

LORAS_DIR = os.path.join(MODELS_DIR, "loras")


def _extract_model_id(url: str) -> str | None:
    m = re.search(r"/models/(\d+)", url)
    return m.group(1) if m else None


@router.get("/", response_class=HTMLResponse)
async def civitai_page():
    with open(Path(__file__).resolve().parent.parent / "templates" / "civitai.html") as f:
        return HTMLResponse(f.read())


@router.post("/download")
async def download_lora(token: str = Form(...), url: str = Form(...)):
    api_url = url
    if "civitai.com/api/download/models/" not in api_url:
        model_id = _extract_model_id(url)
        if not model_id:
            return {"message": "Could not extract model ID from URL"}
        api_url = f"https://civitai.com/api/download/models/{model_id}"

    task = download_manager.create_task()
    task.status = TaskStatus.RUNNING
    task.message = "Connecting to CivitAI..."

    asyncio.create_task(_run_civitai_download(task, api_url, token))

    return {"message": "Download started", "task_id": task.task_id}


async def _run_civitai_download(task, api_url: str, token: str):
    try:
        os.makedirs(LORAS_DIR, exist_ok=True)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "ComfyUI-RunPod/1.0",
        }

        timeout = aiohttp.ClientTimeout(total=None, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 401:
                    task.status = TaskStatus.ERROR
                    task.message = "Auth error: check your CivitAI API key"
                    task.finished_at = time.time()
                    return
                if resp.status == 404:
                    task.status = TaskStatus.ERROR
                    task.message = "Model not found: check the URL"
                    task.finished_at = time.time()
                    return
                resp.raise_for_status()

                cd = resp.headers.get("content-disposition", "")
                filename_match = re.findall(
                    r'filename="?([^";]+)"?', cd
                )
                filename = (
                    filename_match[0]
                    if filename_match
                    else os.path.basename(api_url)
                )
                filepath = os.path.join(LORAS_DIR, filename)

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                last_update = 0

                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if (
                            downloaded - last_update >= PROGRESS_UPDATE_BYTES
                            or (total_size > 0 and downloaded >= total_size)
                        ):
                            last_update = downloaded
                            if total_size > 0:
                                pct = int(downloaded / total_size * 100)
                                task.progress = pct
                                task.message = (
                                    f"Downloading: {filename} ({pct}%)"
                                )
                            else:
                                mb = downloaded / (1024 * 1024)
                                task.message = (
                                    f"Downloading: {filename} ({mb:.1f} MB)"
                                )

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        msg = (
            f"Downloaded: {filename}\n"
            f"Size: {size_mb:.1f} MB\n"
            f"Path: {filepath}"
        )

        if filename.endswith(".zip"):
            try:
                extracted = unzip_and_remove(filepath, LORAS_DIR)
                msg += f"\nArchive extracted: {len(extracted)} file(s)"
                if extracted:
                    shown = ", ".join(extracted[:3])
                    msg += f"\nFiles: {shown}"
                    if len(extracted) > 3:
                        msg += f" and {len(extracted) - 3} more"
            except Exception as e:
                msg += f"\nExtraction error: {e}"

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.message = msg

    except aiohttp.ClientResponseError as e:
        task.status = TaskStatus.ERROR
        task.message = f"HTTP error {e.status}: {e.message}"
    except asyncio.TimeoutError:
        task.status = TaskStatus.ERROR
        task.message = "Timeout: download took too long"
    except Exception as e:
        task.status = TaskStatus.ERROR
        task.message = f"Error: {e}"
    task.finished_at = time.time()


@router.get("/status/{task_id}")
async def civitai_status(task_id: str):
    task = download_manager.get_task(task_id)
    if not task:
        return {"status": "not_found", "message": "Task not found"}
    return task.to_dict()
