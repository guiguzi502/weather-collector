# -*- coding: utf-8 -*-
"""采集缺口规划：只请求库里真正缺失的日期区间。

背景（2026-11-25 修复）：
    原实现每次只采 ``--days 1`` 那一个窗口（昨天）。archive-api 抖动时
    单城重试全超时（2026-11-24 杭州、南京连续 3 次 15s timeout），
    而窗口第二天就滑走了 —— 缺口永久留在库里，CI 依然是 success，
    没有任何告警。

    现在每次运行都按 ``BACKFILL_DAYS`` 检查最近 N 天，算出每城缺失的日期，
    合并成尽量少的连续区间去补。已有数据不重复请求，正常日仍然只发 1 天请求。

    这样一来单次抖动最多滞后一天被自动补齐，不会留下永久缺口。
"""
from __future__ import annotations

from datetime import date, timedelta


def date_range(start: str, end: str) -> list[str]:
    """返回 [start, end] 内所有 ISO 日期字符串（含两端）。"""
    d = date.fromisoformat(start)
    last = date.fromisoformat(end)
    out: list[str] = []
    while d <= last:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def contiguous_ranges(dates) -> list[tuple[str, str]]:
    """把一组日期压成尽量少的连续区间 ``[(start, end), ...]``。"""
    items = sorted({d for d in dates})
    if not items:
        return []

    ranges: list[tuple[str, str]] = []
    lo = hi = items[0]
    for d in items[1:]:
        gap = (date.fromisoformat(d) - date.fromisoformat(hi)).days
        if gap == 1:
            hi = d
            continue
        ranges.append((lo, hi))
        lo = hi = d
    ranges.append((lo, hi))
    return ranges


def plan_backfill(cities, existing, start: str, end: str) -> dict[str, list[tuple[str, str]]]:
    """算出每个城市需要补采的连续区间。

    Args:
        cities:   城市名序列
        existing: ``{city: {已有日期}}``，只含 [start, end] 范围内的日期
        start:    检查窗口起点（ISO）
        end:      检查窗口终点（ISO）

    Returns:
        ``{city: [(range_start, range_end), ...]}``。
        已完整覆盖的城市**不出现**在返回值里 —— 用 ``in`` 判断即可跳过网络请求。
    """
    want = date_range(start, end)
    plan: dict[str, list[tuple[str, str]]] = {}
    for city in cities:
        have = existing.get(city, set())
        missing = [d for d in want if d not in have]
        if not missing:
            continue
        plan[city] = contiguous_ranges(missing)
    return plan


def coverage(cities, existing, days: list[str]) -> tuple[int, int]:
    """统计覆盖度：返回 ``(已完整城市数, 城市总数)``。

    "完整" = 该城在 ``days`` 每一天都有数据。
    """
    complete = 0
    for city in cities:
        have = existing.get(city, set())
        if all(d in have for d in days):
            complete += 1
    return complete, len(list(cities))