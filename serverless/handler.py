"""Runpod serverless handler for ComfyUI image generation.

Input:
  {"prompt": "your positive prompt text", "batch_size": 1}

Output:
  {"images": ["<base64-encoded PNG>", ...]}
  {"error": "message"} on failure
"""

import base64
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import runpod

COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = "/opt/workflow_api.json"

# Node IDs from your workflow (CLIPTextEncode positive prompt and SaveImage output)
POSITIVE_PROMPT_NODE = "4"
BATCH_SIZE_NODE = "11"    # EmptyFlux2LatentImage
MAIN_SAMPLER_NODE = "154" # KSampler (Efficient) — main generation step
OUTPUT_NODE = "22"        # SaveImage

MAX_SEED = 2**32 - 1


# ---------------------------------------------------------------------------
# ComfyUI helpers
# ---------------------------------------------------------------------------

def wait_for_comfyui(timeout: int = 120) -> bool:
    """Block until ComfyUI is accepting requests, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
            print("[handler] ComfyUI is ready")
            return True
        except Exception:
            time.sleep(2)
    return False


def queue_prompt(workflow: dict, client_id: str) -> str:
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    if "error" in data:
        raise RuntimeError(f"ComfyUI rejected prompt: {data['error']}")
    return data["prompt_id"]


def poll_until_done(prompt_id: str, timeout: int = 600) -> dict:
    """Poll /history until the prompt finishes, then return its output dict."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"{COMFYUI_URL}/history/{urllib.parse.quote(prompt_id)}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")


def fetch_image_b64(filename: str, subfolder: str, folder_type: str) -> str:
    params = urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": folder_type}
    )
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}") as resp:
        return base64.b64encode(resp.read()).decode()


# ---------------------------------------------------------------------------
# Runpod handler
# ---------------------------------------------------------------------------

def handler(job: dict) -> dict:
    job_input = job.get("input", {})

    prompt_text = job_input.get("prompt")
    if not prompt_text:
        return {"error": "Missing required field: 'prompt'"}

    batch_size = int(job_input.get("batch_size", 1))

    with open(WORKFLOW_PATH) as f:
        workflow = json.load(f)

    # Inject positive prompt
    workflow[POSITIVE_PROMPT_NODE]["inputs"]["text"] = prompt_text

    # Randomize main generation seed (fixed seed = same image every time)
    seed = job_input.get("seed", random.randint(0, MAX_SEED))
    if MAIN_SAMPLER_NODE in workflow:
        workflow[MAIN_SAMPLER_NODE]["inputs"]["seed"] = seed

    # Override batch size (default in workflow is 4 — expensive for serverless)
    if BATCH_SIZE_NODE in workflow:
        workflow[BATCH_SIZE_NODE]["inputs"]["batch_size"] = batch_size

    client_id = str(uuid.uuid4())

    try:
        prompt_id = queue_prompt(workflow, client_id)
        print(f"[handler] queued prompt_id={prompt_id}")

        result = poll_until_done(prompt_id)

        node_output = result.get("outputs", {}).get(OUTPUT_NODE, {})
        images = node_output.get("images", [])
        if not images:
            return {
                "error": "No images in output — check OUTPUT_NODE id",
                "outputs": list(result.get("outputs", {}).keys()),
            }

        return {
            "images": [
                fetch_image_b64(img["filename"], img["subfolder"], img["type"])
                for img in images
            ],
            "seed": seed,
        }

    except TimeoutError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Entry point — ComfyUI must already be running before this is called
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not wait_for_comfyui(timeout=120):
        raise RuntimeError("ComfyUI did not become ready within 120 s")

    runpod.serverless.start({"handler": handler})
