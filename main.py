# -*- coding: utf-8 -*-
"""天气数据采集与可视化分析系统 - 入口。

用法:
    python main.py                 # 采集窗口 + 缺口回补，全流程
    python main.py --days 30       # 自定义采集窗口
    python main.py --cities 长沙,北京
    python main.py --no-dashboard  # 跳过仪表盘拼图
    python main.py --no-backfill   # 关闭缺口回补（只采窗口，不补历史）
"""
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import CITIES, BACKFILL_DAYS
from weather import (collector, cleaner, storage, visualize, report,
                     annual, map_view, sync, gaps)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args():
    p = argparse.ArgumentParser(description="天气数据采集与可视化分析")
    p.add_argument("--days", type=int, default=90, help="采集最近 N 天（默认 90）")
    p.add_argument("--cities", type=str, default="",
                   help="城市列表，逗号分隔；默认全部 %d 城" % len(CITIES))
    p.add_argument("--no-dashboard", action="store_true", help="跳过仪表盘生成")
    p.add_argument("--no-backfill", action="store_true",
                   help="关闭缺口回补，只采窗口内的数据")
    p.add_argument("--backfill-days", type=int, default=BACKFILL_DAYS,
                   help="回补检查窗口天数（默认 %d）" % BACKFILL_DAYS)
    return p.parse_args()


def update_readme_badge(records: list, summary: dict) -> None:
    """更新 README 顶部徽章：数据日期 + 运行时间 + 总记录数。

    关键设计（2026-11-23 修复）：
        archive API 只能拿到已归档的完整日数据，所以 ``latest`` 永远是"昨天"。
        如果徽章只写数据日期，用户今天看会觉得"没更新"。
        因此额外加一个 ``运行于`` 徽章记录本次执行日期（今天），
        两者一起看才说明系统是活的。
    """
    readme = Path("README.md")
    if not readme.exists():
        logger.warning("README.md 不存在，跳过徽章更新")
        return

    df = pd.DataFrame(records)
    latest = str(df["date"].max())[:10] if not df.empty else "—"
    total = summary.get("total", 0)
    run_day = date.today().isoformat()
    # 数据日期与今天相差的天数，用于说明归档延迟
    lag_days = 0
    try:
        lag_days = (date.today() - date.fromisoformat(latest)).days
    except (ValueError, TypeError):
        pass

    badge_line = (
        f"[![数据日期](https://img.shields.io/badge/数据日期-{latest}-1F4E79)]"
        f"(https://github.com/guiguzi502/weather-collector/actions)  "
        f"[![运行于](https://img.shields.io/badge/运行于-{run_day}-27AE60)]"
        f"(https://github.com/guiguzi502/weather-collector/actions)  "
        f"[![记录数](https://img.shields.io/badge/记录数-{total}-2E86AB)]"
        f"(https://github.com/guiguzi502/weather-collector)  "
        f"[![CI](https://github.com/guiguzi502/weather-collector/actions/workflows/daily.yml/badge.svg)]"
        f"(https://github.com/guiguzi502/weather-collector/actions/workflows/daily.yml)"
    )

    text = readme.read_text(encoding="utf-8")
    lines = text.splitlines()
    # 找到已存在的徽章行（含 img.shields.io/badge）替换
    for i, line in enumerate(lines):
        if "img.shields.io/badge" in line:
            lines[i] = badge_line
            break
    else:
        # 找不到：插到第一个标题后
        for i, line in enumerate(lines):
            if line.startswith("#"):
                lines.insert(i + 1, "")
                lines.insert(i + 2, badge_line)
                break
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("README 徽章已更新：数据 %s（滞后 %d 天）/ 运行于 %s / %s 条",
                latest, lag_days, run_day, total)


def update_duel_stats(records: list, city_a: str = "长沙",
                      city_b: str = "太原", days: int = 60) -> None:
    """更新 README 双城对比统计行（自动计算，不再手写死）。"""
    readme = Path("README.md")
    if not readme.exists():
        logger.warning("README.md 不存在，跳过双城统计更新")
        return

    df = pd.DataFrame(records)
    if df.empty:
        return
    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=days - 1)
    recent = df[df["date"] >= cutoff]

    def stats(city: str) -> str:
        sub = recent[recent["city"] == city]
        if sub.empty:
            return "无数据"
        avg = sub["temp_avg"].mean()
        rain = sub["precip"].sum()
        return f"{avg:.1f}°C / 降水 {rain:.0f}mm"

    a, b = stats(city_a), stats(city_b)
    line = f"> 近 {days} 天：{city_a}均温 {a}｜{city_b}均温 {b}"

    text = readme.read_text(encoding="utf-8")
    lines = text.splitlines()
    replaced = False
    for i, ln in enumerate(lines):
        if ln.startswith("> 近") and "均温" in ln:
            lines[i] = line
            replaced = True
            break
    if not replaced:
        lines.append("")
        lines.append(line)
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("README 双城统计已更新：%s", line)


def _existing_dates(db, city: str, start: str, end: str) -> set:
    """库里某城在 [start, end] 内已有数据的日期集合。"""
    return {r["date"] for r in db.query(city=city, start=start, end=end)}


