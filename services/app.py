"""FastAPI entry point: mounts all routers and serves the landing page."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from services.routers import presets, models, civitai, outputs

app = FastAPI(title="ComfyUI Services", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(presets.router)
app.include_router(models.router)
app.include_router(civitai.router)
app.include_router(outputs.router)


@app.get("/", response_class=HTMLResponse)
async def landing():
    with open(Path(__file__).resolve().parent / "templates" / "index.html") as f:
        return HTMLResponse(f.read())


@app.get("/health")
async def health():
    return {"status": "ok"}
