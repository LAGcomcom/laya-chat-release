# -*- coding: utf-8 -*-
"""会话记忆 + 自动世界书（借鉴 SillyTavern）。

每会话一个 data/memory/<会话>.json:
  {"summary": 叙事摘要(2~3句), "entries": [{keys:[触发词], content: 事实}], "pending": [...]}

- 滚动摘要: 未摘要消息攒够 threshold 条, 调一次便宜模型, 同时产出叙事摘要和事实词条
- 词条注入: 起草时扫描最近消息文本, 命中触发词的词条注入 prompt（治"说话不合时宜"）
- 词条文件可手动编辑, AI 更新时会保留手动条目（manual: true）"""

import json
import os
import re


def _safe_name(session: str) -> str:
    return re.sub(r"[^\w\-一-鿿]", "_", (session or "chat"))[:40] or "chat"


class SessionMemory:
    MAX_ENTRIES = 15

    def __init__(self, root_dir: str, summarize_fn=None, threshold: int = 10):
        self.dir = os.path.join(root_dir, "data", "memory")
        os.makedirs(self.dir, exist_ok=True)
        self.summarize_fn = summarize_fn  # (prev_summary, entries, older_msgs) -> {"summary", "entries"}
        self.threshold = threshold

    def _path(self, session: str) -> str:
        return os.path.join(self.dir, _safe_name(session) + ".json")

    def _load(self, session: str) -> dict:
        try:
            with open(self._path(session), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return {"summary": str(d.get("summary") or ""),
                        "entries": [e for e in d.get("entries", []) if isinstance(e, dict)
                                    and e.get("content")],
                        "pending": [m for m in d.get("pending", [])
                                    if isinstance(m, dict) and m.get("text")]}
        except Exception:
            pass
        return {"summary": "", "entries": [], "pending": []}

    def _save(self, session: str, d: dict) -> None:
        try:
            with open(self._path(session), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def get_summary(self, session: str) -> str:
        return self._load(session)["summary"]

    def relevant_entries(self, session: str, texts) -> str:
        """扫描最近消息文本, 返回命中触发词的词条文本（最多 4 条）。"""
        d = self._load(session)
        blob = " ".join(str(t) for t in texts)
        hits = []
        for e in d["entries"]:
            for k in e.get("keys", []):
                k = str(k).strip()
                if k and k in blob:
                    hits.append(e["content"])
                    break
        return "\n".join("- " + h for h in hits[:4])

    def feed(self, session: str, msgs) -> None:
        """msgs: [(who, text)]——本帧 OCR 新增消息。攒够 threshold 就压缩+提炼词条。"""
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
            res = self.summarize_fn(d["summary"], d["entries"], older) or {}
            if res.get("summary"):
                d["summary"] = str(res["summary"])
            if isinstance(res.get("entries"), list):
                manual = [e for e in d["entries"] if e.get("manual")]
                auto = [e for e in res["entries"] if isinstance(e, dict)
                        and e.get("content") and isinstance(e.get("keys"), list)
                        and e["keys"]][:self.MAX_ENTRIES - len(manual)]
                d["entries"] = manual + auto
        except Exception:
            pass  # 摘要/提炼失败静默跳过, 下轮再试
        self._save(session, d)
