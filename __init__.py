"""人设哨兵 - 入口：注册指令与路由，启动统计与日报。"""

import asyncio

from .plugin import plugin  # noqa: F401
from . import core  # noqa: F401
from . import router  # noqa: F401
from . import consistency  # noqa: F401
from . import complaint  # noqa: F401
from . import vibe  # noqa: F401
from . import chatcheck  # noqa: F401
from . import tools  # noqa: F401

_task = None
_reporter = None
_complaint_task = None


@plugin.mount_init_method()
async def _start_scanner() -> None:
    global _task, _reporter, _complaint_task
    if not (_task and not _task.done()):
        _task = asyncio.create_task(core.scanner_loop())
    if not (_reporter and not _reporter.done()):
        _reporter = asyncio.create_task(core.reporter_loop())
    if not (_complaint_task and not _complaint_task.done()):
        _complaint_task = asyncio.create_task(core.complaint_loop())
    plugin.logger.info("[persona_guard] 统计与日报任务已启动")


@plugin.mount_cleanup_method()
async def _stop_scanner() -> None:
    global _task, _reporter, _complaint_task
    for t in (_task, _reporter, _complaint_task):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except BaseException:  # noqa: BLE001
                pass
    _task = None
    _reporter = None
    _complaint_task = None
    plugin.logger.info("[persona_guard] 任务已停止")


__all__ = ["plugin"]
