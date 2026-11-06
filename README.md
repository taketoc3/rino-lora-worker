# rino-lora-worker

RunPod Serverless worker image for the Rino face-LoRA small test.

- Base: `runpod/comfyui` (torch + ComfyUI preinstalled), same as the pod route.
- The image's `/start.sh` runs in the background (stages ComfyUI, serves :8188);
  the RunPod serverless handler (`handler.py`) is the main process.
- The handler bridges the network volume (`/runpod-volume`) into `/workspace`
  and runs the pipeline staged on the volume (`runpod/boot.sh`).
- Built by GitHub Actions and published to GHCR on every push to `main`.
- No secrets, datasets, or models in this repo or image — all data stays on
  the RunPod network volume.
