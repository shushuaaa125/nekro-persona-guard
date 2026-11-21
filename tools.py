"""人设哨兵 - 聊天指令：手动出日报。"""

from __future__ import annotations

import re

from nekro_agent.api import message as message_api
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.schemas.signal import MsgSignal

from . import complaint, core
from .plugin import plugin

_AT_RE = re.compile(r"\[@id:\d+;nickname:[^\]]*?\]")


@plugin.mount_on_user_message()
async def on_user_command(ctx: AgentCtx, message):
    """聊天里发「人设体检」→ 先扫一次，再回一张日报卡片（可带日期）。"""
    raw = getattr(message, "content_text", "") or ""

    # 先看是不是「有人骂她人机」——是的话异步出日报，不拦截聊天
    try:
        await complaint.handle(ctx, message)
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 投诉检测异常: {exc}")

    text = _AT_RE.sub("", raw).strip()
    is_cmd, day = core.parse_report_command(text)
    if not is_cmd:
        return None

    try:
        if not core.claim_command(ctx.chat_key, text):
            return MsgSignal.BLOCK_TRIGGER
        await core.send_command_report(ctx.chat_key, day)
    except Exception as exc:  # noqa: BLE001
        plugin.logger.warning(f"[persona_guard] 手动日报失败: {exc}")
        try:
            await message_api.send_text(ctx.chat_key, f"日报生成失败：{type(exc).__name__}", ctx)
        except Exception:  # noqa: BLE001
            pass
    return MsgSignal.BLOCK_TRIGGER
