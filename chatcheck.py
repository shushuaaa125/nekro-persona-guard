"""人设哨兵 - 聊天事实抽检。

把她的实际发言对照人设硬事实，找出说反/编造的地方。

实现分两层：
1. 规则层（稳定）：复用 FACT_ANCHORS，再加几条聊天里常见的口误模式
   （年龄、家在学院、认错族、认错能力）。这层不依赖模型，永远可用。
2. 模型层（可选）：少量句子交给模型做语义判断；中转不稳定时自动跳过。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .plugin import get_config, plugin

# 聊天场景的硬校验：(正则, 说明)。默认空，由 CHATCHECK_PATTERNS 配置提供。
EXAMPLE_PATTERNS: List[Tuple[str, str]] = [
    (r"(我|今年|刚满)?\s*(1[0-9]|[2-9][0-9])\s*岁", "年龄不是 16"),
    (r"我(今年|刚满)?\s*(十五|十六|十七|十八|十九|二十)(岁|了)?", "年龄不是 16"),
    (r"我(今年|刚满)\s*(1[0-9]|[2-9][0-9])(?!\s*岁)", "年龄不是 16"),
    (r"(十五|十六|十七|十八|十九|二十)\s*岁\s*那?年", "年龄不是 16"),
    (r"家在\s*(星炬学院|学院|宿舍)", "家不在学院，在浮光林"),
    (r"我是\s*(人类|人|精灵|半精灵)", "她是罗伊族"),
    (r"我的?能力是\s*(?!语义解现)[\u4e00-\u9fa5]{1,6}", "能力是「语义解现」"),
    (r"阿妈是\s*(老师|教授|同事|邻居)", "阿妈是妈妈本人"),
]

PROMPT = """事实：
{facts}

她的发言：
{lines}

找出与人设事实冲突的发言，直接输出 JSON（不要分析过程）：
{{"items":[{{"text":"原话","reason":"冲突点"}}]}}
没有冲突输出 {{"items":[]}}。
"""


def _data_dir() -> Path:
    return Path(plugin.get_plugin_data_dir())


def _cache_path() -> Path:
    return _data_dir() / "chatcheck.json"


def load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: Dict[str, Any]) -> None:
    _cache_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def facts_text() -> str:
    from . import consistency

    rows = consistency.memory_entries()
    keep = [r for r in rows if r["source"].startswith("tier1")][:3]
    return "\n".join(f"- {r['title']}：{str(r['content'])[:150]}" for r in keep)


def _patterns() -> List[Tuple[str, str]]:
    """从配置读聊天校验规则；没配就不跑规则层。"""
    try:
        raw = str(getattr(get_config(), "CHATCHECK_PATTERNS", "") or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        out = []
        for row in data or []:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                out.append((str(row[0]), str(row[1])))
        return out
    except Exception:
        return []


CN_NUM = {"十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20}


def _age_rule() -> dict:
    try:
        raw = str(getattr(get_config(), "CHATCHECK_AGE", "") or "").strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _extract_age(text: str) -> int:
    m = re.search(r"(\d{1,2})\s*岁", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    m = re.search(r"我(?:今年|刚满)?\s*(\d{1,2})", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return 0
    m = re.search(r"(十五|十六|十七|十八|十九|二十)\s*岁", text) or re.search(
        r"我(?:今年|刚满)?\s*(十五|十六|十七|十八|十九|二十)", text
    )
    return CN_NUM.get(m.group(1), 0) if m else 0


def check_texts(pairs: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """规则层：pairs = [(时间, 原话), ...]。"""
    items: List[Dict[str, Any]] = []
    patterns = _patterns()
    age_rule = _age_rule()
    for when, text in pairs:
        t = (text or "").strip()
        if not t:
            continue
        for pat, why in patterns:
            m = re.search(pat, t)
            if not m:
                continue
            if age_rule and "年龄" in why:
                age = _extract_age(t)
                if not age:
                    continue
                words = age_rule.get("entry_words") or []
                in_entry_ctx = any(w in t for w in words)
                expect = age_rule.get("entry") if in_entry_ctx else age_rule.get("current")
                if expect and age == int(expect):
                    continue
            items.append({"time": when, "text": t[:90], "reason": why})
            break

    # 再叠一层事实锚点（记忆/人设里定义的反向说法）
    try:
        from . import consistency

        entries = [{"source": "chat", "title": w, "content": x} for w, x in pairs]
        for h in consistency.check_anchors(entries):
            items.append(
                {
                    "time": str(h.get("title") or h.get("source") or ""),
                    "text": str(h.get("memory") or "")[:90],
                    "reason": f"与「{h.get('topic')}」相反",
                }
            )
    except Exception:
        pass
    return items[:10]


async def fetch_pairs(days: int = 1, limit: int = 200) -> List[Tuple[str, str]]:
    from nekro_agent.models.db_chat_message import DBChatMessage

    since = datetime.now() - timedelta(days=max(1, days))
    rows = await DBChatMessage.filter(sender_id="-1", create_time__gte=since).order_by("-id").limit(limit)
    out: List[Tuple[str, str]] = []
    for m in rows:
        t = (getattr(m, "content_text", "") or "").strip()
        if not t or t.startswith("[") or t.startswith("(成员") or "撤回了一条消息" in t:
            continue
        ts = getattr(m, "create_time", None)
        when = ts.strftime("%m-%d %H:%M") if hasattr(ts, "strftime") else ""
        out.append((when, t))
    return list(reversed(out))


async def llm_check(pairs: List[Tuple[str, str]], group) -> List[Dict[str, Any]]:
    from nekro_agent.services.agent.openai import gen_openai_chat_response

    facts = facts_text()
    items: List[Dict[str, Any]] = []
    for i in range(0, len(pairs), 6):
        chunk = pairs[i: i + 6]
        prompt = PROMPT.replace("{facts}", facts[:500]).replace(
            "{lines}", "\n".join(f"- {t}" for _, t in chunk)
        )
        try:
            text = await gen_openai_chat_response(
                model=group.CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                api_key=group.API_KEY,
                base_url=group.BASE_URL,
                max_tokens=4000,
            )
        except Exception:
            continue
        try:
            a, b = text.find("{"), text.rfind("}")
            data = json.loads(text[a: b + 1]) if a >= 0 and b > a else {}
            items.extend(list(data.get("items") or []))
        except Exception:
            continue
    return items[:10]


async def run_check(days: int = 1, limit: int = 200, use_llm: bool = True) -> Dict[str, Any]:
    cfg = get_config()
    pairs = await fetch_pairs(days, limit)
    if not pairs:
        return {"ok": False, "error": "没有可分析的发言"}

    items = check_texts(pairs)

    if use_llm:
        try:
            from nekro_agent.core.config import config as na_config

            group = na_config.get_model_group_info(
                str(getattr(na_config, "USE_MODEL_GROUP", "") or "default")
            )
            items.extend(await llm_check(pairs[:24], group))
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 聊天抽检模型层跳过: {exc}")

    dedup: Dict[str, Dict[str, Any]] = {}
    for it in items:
        key = str(it.get("text") or "")[:60]
        if key and key not in dedup:
            dedup[key] = it

    result = {
        "ok": True,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sample": len(pairs),
        "count": len(dedup),
        "items": list(dedup.values())[:10],
    }
    _save_cache(result)
    return result
