# ComfyUI Slim – Developer Conventions

This document outlines how to work in this repository from a developer point of view: build targets, runtime behavior, environment, dependency management, customization points, quality gates, and troubleshooting.

## Stack Overview

- **Base OS**: Ubuntu 24.04
- **GPU stack**:
  - Regular image: CUDA 12.8, PyTorch (pinned version via docker-bake.hcl, cu128 wheels)
  - CUDA 13 image (Blackwell / RTX 5090, B200): CUDA 13.0, PyTorch (pinned version, cu130 wheels)
- **Python**: 3.12 (set as system default inside the image)
- **Package manager**: pip + pip-tools (lock file generated at build time with `pip-compile --generate-hashes`)
- **Tools bundled**: FileBrowser (port 8080), JupyterLab (port 8888), Web Services (port 8081), OpenSSH server (port 22), FFmpeg (NVENC), common CLI tools
- **Primary app**: ComfyUI, with pre-installed custom nodes

## Repository Layout

- `Dockerfile` – Single Dockerfile for all variants (CUDA version controlled via build args)
- `start.sh` – Runtime bootstrap (shared by all variants)
- `docker-bake.hcl` – Buildx bake targets (`regular`, `cuda13`, `dev`, `devpush`, `devpush-cuda13`) and all version pins (single source of truth)
- `scripts/fetch-hashes.sh` – Fetches latest custom node commit hashes from GitHub
- `scripts/download_models.sh` – CLI preset downloader, reads from `services/presets.json`
- `scripts/prebake-manager-cache.py` – Pre-populates the ComfyUI-Manager registry cache at build time
- `services/` – FastAPI web services (preset/model/CivitAI downloader, outputs browser)
- `serverless/` – Runpod serverless handler (`handler.py`) and the API-format workflow it runs (`workflow_api.json`)
- `tests/` – Runpod smoke and functional tests (see `tests/README.md`)
- `.github/workflows/` – `dev.yml` (manual dev build), `release.yml` (tagged release), `check-incompatibilities.yml` (GPU matrix check)
- `README.md` / `README_CUDA13.md` – User-facing overviews for the CUDA 12.8 and CUDA 13 images
- `AGENTS.md` – Non-obvious gotchas (fork sync notes)
- `docs/context.md` – This document

At runtime, the container uses:

- `/workspace/runpod-slim/ComfyUI` – ComfyUI checkout and virtual environment
- `/workspace/runpod-slim/comfyui_args.txt` – Optional line-delimited ComfyUI args
- `/workspace/runpod-slim/filebrowser.db` – FileBrowser DB

## Build Targets

Use Docker Buildx Bake with the provided HCL file.

- `regular` (default production):
  - CUDA 12.8, PyTorch cu128
  - Tags: `bodasooqa/runpod-comfyui-starter:${TAG}-cuda12.8`, `:cuda12.8`, `:latest`
  - Platform: `linux/amd64`
- `cuda13` (Blackwell / RTX 5090, B200):
  - CUDA 13.0, PyTorch cu130
  - Tags: `bodasooqa/runpod-comfyui-starter:${TAG}-cuda13.0`, `:cuda13.0`
- `dev` (local testing):
  - Same as regular, output: local docker image (not pushed)
  - Tag: `bodasooqa/runpod-comfyui-starter:dev`
- `devpush` / `devpush-cuda13` (CI dev builds):
  - Push `:dev-cuda12.8` / `:dev-cuda13.0` without touching `latest`

Example commands:

```bash
# Build default regular target
docker buildx bake -f docker-bake.hcl regular

# Build dev image locally
docker buildx bake -f docker-bake.hcl dev

# Build CUDA 13 variant
docker buildx bake -f docker-bake.hcl cuda13
```

Build args and env:

- `TAG` variable in `docker-bake.hcl` controls the tag suffix (default `slim`).
- Build uses BuildKit inline cache.

## Runtime Behavior

Startup is handled by `start.sh` (shared by all variants):

