# -*- coding: utf-8 -*-
'''主动开场：不等对方发消息，AI 主动起话题（童锦程式直球/钩子/调侃）。'''

import time

from .draft import _parse_candidates, _api_key, LLM_ENV
from .providers import DRAFT_PROVIDERS
from . import llm as core_llm

SYSTEM_PROACTIVE = (
    "你是「me」本人，正在主动给对方发消息。不是助手，不是客服。\n"
    "人设规则：\n"
    "- 短句、口语、直球、自信；被冷落也不卑微；先推后拉、反转句式是你的招牌\n"
    "- 禁止「在吗」「吃了吗」「睡了吗」这种废话开场；禁止空洞的「想你了」——要具体到细节\n"
    "- 禁止三连问；禁止客套词（亲/您/希望/祝）\n"
    "- 主动开场的方式（选一种，要具体）：一句直球的想念（带着细节）；分享一件让 TA 想起你的小事；"
    "调侃 TA 上次说过的某句话；抛一个 TA 好接的钩子\n"
    "- 输出恰好 3 条候选，JSON 数组；每条可以是一句，或用换行分隔的 2 句连发"
)


def proactive_candidates(messages_recent: list, relationship: str,
                         summary=None, lore=None, persona=None, style_prompt=None,
                         provider: str = "deepseek", model=None, base_url=None,
                         timeout: float = 30) -> list:
    '''messages_recent: [(who, text)] 最近几条（可空）；返回最多 3 条候选。'''
    spec = DRAFT_PROVIDERS[provider]
    key = _api_key(LLM_ENV)
    model = model or spec.default

    now = time.strftime("%H:%M")
    hour = time.localtime().tm_hour
    daypart = ("早上" if 5 <= hour < 11 else "中午" if 11 <= hour < 14 else
               "下午" if 14 <= hour < 18 else "晚上")
    transcript = "\n".join(f"{w}: {t}" for w, t in messages_recent[-6:]) or "（最近没聊什么）"

    user = (f"relationship: {relationship}\n现在是{daypart} {now}。\n"
            f"你们最近聊过的（供参考，别重复原话）：\n{transcript}\n")
    if summary and summary.strip():
        user += f"\n\n【更早的背景】{summary.strip()[:300]}\n"
    if lore and lore.strip():
        user += f"\n\n【关于 TA 的备忘（开话题时用上，显得你记得 TA 的事）】\n{lore.strip()[:300]}\n"
    if persona:
        if persona.get("background"):
            user += f"\n\n【TA 和我的背景】{str(persona['background'])[:200]}\n"
        if persona.get("personality"):
            user += f"【TA 的性格】{str(persona['personality'])[:150]}\n"
        if persona.get("taboos"):
            user += f"【雷点——开场绝对别碰】{str(persona['taboos'])[:150]}\n"
    if style_prompt and style_prompt.strip():
        user += f"\n\n{style_prompt.strip()}"
    user += f"\n\n输出恰好 3 条主动开场的候选，JSON 数组。"

    content = core_llm.chat(spec.protocol, base_url or spec.base, key, model,
                            SYSTEM_PROACTIVE, [user], temperature=1.0,
                            max_tokens=400, thinking=False,
                            extra_body=spec.extra(False), headers=spec.headers,
                            timeout=timeout)
    return _parse_candidates(content)[:3]