def collect_with_backfill(cities: list[str], days: int,
                          backfill_days: int, db) -> tuple[list[dict], list[str]]:
    """采集窗口数据，并把最近 ``backfill_days`` 天内的历史缺口一并补齐。

    设计要点（2026-11-25 修复永久缺口）：
        原实现只采「昨天」一天。archive-api 抖动导致某城重试全超时后，
        窗口第二天就滑走 —— 那次数据永久缺失，而 CI 依然 success。
        现在每次运行先算最近 N 天的缺口，只请求缺的日期，自动补齐。

    Returns:
        ``(本轮采集到的记录, 补采区间描述列表)``
    """
    end = date.today() - timedelta(days=1)      # archive API 只提供已归档完整日
    win_start = end - timedelta(days=days - 1)

    # 回补窗口与采集窗口取并集：正常日只会检查/请求最近一天
    check_start = min(win_start, end - timedelta(days=backfill_days - 1))
    span = (end - check_start).days + 1
    logger.info("采集窗口 %s ~ %s（%d 天，含回补 %d 天）",
                check_start.isoformat(), end.isoformat(), span, backfill_days)

    existing = {c: _existing_dates(db, c, check_start.isoformat(), end.isoformat())
                for c in cities}
    plan = gaps.plan_backfill(cities, existing, check_start.isoformat(), end.isoformat())

    if not plan:
        logger.info("最近 %d 天数据已完整，无需请求 API", span)
        return [], []

    # 只对真正缺数据的城市发请求
    filled: list[str] = []
    records: list[dict] = []
    for city, ranges in plan.items():
        for (r_start, r_end) in ranges:
            n_days = (date.fromisoformat(r_end) - date.fromisoformat(r_start)).days + 1
            logger.info("回补 %s：%s ~ %s（%d 天）", city, r_start, r_end, n_days)
            recs = collector.collect(city, r_start, r_end)
            recs = [r for r in cleaner.clean(recs) if r_start <= r["date"] <= r_end]
            if recs:
                records.extend(recs)
                filled.append(f"{city} {r_start}~{r_end}")
            else:
                logger.error("回补失败（下次运行会重试）：%s %s~%s", city, r_start, r_end)

    return records, filled


def main():
    args = parse_args()
    cities = [c.strip() for c in args.cities.split(",") if c.strip()] or list(CITIES)

    db = storage.Storage()
    try:
        if args.no_backfill:
            end = date.today() - timedelta(days=1)
            start = end - timedelta(days=args.days - 1)
            logger.info("缺口回补已关闭，直接采集 %s ~ %s",
                        start.isoformat(), end.isoformat())
            all_records, filled = [], []
            for city in cities:
                recs = cleaner.clean(
                    collector.collect(city, start.isoformat(), end.isoformat()))
                all_records.extend(recs)
                if recs:
                    filled.append(f"{city} {start.isoformat()}~{end.isoformat()}")
        else:
            all_records, filled = collect_with_backfill(
                cities, args.days, args.backfill_days, db)

        if not filled:
            logger.info("本次无需补采，直接基于库里已有数据重绘产物")

        # 即便本轮没采到新数据，只要库里有过数据就继续重绘——
        # 保证 README 徽章里的「运行于」每天都会推进，不会看起来像停了。
        if all_records:
            db.upsert_many(all_records)
        info = db.summary()
        logger.info("数据库概况: %s", info)

        full = db.query()
        if not full:
            logger.error("库里一条数据都没有，无法出图，流程终止")
            return 1

        # 覆盖度自检：最近 BACKFILL_DAYS 天缺任何一个城市都记 WARNING，
        # 让「CI 绿了但数据有洞」这种情况在日志里看得见，而不是静默通过。
        end = date.today() - timedelta(days=1)
        check_start = end - timedelta(days=args.backfill_days - 1)
        recent_days = [r["date"] for r in full
                       if check_start.isoformat() <= r["date"] <= end.isoformat()]
        all_days = sorted(set(recent_days))
        if all_days:
            have = {}
            for r in full:
                have.setdefault(r["city"], set()).add(r["date"])
            ok, total = gaps.coverage(cities, have, all_days)
            if ok == total:
                logger.info("覆盖度自检通过：最近 %d 天 %d/%d 城数据完整",
                            len(all_days), ok, total)
            else:
                holes = []
                for c in cities:
                    miss = [d for d in all_days if d not in have.get(c, set())]
                    if miss:
                        holes.append(f"{c}:{','.join(miss)}")
                logger.warning("覆盖度不足 %d/%d 城，缺口：%s",
                               ok, total, " | ".join(holes))

        # 从库里取全量数据画图（保证图表包含历史积累的数据）
        visualize.plot_daily_temperature(full, "长沙", days=60)
        visualize.plot_monthly_precipitation(full, months=6)
        visualize.plot_city_comparison(full)
        visualize.plot_city_duel(full, "长沙", "太原", days=60)
        if not args.no_dashboard:
            visualize.make_dashboard(full)

        # 生成可视化报告（SVG 卡片 + ECharts 交互式 HTML）
        report.make_svg_card(full)
        report.make_duel_dressing_card(full, "长沙", "太原")
        report.make_html_report(full)
        annual.make_annual_report(full)
        map_view.make_weather_map(full)

        # 统一把 output/ 产物镜像到 docs/（README 引用的路径）
        sync.sync_docs()

        update_readme_badge(full, info)
        update_duel_stats(full, "长沙", "太原", days=60)
    finally:
        db.close()

    # 自检：README 引用的本地图片必须全部存在，否则 CI 直接失败
    missing = sync.check_readme_refs()
    if missing:
        logger.error("README 引用的图片缺失：%s", ", ".join(missing))
        return 1
    logger.info("README 图片引用自检通过")

    # 控制台摘要
    if all_records:
        df = pd.DataFrame(all_records)
        print("\n================ 本轮采集摘要 ================")
        print(df.groupby("city").agg(
            天数=("date", "count"),
            平均气温=("temp_avg", lambda s: round(s.mean(), 1)),
            总降水=("precip", "sum"),
        ).to_string())
    print(f"\n数据总量: {info['total']} 条 | 城市: {info['cities']} | "
          f"区间: {info['date_from']} ~ {info['date_to']}")
    print("图表输出目录: output/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())