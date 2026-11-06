# Rino LoRA test — RunPod Serverless worker image.
# Same base as the pod route (torch + ComfyUI preinstalled); the only change
# is the entrypoint: the image's own /start.sh runs in the background
# (it stages ComfyUI into /workspace/runpod-slim and serves it on :8188,
# which gen_test.py drives), while the serverless handler is the main process.
FROM runpod/comfyui:2.0.0-rc.194-comfyuiv0.35.0-cuda12.8

RUN pip install --no-cache-dir "runpod==1.7.13"

COPY handler.py /handler.py
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh

ENTRYPOINT ["/bin/bash", "/entry.sh"]
