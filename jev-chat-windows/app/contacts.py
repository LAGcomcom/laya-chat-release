# -*- coding: utf-8 -*-
"""按联系人的关系/风格卡：data/contacts/<会话>.json = {"relationship", "style"}。
空值 = 沿用全局设置。"""

import json
import os
import re


def _safe(session: str) -> str:
    return re.sub(r"[^\w\-一-鿿]", "_", (session or "chat"))[:40] or "chat"


class ContactStore:
    def __init__(self, root_dir: str):
        self.dir = os.path.join(root_dir, "data", "contacts")
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, session: str) -> str:
        return os.path.join(self.dir, _safe(session) + ".json")

    def get(self, session: str) -> dict:
        try:
            with open(self._path(session), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return {"relationship": str(d.get("relationship") or ""),
                        "style": str(d.get("style") or "")}
        except Exception:
            pass
        return {"relationship": "", "style": ""}

    def set(self, session: str, **kw) -> None:
        d = self.get(session)
        d.update({k: str(v) for k, v in kw.items()})
        with open(self._path(session), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)


contacts = ContactStore(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
