<!-- Do not edit or remove this section -->
This document exists for non-obvious, error-prone shortcomings in the codebase, the model, or the tooling that an agent cannot figure out by reading the code alone.

---

## Fork of runpod-workers/comfyui-base

This repo is a fork of [runpod-workers/comfyui-base](https://github.com/runpod-workers/comfyui-base). Fork-only additions: `services/` (web UI on :8081), `serverless/`, `scripts/download_models.sh`, and seven extra baked custom nodes. When merging upstream, keep these in sync:

- The baked custom node list lives in four places: Dockerfile download + `git init` blocks, Dockerfile bundle manifest (`.runpod-bundle-version`), `BAKED_NODES` in `start.sh`, and `NODES` in `scripts/fetch-hashes.sh`. SHAs live in `docker-bake.hcl`.
- Upstream CI runs on Blacksmith runners and publishes `runpod/comfyui`; the fork uses `ubuntu-latest` and `bodasooqa/runpod-comfyui-starter`.
- Upstream Runpod template IDs (`cw3nka7d08`, `2lv7ev3wfp`) belong to runpod-workers, not this fork.
