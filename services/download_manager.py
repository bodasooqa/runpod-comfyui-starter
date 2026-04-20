"""Shared async download engine with progress tracking and TTL cleanup."""

import asyncio
import os
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from enum import Enum

import aiohttp

COMFYUI_DIR = os.environ.get("COMFYUI_DIR", "/workspace/runpod-slim/ComfyUI")
MODELS_DIR = os.path.join(COMFYUI_DIR, "models")
OUTPUT_DIR = os.path.join(COMFYUI_DIR, "output")
CIVITAI_API_KEY = os.environ.get("CIVITAI_API_KEY", "")

TASK_TTL_SECONDS = 3600
CHUNK_SIZE = 1024 * 1024
PROGRESS_UPDATE_BYTES = 5 * 1024 * 1024


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Task:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = ""
    progress: float = 0.0
    total_files: int = 0
    current_file: int = 0
    current_filename: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "message": self.message,
            "progress": self.progress,
            "total_files": self.total_files,
            "current_file": self.current_file,
            "current_filename": self.current_filename,
        }


class DownloadManager:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create_task(self) -> Task:
        self._cleanup_expired()
        task = Task(task_id=str(uuid.uuid4()))
        self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            tid
            for tid, t in self._tasks.items()
            if t.finished_at and (now - t.finished_at) > TASK_TTL_SECONDS
        ]
        for tid in expired:
            del self._tasks[tid]

    async def download_file(
        self,
        url: str,
        dest_dir: str,
        *,
        custom_filename: str | None = None,
        headers: dict[str, str] | None = None,
        task: Task | None = None,
        file_index: int = 1,
        total_files: int = 1,
    ) -> tuple[str, str]:
        """Download a single file. Returns (status, filename).

        status is one of: "downloaded", "skipped", "failed".
        """
        url = _inject_civitai_token(url)
        filename = custom_filename or _filename_from_url(url)
        filepath = os.path.join(dest_dir, filename)
        os.makedirs(dest_dir, exist_ok=True)

        if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
            if task:
                task.current_file = file_index
                task.current_filename = filename
                task.progress = file_index / total_files * 100
                task.message = f"Skipped (exists): {filename} ({file_index}/{total_files})"
            return "skipped", filename

        if task:
            task.status = TaskStatus.RUNNING
            task.current_file = file_index
            task.current_filename = filename
            task.total_files = total_files
            task.progress = (file_index - 1) / total_files * 100
            task.message = f"Downloading {file_index}/{total_files}: {filename} (0%)"

        tmp_path = filepath + ".part"
        try:
            timeout = aiohttp.ClientTimeout(total=None, sock_read=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                req_headers = {"User-Agent": "ComfyUI-RunPod/1.0"}
                if headers:
                    req_headers.update(headers)

                async with session.get(url, headers=req_headers) as resp:
                    resp.raise_for_status()

                    if not custom_filename:
                        cd = resp.headers.get("content-disposition", "")
                        parsed = _filename_from_content_disposition(cd)
                        if parsed:
                            filename = parsed
                            filepath = os.path.join(dest_dir, filename)
                            tmp_path = filepath + ".part"

                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    last_update = 0

                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if task and (
                                downloaded - last_update >= PROGRESS_UPDATE_BYTES
                                or (total_size > 0 and downloaded >= total_size)
                            ):
                                last_update = downloaded
                                file_pct = (
                                    int(downloaded / total_size * 100)
                                    if total_size > 0
                                    else 0
                                )
                                overall = (
                                    (file_index - 1) / total_files * 100
                                    + file_pct / total_files
                                )
                                task.progress = min(overall, 100)
                                if total_size > 0:
                                    task.message = (
                                        f"Downloading {file_index}/{total_files}: "
                                        f"{filename} ({file_pct}%)"
                                    )
                                else:
                                    mb = downloaded / (1024 * 1024)
                                    task.message = (
                                        f"Downloading {file_index}/{total_files}: "
                                        f"{filename} ({mb:.1f} MB)"
                                    )

            os.replace(tmp_path, filepath)

            if task:
                task.current_file = file_index
                task.progress = file_index / total_files * 100
                task.message = f"Done: {filename} ({file_index}/{total_files})"

            return "downloaded", filename

        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if task:
                task.message = (
                    f"Failed: {filename} ({file_index}/{total_files}) - "
                    f"{str(e)[:200]}"
                )
            return "failed", filename

    async def download_multiple(
        self,
        files: list[dict],
        task: Task,
    ) -> dict[str, list[str]]:
        """Download a list of files sequentially with progress.

        Each entry in files: {"url": str, "dest_dir": str, "filename"?: str, "headers"?: dict}
        Returns {"downloaded": [...], "skipped": [...], "failed": [...]}.
        """
        task.status = TaskStatus.RUNNING
        task.total_files = len(files)
        task.progress = 0

        results: dict[str, list[str]] = {
            "downloaded": [],
            "skipped": [],
            "failed": [],
        }

        for idx, entry in enumerate(files, 1):
            status, fname = await self.download_file(
                url=entry["url"],
                dest_dir=entry["dest_dir"],
                custom_filename=entry.get("filename"),
                headers=entry.get("headers"),
                task=task,
                file_index=idx,
                total_files=len(files),
            )
            results[status].append(fname)

        summary = []
        if results["downloaded"]:
            summary.append(f"Downloaded: {len(results['downloaded'])}")
        if results["skipped"]:
            summary.append(f"Skipped (exist): {len(results['skipped'])}")
        if results["failed"]:
            summary.append(f"Failed: {len(results['failed'])}")

        task.progress = 100
        task.message = " | ".join(summary)
        task.status = TaskStatus.ERROR if results["failed"] else TaskStatus.COMPLETED
        task.finished_at = time.time()

        return results


def unzip_and_remove(zip_path: str, extract_to: str) -> list[str]:
    """Extract a zip to extract_to (flat, no subdirs) and delete the archive."""
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            basename = os.path.basename(member)
            if not basename:
                continue
            target = os.path.join(extract_to, basename)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            extracted.append(basename)
    os.remove(zip_path)
    return extracted


def _inject_civitai_token(url: str) -> str:
    """Append CivitAI API token to the URL if it's a CivitAI link and the token is set."""
    if CIVITAI_API_KEY and "civitai" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}token={CIVITAI_API_KEY}"
    return url


def _filename_from_url(url: str) -> str:
    name = os.path.basename(url.split("?")[0])
    return name if name else "downloaded_file"


def _filename_from_content_disposition(cd: str) -> str | None:
    if not cd:
        return None
    import urllib.parse

    utf8 = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if utf8:
        return urllib.parse.unquote(utf8.group(1))
    match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', cd)
    if match:
        return match.group(1).strip("'\"")
    return None


download_manager = DownloadManager()
