# -*- coding: utf-8 -*-
"""One-click installer for the Laya chat advisor.

Run by install.bat (Windows, Python 3.10-3.12). Fully automatic:
venv -> pip deps (CUDA torch first, CN mirrors) -> model download (hf-mirror)
-> API key prompt -> config files -> desktop-style start script.
Re-running is safe: finished steps are skipped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"
PROJ = ROOT / "jev-chat-windows"
TORCH_INDEX = "https://download.pytorch.org/whl/cu121"
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
LAYER_PORT = "8199"

STEP = 0


def step(msg: str) -> None:
    global STEP
    STEP += 1
    print(f"\n===== [{STEP}] {msg} =====", flush=True)


def run(cmd: list, env: dict | None = None, check: bool = True) -> int:
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(cmd, env=e)
    if check and r.returncode != 0:
        print(f"[ERROR] command failed: {' '.join(map(str, cmd))}", file=sys.stderr)
        sys.exit(r.returncode)
    return r.returncode


def pip(args: list, extra: list | None = None) -> None:
    run([PY, "-m", "pip", "install", "--quiet", *args, *(extra or [])])


def main() -> None:
    # ---- 1. venv ----
    step("Create virtual environment")
    if not (PY.exists()):
        venv.create(ROOT / ".venv", with_pip=True)
        print("venv created.")
    else:
        print("venv already exists, skip.")
    run([PY, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], extra=["-i", PYPI_MIRROR])

    # ---- 2. torch (CUDA) ----
    step("Install PyTorch (CUDA 12.1, ~2.5GB download)")
    r = run([PY, "-c", "import torch; assert torch.cuda.is_available()"], check=False)
    if r == 0:
        print("torch with CUDA already installed, skip.")
    else:
        pip(["torch"], extra=["--index-url", TORCH_INDEX])
        r = run([PY, "-c", "import torch; assert torch.cuda.is_available()"], check=False)
        if r != 0:
            print("[WARN] CUDA torch failed (no NVIDIA driver?). Falling back to CPU torch.")
            pip(["torch"], extra=["-i", PYPI_MIRROR, "--force-reinstall"])

    # ---- 3. other deps ----
    step("Install app dependencies (OCR / GUI / SDKs)")
    req = (PROJ / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pkgs = [ln.strip() for ln in req
            if ln.strip() and not ln.strip().startswith("#")]
    pip(pkgs, extra=["-i", PYPI_MIRROR])
    pip(["numpy", "fastapi", "uvicorn[standard]", "openai", "laya"],
        extra=["-i", PYPI_MIRROR])

    # ---- 4. models ----
    step("Download Laya models via hf-mirror (~3.5GB, one time)")
    env = {"HF_ENDPOINT": "https://hf-mirror.com", "HF_HUB_DISABLE_XET": "1"}
    run([PY, "-c", "import laya; from laya import Router; Router(preload=True)"], env=env)
    print("Laya checkpoints ready (english / multilingual / typed-decisions).")

    # ---- 5. API key ----
    step("Configure draft-model API key")
    cfg_path = PROJ / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if os.environ.get("LLM_API_KEY", "").strip() or (cfg.get("_key_saved") is True):
        print("API key already configured, skip (delete config.json to re-run).")
    else:
        print("The drafting model needs an OpenAI-compatible API key.")
        print("Supported: SenseNova (token.sensenova.cn) / DeepSeek / any OpenAI-compatible base.")
        base = input(f"Base URL [default: https://token.sensenova.cn/v1]: ").strip() \
            or "https://token.sensenova.cn/v1"
        model = input(f"Model name [default: glm-5.2]: ").strip() or "glm-5.2"
        while True:
            key = ask_secret("Paste your API key: ").strip()
            if key:
                break
        # write key to user env (HKCU\Environment), never into files
        run(["setx", "LLM_API_KEY", key], check=False)
        os.environ["LLM_API_KEY"] = key
        cfg.update({"jev_provider": "laya", "jev_model": "laya-local",
                    "draft_provider": "sensenova" if "sensenova" in base else "custom_openai",
                    "draft_base_url": base, "draft_model": model, "_key_saved": True})
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Key saved to user environment variables (not to any file).")

    # ---- 6. start script ----
    step("Write one-click start script")
    bat = f"""@echo off
title Chat Advisor Launcher
set LAYA_DEVICE=cuda
set LAYA_PORT={LAYER_PORT}
start "LayaService" /min cmd /c ""{PY}" -m laya.serve > "{ROOT / 'laya_server.log'}" 2>&1"
echo Waiting for local service...
:wait
ping -n 4 127.0.0.1 >nul
curl -s -m 3 http://127.0.0.1:{LAYER_PORT}/health >nul 2>&1
if errorlevel 1 goto wait
cd /d "{PROJ}"
"{PY}" main.py
"""
    (ROOT / "start.bat").write_text(bat, encoding="ascii", errors="ignore")
    print("start.bat written. Double-click it to launch the assistant.")

    print("\n============================================")
    print("ALL DONE. Double-click start.bat to run.")
    print("============================================")


def ask_secret(prompt: str) -> str:
    try:
        import msvcrt
        print(prompt, end="", flush=True)
        chars = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                print()
                return "".join(chars)
            if ch in ("\b",):
                if chars:
                    chars.pop()
                    print("\b \b", end="", flush=True)
            elif ch >= " ":
                chars.append(ch)
                print("*", end="", flush=True)
    except ImportError:
        return input(prompt)


if __name__ == "__main__":
    sys.exit(main())
