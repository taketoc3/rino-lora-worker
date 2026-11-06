#!/usr/bin/env bash
# entry.sh — container entrypoint for the serverless worker.
# 1. The base image's /start.sh in the background: copies ComfyUI to
#    /workspace/runpod-slim and starts ComfyUI (:8188) + aux services.
# 2. The RunPod serverless handler as the main process (PID kept alive by
#    exec, so the worker lives and dies with the handler).
/start.sh &
exec python3 -u /handler.py
