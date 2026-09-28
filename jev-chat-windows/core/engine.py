# -*- coding: utf-8 -*-
"""整条链的唯一入口：对话 → Jev 判断 → 带着判断起草 3 条 → Jev 排序 → 结构化结果。

平台无关。SSE 消费者、悬浮窗、命令行 demo 都只调 analyze()。
"""
from __future__ import annotations

try:
    from .draft import draft_candidates
    from .jev_client import JevError, ask
    from .questions import JUDGE_QUESTIONS, build_rank_question, build_state, guidance_text
except ImportError:
    from draft import draft_candidates
    from jev_client import JevError, ask
    from questions import JUDGE_QUESTIONS, build_rank_question, build_state, guidance_text

_REPLY_IDX = {"reply_a": 0, "reply_b": 1, "reply_c": 2}


def _add_usage(total: dict, one: dict | None) -> None:
    """两次 Jev 调用的 usage 相加（tokens、cost）；非数字的字段后来的盖掉前面的。"""
    for k, v in (one or {}).items():
        total[k] = total.get(k, 0) + v if isinstance(v, (int, float)) else v


def analyze(messages: list, relationship: str, model: str | None = None,
            timeout: float = 30, context: int = 10, provider: str = "deepseek",
            base_url: str | None = None, reply_to: str | None = None, style: str = "",
            thinking: bool = False, summary: str | None = None, lore: str | None = None, style_prompt: str | None = None,
            persona: dict | None = None,
            jev_provider: str = "openrouter",
            jev_model: str | None = None) -> dict:
    """messages: [(from, text)] from ∈ {her, me}，最新一条在最后；
    群聊里可以带第三项 name（说这句话的人），单聊不带。
    context: 起草和判断各看最近多少条消息（用户设置里的「参考上下文」）。
    provider: 起草走哪家（core.providers.DRAFT_PROVIDERS），base_url 只有自定义来源要传。
    jev_provider / jev_model: 判断和排序走哪家、哪个模型（core.providers.JEV_PROVIDERS）。
    reply_to: 群聊里指定回复给谁；None = 正常回复。
    style: 用户自己描述的说话风格，只影响起草。
    thinking: 起草时是否开思考模式，只影响起草，默认关。
    model / jev_model = None 用该来源的默认模型。

    返回 {candidates, best_index, best_reply, scores, answers, usage, reply_to}。
    scores 是每条候选的胜出概率（0~1），取自 best_reply.probabilities，取不到记 0.0。
    只有对方最新说话时才有意义调它——是不是该触发由调用方判断（看 latest_from）。

    三段式（issue #4）：先让 Jev 答 7 道判断题，把判断当小抄喂给起草，最后 Jev 只排序。
    判断那次挂了就退回老路：盲起草 + 判断和排序一次问完，行为跟以前一样。usage 是两次之和。
    """
    state = build_state(messages, relationship, keep=context, reply_to=reply_to)
    usage: dict = {}
    answers: dict = {}
    judged = False
    try:
        first = ask(state, dict(JUDGE_QUESTIONS), timeout=timeout,
                    provider=jev_provider, model=jev_model)
        answers = first.get("answers") or {}
        _add_usage(usage, first.get("usage"))
        judged = True
    except JevError:
        pass  # 退回盲起草 + 老的一次合问；错误不打日志（里面可能带请求内容）

    # 置信度闸门：本地 Laya 基础模型零样本下部分题乱答（None/低置信），
    # 没把握的判断喂给起草只会带偏口吻——只保留有把握的条目当小抄。
    CONF_GATE = 0.60
    safe_answers = {
        k: v for k, v in answers.items()
        if isinstance(v, dict)
        and (v.get("choice") is not None or isinstance(v.get("score"), (int, float)))
        and (v.get("confidence") or 0) >= CONF_GATE
    }
    # 情绪承接加码：判断出 TA 在发泄/需要被理解时，给起草一条硬提示
    emo_hint = ""
    vi = (safe_answers.get("true_intent") or {}).get("choice")
    sn = (safe_answers.get("she_needs") or {}).get("choice")
    if vi == "vent_anger" or sn in ("care", "apology"):
        emo_hint = "对方现在最需要的是【被理解】而不是被解决——第一条候选的第一句必须先接住情绪，之后才能说别的。"
    guidance_final = (guidance_text(safe_answers) + chr(10) + chr(10) + emo_hint).strip() if (safe_answers or emo_hint) else None
    candidates = draft_candidates(messages, relationship, provider=provider, model=model,
                                  base_url=base_url, timeout=timeout, keep=context,
                                  reply_to=reply_to, style=style, thinking=thinking,
                                  guidance=guidance_text(safe_answers) if safe_answers else None,
                                  summary=summary, lore=lore, persona=persona, style_prompt=style_prompt)
    if not candidates:  # 注入过滤可以把起草结果全扔掉；接着取 [0] 会 IndexError
        raise JevError("起草结果没有可用候选回复")

    questions = {} if judged else dict(JUDGE_QUESTIONS)
    if len(candidates) >= 2:  # 起草只给了 1 条就没什么可排的，判断题照问
        questions.update(build_rank_question(candidates))
    if questions:
        try:
            second = ask(state, questions, timeout=timeout,
                         provider=jev_provider, model=jev_model)
        except JevError:
            if not judged:  # 老路只有这一次调用，挂了就是挂了
                raise
            second = {}  # 判断还在，只是没排上序：下面按第一条推荐
        answers = {**answers, **(second.get("answers") or {})}
        _add_usage(usage, second.get("usage"))

    best_key = (answers.get("best_reply") or {}).get("choice")
    best_index = _REPLY_IDX.get(best_key, 0)  # 解析不出就退第一条
    if best_index >= len(candidates):
        best_index = 0

    probabilities = (answers.get("best_reply") or {}).get("probabilities") or {}
    scores = [0.0, 0.0, 0.0]
    for key, idx in _REPLY_IDX.items():
        try:
            scores[idx] = float(probabilities.get(key, 0.0))
        except (TypeError, ValueError):
            scores[idx] = 0.0  # 脏数据一律按 0 处理

    return {
        "candidates": candidates,
        "best_index": best_index,
        "best_reply": candidates[best_index],
        "scores": scores,
        "answers": answers,
        "usage": usage,
        "reply_to": reply_to,
    }


