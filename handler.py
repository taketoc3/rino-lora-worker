#!/usr/bin/env python3
"""Serverless handler for the Rino LoRA small test.

Volume layout: in serverless the network volume mounts at /runpod-volume,
while the pipeline (boot.sh and friends) hardcodes /workspace. At import
time we bridge the pipeline's directories into /workspace as symlinks, so
everything the pipeline writes (logs, models, datasets, outputs, and the
runpod/ scripts themselves) lands on the volume and survives the worker.

Modes (job input {"mode": ...}):
- "probe": report GPU + volume layout + ComfyUI reachability, write nothing.
- "full" (default): run /workspace/runpod/boot.sh (the volume's boot_mode
  decides; currently "full": post_start -> setup -> train -> gen_test) and
  return the tail of logs/ATTEMPT2_STATUS.
"""
import os
import subprocess
import urllib.request

VOL = "/runpod-volume"
WS = "/workspace"
BRIDGED = ["runpod", "logs", "models", "datasets", "outputs"]


def _bridge_volume():
    os.makedirs(WS, exist_ok=True)
    for name in BRIDGED:
        src = os.path.join(VOL, name)
        dst = os.path.join(WS, name)
        if os.path.isdir(src) and not os.path.islink(dst) and not os.path.exists(dst):
            try:
                os.symlink(src, dst)
            except OSError:
                pass


_bridge_volume()

import runpod  # noqa: E402


def _tail(path, n=800):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()[-n:]
    except Exception as e:  # noqa: BLE001
        return f"<no file: {e}>"


def _comfy_ready():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def handler(job):
    mode = (job.get("input") or {}).get("mode", "full")
    if mode == "probe":
        out = subprocess.run(
            ["bash", "-c",
             "nvidia-smi -L; echo ---vol---; ls /runpod-volume; echo ---ws---; "
             "ls /workspace; echo ---runpod---; ls /workspace/runpod; echo ---; "
             "cat /workspace/runpod/boot_mode.txt"],
            capture_output=True, text=True, timeout=180)
        return {"mode": "probe", "rc": out.returncode, "comfy_ready": _comfy_ready(),
                "stdout": out.stdout[-1500:], "stderr": out.stderr[-400:]}
    p = subprocess.run(["bash", "/workspace/runpod/boot.sh"],
                       capture_output=True, text=True)
    return {"mode": "full", "rc": p.returncode,
            "attempt2_status": _tail("/workspace/logs/ATTEMPT2_STATUS"),
            "stdout_tail": p.stdout[-400:], "stderr_tail": p.stderr[-400:]}


runpod.serverless.start({"handler": handler})
