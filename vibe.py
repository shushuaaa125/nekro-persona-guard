"""人设哨兵 - 语感抽检（LLM 判定「像不像真人聊天」）。

正则抓的是固定句式，抓不到「整体语气像 AI/像小说」。
这里把最近若干条发言交给模型，让它指出哪几句不像人话，并给改写建议。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .plugin import get_config, plugin

PROMPT = """下面是某个角色在群聊里的真实发言。请判断哪些**不像真人随口的聊天**，而像：
- AI 助手在回答
- 小说旁白 / 散文（工整、意象化、爱用破折号）
- 刻意表演「我很温柔/我很深沉」

对每一条可疑的给：原文、为什么可疑（一句话）、更像人会怎么说（口语、短）。
只输出 JSON：
{"items":[{"text":"原文","reason":"为什么","fix":"改成什么"}]}

没有可疑的就输出 {"items":[]}。不要解释，不要输出 JSON 以外内容。

【发言】
{lines}
"""


def _data_dir() -> Path:
    return Path(plugin.get_plugin_data_dir())


def _cache_path() -> Path:
    return _data_dir() / "vibe.json"


def load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: Dict[str, Any]) -> None:
    _cache_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def fetch_lines(days: int = 1, limit: int = 30, group_only: bool = True) -> List[str]:
    from nekro_agent.models.db_chat_message import DBChatMessage

    since = datetime.now() - timedelta(days=max(1, days))
    q = DBChatMessage.filter(sender_id="-1", create_time__gte=since)
    if group_only:
        q = q.filter(chat_type__contains="GROUP")
    rows = await q.order_by("-id").limit(limit * 3)
    out: List[str] = []
    for m in rows:
        t = (getattr(m, "content_text", "") or "").strip()
        if not t or t.startswith("[") or t.startswith("(成员") or "撤回了一条消息" in t:
            continue
        out.append(t[:120])
        if len(out) >= limit:
            break
    return list(reversed(out))


async def run_check(days: int = 1, limit: int = 30) -> Dict[str, Any]:
    cfg = get_config()
    lines = await fetch_lines(days, limit)
    if not lines:
        return {"ok": False, "error": "没有可分析的发言"}

    body = "\n".join(f"- {x}" for x in lines)
    try:
        from nekro_agent.core.config import config as na_config
        from nekro_agent.services.agent.openai import gen_openai_chat_response

        grp_name = str(getattr(cfg, "VIBE_MODEL_GROUP", "") or "").strip() or str(
            getattr(na_config, "USE_MODEL_GROUP", "") or "default"
        )
        group = na_config.get_model_group_info(grp_name)
        resp = await gen_openai_chat_response(
            model=group.CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你只输出 JSON。"},
                {"role": "user", "content": PROMPT.replace("{lines}", body)},
            ],
            api_key=group.API_KEY,
            base_url=group.BASE_URL,
            max_tokens=2600,
            extra_body={"thinking": {"type": "disabled"},
                        "response_format": {"type": "json_object"}},
        )
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 语感抽检失败: {exc}")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    text = resp if isinstance(resp, str) else str(resp)
    items: List[Dict[str, Any]] = []
    try:
        i, j = text.find("{"), text.rfind("}")
        data = json.loads(text[i: j + 1]) if i >= 0 and j > i else {}
        items = list(data.get("items") or [])
    except Exception:
        items = []

    result = {
        "ok": True,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": getattr(group, "CHAT_MODEL", ""),
        "sample": len(lines),
        "count": len(items),
        "items": items[:20],
    }
    _save_cache(result)
    return result