if __name__ == "__main__":
    # 候选被过滤光时要抛 JevError，不能在取第一条时 IndexError。
    from unittest.mock import patch

    with patch("__main__.ask", return_value={"answers": {}, "usage": {}}), \
         patch("__main__.draft_candidates", return_value=[]):
        try:
            analyze([("her", "hello")], "friends")
            raise SystemExit("应当抛错")
        except JevError as e:
            assert "没有可用候选" in str(e)
    print("engine ok")


def proactive(messages_recent: list, relationship: str, summary=None, lore=None,
              persona=None, style_prompt=None, provider: str = "deepseek",
              model=None, base_url=None, timeout: float = 40,
              jev_provider=None, jev_model=None) -> dict:
    """主动开场 3 条候选 + 用判断模型给"现在发合不合适"打分。
    返回与 analyze 同形的结果（candidates/scores/best_index），可直接喂给悬浮窗。"""
    from .proactive import proactive_candidates
    from .jev_client import ask
    cands = proactive_candidates(messages_recent, relationship, summary=summary,
                                 lore=lore, persona=persona, style_prompt=style_prompt,
                                 provider=provider, model=model, base_url=base_url,
                                 timeout=timeout)
    if not cands:
        raise RuntimeError("主动开场候选为空")

    scores = [0.0] * len(cands)
    try:
        state = {"chat": {"relationship": relationship,
                          "messages": [{"from": m[0], "text": m[1]} for m in messages_recent[-6:]],
                          "latest_from": "me", "is_group": False}}
        questions = {f"c{i}": {"type": "noul",
                     "instructions": "If 'me' sends this message to 'her' right now, would it land well - natural, timely, and likely to get a good response?"}
                     for i in range(len(cands))}
        gold = {}
        for i in range(len(cands)):
            gold[f"c{i}"] = {"probabilities": {"false": 0.0, "true": 1.0}}
        state["chat"]["proactive_drafts"] = cands
        r = ask(state, questions, provider=jev_provider or "laya", model=jev_model, timeout=timeout)
        for i in range(len(cands)):
            a = (r.get("answers") or {}).get(f"c{i}") or {}
            scores[i] = float(a.get("noul") or 0.0)
    except Exception:
        pass  # 打分失败就按原序展示

    best = scores.index(max(scores)) if scores else 0
    return {"candidates": cands, "best_index": best, "best_reply": cands[best],
            "scores": scores, "answers": {}, "usage": {}, "reply_to": None,
            "draft_provider": "proactive"}
