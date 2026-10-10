[![Watch the video](https://i3.ytimg.com/vi/JovhfHhxqdM/hqdefault.jpg)](https://www.youtube.com/watch?v=JovhfHhxqdM)

Run the latest ComfyUI with CUDA 12.8. All dependencies are pre-installed in the image. On first boot, ComfyUI is copied to your workspace — when you see `[ComfyUI-Manager] All startup tasks have been completed.` in the logs, it's ready to use.

> **This image is for CUDA 12 only.** It does not support CUDA 13 (Blackwell / RTX 5090).
> For CUDA 13, use the `bodasooqa/runpod-comfyui-starter:cuda13.0` image (see `README_CUDA13.md`).

## Upgrading from a previous version

When the image is updated, ComfyUI and the bundled custom nodes in your workspace are refreshed to the versions pinned by the image on the next boot. Models, inputs, outputs, user settings, and user-installed custom nodes are preserved. Pods created with the old CUDA 12.4 template get a one-time virtual environment migration, which may take a few extra minutes.

## Access

- `8188`: ComfyUI web UI
- `8080`: FileBrowser (admin / `FILEBROWSER_PASSWORD`, default: `qwerty123`)
- `8081`: Web Services — preset downloader, HuggingFace model downloader, CivitAI LoRA downloader, outputs browser
- `8888`: JupyterLab (token via `JUPYTER_PASSWORD`, root at `/workspace`)
- `22`: SSH (set `PUBLIC_KEY` or check logs for generated root password)

## Pre-installed custom nodes

- ComfyUI-Manager
- ComfyUI-KJNodes
- Civicomfy
- ComfyUI-RunpodDirect
- efficiency-nodes-comfyui
- rgthree-comfy
- ComfyUI-Impact-Pack
- ComfyUI-Impact-Subpack
- CRT-Nodes
- ComfyUI-Inpaint-CropAndStitch
- ComfyUI-TBG-SAM3

## Source Code

This is an open source template. Source code available at: [github.com/bodasooqa/runpod-comfyui-starter](https://github.com/bodasooqa/runpod-comfyui-starter)

## Environment Variables

- `JUPYTER_PASSWORD`: Token for JupyterLab access
- `PUBLIC_KEY`: SSH public key for root login (otherwise a random password is generated)
- `FILEBROWSER_PASSWORD`: FileBrowser admin password, applied on first boot only (default: `qwerty123`)
- `PRESET_DOWNLOAD`: Comma-separated preset names to download at boot (e.g. `Z_IMAGE`). Presets are defined in `/opt/services/presets.json`.
- `CIVITAI_API_KEY`: CivitAI API token — required for downloading models from CivitAI. Get yours at civitai.com/user/account.
- `RUNPOD_SERVERLESS`: Set to `1` to run in serverless mode (skips pod-only services, starts the runpod handler instead).

## Serverless Mode

With `RUNPOD_SERVERLESS=1` the container starts only ComfyUI and the handler from `serverless/handler.py`, which runs the bundled `serverless/workflow_api.json`. The models it references must be present in the workspace (e.g. on a network volume).

Input:

```json
{"input": {"prompt": "a cat in a spacesuit", "batch_size": 1, "seed": 42}}
```

Output: `{"images": ["<base64 PNG>", ...], "seed": 42}`, or `{"error": "..."}` on failure. `batch_size` defaults to 1, `seed` is random when omitted.

## Custom Arguments

Edit `/workspace/runpod-slim/comfyui_args.txt` (one arg per line):

```
--max-batch-size 8
--preview-method auto
```

## Directory Structure

- `/workspace/runpod-slim/ComfyUI`: ComfyUI install
- `/workspace/runpod-slim/comfyui_args.txt`: ComfyUI args
- `/workspace/runpod-slim/filebrowser.db`: FileBrowser DB
