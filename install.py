# -*- coding: utf-8 -*-
"""Laya Chat Advisor - GUI installer.

Launched by install.bat with system Python (tkinter is bundled).
Shows: step checklist (pending/running/done/error), overall progress bar,
live pip/model-download log. Re-running skips finished steps (idempotent).
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import venv
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
except ImportError:  # pragma: no cover
    print("tkinter missing; run install.bat --cli for command-line install")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"
PROJ = ROOT / "jev-chat-windows"
TORCH_INDEX = "https://download.pytorch.org/whl/cu121"
PYPI_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
LAYER_PORT = "8199"

STEPS = [
    "创建虚拟环境",
    "安装 PyTorch（CUDA，约 2.5GB）",
    "安装程序依赖（OCR / 界面 / SDK）",
    "下载 Laya 模型（约 3.5GB，仅此一次）",
    "配置 API 密钥",
    "生成启动脚本",
]


def run(cmd: list, env: dict | None = None, on_line=None, check: bool = True) -> int:
    e = os.environ.copy()
    if env:
        e.update(env)
    p = subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1)
    assert p.stdout
    for line in p.stdout:
        line = line.rstrip()
        if line and on_line:
            on_line(line)
    p.wait()
    if check and p.returncode != 0:
        raise RuntimeError(f"命令失败({' '.join(map(str, cmd))})，见日志")
    return p.returncode


# ---------------- installer steps (run in worker thread) ----------------

class Installer:
    def __init__(self, ui_log, ui_step):
        self.log = ui_log          # fn(str line)
        self.step_ui = ui_step     # fn(index, state)  state in run/done/error

    def step_env(self):
        if PY.exists():
            self.log("虚拟环境已存在，跳过")
            return
        venv.create(VENV, with_pip=True)
        self.log("虚拟环境创建完成")
        run([PY, "-m", "pip", "install", "--quiet", "--upgrade", "pip",
             "-i", PYPI_MIRROR], on_line=self.log)

    def step_torch(self):
        try:
            r = run([PY, "-c", "import torch; assert torch.cuda.is_available()"],
                    on_line=self.log, check=False)
        except OSError:
            r = 1
        if r == 0:
            self.log("CUDA 版 torch 已安装，跳过")
            return
        run([PY, "-m", "pip", "install", "--quiet", "torch",
             "--index-url", TORCH_INDEX], on_line=self.log)
        r = run([PY, "-c", "import torch; assert torch.cuda.is_available()"],
                on_line=self.log, check=False)
        if r != 0:
            self.log("[警告] CUDA 不可用（无 N 卡或驱动旧），退回 CPU 版")
            run([PY, "-m", "pip", "install", "--quiet", "torch", "-i", PYPI_MIRROR,
                 "--force-reinstall"], on_line=self.log)

    def step_deps(self):
        req = [ln.strip() for ln in (PROJ / "requirements.txt")
               .read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
        run([PY, "-m", "pip", "install", "--quiet", *req, "-i", PYPI_MIRROR],
            on_line=self.log)
        run([PY, "-m", "pip", "install", "--quiet", "numpy", "fastapi",
             "uvicorn[standard]", "openai", "laya", "-i", PYPI_MIRROR],
            on_line=self.log)

    def step_models(self):
        env = {"HF_ENDPOINT": "https://hf-mirror.com", "HF_HUB_DISABLE_XET": "1"}
        run([PY, "-c", "from laya import Router; Router(preload=True); print('models ok')"],
            env=env, on_line=self.log)
        self.log("模型就绪：english / multilingual / typed-decisions")

    def step_key(self):
        cfg_path = PROJ / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        if os.environ.get("LLM_API_KEY", "").strip() or cfg.get("_key_saved"):
            self.log("API key 已配置，跳过")
            return
        # 在主线程弹对话框拿 key（由 pipeline 通过事件队列请求）
        ans = KEY_ASKER["fn"]()
        if not ans:
            raise RuntimeError("未填写 API 密钥，安装中止")
        base, model, key = ans
        run(["setx", "LLM_API_KEY", key], check=False)
        os.environ["LLM_API_KEY"] = key
        cfg.update({"jev_provider": "laya", "jev_model": "laya-local",
                    "draft_provider": "sensenova" if "sensenova" in base else "custom_openai",
                    "draft_base_url": base, "draft_model": model, "_key_saved": True})
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log("密钥已写入用户环境变量（不落文件）")

    def step_startscript(self):
        bat = (f"@echo off\r\ntitle Chat Advisor\r\n"
               f"set LAYA_DEVICE=cuda\r\nset LAYA_PORT={LAYER_PORT}\r\n"
               f'start "LayaService" /min cmd /c ""{PY}" -m laya.serve > "{ROOT / "laya_server.log"}" 2>&1"\r\n'
               f"echo Waiting for local service...\r\n:wait\r\n"
               f"ping -n 4 127.0.0.1 >nul\r\n"
               f"curl -s -m 3 http://127.0.0.1:{LAYER_PORT}/health >nul 2>&1\r\n"
               f"if errorlevel 1 goto wait\r\n"
               f'cd /d "{PROJ}"\r\n"{PY}" main.py\r\n')
        (ROOT / "start.bat").write_bytes(bat.encode("ascii", errors="ignore"))
        self.log("start.bat 已生成，双击即可启动")


PIPELINE = [("step_env", STEPS[0]), ("step_torch", STEPS[1]), ("step_deps", STEPS[2]),
            ("step_models", STEPS[3]), ("step_key", STEPS[4]),
            ("step_startscript", STEPS[5])]

# 主线程往这里塞"问 key"的函数，worker 线程调用
KEY_ASKER = {"fn": lambda: None}


# ---------------- GUI ----------------

def gui() -> None:
    win = tk.Tk()
    win.title("Laya 聊天决策助手 · 安装向导")
    win.geometry("720x560")
    win.minsize(640, 500)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    head = tk.Label(win, text="Laya 聊天决策助手 · 一键安装",
                    font=("Microsoft YaHei UI", 15, "bold"), fg="#1a6f4b")
    head.pack(pady=(14, 4))
    tk.Label(win, text="全自动安装：环境 → 依赖 → 模型 → 配置。可中断后重跑，已完成的步骤自动跳过。",
             font=("Microsoft YaHei UI", 9), fg="#666").pack()

    rows, marks = [], []
    listbox = tk.Frame(win)
    listbox.pack(pady=10, padx=24, fill="x")
    for i, (_, label) in enumerate(PIPELINE):
        mark = tk.Label(listbox, text="○", width=3, font=("Segoe UI Symbol", 11),
                        fg="#999")
        mark.grid(row=i, column=0, sticky="nw")
        name = tk.Label(listbox, text=f"{i+1}. {label}", font=("Microsoft YaHei UI", 10),
                        fg="#444", anchor="w")
        name.grid(row=i, column=1, sticky="w")
        rows.append(name)
        marks.append(mark)

    prog = ttk.Progressbar(win, maximum=len(PIPELINE), value=0, length=660)
    prog.pack(pady=6)
    phase = tk.Label(win, text="点击「开始安装」", font=("Microsoft YaHei UI", 9, "bold"),
                     fg="#1a6f4b")
    phase.pack()

    logbox = tk.Text(win, height=12, bg="#101418", fg="#9fd6a8",
                     font=("Consolas", 8), state="disabled", wrap="none")
    logbox.pack(fill="both", expand=True, padx=24, pady=10)

    q: queue.Queue = queue.Queue()

    def ui_log(line: str) -> None:
        q.put(("log", line))

    def ui_step(idx: int, state: str) -> None:
        q.put(("step", idx, state))

    def start():
        btn.configure(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    def ask_key_dialog() -> tuple | None:
        box = tk.Toplevel(win)
        box.title("配置起草模型")
        box.geometry("460x250")
        box.grab_set()
        tk.Label(box, text="起草模型需要一个 OpenAI 兼容 API 密钥", font=("Microsoft YaHei UI", 10, "bold")).pack(pady=(14, 2))
        tk.Label(box, text="支持：商汤 SenseNova / DeepSeek 官方 / 其他 OpenAI 兼容接口", fg="#666").pack()
        f1 = tk.Frame(box); f1.pack(fill="x", padx=20, pady=4)
        tk.Label(f1, text="接口地址", width=9, anchor="w").pack(side="left")
        e_base = tk.Entry(f1); e_base.insert(0, "https://token.sensenova.cn/v1"); e_base.pack(side="left", fill="x", expand=True)
        f2 = tk.Frame(box); f2.pack(fill="x", padx=20, pady=4)
        tk.Label(f2, text="模型名", width=9, anchor="w").pack(side="left")
        e_model = tk.Entry(f2); e_model.insert(0, "glm-5.2"); e_model.pack(side="left", fill="x", expand=True)
        f3 = tk.Frame(box); f3.pack(fill="x", padx=20, pady=4)
        tk.Label(f3, text="API 密钥", width=9, anchor="w").pack(side="left")
        e_key = tk.Entry(f3, show="*"); e_key.pack(side="left", fill="x", expand=True)
        result: list = []

        def ok():
            if not e_key.get().strip():
                messagebox.showwarning("提示", "密钥不能为空", parent=box)
                return
            result.append((e_base.get().strip(), e_model.get().strip(), e_key.get().strip()))
            box.destroy()
        tk.Button(box, text="保存并继续", command=ok, bg="#1a6f4b", fg="white",
                  padx=12).pack(pady=12)
        box.protocol("WM_DELETE_WINDOW", box.destroy)
        box.wait_window()
        return result[0] if result else None

    KEY_ASKER["fn"] = ask_key_dialog

    def worker():
        inst = Installer(ui_log, ui_step)
        ok = True
        for i, (fname, _) in enumerate(PIPELINE):
            ui_step(i, "run")
            q.put(("phase", f"正在执行：{PIPELINE[i][1]}"))
            try:
                getattr(inst, fname)()
                ui_step(i, "done")
                q.put(("progress", i + 1))
            except Exception as exc:  # noqa: BLE001
                ui_step(i, "error")
                q.put(("log", f"[错误] {exc}"))
                q.put(("phase", "安装失败 —— 修复问题后重新运行即可续装"))
                ok = False
                break
        if ok:
            q.put(("phase", "全部完成！双击 start.bat 启动助手"))
            q.put(("done", None))

    btn = tk.Button(win, text="开 始 安 装", font=("Microsoft YaHei UI", 12, "bold"),
                    bg="#1a6f4b", fg="white", padx=24, pady=6, command=start)
    btn.pack(pady=(2, 12))

    def phase_drain():
        try:
            while True:
                item = q.get_nowait()
                if item[0] == "log":
                    logbox.configure(state="normal")
                    logbox.insert("end", item[1] + "\n")
                    logbox.see("end")
                    logbox.configure(state="disabled")
                elif item[0] == "step":
                    _, idx, state = item
                    glyph, color = {"run": ("◐", "#c07a00"), "done": ("✔", "#1a6f4b"),
                                    "error": ("✘", "#b03030")}[state]
                    marks[idx].configure(text=glyph, fg=color)
                    rows[idx].configure(fg="#111")
                elif item[0] == "progress":
                    prog.configure(value=item[1])
                elif item[0] == "phase":
                    phase.configure(text=item[1])
                elif item[0] == "done":
                    btn.configure(text="完成 ✔", state="disabled",
                                  bg="#1a6f4b")
        except queue.Empty:
            pass
        win.after(80, phase_drain)

    phase_drain()
    win.mainloop()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        inst = Installer(lambda s: print(s, flush=True),
                         lambda i, s: print(f"  [{s}] {STEPS[i]}", flush=True))
        try:
            for fname, label in PIPELINE:
                print(f"== {label}", flush=True)
                if fname == "step_key":
                    b = (input("接口地址 [https://token.sensenova.cn/v1]: ").strip()
                         or "https://token.sensenova.cn/v1")
                    m = input("模型名 [glm-5.2]: ").strip() or "glm-5.2"
                    k = input("API 密钥: ").strip()
                    if not k:
                        raise RuntimeError("未填写密钥")
                    KEY_ASKER["fn"] = (lambda bb, mm, kk: lambda: (bb, mm, kk))(b, m, k)
                getattr(inst, fname)()
            print("全部完成！双击 start.bat 启动。")
        except Exception as exc:
            print(f"[错误] {exc}")
            sys.exit(1)
    else:
        gui()
