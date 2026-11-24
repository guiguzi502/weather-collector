# -*- coding: utf-8 -*-
"""业务日期计算：统一按北京时间，不依赖机器本地时区。

背景（2026-11-25 修复）：
    GitHub Actions runner 的 TZ 是 UTC，``date.today()`` 返回的是 UTC 日期。
    每天 08:00（北京）那次定时运行恰好 UTC 也是同一天，所以看不出问题；
    但任何在 00:00–08:00（北京）之间的运行 —— 手动 workflow_dispatch、
    重跑失败任务 —— UTC 还停在前一天，徽章写成「运行于 昨天」，
    用户会以为自动化没跑。归档日期 ``today - 1`` 同样会被算错一天。

    这里用 ``zoneinfo``（Python 3.9+ 标准库）显式按 Asia/Shanghai 取日期，
    与 runner 的 TZ 解耦。Windows 上没有 tzdata 时退回固定 +08:00
    （北京时间无夏令时，固定偏移等价）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from config import TIMEZONE

_CST = timezone(timedelta(hours=8))     # 北京时间固定偏移（无夏令时）


def _tz():
    """优先用 zoneinfo，取不到就退回固定 +08:00。"""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TIMEZONE)
    except Exception:                    # ImportError / ZoneInfoNotFoundError
        return _CST


def now() -> datetime:
    """当前时间（北京时间，带 tzinfo）。"""
    return datetime.now(_tz())


def today() -> date:
    """今天（北京时间）。"""
    return now().date()


def yesterday() -> date:
    """昨天（北京时间）—— archive API 的采集终点。"""
    return today() - timedelta(days=1)


def iso_today() -> str:
    return today().isoformat()


def iso_yesterday() -> str:
    return yesterday().isoformat()