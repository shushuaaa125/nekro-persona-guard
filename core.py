"""人设哨兵 - 扫描、统计与日报。

统计以「天」为单位，并记录每个会话（群/私聊）的明细。
只读消息，不改回复。
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
import asyncio
from pathlib import Path
from typing import Any, Dict, List

from .plugin import GuardConfig, get_config, plugin

ROW_KEYS = ("total", "ai", "conflict", "address", "ellipsis", "long", "len_sum", "particles", "brackets", "scene", "habit")


def _empty_row() -> Dict[str, int]:
    return {k: 0 for k in ROW_KEYS}


def _data_dir() -> Path:
    d = Path(plugin.get_plugin_data_dir())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stats_path() -> Path:
    return _data_dir() / "stats.json"


def _hits_path() -> Path:
    return _data_dir() / "hits.jsonl"


def baseline_path() -> Path:
    return _data_dir() / "baseline.json"


def overrides_path() -> Path:
    return _data_dir() / "habit_overrides.json"


def _state_path() -> Path:
    return _data_dir() / "state.json"


TRIGGER_WORDS = ("人设体检", "哨兵日报", "人设日报", "人设报告", "人设扫描", "查人设")

_CMD_PAT = None


def parse_report_command(text: str):
    """解析「人设体检 [日期]」。返回 (是否指令, 日期 or None)。"""
    import re as _re

    global _CMD_PAT
    t = _re.sub(r"\[@id:\d+;nickname:[^\]]*?\]", "", text or "").strip()
    if _CMD_PAT is None:
        _CMD_PAT = _re.compile(
            r"^(?P<cmd>" + "|".join(TRIGGER_WORDS) + r")"
            r"(?:\s*(?P<date>(?:20\d{2}[-/年])?\d{1,2}[-/月]\d{1,2}日?))?"
            r"[？?。！!~～]*$"
        )
    m = _CMD_PAT.match(t)
    if not m:
        return False, None
    raw = (m.group("date") or "").strip()
    if not raw:
        return True, None

    d = raw.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    parts = [x for x in d.split("-") if x]
    try:
        from datetime import date as _date

        if len(parts) == 3:
            y, mo, dd = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            y, mo, dd = _date.today().year, int(parts[0]), int(parts[1])
        else:
            return True, None
        return True, _date(y, mo, dd).isoformat()
    except Exception:
        return True, None


def is_report_command(text: str) -> bool:
    return parse_report_command(text)[0]


def claim_command(chat_key: str, text: str, window: int = 30) -> bool:
    """同会话同指令在窗口期内只处理一次（钩子与轮询共用）。"""
    import time as _time

    key = f"{chat_key}|{(text or '').strip()}"
    state = load_state()
    recent = dict(state.get("cmd_recent") or {})
    now = _time.time()
    last = float(recent.get(key, 0) or 0)
    if now - last < window:
        return False
    recent[key] = now
    state["cmd_recent"] = {k: v for k, v in recent.items() if now - float(v or 0) < 600}
    save_state(state)
    return True


def mark_cmd_done(msg_id: int) -> None:
    state = load_state()
    done = list(state.get("cmd_done") or [])
    done.append(int(msg_id))
    state["cmd_done"] = done[-50:]
    save_state(state)


def cmd_done_ids() -> set:
    return set(int(x) for x in (load_state().get("cmd_done") or []))


async def send_command_report(chat_key: str, day=None) -> Dict[str, Any]:
    """执行一次「人设体检」：补扫 + 出卡片发到当前会话。可指定日期。"""
    await scan_once()
    data = await report_data(day)
    if int(data.get("total", 0)) <= 0:
        try:
            from nekro_agent.api import message as message_api
            from nekro_agent.schemas.agent_ctx import AgentCtx

            ctx = await AgentCtx.create_by_chat_key(chat_key=chat_key)
            label = day or data.get("date", "")
            await message_api.send_text(chat_key, f"{label} 没有记录。", ctx, record=False)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "reason": "no data", "day": day}

    from nekro_agent.api import message as message_api
    from nekro_agent.schemas.agent_ctx import AgentCtx

    image = render_report_image(data)
    ctx = await AgentCtx.create_by_chat_key(chat_key=chat_key)
    head = (
        f"人设哨兵 · {data.get('date', '')} 日报\n"
        f"消息 {data.get('total', 0)} · 人机味 {data.get('ai', 0)} · 冲突 {data.get('conflict', 0)}"
    )
    await message_api.send_text(chat_key, head, ctx, record=False)
    await message_api.send_image(chat_key, publish_image(image, chat_key), ctx, record=False)
    return {"ok": True, "day": data.get("date")}


def _cfg() -> GuardConfig:
    return get_config()


def _family_of(model: str) -> str:
    m = (model or "").lower()
    for fam in ("gemini", "deepseek", "claude", "gpt", "qwen", "glm", "doubao", "volc",
                "kimi", "moonshot", "grok", "ernie", "wenxin", "hunyuan",
                "spark", "xinghuo", "o1", "reasoner"):
        if fam in m:
            if fam in ("doubao", "volc"):
                return "doubao"
            if fam in ("moonshot",):
                return "kimi"
            if fam in ("wenxin",):
                return "ernie"
            if fam in ("xinghuo",):
                return "spark"
            if fam in ("reasoner",):
                return "o1"
            return fam
    return "generic"


def _na_configs_dir() -> Path:
    return Path(plugin.get_plugin_data_dir()).parent.parent / "configs"


def _channel_model_group(chat_key: str) -> str | None:
    """频道单独覆盖的模型组（enable_USE_MODEL_GROUP 为 true 才生效）。"""
    if not chat_key:
        return None
    adapter = chat_key.split("-", 1)[0] if "-" in chat_key else ""
    if not adapter:
        return None
    path = _na_configs_dir() / "channels" / adapter / f"{chat_key}.yaml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not data.get("enable_USE_MODEL_GROUP"):
        return None
    group = str(data.get("USE_MODEL_GROUP") or "").strip()
    return group or None


def _group_model(model_group: str) -> str:
    try:
        from nekro_agent.core.config import config

        groups = getattr(config, "MODEL_GROUPS", {}) or {}
        item = groups.get(model_group) or groups.get("default") or {}
        if isinstance(item, dict):
            return str(item.get("CHAT_MODEL") or item.get("model") or "")
        return str(getattr(item, "CHAT_MODEL", "") or "")
    except Exception:
        return ""


def active_model(chat_key: str = "") -> tuple[str, str]:
    """当前模型名与族。优先频道覆盖，其次 NA 全局 USE_MODEL_GROUP。"""
    try:
        forced = (getattr(_cfg(), "MODEL_GROUP", "") or "auto").strip()
        if forced and forced.lower() != "auto":
            model = _group_model(forced)
            return (model or "unknown"), _family_of(model)

        group = _channel_model_group(chat_key) if chat_key else None
        if not group:
            from nekro_agent.core.config import config

            group = str(getattr(config, "USE_MODEL_GROUP", "") or "").strip() or "default"
        model = _group_model(group)
        return (model or "unknown"), _family_of(model)
    except Exception:
        pass
    return "unknown", "generic"


# ---------------- 内置预设（用户可改配置覆盖） ----------------
BUILTIN_AI_PHRASES = [
    "我在这儿听着",
    "有事就说",
    "早点睡吧",
    "那就好",
    "太生硬",
    "脑子.{0,4}(还没)?转不过",
    "硬憋",
    "我这不是",
    "作为一个",
    "总而言之",
    "希望能帮到你",
    "还有什么可以帮",
    "你的意思我明白",
    "(这话|这句(话)?)我(记|认|不接|收|留)",
    "(这话|这句(话)?)(说得|有点重|重了|稳|漂亮)",
    "这句话我",
    "我记(下|住|牢|着|一下)",
    "这个账我记着",
    "记住了",
    "记着呢",
    "我盯着|盯着呢|我守着|我听着|我拿笔记|我听见了|我看见了|我看到了",
    "收下了|我收下|收着点",
    "我听你的|都听你的|听你的",
    "没敢",
    "——\\\\s*我",
    "睡吧[，,]?我守着",
    "问别人.{0,6}问自己",
    "还是问自己",
    "行[，,]?我认",
    "我认了",
    "认这个",
    "认得实",
    "认下来",
    "认住该认",
    "就是认了",
    "比刚才(稳|重|轻|平)",
    "比之前(都)?(重|轻|稳|平)",
    "声音没抖",
    "很平",
    "挺稳",
    "我不拦",
    "我不催",
    "不催你",
    "你自己掂量",
    "你掂量",
    "这个.{0,3}我先不接",
    "没接你那句",
    "话我留着",
    "收不回去",
    "什么心思都写着",
    "比谁都响",
    "你往下讲",
    "回去睡",
    "接的漂亮",
    "有什么(可以|能)(帮|为)(您|你)的?(吗|么|呢)?",
    "希望对(您|你)有(所)?帮助",
    "很高兴(为|能|可以)(您|你)",
    "请问(还)?有(什么|其他)(需要|可以)",
    "如有(任何)?(问题|疑问)",
    "感谢(您|你)的(理解|耐心|反馈|支持)",
    "非常抱歉(给|为)(您|你)",
    "让(您|你)久等了",
    "请(您|你)稍等",
    "总的来说",
    "综上所述",
    "值得注意的是",
    "需要注意的是",
    "这是一个(很好|复杂|重要)的问题",
    "我可以(帮|为)(您|你)",
    "建议(您|你)(可以|不妨)",
    "需要我(帮|为)(您|你)",
    "作为(一个)?(AI|人工智能|助手|语言模型)",
    "我(只)?是一个(程序|模型|助手)",
    "如果(您|你)(还)?有(需要|疑问)",
    "希望(这|以上)(对|能)",
    "下面(我)?(来|将)(介绍|说明)",
    "首先[，,].{0,12}其次"
]

BUILTIN_CONFLICT = ["我是AI", "我是个语言模型"]

BUILTIN_MODEL_RULES = {
    "qwen": [
        "以下是",
        "根据您",
        "建议您",
        "希望对您有帮助",
        "如有其他问题",
        "欢迎随时提问",
        "需要注意的是",
        "如果你需要",
        "我可以为您",
        "您的",
        "总的来说",
        "首先[，,]",
        "其次[，,]"
    ],
    "deepseek": [
        "这话我记",
        "这话我认",
        "这话我不接",
        "这话我收",
        "这话我留",
        "我记(下|住|牢|着)",
        "认下来",
        "我守着",
        "比刚才",
        "我不拦"
    ],
    "doubao": [
        "好呀好呀",
        "当然啦",
        "可以呀",
        "没问题呀",
        "宝子",
        "亲~",
        "让我想想哈",
        "我懂你的意思啦",
        "你放心好啦",
        "首先呢",
        "然后呢",
        "最后呀",
        "要不我们",
        "我们可以这样",
        "希望(可以|能)帮到你呀",
        "还有什么(问题|需要)随时(问我|找我)哦?",
        "随时找我呀"
    ],
    "glm": [
        "以下是",
        "需要注意的是",
        "希望对您有帮助",
        "如果您需要",
        "我将",
        "我们可以",
        "您的",
        "总的来说",
        "首先[，,]",
        "其次[，,]",
        "值得一提的是"
    ],
    "gemini": [
        "当然可以",
        "希望这能",
        "希望对你(有)?帮助",
        "需要注意的是",
        "让我来",
        "以下(是|几点)",
        "如果你愿意",
        "这是一个很好的问题",
        "让我们",
        "首先[，,]",
        "其次[，,]",
        "最后[，,]",
        "总的来说",
        "值得注意的是",
        "我理解你的意思",
        "你可以试试",
        "建议你",
        "简单来说",
        "换句话说",
        "如有需要",
        "需要我(帮|为)",
        "还有什么(可以|需要)",
        "很高兴(能|为)",
        "我建议"
    ],
    "generic": [
        "作为AI",
        "希望能帮到你",
        "我来帮你"
    ],
    "gpt": [
        "作为一个AI",
        "作为一个语言模型",
        "以下是",
        "总结一下",
        "需要注意的是",
        "值得一提的是",
        "更重要的是",
        "希望对你有帮助",
        "如果你需要",
        "让我为你",
        "我可以帮你",
        "总的来说",
        "首先[，,]",
        "其次[，,]",
        "最后[，,]",
        "简单来说",
        "换句话说",
        "我无法",
        "抱歉[，,]"
    ],
    "claude": [
        "某种程度上",
        "或许",
        "也许",
        "似乎",
        "我觉得",
        "我理解",
        "我明白",
        "让我(想|想想)",
        "不妨",
        "这让我想到",
        "真正的问题是",
        "重要的是",
        "说到底",
        "归根结底",
        "不仅.{0,12}而且",
        "这意味着",
        "从某种意义",
        "一方面.{0,20}另一方面",
        "坦率地说",
        "说实话",
        "诚然",
        "我注意到",
        "你可能(会)?发现",
        "我倾向于"
    ],
    "kimi": [
        "让我(来)?(帮|为)你(梳理|整理)",
        "可以这样理解",
        "先(给|说)结论",
        "分成(几|以下)点",
        "简单来说",
        "以下(是|有)",
        "希望(对你|对你有)帮助",
        "我来(帮|为)你(总结|分析)",
        "这样(安排|理解)(是否)?可以"
    ],
    "grok": [
        "哈哈",
        "说实话",
        "老实说",
        "直说吧",
        "开个玩笑",
        "别担心",
        "不(妨|如)直接(说|讲)",
        "我(可以)?直接(说|告诉)"
    ],
    "ernie": [
        "根据我的了解",
        "据我所知",
        "为您解答",
        "下面(我)?(将|来)(介绍|说明|解答)",
        "希望以上(回答|内容)",
        "如果您还(有|需要)",
        "总的来说",
        "需要注意的是"
    ],
    "hunyuan": [
        "有什么可以帮(你|您)",
        "请(告诉我|随时告诉我)",
        "我会(尽力|尽量)",
        "希望对(你|您)有帮助",
        "需要我(帮|为)(你|您)",
        "随时(可以)?(问我|找我)"
    ],
    "spark": [
        "我是讯飞星火",
        "请问有什么可以帮(您|你)",
        "为您提供",
        "希望对(您|你)有帮助",
        "如(需|有)帮助",
        "您还(有|需要)",
        "我可以帮(您|你)(解答|解决)"
    ],
    "o1": [
        "让我(先)?(仔细)?(分析|思考)一下",
        "首先[，,].{0,10}我们需要",
        "从逻辑上",
        "可以推导出",
        "因此[，,].{0,8}得出结论",
        "综上所述",
        "让我(分步|逐步)"
    ]
}

# 审计类 LLM 调用同一时间只允许一轮，避免群刷屏时把配额打穿
LLM_LOCK = asyncio.Lock()


async def run_exclusive(fn, *args, **kwargs):
    """同一时间只跑一轮审计；已经在跑就跳过，不排队。"""
    if LLM_LOCK.locked():
        return {"ok": False, "error": "已有一轮审计在跑，本次跳过"}
    async with LLM_LOCK:
        return await fn(*args, **kwargs)


def model_rules() -> Dict[str, List[str]]:
    """模型腔：配置为空时用内置预设。"""
    data = {}
    try:
        raw = str(getattr(_cfg(), "MODEL_RULES_JSON", "") or "").strip()
        if raw and raw not in ("{}", "null"):
            data = json.loads(raw)
    except Exception:
        data = {}
    if not data:
        data = BUILTIN_MODEL_RULES
    return {str(k): [str(x) for x in (v or [])] for k, v in data.items()}


# ---------------- 规则 ----------------


def load_rules() -> Dict[str, Any]:
    raw = _cfg().RULES_JSON or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    base_ai = [str(x) for x in (data.get("ai_phrases") or []) if str(x).strip()]
    if not base_ai:
        base_ai = list(BUILTIN_AI_PHRASES)
    _model, family = active_model()
    extra = model_rules().get(family) or []
    merged: List[str] = []
    for p in base_ai + extra:
        if p not in merged:
            merged.append(p)
    return {
        "ai_phrases": merged,
        "conflict_patterns": [str(x) for x in (data.get("conflict_patterns") or []) if str(x).strip()]
        or list(BUILTIN_CONFLICT),
        "address_words": [str(x) for x in (data.get("address_words") or []) if str(x).strip()],
    }


def save_rules(rules: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _cfg()
    cfg.RULES_JSON = json.dumps(rules, ensure_ascii=False, indent=2)
    plugin.save_config(cfg)
    return rules


def classify_dialects(ai_patterns: List[str]) -> List[str]:
    """把命中的规则归类到「通用 / gemini / deepseek / claude」。"""
    fams: List[str] = []
    mr = model_rules()
    for fam, pats in mr.items():
        if fam == "generic":
            continue
        if any(p in pats for p in ai_patterns):
            fams.append(fam)
    if not fams and ai_patterns:
        fams.append("base")
    return fams


def _should_skip(text: str) -> bool:
    """系统提示/撤回通知/纯媒体占位不算她的话。"""
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("["):
        return True
    if t.startswith("(成员") or t.startswith("（成员"):
        return True
    if "撤回了一条消息" in t:
        return True
    return False


def _compile(patterns: List[str]) -> List["re.Pattern[str]"]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p))
        except re.error:
            out.append(re.compile(re.escape(p)))
    return out


_QUOTE_RE = None


def _strip_quotes(text: str) -> str:
    """引号内的内容视为「引用」，不参与她自己说话的判定。"""
    global _QUOTE_RE
    import re as _re

    if _QUOTE_RE is None:
        _QUOTE_RE = _re.compile(
            r"「[^」]{0,80}」|『[^』]{0,80}』|“[^”]{0,80}”|\"[^\"]{0,80}\"|\'[^\']{0,80}\'"
        )
    return _QUOTE_RE.sub("（引用）", text or "")


def analyze(text: str, rules: Dict[str, Any]) -> Dict[str, Any]:
    t = (text or "").strip()
    if not t:
        return {"ai": [], "conflict": [], "address": False, "ellipsis": False, "long": False}
    scan = _strip_quotes(t)
    ai = [p.pattern for p in _compile(rules["ai_phrases"]) if p.search(scan)]
    conflict = [p.pattern for p in _compile(rules["conflict_patterns"]) if p.search(scan)]

    # 解释/引用语境：不算设定冲突
    if conflict:
        try:
            exempt_raw = str(getattr(_cfg(), "CONFLICT_CONTEXT_EXEMPT", "") or "")
            exempt = [x.strip() for x in exempt_raw.replace("，", ",").split(",") if x.strip()]
            if any(w in t for w in exempt):
                conflict = []
        except Exception:
            pass
    words = rules.get("address_words") or []
    import re as _re

    particle_re = _re.compile(r"[呀呢啦哦嘛～~]|……|\.\.\.|>\.<")
    scene_re = _re.compile(r"仿佛|像是|空气里|光线|声音里|眼底|嘴角|沉默了一?[会儿]|氛围|气息")
    bracket_re = _re.compile(r"[（(][^）)]{1,40}[）)]")
    return {
        "ai": ai,
        "conflict": conflict,
        "address": any(t.startswith(w) for w in words),
        "ellipsis": ("……" in t) or ("..." in t),
        "long": len(t) > 60,
        "particles": bool(particle_re.search(t)),
        "brackets": bool(bracket_re.search(t)),
        "scene": bool(scene_re.search(t)),
        "length": len(t),
    }


# ---------------- 存取 ----------------


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_stats() -> Dict[str, Any]:
    return _load_json(_stats_path(), {})


def load_state() -> Dict[str, Any]:
    return _load_json(_state_path(), {})


def save_state(state: Dict[str, Any]) -> None:
    _save_json(_state_path(), state)


def append_hit(hit: Dict[str, Any]) -> None:
    cfg = _cfg()
    path = _hits_path()
    lines: List[str] = []
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []
    lines.append(json.dumps(hit, ensure_ascii=False))
    if len(lines) > int(cfg.MAX_RECENT):
        lines = lines[-int(cfg.MAX_RECENT):]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def recent_hits(limit: int = 50) -> List[Dict[str, Any]]:
    path = _hits_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:][::-1]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def record_message(hit: Dict[str, Any], day: str | None = None) -> Dict[str, int]:
    """计进某天统计（默认今天，含会话明细）。"""
    stats = load_stats()
    today = day or date.today().isoformat()
    day = stats.setdefault(today, {})
    for k in ROW_KEYS:
        day.setdefault(k, 0)
    day.setdefault("chats", {})
    day.setdefault("models", {})

    model_name, family = active_model(str(hit.get("chat_key") or ""))
    hit.setdefault("model", model_name)
    hit.setdefault("family", family)
    model_row = day["models"].setdefault(family, _empty_row())

    chat_key = str(hit.get("chat_key") or "unknown")
    chat = day["chats"].setdefault(chat_key, _empty_row())
    chat["model"] = model_name
    chat["family"] = family
    day.setdefault("dialects", {})
    chat.setdefault("dialects", {})
    for fam in hit.get("families") or []:
        day["dialects"][fam] = int(day["dialects"].get(fam, 0)) + 1
        chat["dialects"][fam] = int(chat["dialects"].get(fam, 0)) + 1
    counts = chat.setdefault("model_counts", {})
    counts[family] = int(counts.get(family, 0)) + 1

    for bucket in (day, chat, model_row):
        bucket["total"] = int(bucket.get("total", 0)) + 1
        if hit.get("ai"):
            bucket["ai"] = int(bucket.get("ai", 0)) + 1
        if hit.get("habit"):
            bucket["habit"] = int(bucket.get("habit", 0)) + 1
        if hit.get("conflict"):
            bucket["conflict"] = int(bucket.get("conflict", 0)) + 1
        if hit.get("address"):
            bucket["address"] = int(bucket.get("address", 0)) + 1
        if hit.get("ellipsis"):
            bucket["ellipsis"] = int(bucket.get("ellipsis", 0)) + 1
        if hit.get("long"):
            bucket["long"] = int(bucket.get("long", 0)) + 1
        if hit.get("particles"):
            bucket["particles"] = int(bucket.get("particles", 0)) + 1
        if hit.get("brackets"):
            bucket["brackets"] = int(bucket.get("brackets", 0)) + 1
        if hit.get("scene"):
            bucket["scene"] = int(bucket.get("scene", 0)) + 1
        bucket["len_sum"] = int(bucket.get("len_sum", 0)) + int(hit.get("length", 0) or 0)

    keep = int(_cfg().KEEP_DAYS)
    cutoff = (date.today() - timedelta(days=keep)).isoformat()
    for k in list(stats.keys()):
        if k < cutoff:
            stats.pop(k, None)

    _save_json(_stats_path(), stats)

    if hit.get("ai") or hit.get("conflict"):
        append_hit(hit)
    return chat


# ---------------- 会话名 ----------------


def _chat_number(chat_key: str) -> str:
    tail = chat_key.rsplit("_", 1)[-1] if "_" in chat_key else chat_key
    return tail if tail.isdigit() else chat_key


async def chat_names(keys: List[str]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    if not keys:
        return names
    try:
        from nekro_agent.models.db_chat_channel import DBChatChannel

        rows = await DBChatChannel.filter(chat_key__in=keys)
        for r in rows:
            name = getattr(r, "channel_name", "") or ""
            if name.strip():
                names[r.chat_key] = name.strip()
    except Exception:
        pass
    for k in keys:
        if k not in names:
            names[k] = k.replace("onebot_v11-", "").replace("group_", "群").replace("private_", "私聊")
    return names


# ---------------- 扫描 ----------------


async def compute_baseline(days: int = 0) -> Dict[str, Any]:
    """统计她过去 N 天的口癖：哪些 AI 规则其实是她的日常说法。"""
    from datetime import datetime as _dt
    from datetime import time as _time
    from datetime import timedelta as _td

    cfg = _cfg()
    days = int(days or cfg.BASELINE_DAYS or 7)
    try:
        from nekro_agent.models.db_chat_message import DBChatMessage
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    frm = str(getattr(cfg, "BASELINE_FROM", "") or "").strip()
    to = str(getattr(cfg, "BASELINE_TO", "") or "").strip()
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Shanghai")
    if frm:
        start = _dt.combine(date.fromisoformat(frm), _time.min, tzinfo=tz)
        end = _dt.combine(date.fromisoformat(to), _time.max, tzinfo=tz) if to else _dt.now(tz)
    else:
        start = _dt.now(tz) - _td(days=days)
        end = _dt.now(tz)

    try:
        rows = await DBChatMessage.filter(
            sender_id="-1", create_time__gte=start, create_time__lte=end
        ).order_by("-id").limit(5000)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    texts = []
    for m in rows:
        t = (getattr(m, "content_text", "") or "").strip()
        if t and not t.startswith("["):
            texts.append(t)

    rules = load_rules()
    patterns = _compile(rules["ai_phrases"])
    counts: Dict[str, int] = {}
    for pat in patterns:
        n = sum(1 for t in texts if pat.search(t))
        if n:
            counts[pat.pattern] = n

    # 顺便算她的真实语气词率与平均句长（给匹配度当目标）
    particle_re = _compile(["[" + "\\u5440\\u5462\\u5566\\u54e6\\u561b\\uff5e~" + "]|……|\\.\\.\\.|>\\.<"])[0]
    particles = sum(1 for t in texts if particle_re.search(t))
    particle_rate = round(particles / len(texts), 4) if texts else 0.0
    avg_len = round(sum(len(t) for t in texts) / len(texts), 2) if texts else 0.0

    min_hits = int(cfg.HABIT_MIN_HITS or 5)
    habits = [p for p, n in counts.items() if n >= min_hits]
    ov = load_overrides()
    habits = [p for p in habits if p not in set(ov.get("exclude") or [])]
    for extra in ov.get("include") or []:
        if extra not in habits:
            habits.append(extra)

    data = {
        "ok": True,
        "computed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
        "days": days,
        "messages": len(texts),
        "particle_rate": particle_rate,
        "avg_len": avg_len,
        "counts": counts,
        "habits": habits,
        "min_hits": min_hits,
    }
    _save_json(baseline_path(), data)
    return data


def load_overrides() -> Dict[str, Any]:
    data = _load_json(overrides_path(), {})
    return {
        "exclude": [str(x) for x in (data.get("exclude") or [])],
        "include": [str(x) for x in (data.get("include") or [])],
    }


def save_overrides(mode: str, pattern: str) -> Dict[str, Any]:
    data = load_overrides()
    for key in ("exclude", "include"):
        data[key] = [x for x in data[key] if x != pattern]
    if mode in ("exclude", "include"):
        data[mode].append(pattern)
    _save_json(overrides_path(), data)
    return data


def load_baseline() -> Dict[str, Any]:
    return _load_json(baseline_path(), {})


def habit_set() -> set:
    cfg = _cfg()
    if not bool(getattr(cfg, "HABIT_ENABLED", True)):
        return set()
    ov = load_overrides()
    habits = set(load_baseline().get("habits") or [])
    habits -= set(ov.get("exclude") or [])
    habits |= set(ov.get("include") or [])
    return habits


def split_drift(ai_patterns: List[str]) -> tuple:
    """把命中拆成「漂移（计入）」和「习惯（忽略）」两组。"""
    habits = habit_set()
    drift = [p for p in ai_patterns if p not in habits]
    habit = [p for p in ai_patterns if p in habits]
    return drift, habit


async def recent_new_rules(days: int = 7) -> Dict[str, Any]:
    """最近 N 天出现、但基线里没有的说法 —— 真正的漂移信号。"""
    from datetime import timedelta as _td

    try:
        from nekro_agent.models.db_chat_message import DBChatMessage
        from zoneinfo import ZoneInfo
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    tz = ZoneInfo("Asia/Shanghai")
    start = datetime.now(tz) - _td(days=days)
    try:
        rows = await DBChatMessage.filter(
            sender_id="-1", create_time__gte=start
        ).order_by("-id").limit(3000)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    texts = [
        (getattr(m, "content_text", "") or "").strip()
        for m in rows
        if (getattr(m, "content_text", "") or "").strip()
        and not (getattr(m, "content_text", "") or "").startswith("[")
    ]
    rules = load_rules()
    base_counts = load_baseline().get("counts") or {}
    habits = habit_set()
    fresh = []
    for pat in _compile(rules["ai_phrases"]):
        if pat.pattern in habits:
            continue
        n = sum(1 for t in texts if pat.search(t))
        if n <= 0:
            continue
        fresh.append({
            "pattern": pat.pattern,
            "recent": n,
            "baseline": int(base_counts.get(pat.pattern, 0)),
            "is_new": int(base_counts.get(pat.pattern, 0)) == 0,
        })
    fresh.sort(key=lambda x: (-int(x["is_new"]), -x["recent"]))
    return {"ok": True, "days": days, "messages": len(texts), "items": fresh[:30]}


async def scan_once() -> Dict[str, Any]:
    cfg = _cfg()
    if not cfg.ENABLED:
        return {"skipped": True}

    try:
        from nekro_agent.models.db_chat_message import DBChatMessage
    except Exception:
        return {"error": "no db model"}

    state = load_state()
    last_id = int(state.get("last_id") or 0)

    if not state.get("baseline_done"):
        try:
            newest = await DBChatMessage.filter(sender_id="-1").order_by("-id").first()
            state["last_id"] = int(getattr(newest, "id", 0) or 0) if newest else 0
            if not state.get("last_user_id"):
                newest_u = await DBChatMessage.filter(sender_id__not="-1").order_by("-id").first()
                state["last_user_id"] = int(getattr(newest_u, "id", 0) or 0) if newest_u else 0
            state["baseline_done"] = True
            save_state(state)
            return {"baseline": True, "last_id": state["last_id"]}
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 初始化基线失败: {exc}")
            return {"error": str(exc)}

    try:
        rows = await DBChatMessage.filter(sender_id="-1", id__gt=last_id).order_by("id").limit(300)
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 查询消息失败: {exc}")
        return {"error": str(exc)}

    rules = load_rules()
    scanned = 0
    last_row = None
    for m in rows:
        last_row = m
        text = getattr(m, "content_text", "") or ""
        if _should_skip(text):
            continue
        hit = analyze(text, rules)
        drift, habit = split_drift(hit.get("ai") or [])
        hit["ai"], hit["habit"] = drift, habit
        hit["families"] = classify_dialects(drift)
        hit.update(
            {
                "id": getattr(m, "id", 0),
                "chat_key": getattr(m, "chat_key", ""),
                "time": (getattr(m, "create_time", None) or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                "text": text[:120],
            }
        )
        record_message(hit)
        scanned += 1

    if last_row is not None:
        state["last_id"] = int(getattr(last_row, "id", last_id))
        save_state(state)

    # ---- 扫用户消息里的「说她人机」 ----
    complaints = 0
    try:
        from types import SimpleNamespace

        from . import complaint

        state = load_state()
        last_uid = int(state.get("last_user_id") or 0)
        urows = await DBChatMessage.filter(
            id__gt=last_uid, sender_id__not="-1"
        ).order_by("id").limit(300)
        for m in urows:
            text = getattr(m, "content_text", "") or ""
            hit, _reason = complaint.detect(text, bool(getattr(m, "is_tome", 0)))
            if hit:
                await complaint.handle(
                    SimpleNamespace(chat_key=getattr(m, "chat_key", "")), m
                )
                complaints += 1
            elif _reason == "no-target":
                complaint._append_shadow({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "chat_key": str(getattr(m, "chat_key", "") or ""),
                    "sender": str(getattr(m, "sender_nickname", "") or ""),
                    "text": text[:80],
                    "reason": _reason,
                })
        if urows:
            state["last_user_id"] = int(getattr(urows[-1], "id", last_uid))
            save_state(state)
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 用户消息扫描失败: {exc}")

    return {"scanned": scanned, "last_id": state.get("last_id"), "complaints": complaints}


async def backfill_day(day: str) -> Dict[str, Any]:
    """回溯分析某一天的历史消息，写入那一天的统计（用于补齐旧数据）。"""
    try:
        from datetime import datetime as _dt
        from datetime import time as _time
        from zoneinfo import ZoneInfo

        from nekro_agent.models.db_chat_message import DBChatMessage
    except Exception as exc:  # noqa: BLE001
        return {"error": f"import: {exc}"}

    tz = ZoneInfo("Asia/Shanghai")
    start = _dt.combine(date.fromisoformat(day), _time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    try:
        rows = await DBChatMessage.filter(
            sender_id="-1", create_time__gte=start, create_time__lt=end
        ).order_by("id").limit(5000)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    stats = load_stats()
    stats[day] = {**_empty_row(), "chats": {}, "models": {}}
    _save_json(_stats_path(), stats)

    # 清掉这一天的旧命中样本，避免重复
    try:
        hp = _hits_path()
        if hp.exists():
            kept = [
                line for line in hp.read_text(encoding="utf-8").splitlines()
                if line.strip() and f'"time": "{day}' not in line
            ]
            hp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    except Exception:
        pass

    rules = load_rules()
    scanned = 0
    for m in rows:
        text = getattr(m, "content_text", "") or ""
        if _should_skip(text):
            continue
        hit = analyze(text, rules)
        drift, habit = split_drift(hit.get("ai") or [])
        hit["ai"], hit["habit"] = drift, habit
        hit["families"] = classify_dialects(drift)
        hit.update(
            {
                "id": getattr(m, "id", 0),
                "chat_key": getattr(m, "chat_key", ""),
                "time": (getattr(m, "create_time", None) or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                "text": text[:120],
                "backfill": True,
            }
        )
        record_message(hit, day=day)
        scanned += 1
    return {"day": day, "scanned": scanned, "row": load_stats().get(day, {})}


async def scan_user_complaints() -> Dict[str, Any]:
    """只扫用户消息里的「说她人机」，轻量、可高频。"""
    try:
        from types import SimpleNamespace

        from nekro_agent.models.db_chat_message import DBChatMessage

        from . import complaint
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    state = load_state()
    last_uid = int(state.get("last_user_id") or 0)
    try:
        rows = await DBChatMessage.filter(
            id__gt=last_uid, sender_id__not="-1"
        ).order_by("id").limit(100)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    hits = 0
    for m in rows:
        text = getattr(m, "content_text", "") or ""
        # 指令词优先：整句「人设体检」等
        _is_cmd, _cmd_day = parse_report_command(text)
        if _is_cmd:
            try:
                _ck = str(getattr(m, "chat_key", "") or "")
                if claim_command(_ck, text):
                    await send_command_report(_ck, _cmd_day)
                    mark_cmd_done(int(getattr(m, "id", 0) or 0))
            except Exception as exc:  # noqa: BLE001
                plugin.logger.warning(f"[persona_guard] 轮询出日报失败: {exc}")
            continue

        hit, reason = complaint.detect(text, bool(getattr(m, "is_tome", 0)))
        if hit:
            await complaint.handle(SimpleNamespace(chat_key=getattr(m, "chat_key", "")), m)
            hits += 1
        elif reason == "no-target":
            complaint._append_shadow({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "chat_key": str(getattr(m, "chat_key", "") or ""),
                "sender": str(getattr(m, "sender_nickname", "") or ""),
                "text": text[:80],
                "reason": reason,
            })
    if rows:
        state["last_user_id"] = int(getattr(rows[-1], "id", last_uid))
        save_state(state)
    return {"checked": len(rows), "hits": hits}


async def complaint_loop() -> None:
    """高频轻量轮询：被说人机时尽快发日报。"""
    await asyncio.sleep(5)
    while True:
        try:
            await scan_user_complaints()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 投诉轮询异常: {exc}")
        await asyncio.sleep(max(5, int(_cfg().COMPLAINT_SCAN_SECONDS)))


async def scanner_loop() -> None:
    """持续统计（默认每 120 秒）：保证不漏消息。"""
    await asyncio.sleep(10)
    while True:
        try:
            await scan_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 扫描异常: {exc}")
        await asyncio.sleep(max(30, int(_cfg().SCAN_SECONDS)))


async def reporter_loop() -> None:
    """每天一次日报（默认每天 REPORT_HOUR 点，间隔 24 小时）。"""
    await asyncio.sleep(20)
    while True:
        try:
            cfg = _cfg()
            if cfg.AUTO_REPORT_ENABLED:
                state = load_state()
                now = datetime.now()
                last = state.get("last_report_ts") or 0
                due = (now.timestamp() - float(last)) >= 86400 and now.hour >= int(cfg.REPORT_HOUR)
                if due:
                    await send_daily_report()
                    state = load_state()
                    state["last_report_ts"] = now.timestamp()
                    save_state(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 日报异常: {exc}")
        await asyncio.sleep(600)


# ---------------- 汇报 ----------------


def today_row() -> Dict[str, Any]:
    return load_stats().get(date.today().isoformat(), {**_empty_row(), "chats": {}})


def trend(days: int = 7) -> List[Dict[str, Any]]:
    stats = load_stats()
    out = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = stats.get(d, {})
        out.append(
            {
                "date": d,
                "total": int(row.get("total", 0)),
                "ai": int(row.get("ai", 0)),
                "conflict": int(row.get("conflict", 0)),
            }
        )
    return out


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """把一组统计换算成人设匹配度（0-100）。"""
    cfg = _cfg()
    total = int(row.get("total", 0)) or 0
    if total == 0:
        return {"score": 0, "parts": {}, "total": 0}
    avg_len = float(row.get("len_sum", 0)) / total
    particle_rate = float(row.get("particles", 0)) / total
    bracket_rate = float(row.get("brackets", 0)) / total
    ai_rate = float(row.get("ai", 0)) / total
    cf_rate = float(row.get("conflict", 0)) / total

    base_data = load_baseline()
    target_len = float(base_data.get("avg_len") or cfg.TARGET_LEN)
    mode = str(getattr(cfg, "TARGET_PARTICLE_MODE", "auto") or "auto").lower()
    if mode == "auto":
        target_particle = float(base_data.get("particle_rate") or cfg.TARGET_PARTICLE_RATE)
    else:
        target_particle = float(cfg.TARGET_PARTICLE_RATE)

    s_len = _clamp(100 - abs(avg_len - target_len) * 3.2)
    s_particle = _clamp(100 - abs(particle_rate - target_particle) * 320)
    s_human = _clamp(100 - ai_rate * 320)
    s_setting = _clamp(100 - cf_rate * 600)
    # 对话感 = 少括号动作 + 少长旁白 + 少小说式描写词
    long_rate = float(row.get("long", 0)) / total
    scene_rate = float(row.get("scene", 0)) / total
    s_dialogue = _clamp(
        100 - bracket_rate * 180 - long_rate * 50 - scene_rate * 150
    )

    score = (
        s_len * 0.20
        + s_particle * 0.18
        + s_human * 0.27
        + s_setting * 0.20
        + s_dialogue * 0.15
    )
    return {
        "score": round(score, 1),
        "total": total,
        "avg_len": round(avg_len, 1),
        "particle_rate": round(100 * particle_rate),
        "parts": {
            "句式贴合": round(s_len),
            "口头习惯": round(s_particle),
            "去人机味": round(s_human),
            "设定一致": round(s_setting),
            "对话感": round(s_dialogue),
        },
    }


def _chatcheck_info(day: str) -> Dict[str, Any]:
    try:
        from . import chatcheck

        c = chatcheck.load_cache()
        if not c or c.get("date") != day:
            return {"count": 0, "items": []}
        return {"count": int(c.get("count") or 0), "items": list(c.get("items") or [])[:3]}
    except Exception:
        return {"count": 0, "items": []}


def _shadow_info(day: str) -> Dict[str, Any]:
    try:
        from . import complaint

        items = complaint.load_shadow(limit=30, day=day)
        return {"count": complaint.shadow_count(day), "items": items}
    except Exception:
        return {"count": 0, "items": []}


def _consistency_cache() -> Dict[str, Any]:
    try:
        from . import consistency

        return consistency.load_cache()
    except Exception:
        return {}


def match_report(day: str | None = None) -> Dict[str, Any]:
    day = day or date.today().isoformat()
    row = load_stats().get(day, {})
    overall = _score_row(row)
    min_sample = int(getattr(_cfg(), "MIN_SAMPLE", 20) or 20)
    per_model = []
    for fam, m in (row.get("models") or {}).items():
        sc = _score_row(m)
        if sc["total"] <= 0:
            continue
        per_model.append({"family": fam, **sc})
    per_model.sort(key=lambda x: x["score"], reverse=True)
    model_name, family = active_model()
    insufficient = int(overall.get("total", 0)) < min_sample
    base_data = load_baseline()
    cfg2 = _cfg()
    target_len = float(base_data.get("avg_len") or cfg2.TARGET_LEN)
    if str(getattr(cfg2, "TARGET_PARTICLE_MODE", "auto")).lower() == "auto":
        target_particle = float(base_data.get("particle_rate") or cfg2.TARGET_PARTICLE_RATE) * 100
    else:
        target_particle = float(cfg2.TARGET_PARTICLE_RATE) * 100

    return {
        "insufficient": insufficient,
        "total": int(overall.get("total", 0)),
        "min_sample": min_sample,
        "target_len": round(target_len, 1),
        "target_particle": round(target_particle, 1),
        "score": overall["score"],
        "parts": {} if insufficient else overall["parts"],
        "avg_len": overall.get("avg_len"),
        "particle_rate": overall.get("particle_rate"),
        "model": model_name,
        "family": family,
        "current": next((x for x in per_model if x["family"] == family), None),
        "per_model": per_model,
    }


async def report_data(day: str | None = None) -> Dict[str, Any]:
    day = day or date.today().isoformat()
    stats = load_stats()
    row = stats.get(day, {})
    chats = row.get("chats", {}) or {}
    keys = list(chats.keys())
    names = await chat_names(keys)
    items = []
    for k in keys:
        c = chats[k] or {}
        items.append(
            {
                "chat_key": k,
                "name": names.get(k, k),
                "model": str(c.get("model") or ""),
                "family": str(c.get("family") or ""),
                "total": int(c.get("total", 0)),
                "ai": int(c.get("ai", 0)),
                "conflict": int(c.get("conflict", 0)),
                "address": int(c.get("address", 0)),
                "ellipsis": int(c.get("ellipsis", 0)),
                "long": int(c.get("long", 0)),
            }
        )
    items.sort(key=lambda x: (x["ai"] + x["conflict"], x["total"]), reverse=True)
    model_name, family = active_model()
    models = [
        {"family": fam, **{k: int(v.get(k, 0)) for k in ROW_KEYS}}
        for fam, v in (row.get("models") or {}).items()
    ]
    models.sort(key=lambda x: x["total"], reverse=True)
    hits = [h for h in recent_hits(200) if str(h.get("time", "")).startswith(day)]
    hits.sort(key=lambda h: str(h.get("time", "")), reverse=True)

    # 给命中样本补「哪个群 / 哪个私聊」
    hit_names = await chat_names(list({str(h.get("chat_key") or "") for h in hits}))
    for h in hits:
        key = str(h.get("chat_key") or "")
        h["chat_name"] = hit_names.get(key, key)
        h["chat_no"] = _chat_number(key)
        h["chat_kind"] = "私聊" if "private" in key else "群"
    return {
        "date": day,
        "total": int(row.get("total", 0)),
        "ai": int(row.get("ai", 0)),
        "conflict": int(row.get("conflict", 0)),
        "address": int(row.get("address", 0)),
        "ellipsis": int(row.get("ellipsis", 0)),
        "long": int(row.get("long", 0)),
        "habit": int(row.get("habit", 0)),
        "chats": items,
        "models": models,
        "model": model_name,
        "model_family": family,
        "match": match_report(day),
        "habits": {"habits": list(habit_set()), "baseline": {k: v for k, v in load_baseline().items() if k != "counts"}},
        "dialects": {k: int(v) for k, v in (row.get("dialects") or {}).items()},
        "consistency": _consistency_cache(),
        "shadow": _shadow_info(day),
        "chatcheck": _chatcheck_info(day),
        "hits": hits[:6],
    }


def _resolve_theme() -> str:
    cfg = _cfg()
    # 只做夜版：不管配置和时间，一律深色
    return "dark"


def publish_image(path: str, chat_key: str) -> str:
    """把图拷进 uploads/<chat_key>/，返回可被 NA 转换的 /app/uploads 路径。"""
    try:
        import shutil

        from nekro_agent.core.os_env import USER_UPLOAD_DIR

        safe_key = "".join(c if c.isalnum() or c in "-_." else "_" for c in (chat_key or "misc"))
        up = Path(USER_UPLOAD_DIR) / safe_key
        up.mkdir(parents=True, exist_ok=True)
        src = Path(path)
        dst = up / f"persona_guard_{src.stem}_{int(datetime.now().timestamp())}.png"
        shutil.copyfile(src, dst)
        return f"/app/uploads/{dst.name}"
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 图片发布失败: {exc}")
        return path


def render_report_image(data: Dict[str, Any], theme: str = "", layout: str = "", font: str = "") -> str:
    cfg = _cfg()
    t = theme or _resolve_theme()
    lay = (layout or str(getattr(cfg, "CARD_LAYOUT", "mobile") or "mobile")).strip().lower()
    if lay not in ("mobile", "desktop"):
        lay = "mobile"
    avatar_path = _data_dir() / "assets" / "avatar.png"
    tf = (font or str(getattr(cfg, "CARD_TITLE_FONT", "smiley") or "smiley")).strip().lower()
    path = _data_dir() / f"report_{lay}_{t}_{tf}.png"
    kwargs = dict(
        theme=t,
        avatar_url=str(getattr(cfg, "AVATAR_URL", "") or ""),
        avatar_path=avatar_path if avatar_path.exists() else None,
        title_font=tf,
    )
    if lay == "desktop":
        from .render import render_report_card

        render_report_card(data, path, **kwargs)
    else:
        from .render_mobile import render_mobile_card

        render_mobile_card(data, path, **kwargs)
    return str(path)


async def _maybe_chatcheck() -> None:
    try:
        from . import chatcheck

        if bool(getattr(_cfg(), "CHATCHECK_ENABLED", True)):
            await run_exclusive(chatcheck.run_check, 1,
                                int(getattr(_cfg(), "CHATCHECK_LIMIT", 40)))
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 聊天事实抽检跳过: {exc}")


async def send_daily_report(chat_keys: str | None = None, day: str | None = None) -> Dict[str, Any]:
    cfg = _cfg()
    keys_raw = chat_keys if chat_keys is not None else (cfg.REPORT_CHAT_KEYS or cfg.ALERT_CHAT_KEYS or "")
    keys = [x.strip() for x in keys_raw.replace("，", ",").split(",") if x.strip()]
    data = await report_data(day)
    if data["total"] <= 0:
        return {"skipped": "no data"}
    image_path = render_report_image(data)

    from nekro_agent.api import message as message_api
    from nekro_agent.schemas.agent_ctx import AgentCtx

    sent = []
    await _maybe_chatcheck()
    for key in keys:
        try:
            ctx = await AgentCtx.create_by_chat_key(chat_key=key)
            head = (
                f"人设哨兵 · {data.get('date', '')} 日报\n"
                f"消息 {data.get('total', 0)} · 人机味 {data.get('ai', 0)} · 冲突 {data.get('conflict', 0)}"
            )
            await message_api.send_text(key, head, ctx, record=False)
            await message_api.send_image(key, publish_image(image_path, key), ctx, record=False)
            sent.append(key)
        except Exception as exc:  # noqa: BLE001
            plugin.logger.warning(f"[persona_guard] 日报发送失败 {key}: {exc}")
    return {"sent": sent, "data": data}