- If `RUNPOD_SERVERLESS=1`: refreshes the workspace bundle, starts ComfyUI in the background and `exec`s `/opt/handler.py` (waits for ComfyUI, then `runpod.serverless.start`). Everything below is skipped.
- Exports `PIP_CONSTRAINT=/opt/comfyui-runtime-constraints.txt` so runtime pip installs cannot replace the CUDA-matched torch stack.
- Initializes SSH server. If `PUBLIC_KEY` is set, it is added to `~/.ssh/authorized_keys`; otherwise a random root password is generated and printed to logs.
- Exports selected env vars broadly to `/etc/environment`, PAM, and `~/.ssh/environment` for non-interactive shells.
- Initializes and starts FileBrowser on port 8080 (root `/workspace`). Default admin user is created on first run with password `FILEBROWSER_PASSWORD` (default `qwerty123`).
- Starts JupyterLab on port 8888, root at `/workspace`. Token set via `JUPYTER_PASSWORD` if provided.
- Starts web services on port 8081 (FastAPI app: preset downloader, HF model downloader, CivitAI LoRA downloader, outputs browser).
- If `PRESET_DOWNLOAD` env var is set, runs `download_models.sh` to fetch model presets before starting ComfyUI.
- Ensures `comfyui_args.txt` exists.
- If the workspace bundle manifest (`.runpod-bundle-version`) differs from the image, rsyncs ComfyUI core and the image-managed custom nodes from `/opt/comfyui-baked` (models, input, output, user, venvs, user-installed nodes are preserved).
- Migrates a legacy CUDA 12.4 `.venv` to `.venv-cu128` (one-time, the only place `start.sh` runs pip installs).
- On first boot: copies baked ComfyUI and custom nodes from `/opt/comfyui-baked` to `/workspace/runpod-slim/ComfyUI/`, then creates a Python 3.12 venv with `--system-site-packages`.
- On subsequent boots: activates existing venv (no network calls).
- Warms up pip (ComfyUI-Manager has a 5s timeout) and logs CUDA / venv diagnostics (torch build vs image, locally installed CUDA-sensitive packages).
- If `PRESET_DOWNLOAD` is set, downloads model presets.
- Starts ComfyUI with fixed args `--listen 0.0.0.0 --port 8188 --enable-cors-header` plus any custom args from `comfyui_args.txt`, then `wait`s on it. If ComfyUI crashes, the container stays alive (`sleep infinity`) so SSH/Jupyter remain usable. Logs go to container stdout.

## Ports

- 8188 – ComfyUI
- 8080 – FileBrowser
- 8081 – Web Services (preset/model downloader, CivitAI LoRA, outputs browser)
- 8888 – JupyterLab
- 22 – SSH

Expose settings are declared in Dockerfiles.

## Environment Variables

Recognized at runtime by the start scripts:

- `PUBLIC_KEY` – If provided, enables key-based SSH for root; otherwise a random password is generated and printed.
- `JUPYTER_PASSWORD` – If set, used as the JupyterLab token (no browser; root at `/workspace`).
- `FILEBROWSER_PASSWORD` – FileBrowser admin password, applied only when the FileBrowser DB is first created (default `qwerty123`).
- `CIVITAI_API_KEY` – Default CivitAI token for the web services.
- `RUNPOD_SERVERLESS` – `1` switches to serverless mode (no SSH/FileBrowser/Jupyter/web services).
- `PRESET_DOWNLOAD` – Comma-separated preset names (e.g. `Z_IMAGE`). If set, `download_models.sh` runs at boot before ComfyUI starts. Presets are defined in `/opt/services/presets.json`.
- GPU/CUDA-related environment variables are propagated (`CUDA*`, `LD_LIBRARY_PATH`, `PYTHONPATH`, and `RUNPOD_*` vars if present in the environment).

## Dependency Management

- Python 3.12 is the default interpreter in the image.
- Venv location:
  - Both images: `/workspace/runpod-slim/ComfyUI/.venv-cu128`
