"""人设哨兵 - 一致性检查：人设卡 vs 人格记忆 / 其他插件注入。

用一次 LLM 调用对比「人设卡正文」和「人格插件各档记忆条目」，
找出互相矛盾的地方（地点、关系、年龄、身份、禁忌）。

结果缓存到 data/consistency.json，不会每条消息都跑。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .plugin import get_config, plugin

PROMPT = """你在做「人设一致性审查」。

第一步：从【人设卡】里摘出关键事实（家在哪、谁是母亲/家人、年龄、身份、禁忌），
        内部先列一遍，不要输出。
第二步：逐条看【记忆条目】，凡与这些事实**互相矛盾**的，全部列出。
        记忆条目里带 extra/ 前缀的是**其它插件注入的数据**，同样要检查。

只输出 JSON：
{"conflicts":[{"topic":"家在哪","card":"人设卡说……","memory":"记忆说……","source":"tier3/world.json","severity":"high"}]}

没有冲突输出 {"conflicts":[]}。不要解释，不要输出 JSON 以外的内容。

【人设卡】
{card}

【记忆条目】
{memory}
"""


def _data_dir() -> Path:
    d = Path(plugin.get_plugin_data_dir())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path() -> Path:
    return _data_dir() / "consistency.json"


def load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: Dict[str, Any]) -> None:
    _cache_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _card_text() -> str:
    """读当前预设（人设卡）正文。"""
    try:
        from nekro_agent.core.config import config
        from nekro_agent.models.db_preset import DBPreset

        pid = int(getattr(config, "AI_CHAT_DEFAULT_PRESET_ID", 0) or 0)
        preset = None
        if pid:
            preset = await DBPreset.filter(id=pid).first()
        if preset is None:
            preset = await DBPreset.all().order_by("id").first()
        return str(getattr(preset, "content", "") or "") if preset else ""
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 读人设卡失败: {exc}")
        return ""


def memory_entries() -> List[Dict[str, str]]:
    """读人格插件的阶梯记忆（tier1/2/3）。"""
    base = Path(plugin.get_plugin_data_dir()).parent / "NTidal.nekro_persona" / "backgrounds"
    out: List[Dict[str, str]] = []
    extras: List[Dict[str, str]] = []
    for tier in ("tier1", "tier2", "tier3"):
        for f in sorted((base / tier).glob("*.json")):
            if ".bak" in f.name:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows = data.get("entries") if isinstance(data, dict) else data
            for e in rows or []:
                content = str(e.get("content") or "").strip()
                if not content:
                    continue
                out.append(
                    {
                        "source": f"{tier}/{f.name}",
                        "title": str(e.get("title") or e.get("id") or ""),
                        "content": content,
                    }
                )
    # 额外来源（其它插件的数据文件）
    # 长期记忆：最近 7 天的日记摘要也纳入对照
    try:
        daily_dir = base / "longmem" / "daily"
        for f in sorted(daily_dir.glob("*.json"))[-7:]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            summary = str(d.get("summary") or "").strip()
            if not summary:
                continue
            out.append(
                {
                    "source": f"longmem/daily/{f.name}",
                    "title": str(d.get("date") or f.stem),
                    "content": summary[:220],
                }
            )
    except Exception:
        pass

    try:
        raw = str(getattr(get_config(), "EXTRA_SOURCES", "") or "")
        patterns = [x.strip() for x in raw.replace("，", ",").replace(",", "\n").splitlines() if x.strip()]
        root = Path(plugin.get_plugin_data_dir()).parent.parent
        for pat in patterns:
            p = Path(pat)
            if not p.is_absolute():
                p = root / pat
            files = list(p.parent.glob(p.name)) if any(ch in pat for ch in "*?[") else ([p] if p.exists() else [])
            for f in files[:5]:
                if ".bak" in f.name or not f.is_file():
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")[:1200]
                extras.append({"source": f"extra/{f.name}", "title": "插件数据", "content": text})
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 读额外来源失败: {exc}")

    return extras + out


def check_anchors(entries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """确定性检查：记忆/插件数据里出现与卡片锚点相反的说法。"""
    try:
        anchors = json.loads(get_config().FACT_ANCHORS or "[]")
    except Exception:
        anchors = []
    found: List[Dict[str, Any]] = []
    for e in entries:
        text = e.get("content", "")
        for a in anchors:
            topic = str(a.get("topic") or "")
            for bad in a.get("reject") or []:
                bad = str(bad)
                if bad and bad in text:
                    found.append(
                        {
                            "topic": topic,
                            "card": f"人设卡与「{bad}」相反",
                            "memory": text[:160],
                            "source": e.get("source", ""),
                            "severity": "high",
                            "kind": "rule",
                        }
                    )
                    break
    return found


async def run_check(max_entries: int = 90, batch: int = 28) -> Dict[str, Any]:
    """记忆 ↔ 人设卡一致性：分批送模型，避免长上下文被截断。"""
    cfg = get_config()
    card = await _card_text()
    entries = memory_entries()
    for _e in entries:
        _e["content"] = str(_e.get("content") or "")[:180]
    if len(entries) > max_entries:
        entries = entries[:max_entries]
    if not card or not entries:
        return {
            "ok": False,
            "error": "没有读到人设卡或记忆条目",
            "card_len": len(card),
            "entries": len(entries),
        }

    rule_conflicts = check_anchors(entries)

    if not bool(getattr(cfg, "USE_LLM_CHECK", True)):
        result = {
            "ok": True,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": "rules-only",
            "entries": len(entries),
            "conflicts": rule_conflicts[:20],
            "count": len(rule_conflicts),
            "sources": [e["source"] for e in entries],
        }
        _save_cache(result)
        return result

    from nekro_agent.core.config import config
    from nekro_agent.services.agent.openai import gen_openai_chat_response

    group_name = str(getattr(config, "USE_MODEL_GROUP", "") or "default")
    group = config.get_model_group_info(group_name)

    conflicts: List[Dict[str, Any]] = []
    errors: List[str] = []
    calls = [0]

    async def judge(chunk_entries) -> None:
        mem_text = "\n".join(
            f"- [{e['source']}] {e['title']}: {e['content']}" for e in chunk_entries
        )
        prompt = PROMPT.replace("{card}", card[:2000]).replace("{memory}", mem_text[:4000])
        calls[0] += 1
        try:
            resp = await gen_openai_chat_response(
                model=group.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": "你只输出 JSON，不要解释。"},
                    {"role": "user", "content": prompt},
                ],
                api_key=group.API_KEY,
                base_url=group.BASE_URL,
                max_tokens=2000,
                extra_body={"thinking": {"type": "disabled"},
                            "response_format": {"type": "json_object"}},
            )
        except Exception as exc:  # noqa: BLE001
            if len(chunk_entries) > 4:
                mid = len(chunk_entries) // 2
                await judge(chunk_entries[:mid])
                await judge(chunk_entries[mid:])
            else:
                errors.append(f"{type(exc).__name__}: {str(exc)[:60]}")
            return
        text = resp if isinstance(resp, str) else str(resp)
        try:
            i, j = text.find("{"), text.rfind("}")
            data = json.loads(text[i: j + 1]) if i >= 0 and j > i else {}
            conflicts.extend(list(data.get("conflicts") or []))
        except Exception:
            errors.append("解析失败")

    for i in range(0, len(entries), batch):
        await judge(entries[i: i + batch])

    all_conflicts = rule_conflicts + conflicts
    result = {
        "ok": True,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": getattr(group, "CHAT_MODEL", ""),
        "entries": len(entries),
        "calls": calls[0],
        "conflicts": all_conflicts[:20],
        "count": len(all_conflicts),
        "rule_conflicts": len(rule_conflicts),
        "llm_conflicts": len(conflicts),
        "errors": errors[:3],
        "sources": [e["source"] for e in entries],
    }
    _save_cache(result)
    return result
