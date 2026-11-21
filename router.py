"""人设哨兵 - WebUI 与 API。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, HTMLResponse

from .plugin import GuardConfig, plugin

_HERE = Path(__file__).parent


@plugin.mount_router()
def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/panel", summary="人设哨兵面板", include_in_schema=False)
    async def panel():
        return HTMLResponse((_HERE / "webui.html").read_text(encoding="utf-8"))

    @router.get("/api/stats", summary="今日与近七日统计")
    async def api_stats(day: str = ""):
        from . import core

        cfg: GuardConfig = plugin.get_config(GuardConfig)  # type: ignore[assignment]
        target = day or None
        row = core.today_row() if not target else (core.load_stats().get(target, {}) or {})
        return {
            "ok": True,
            "day": target or "today",
            "today": row,
            "trend": core.trend(7),
            "recent": core.recent_hits(40),
            "report": await core.report_data(target),
            "rules": core.load_rules(),
            "config": {
                "threshold": cfg.ALERT_THRESHOLD,
                "alert_chat_keys": cfg.ALERT_CHAT_KEYS,
                "scan_seconds": cfg.SCAN_SECONDS,
                "enabled": cfg.ENABLED,
                "auto_report": cfg.AUTO_REPORT_ENABLED,
                "report_hour": cfg.REPORT_HOUR,
            },
        }

    @router.post("/api/rules", summary="保存规则")
    async def api_save_rules(payload: dict = Body(...)):
        from . import core

        rules = core.save_rules(
            {
                "ai_phrases": payload.get("ai_phrases") or [],
                "conflict_patterns": payload.get("conflict_patterns") or [],
                "address_words": payload.get("address_words") or [],
            }
        )
        return {"ok": True, "rules": rules}

    @router.post("/api/model-rules", summary="保存模型特征词")
    async def api_model_rules(payload: dict = Body(...)):
        from .plugin import get_config

        cfg = get_config()
        cfg.MODEL_RULES_JSON = __import__("json").dumps(payload, ensure_ascii=False, indent=2)
        plugin.save_config(cfg)
        from . import core

        return {"ok": True, "rules": core.model_rules()}

    @router.get("/api/baseline", summary="角色习惯基线")
    async def api_baseline_get():
        from . import core

        return {"ok": True, "data": core.load_baseline(), "habits": list(core.habit_set())}

    @router.post("/api/baseline/run", summary="重算角色习惯基线")
    async def api_baseline_run(payload: dict = Body(default={})):
        from . import core
        from .plugin import GuardConfig

        cfg = plugin.get_config(GuardConfig)
        if "from" in payload:
            cfg.BASELINE_FROM = str(payload.get("from") or "")
        if "to" in payload:
            cfg.BASELINE_TO = str(payload.get("to") or "")
        plugin.save_config(cfg)
        return {"ok": True, "result": await core.compute_baseline(int(payload.get("days") or 0))}

    @router.post("/api/baseline/override", summary="手动加入/排除习惯")
    async def api_baseline_override(payload: dict = Body(...)):
        from . import core

        pattern = str(payload.get("pattern") or "")
        mode = str(payload.get("mode") or "")
        if not pattern:
            return {"ok": False, "error": "pattern 不能为空"}
        data = core.save_overrides(mode, pattern)
        return {"ok": True, "data": data, "habits": sorted(core.habit_set())}

    @router.get("/api/baseline/recent", summary="最近新出现的说法")
    async def api_baseline_recent(days: int = 7):
        from . import core

        return {"ok": True, "data": await core.recent_new_rules(days)}

    @router.post("/api/complaint/test", summary="模拟一条「人机」投诉")
    async def api_complaint_test(payload: dict = Body(...)):
        from . import complaint

        text = str(payload.get("text") or "这 bot 怎么这么人机")
        is_tome = bool(payload.get("is_tome", False))
        hit, reason = complaint.detect(text, is_tome)
        if bool(payload.get("log_shadow")) and not hit and reason == "no-target":
            from datetime import datetime as _dt

            complaint._append_shadow({
                "time": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                "chat_key": str(payload.get("chat_key") or "onebot_v11-group_1017573682"),
                "sender": str(payload.get("nick") or "测试"),
                "text": text[:80],
                "reason": reason,
            })
        return {"ok": True, "hit": hit, "reason": reason}

    @router.post("/api/complaint/preview", summary="预览群回执措辞（可只发自己）")
    async def api_complaint_preview(payload: dict = Body(default={})):
        from . import core
        from .plugin import GuardConfig

        cfg = plugin.get_config(GuardConfig)
        when = str(payload.get("time") or "").strip()
        if not when:
            from datetime import datetime as _dt

            when = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        ai = payload.get("ai")
        conflict = payload.get("conflict")
        if ai is None:
            data = await core.report_data(payload.get("day") or None)
            ai, conflict = data.get("ai", 0), data.get("conflict", 0)
        import random

        pool_raw = str(payload.get("template") or cfg.COMPLAINT_GROUP_TEXT or "").strip()
        pool = [x.strip() for x in pool_raw.split("|") if x.strip()] or ["诶？人机？我…我吗？"]
        pick = payload.get("pick")
        head = pool[int(pick)] if isinstance(pick, int) and 0 <= pick < len(pool) else random.choice(pool)
        tail_tpl = str(cfg.COMPLAINT_GROUP_TAIL or "").strip() or "（{time}）今天 {ai} 次"
        tail = (
            tail_tpl.replace("{time}", when)
            .replace("{ai}", str(ai))
            .replace("{conflict}", str(conflict))
        )
        text = head + ("\n" + tail if tail else "")
        sent = False
        if bool(payload.get("send_private")):
            keys = [
                x.strip()
                for x in str(cfg.COMPLAINT_ALERT_CHAT_KEYS or cfg.REPORT_CHAT_KEYS or cfg.ALERT_CHAT_KEYS or "")
                .replace("，", ",")
                .split(",")
                if x.strip()
            ]
            if keys:
                from nekro_agent.api import message as message_api
                from nekro_agent.schemas.agent_ctx import AgentCtx

                for key in keys:
                    try:
                        actx = await AgentCtx.create_by_chat_key(chat_key=key)
                        await message_api.send_text(key, text, actx, record=False)
                        sent = True
                    except Exception as exc:  # noqa: BLE001
                        plugin.logger.warning(f"[persona_guard] 预览发送失败 {key}: {exc}")
        return {"ok": True, "text": text, "sent_private": sent}

    @router.get("/api/vibe", summary="语感抽检结果")
    async def api_vibe_get():
        from . import vibe

        return {"ok": True, "data": vibe.load_cache()}

    @router.post("/api/vibe/run", summary="跑一次语感抽检（LLM）")
    async def api_vibe_run(payload: dict = Body(default={})):
        from . import vibe

        return {
            "ok": True,
            "result": await vibe.run_check(
                int(payload.get("days") or 1), int(payload.get("limit") or 30)
            ),
        }

    @router.post("/api/debug/write-life", summary="导入生活状态（内部用）")
    async def api_write_life(payload: dict = Body(default={})):
        import json as _json

        from nekro_agent.models.db_plugin_data import DBPluginData

        data = payload.get("data")
        if not isinstance(data, dict):
            return {"ok": False, "error": "data 必须是对象"}
        key = {"plugin_key": "NTidal.nekro_persona", "data_key": "life_state",
               "target_chat_key": "global"}
        value = _json.dumps(data, ensure_ascii=False)
        row = await DBPluginData.filter(**key).first()
        if row:
            row.data_value = value
            await row.save()
        else:
            await DBPluginData.create(data_value=value, target_user_id="", **key)
        return {"ok": True, "len": len(value)}

    @router.get("/api/chatcheck", summary="聊天事实抽检结果")
    async def api_chatcheck_get():
        from . import chatcheck

        return {"ok": True, "data": chatcheck.load_cache()}

    @router.post("/api/chatcheck/run", summary="跑一次聊天事实抽检")
    async def api_chatcheck_run(payload: dict = Body(default={})):
        from . import chatcheck

        return {
            "ok": True,
            "result": await chatcheck.run_check(
                int(payload.get("days") or 1),
                int(payload.get("limit") or 200),
                bool(payload.get("use_llm", True)),
            ),
        }

    @router.get("/api/shadow", summary="疑似漏检（有人机字样但没命中）")
    async def api_shadow(limit: int = 30, day: str = ""):
        from . import complaint

        return {"ok": True, "items": complaint.load_shadow(limit, day)}

    @router.get("/api/complaint/log", summary="人机投诉判定日志")
    async def api_complaint_log(limit: int = 30):
        from . import complaint

        return {"ok": True, "items": complaint.load_log(limit)}

    @router.post("/api/complaint/send", summary="按一条投诉真实触发一次日报")
    async def api_complaint_send(payload: dict = Body(...)):
        from . import complaint

        class _Msg:
            def __init__(self, t, tome, nick):
                self.content_text = t
                self.is_tome = tome
                self.sender_nickname = nick
                self.sender_name = nick
                self.sender_id = "test"
                self.chat_key = ""

        class _Ctx:
            def __init__(self, key):
                self.chat_key = key

        chat_key = str(payload.get("chat_key") or "onebot_v11-group_872553566")
        ok = await complaint.handle(
            _Ctx(chat_key),
            _Msg(str(payload.get("text") or "这 bot 怎么这么人机"), bool(payload.get("is_tome", False)),
                 str(payload.get("nick") or "测试用户")),
            test_mode=True,
        )
        return {"ok": True, "handled": ok}

    @router.post("/api/scan", summary="立即扫描一次")
    async def api_scan():
        from . import core

        return {"ok": True, "result": await core.scan_once()}

    @router.post("/api/backfill", summary="回溯分析某一天")
    async def api_backfill(payload: dict = Body(default={})):
        from . import core

        day = str(payload.get("date") or "")
        if not day:
            import datetime as _d

            day = (_d.date.today() - _d.timedelta(days=1)).isoformat()
        result = await core.backfill_day(day)
        return {"ok": True, "result": result}

    @router.get("/api/consistency", summary="一致性检查结果")
    async def api_consistency():
        from . import consistency

        return {"ok": True, "data": consistency.load_cache()}

    @router.post("/api/consistency/run", summary="跑一次一致性检查")
    async def api_consistency_run():
        from . import consistency

        return {"ok": True, "result": await consistency.run_check()}

    @router.get("/api/report.png", summary="今日日报卡片", include_in_schema=False)
    async def api_report_png(day: str = "", theme: str = "", layout: str = "", font: str = ""):
        from . import core

        data = await core.report_data(day or None)
        path = Path(core.render_report_image(data, theme, layout, font))
        return FileResponse(str(path), media_type="image/png")

    @router.post("/api/report/send", summary="把日报卡发到会话")
    async def api_report_send(payload: dict = Body(default={})):
        from . import core

        return {
            "ok": True,
            "result": await core.send_daily_report(
                payload.get("chat_keys"), payload.get("day")
            ),
        }

    return router