- All dependencies are pre-installed at image build time. No pip installs occur at runtime.
- **Version pins live in `docker-bake.hcl`** (single source of truth, not in the Dockerfiles). Dockerfiles declare `ARG` names but the default values are set in the bake file:
  - `COMFYUI_VERSION` — ComfyUI release tag
  - `MANAGER_SHA`, `KJNODES_SHA`, `CIVICOMFY_SHA`, `RUNPODDIRECT_SHA`, `EFFICIENCY_SHA`, `RGTHREE_SHA`, `IMPACT_SHA`, `IMPACT_SUBPACK_SHA`, `CRT_SHA`, `INPAINT_SHA`, `TBGSAM3_SHA` — custom node commit hashes
  - `TORCH_VERSION`, `TORCHVISION_VERSION`, `TORCHAUDIO_VERSION` — PyTorch stack versions with local build suffix (e.g. `2.10.0+cu128`, regular image)
  - `TORCH_VERSION_5090`, `TORCHVISION_VERSION_5090`, `TORCHAUDIO_VERSION_5090` — PyTorch stack versions for the CUDA 13 image (e.g. `2.10.0+cu130`, can diverge)
  - `CUDA_VERSION_DASH` — CUDA toolkit apt package suffix (e.g., `12-8`, `13-0`)
  - `TORCH_INDEX_SUFFIX` — PyTorch wheel index (e.g., `cu128`, `cu130`)
  - `FILEBROWSER_VERSION` + `FILEBROWSER_SHA256` — FileBrowser binary with checksum
- To update a version: edit the corresponding `variable` block in `docker-bake.hcl`.
- CI or ad-hoc builds can override any variable via environment variables:
  ```bash
  COMFYUI_VERSION=v0.30.0 docker buildx bake regular
  ```
- `scripts/fetch-hashes.sh` queries the GitHub API for the latest commit hash of each custom node repo and prints HCL-formatted variable blocks ready to copy-paste into `docker-bake.hcl`. Set `GITHUB_TOKEN` env var for authenticated requests (higher API rate limit).
- Source code is downloaded as zip archives from GitHub (no git clone in build or runtime).
- A lock file with SHA256 hashes is generated inside the builder stage using `pip-compile --generate-hashes`. Torch pins from custom-node requirements are stripped and replaced with the bake pins; the build fails if the installed torch/torchvision/torchaudio versions don't match.
- PyTorch wheel index is controlled by `TORCH_INDEX_SUFFIX` build arg (`cu128` for regular, `cu130` for CUDA 13).
- The runtime image writes `/opt/comfyui-runtime-constraints.txt` from the same PyTorch pins and `start.sh` exports it as `PIP_CONSTRAINT`, so legacy venv migration and ComfyUI-Manager dependency installs cannot silently replace the CUDA-matched torch stack.
- At runtime, baked ComfyUI is copied from `/opt/comfyui-baked` to `/workspace/runpod-slim/ComfyUI/` on first boot. On later boots, a bundle manifest detects image upgrades and refreshes ComfyUI core plus the image-managed custom nodes (`BAKED_NODES` in `start.sh`). Models, inputs, outputs, user settings, virtual environments, and user-installed custom nodes are preserved.

Preinstalled custom nodes:

- `ComfyUI-Manager` (ltdrdata)
- `ComfyUI-KJNodes` (kijai)
- `Civicomfy` (MoonGoblinDev)
- `ComfyUI-RunpodDirect` (MadiatorLabs)
- `efficiency-nodes-comfyui` (LucianoCirino)
- `rgthree-comfy` (rgthree)
- `ComfyUI-Impact-Pack` (ltdrdata)
- `ComfyUI-Impact-Subpack` (ltdrdata)
- `CRT-Nodes` (PGCRT)
- `ComfyUI-Inpaint-CropAndStitch` (lquesada)
- `ComfyUI-TBG-SAM3` (Ltamann)

## Customization Points

