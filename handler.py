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
        # Create the directory on the volume first if missing: without this,
        # the pipeline's own mkdir would create a container-local directory
        # and its outputs (models, test images, logs) would die with the
        # worker instead of persisting on the volume.
        try:
            os.makedirs(src, exist_ok=True)
        except OSError:
            pass
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


def _comfy_dir():
    for cand in ("/opt/ComfyUI", "/workspace/runpod-slim/ComfyUI",
                 "/workspace/apps/ComfyUI"):
        if os.path.isdir(cand):
            return cand
    return None


def _ensure_comfy(wait_s=150):
    """Make sure ComfyUI answers on :8188 before the pipeline needs it.

    The image's background /start.sh may or may not bring ComfyUI up inside
    a serverless worker; post_start.sh would start it with the system
    python, which is unproven for this image. So: wait a bit for an
    existing instance, else start it the way the image does (its venv
    python), logging to the volume so failures stay diagnosable.
    Returns (ready: bool, how: str).
    """
    import time
    if _comfy_ready():
        return True, "already-running"
    waited = 0
    while waited < 45 and not _comfy_ready():
        time.sleep(5)
        waited += 5
    if _comfy_ready():
        return True, f"came-up-after-{waited}s"
    cdir = _comfy_dir()
    if not cdir:
        return False, "no-comfyui-dir"
    venv_py = os.path.join(cdir, ".venv-cu128", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else "python3"
    os.makedirs("/workspace/outputs/comfy", exist_ok=True)
    os.makedirs("/workspace/inputs", exist_ok=True)
    os.makedirs("/workspace/logs", exist_ok=True)
    logf = open("/workspace/logs/comfyui_handler.log", "ab")
    subprocess.Popen(
        [py, "main.py", "--listen", "0.0.0.0", "--port", "8188",
         "--output-directory", "/workspace/outputs/comfy",
         "--input-directory", "/workspace/inputs"],
        cwd=cdir, stdout=logf, stderr=subprocess.STDOUT)
    waited = 0
    while waited < wait_s and not _comfy_ready():
        time.sleep(5)
        waited += 5
    return _comfy_ready(), f"started-with-{py}-waited-{waited}s"


def handler(job):
    mode = (job.get("input") or {}).get("mode", "full")
    if mode == "probe":
        # Give the background /start.sh time to bring ComfyUI up; report
        # whether it ever answered, so a dead ComfyUI is visible pre-flight.
        import time
        waited = 0
        while not _comfy_ready() and waited < 90:
            time.sleep(5)
            waited += 5
        out = subprocess.run(
            ["bash", "-c",
             "nvidia-smi -L; echo ---vol---; ls /runpod-volume; echo ---ws---; "
             "ls /workspace; echo ---runpod---; ls /workspace/runpod; echo ---; "
             "cat /workspace/runpod/boot_mode.txt"],
            capture_output=True, text=True, timeout=180)
        return {"mode": "probe", "rc": out.returncode, "comfy_ready": _comfy_ready(),
                "comfy_waited_s": waited,
                "stdout": out.stdout[-1500:], "stderr": out.stderr[-400:]}
    if mode == "logs":
        files = ["boot.log", "post_start.log", "comfyui.log",
                 "comfyui_handler.log", "attempt2.log", "train.log"]
        return {"mode": "logs",
                "attempt2_status": _tail("/workspace/logs/ATTEMPT2_STATUS"),
                "logs": {f: _tail(f"/workspace/logs/{f}", 1200) for f in files}}
    ready, how = _ensure_comfy()
    p = subprocess.run(["bash", "/workspace/runpod/boot.sh"],
                       capture_output=True, text=True)
    return {"mode": "full", "rc": p.returncode, "comfy_ready": ready,
            "comfy_how": how,
            "attempt2_status": _tail("/workspace/logs/ATTEMPT2_STATUS"),
            "stdout_tail": p.stdout[-400:], "stderr_tail": p.stderr[-400:]}


runpod.serverless.start({"handler": handler})
