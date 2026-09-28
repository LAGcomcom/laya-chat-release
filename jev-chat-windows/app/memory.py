# -*- coding: utf-8 -*-
"""会话滚动摘要：每会话一个 data/memory/<会话>.json，内容 {"summary", "pending"}。
未摘要消息攒够 threshold 条就把旧的压成 2~3 句摘要（调起草模型，便宜档），
起草时把摘要带进 prompt——聊了多久、翻了多远，模型都知道话题锚在哪。"""

import json
import os
import re


def _safe_name(session: str) -> str:
    return re.sub(r"[^\w\-一-鿿]", "_", (session or "chat"))[:40] or "chat"


class SessionMemory:
    def __init__(self, root_dir: str, summarize_fn=None, threshold: int = 10):
        self.dir = os.path.join(root_dir, "data", "memory")
        os.makedirs(self.dir, exist_ok=True)
        self.summarize_fn = summarize_fn
        self.threshold = threshold

    def _path(self, session: str) -> str:
        return os.path.join(self.dir, _safe_name(session) + ".json")

    def _load(self, session: str) -> dict:
        try:
            with open(self._path(session), encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    return {"summary": str(d.get("summary") or ""),
                            "pending": [m for m in d.get("pending", [])
                                        if isinstance(m, dict) and m.get("text")]}
        except Exception:
            pass
        return {"summary": "", "pending": []}

    def _save(self, session: str, d: dict) -> None:
        try:
            with open(self._path(session), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def get_summary(self, session: str) -> str:
        return self._load(session)["summary"]

    def feed(self, session: str, msgs) -> None:
        """msgs: [(who, text)]——本帧 OCR 新增的消息。攒够就压缩旧的。"""
        if not msgs:
            return
        d = self._load(session)
        d["pending"].extend({"from": w, "text": str(t or "")} for w, t in msgs)
        d["pending"] = [m for m in d["pending"] if m["text"]]
        if len(d["pending"]) < self.threshold or self.summarize_fn is None:
            self._save(session, d)
            return
        keep = 4
        older = d["pending"][:-keep]
        d["pending"] = d["pending"][-keep:]
        try:
            d["summary"] = self.summarize_fn(d["summary"], older) or d["summary"]
        except Exception:
            pass  # 摘要失败静默跳过，下轮再试
        self._save(session, d)
