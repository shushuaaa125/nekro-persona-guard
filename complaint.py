"""人设哨兵 - 被说「人机」时自动出日报。

只在**说她的 bot** 时触发：
- 提到她的名字（COMPLAINT_NAMES）或直接 @她
- 且出现「人机 / 入机 / 机器人 / AI 味」这类词
- 且不是游戏语境（打人机、人机模式…）

触发后：补扫一次 → 生成日报卡 → 私聊发给主人。
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from .plugin import get_config, plugin


def _cfg():
    return get_config()


def _state_path() -> Path:
    d = Path(plugin.get_plugin_data_dir())
    d.mkdir(parents=True, exist_ok=True)
    return d / "complaint_state.json"


def _shadow_path() -> Path:
    return Path(plugin.get_plugin_data_dir()) / "shadow.jsonl"


def _append_shadow(entry: Dict[str, Any]) -> None:
    """记一条「有人机字样但没命中」的消息，用来找漏检。"""
    import json

    try:
        p = _shadow_path()
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        lines.append(json.dumps(entry, ensure_ascii=False))
        p.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def load_shadow(limit: int = 30, day: str = "") -> list:
    import json

    p = _shadow_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for line in lines[::-1]:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if day and not str(item.get("time", "")).startswith(day):
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def shadow_count(day: str) -> int:
    return len(load_shadow(limit=500, day=day))


def _log_path() -> Path:
    return Path(plugin.get_plugin_data_dir()) / "complaint_log.jsonl"


def _append_log(entry: Dict[str, Any]) -> None:
    """记录每次判定，便于审计「到底有没有在监测真消息」。"""
    import json

    try:
        p = _log_path()
        lines = []
        if p.exists():
            lines = p.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(entry, ensure_ascii=False))
        p.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def load_log(limit: int = 30) -> list:
    import json

    p = _log_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for line in lines[-limit:][::-1]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _load_state() -> Dict[str, Any]:
    import json

    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(data: Dict[str, Any]) -> None:
    import json

    _state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _split(raw: str) -> list:
    return [x.strip() for x in (raw or "").replace("，", ",").split(",") if x.strip()]


def detect(text: str, is_tome: bool = False) -> Tuple[bool, str]:
    """判断这条消息是不是在说「她的 bot 很人机」。"""
    cfg = _cfg()
    t = (text or "").strip()
    if not t:
        return False, ""
    if not bool(getattr(cfg, "COMPLAINT_ENABLED", True)):
        return False, ""

    # 合并转发 / 卡片 / 超长文本：里面常带历史聊天里的「西西 人机」，不算投诉
    forward_marks = ("[合并转发", "合并转发消息", "聊天记录：", "聊天记录:", "[卡片消息]", "[CQ:forward")
    if any(x in t for x in forward_marks) or len(t) > 300:
        return False, "forward"

    words = _split(str(getattr(cfg, "COMPLAINT_WORDS", "") or ""))
    names = _split(str(getattr(cfg, "COMPLAINT_NAMES", "") or ""))
    excludes = _split(str(getattr(cfg, "COMPLAINT_EXCLUDE", "") or ""))

    if any(x in t for x in excludes):
        return False, "excluded"

    tech = _split(str(getattr(cfg, "COMPLAINT_TECH_WORDS", "") or ""))
    low = t.lower()
    if ("机器人" in t or "bot" in low) and any(w.lower() in low for w in tech):
        return False, "tech"

    positive = _split(str(getattr(cfg, "COMPLAINT_POSITIVE", "") or ""))
    if any(w in t for w in positive):
        return False, "positive"

    word = next((w for w in words if w in t), "")
    if not word:
        return False, ""

    if is_tome:
        return True, word
    name = next((n for n in names if n in t), "")
    if name:
        return True, f"{word}@{name}"
    return False, "no-target"


async def handle(ctx: Any, message: Any, test_mode: bool = False) -> bool:
    """命中则触发扫描 + 私聊日报；返回是否命中。"""
    cfg = _cfg()
    text = getattr(message, "content_text", "") or ""
    is_tome = bool(getattr(message, "is_tome", False))
    hit, reason = detect(text, is_tome)

    if bool(getattr(cfg, "COMPLAINT_DEBUG", True)):
        _append_log({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "chat_key": str(getattr(ctx, "chat_key", "") or ""),
            "sender": str(getattr(message, "sender_nickname", "") or getattr(message, "sender_name", "") or ""),
            "text": text[:60],
            "is_tome": is_tome,
            "hit": hit,
            "reason": reason,
            "test": test_mode,
        })

    if not hit:
        if reason == "no-target":
            _append_shadow({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "chat_key": str(getattr(ctx, "chat_key", "") or ""),
                "sender": str(getattr(message, "sender_nickname", "") or getattr(message, "sender_name", "") or ""),
                "text": text[:80],
                "reason": reason,
            })
        return False

    chat_key = str(getattr(ctx, "chat_key", "") or getattr(message, "chat_key", "") or "")

    # 冷却，避免刷屏
    cooldown = int(getattr(cfg, "COMPLAINT_COOLDOWN_MINUTES", 30) or 0) * 60
    state = _load_state()
    last = float(state.get(chat_key, 0) or 0)
    if cooldown and time.time() - last < cooldown:
        plugin.logger.info(f"[persona_guard] 人机投诉命中但仍在冷却: {chat_key}")
        return True
    state[chat_key] = time.time()
    _save_state(state)

    sender = (
        getattr(message, "sender_nickname", "")
        or getattr(message, "sender_name", "")
        or getattr(message, "sender_id", "")
    )

    try:
        from . import core

        await core.scan_once()

        # 用「被说人机那天」的日报，而不是今天
        when_day = None
        try:
            when0 = getattr(message, "create_time", None)
            if when0 is not None:
                when_day = when0.strftime("%Y-%m-%d")
        except Exception:
            when_day = None
        data = await core.report_data(when_day)
        image = Path(core.render_report_image(data))

        names = await core.chat_names([chat_key])
        group = names.get(chat_key, chat_key)
        no = core._chat_number(chat_key) if hasattr(core, "_chat_number") else ""
        kind = "私聊" if "private" in chat_key else "群"

        when = getattr(message, "create_time", None)
        try:
            when_txt = when.strftime("%Y-%m-%d %H:%M:%S") if when else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            when_txt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            ("⚠️【测试】有人觉得她人机" if test_mode else "⚠️ 有人觉得她人机"),
            f"触发时间: {when_txt}",
            f"{kind}: {group}" + (f"({no})" if no and no != group else ""),
            f"说的: {sender}",
            f"原话: 「{text[:60]}」",
            f"今日: 人机味 {data.get('ai', 0)} · 冲突 {data.get('conflict', 0)}"
            + (f" · 匹配 {data.get('match', {}).get('score', 0):.0f}" if data.get("match", {}).get("parts") else ""),
        ]
        text_out = "\n".join(lines)

        keys_raw = str(getattr(cfg, "COMPLAINT_ALERT_CHAT_KEYS", "") or "") or str(
            getattr(cfg, "REPORT_CHAT_KEYS", "") or ""
        ) or str(getattr(cfg, "ALERT_CHAT_KEYS", "") or "")
        keys = _split(keys_raw)

        # 出事那个群也发一份（全局开关 或 群白名单）
        allow_groups = [
            x.strip()
            for x in str(getattr(cfg, "COMPLAINT_GROUP_CHAT_KEYS", "") or "").replace("，", ",").split(",")
            if x.strip()
        ]
        group_on = bool(getattr(cfg, "COMPLAINT_GROUP_REPLY", False)) or (chat_key in allow_groups)
        if group_on and chat_key and chat_key not in keys:
            keys.append(chat_key)

        import random

        pool_raw = str(getattr(cfg, "COMPLAINT_GROUP_TEXT", "") or "").strip()
        pool = [x.strip() for x in pool_raw.split("|") if x.strip()]
        if not pool:
            pool = ["诶？人机？我…我吗？"]
        head = random.choice(pool)

        tail_tpl = str(getattr(cfg, "COMPLAINT_GROUP_TAIL", "") or "").strip()
        if not tail_tpl:
            tail_tpl = "（{time}）今天 {ai} 次"
        tail = (
            tail_tpl.replace("{time}", when_txt)
            .replace("{ai}", str(data.get("ai", 0)))
            .replace("{conflict}", str(data.get("conflict", 0)))
        )
        group_text = head + ("\n" + tail if tail else "")

        plugin.logger.info(f"[persona_guard] 投诉日报发送目标: {keys}（触发群: {chat_key}）")
        plugin.logger.info("[persona_guard] 投诉内容: " + text_out.replace("\n", " | "))
        if keys:
            from nekro_agent.api import message as message_api
            from nekro_agent.schemas.agent_ctx import AgentCtx

            for key in keys:
                try:
                    actx = await AgentCtx.create_by_chat_key(chat_key=key)
                    body = group_text if key == chat_key else text_out
                    await message_api.send_text(key, body, actx, record=False)
                    await message_api.send_image(key, core.publish_image(str(image), key), actx, record=False)
                except Exception as exc:  # noqa: BLE001
                    plugin.logger.warning(f"[persona_guard] 投诉日报发送失败 {key}: {exc}")
        else:
            plugin.logger.info(f"[persona_guard] 命中投诉但没配接收会话: {text_out}")
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 投诉处理失败: {exc}")

    return True