- `comfyui_args.txt` – Add one CLI arg per line; comments starting with `#` are ignored. These are appended after fixed args.
- `services/presets.json` – Define model presets for the web downloader and `download_models.sh`. Ships empty; see the `_example` key for format.
- Add/remove baked custom nodes in all of: Dockerfile download + `git init` blocks and ARGs, the Dockerfile bundle manifest, `docker-bake.hcl` (variable + `common.args`), `BAKED_NODES` in `start.sh`, and `NODES` in `scripts/fetch-hashes.sh`.
- `serverless/workflow_api.json` – Swap in another API-format workflow; update the node IDs at the top of `serverless/handler.py` (`POSITIVE_PROMPT_NODE`, `BATCH_SIZE_NODE`, `MAIN_SAMPLER_NODE`, `OUTPUT_NODE`).
- Additional system packages: modify the Dockerfile `apt-get install` lines.
- Users can install additional custom nodes at runtime via ComfyUI-Manager (user's responsibility, not baked).

## Web Services (`/opt/services`)

A single FastAPI application on port 8081 provides four sub-services:

- `/presets` – Download pre-configured model bundles defined in `presets.json`.
- `/models` – Download models from HuggingFace by direct URL or repo name (supports API tokens for gated models).
- `/civitai` – Download LoRA from CivitAI with API token. Auto-unzips `.zip` downloads.
- `/outputs` – Browse and download files from ComfyUI's output directory.

All downloads are async with real-time progress tracking via polling. Completed tasks auto-expire from memory after 1 hour.

## Dev Conventions

- Keep images lean. All Python dependencies are baked at build time via lock file.
- To update a dependency: bump the relevant variable in `docker-bake.hcl`, push, trigger build.
- Source archives are used instead of `git clone` — no git dependency in builds.
- Avoid changing ports; they are referenced by external templates (RunPod/UI tooling).
- Use Python 3.12. Do not downgrade in scripts.
- When adding new env vars needed by downstream processes, ensure they are exported in `export_env_vars()` the same way as others.
- Shell scripting: keep `set -e` at top; prefer explicit guards; write idempotent steps safe to re-run.
- Runtime `start.sh` must NEVER call pip, git clone, or execute arbitrary install scripts (the legacy CUDA 12.4 venv migration is the only exception). All dependencies are baked in the image.

## Local Development Tips

- Use the `dev` target to build a locally loadable image without pushing:
  ```bash
  docker buildx bake -f docker-bake.hcl dev
  docker run --rm -p 8188:8188 -p 8080:8080 -p 8081:8081 -p 8888:8888 -p 2222:22 \
    -e PUBLIC_KEY="$(cat ~/.ssh/id_rsa.pub)" \
    -e JUPYTER_PASSWORD=yourtoken \
    -v "$PWD/workspace":/workspace \
    bodasooqa/runpod-comfyui-starter:dev
  ```
- Mount a host `workspace` to persist ComfyUI, args, and FileBrowser DB.

## Troubleshooting

- ComfyUI not reachable on 8188:
  - Check container logs (ComfyUI runs in foreground, logs go to stdout).
  - Ensure `comfyui_args.txt` doesn't contain invalid flags (comments with `#` are okay).
- JupyterLab auth:
  - If `JUPYTER_PASSWORD` is unset, Jupyter may allow tokenless or default behavior. Set it explicitly if needed.
- SSH access:
  - If no `PUBLIC_KEY` is provided, a random root password is generated and printed to stdout. Check container logs.
  - Ensure port 22 is mapped from the host, e.g., `-p 2222:22`.
- GPU/torch issues:
  - Check the "CUDA / venv diagnostics" block in the logs: a `CUDA_MISMATCH` or `LOCAL_TORCH` warning means a torch build was installed into the persistent venv and overrides the image stack.
  - Blackwell GPUs (RTX 5090, B200) need the `cuda13.0` tag; confirm the host driver supports CUDA 13.0 (driver 580+).

## Release & Tagging

- Default tag base is `slim` via `TAG` in `docker-bake.hcl`; `release.yml` sets `TAG` to the release version.
- Pushing a `v*` tag (or a manual dispatch) builds and pushes both images, optionally smoke-tests them, then creates the GitHub Release.
- Smoke/functional tests start real GPU pods on Runpod. They run only when the repo variable `RUN_SMOKE_TESTS=true` and secrets `TESTING_RUNPOD_API_KEY` / `TESTING_RUNPOD_SSH_PRIVATE_KEY` are set.
- Keep `README.md` and `README_CUDA13.md` ports and features in sync when changing defaults.

## License

- GPLv3 as per `LICENSE`.
