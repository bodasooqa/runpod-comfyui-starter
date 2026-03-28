"""HuggingFace model downloader: direct URL or repo-based downloads."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from services.download_manager import (
    MODELS_DIR,
    TaskStatus,
    download_manager,
)

router = APIRouter(prefix="/models", tags=["models"])

MODEL_FOLDERS = [
    "diffusion_models", "loras", "vae", "text_encoders", "upscale_models",
    "clip_vision", "audio_encoders", "checkpoints", "clip", "configs",
    "controlnet", "diffusers", "embeddings", "gligen", "hypernetworks",
    "ipadapter", "model_patches", "onnx", "photomaker", "sams",
    "style_models", "unet", "vae_approx", "detection",
]


@router.get("/", response_class=HTMLResponse)
async def models_page():
    options = "\n".join(
        f'<option value="{f}">{f}</option>' for f in MODEL_FOLDERS
    )
    with open(Path(__file__).resolve().parent.parent / "templates" / "models.html") as f:
        template = f.read()
    return HTMLResponse(template.replace("{{ folder_options }}", options))


@router.post("/download-url")
async def download_by_url(url: str = Form(...), folder: str = Form("diffusion_models")):
    if folder not in MODEL_FOLDERS:
        return {"message": f"Unknown folder: {folder}"}

    task = download_manager.create_task()
    task.status = TaskStatus.RUNNING
    task.message = f"Starting download: {url}"

    dest_dir = os.path.join(MODELS_DIR, folder)
    asyncio.create_task(_run_url_download(task, url, dest_dir))

    return {"message": f"Download started", "task_id": task.task_id}


async def _run_url_download(task, url, dest_dir):
    try:
        status, filename = await download_manager.download_file(
            url, dest_dir, task=task
        )
        size_mb = 0
        fpath = os.path.join(dest_dir, filename)
        if os.path.isfile(fpath):
            size_mb = os.path.getsize(fpath) / (1024 * 1024)

        if status == "downloaded":
            task.status = TaskStatus.COMPLETED
            task.message = (
                f"Downloaded: {filename}\n"
                f"Size: {size_mb:.1f} MB\n"
                f"Path: {dest_dir}"
            )
        elif status == "skipped":
            task.status = TaskStatus.COMPLETED
            task.message = f"Skipped (already exists): {filename}"
        else:
            task.status = TaskStatus.ERROR
        task.progress = 100
    except Exception as e:
        task.status = TaskStatus.ERROR
        task.message = f"Error: {e}"
    task.finished_at = __import__("time").time()


@router.post("/download-hf")
async def download_from_hf(
    repo: str = Form(...),
    filename: str = Form(""),
    token: str = Form(""),
    folder: str = Form("diffusion_models"),
):
    if folder not in MODEL_FOLDERS:
        return {"message": f"Unknown folder: {folder}"}

    task = download_manager.create_task()
    task.status = TaskStatus.RUNNING
    task.message = f"Starting HuggingFace download: {repo}"

    dest_dir = os.path.join(MODELS_DIR, folder)
    asyncio.create_task(_run_hf_download(task, repo, filename, token, dest_dir))

    return {"message": f"Download started: {repo}", "task_id": task.task_id}


async def _run_hf_download(task, repo, filename, token, dest_dir):
    import time as _time

    try:
        os.makedirs(dest_dir, exist_ok=True)

        if filename:
            url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            status, fname = await download_manager.download_file(
                url, dest_dir, custom_filename=filename, headers=headers, task=task
            )

            fpath = os.path.join(dest_dir, fname)
            size_mb = (
                os.path.getsize(fpath) / (1024 * 1024)
                if os.path.isfile(fpath)
                else 0
            )

            if status == "downloaded":
                task.status = TaskStatus.COMPLETED
                task.message = (
                    f"Downloaded: {fname}\n"
                    f"Size: {size_mb:.1f} MB\n"
                    f"Path: {dest_dir}"
                )
            elif status == "skipped":
                task.status = TaskStatus.COMPLETED
                task.message = f"Skipped (already exists): {fname}"
            else:
                task.status = TaskStatus.ERROR
        else:
            task.message = f"Downloading repo {repo} (this may take a while)..."
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _snapshot_download, repo, token, dest_dir
            )
            task.status = TaskStatus.COMPLETED
            task.message = f"Downloaded repo: {repo}\nPath: {dest_dir}"

        task.progress = 100

    except Exception as e:
        task.status = TaskStatus.ERROR
        err = str(e)
        task.message = f"Error: {err}"
        if "401" in err or "authentication" in err.lower():
            task.message += "\n\nHint: Try providing a HuggingFace API token."
    task.finished_at = _time.time()


def _snapshot_download(repo: str, token: str, dest_dir: str):
    from huggingface_hub import snapshot_download, login

    if token:
        login(token=token)
    snapshot_download(
        repo_id=repo,
        local_dir=dest_dir,
    )


@router.get("/status/{task_id}")
async def model_status(task_id: str):
    task = download_manager.get_task(task_id)
    if not task:
        return {"status": "not_found", "message": "Task not found"}
    return task.to_dict()
