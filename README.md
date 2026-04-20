[![Watch the video](https://i3.ytimg.com/vi/JovhfHhxqdM/hqdefault.jpg)](https://www.youtube.com/watch?v=JovhfHhxqdM)

Run the latest ComfyUI. All dependencies are pre-installed in the image. On first boot, ComfyUI is copied to your workspace — when you see `[ComfyUI-Manager] All startup tasks have been completed.` in the logs, it's ready to use.

## Access

- `8188`: ComfyUI web UI
- `8080`: FileBrowser (admin / qwerty123)
- `8081`: Web Services — preset downloader, HuggingFace model downloader, CivitAI LoRA downloader, outputs browser
- `8888`: JupyterLab (token via `JUPYTER_PASSWORD`, root at `/workspace`)
- `22`: SSH (set `PUBLIC_KEY` or check logs for generated root password)

## Pre-installed custom nodes

- ComfyUI-Manager
- ComfyUI-KJNodes
- Civicomfy
- ComfyUI-RunpodDirect

## Source Code

This is an open source template. Source code available at: [github.com/bodasooqa/runpod-comfyui-starter](https://github.com/bodasooqa/runpod-comfyui-starter)

## Environment Variables

- `JUPYTER_PASSWORD`: Token for JupyterLab access
- `PUBLIC_KEY`: SSH public key for root login (otherwise a random password is generated)
- `PRESET_DOWNLOAD`: Comma-separated preset names to download at boot (e.g. `Z_IMAGE`). Presets are defined in `/opt/services/presets.json`.
- `CIVITAI_API_KEY`: CivitAI API token — required for downloading models from CivitAI. Get yours at civitai.com/user/account.
- `RUNPOD_SERVERLESS`: Set to `1` to run in serverless mode (skips pod-only services, starts the runpod handler instead).

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
