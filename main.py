# -*- coding: utf-8 -*-
"""天气数据采集与可视化分析系统 - 入口。

用法:
    python main.py                 # 采集最近 90 天，全流程
    python main.py --days 30       # 自定义天数
    python main.py --cities 长沙,北京
    python main.py --no-dashboard  # 跳过仪表盘拼图
"""
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import CITIES
from weather import collector, cleaner, storage, visualize, report

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
                   help="城市列表，逗号分隔；默认全部 12 城")
    p.add_argument("--no-dashboard", action="store_true", help="跳过仪表盘生成")
    return p.parse_args()


def update_readme_badge(records: list, summary: dict) -> None:
    """更新 README 顶部徽章：显示数据更新日期与总记录数。

    替换 README 中形如 ``[![...](...)]`` 的徽章行；不存在则插入标题下方。
    徽章使用 shields.io 动态端点，无需额外服务。
    """
    readme = Path("README.md")
    if not readme.exists():
        logger.warning("README.md 不存在，跳过徽章更新")
        return

    df = pd.DataFrame(records)
    latest = str(df["date"].max())[:10] if not df.empty else "—"
    total = summary.get("total", 0)

    badge_line = (
        f"[![数据更新](https://img.shields.io/badge/数据更新-{latest}-1F4E79)]"
        f"(https://github.com/guiguzi502/weather-collector/actions)  "
        f"[![记录数](https://img.shields.io/badge/记录数-{total}-2E86AB)]"
        f"(https://github.com/guiguzi502/weather-collector)"
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
    logger.info("README 徽章已更新：%s / %s 条", latest, total)


def main():
    args = parse_args()
    # archive API 只提供已归档数据：终点用"昨天"，避免请求到未归档日期
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] or list(CITIES)

    all_records = []
    for city in cities:
        records = collector.collect(city, start.isoformat(), end.isoformat())
        records = cleaner.clean(records)
        all_records.extend(records)

    if not all_records:
        logger.error("本次采集无有效数据，流程终止")
        return 1

    db = storage.Storage()
    db.upsert_many(all_records)
    info = db.summary()
    logger.info("数据库概况: %s", info)

    # 从库里取全量数据画图（保证图表包含历史积累的数据）
    full = db.query()
    visualize.plot_daily_temperature(full, "长沙", days=60)
    visualize.plot_monthly_precipitation(full, months=6)
    visualize.plot_city_comparison(full)
    visualize.plot_city_duel(full, "长沙", "太原", days=60)
    if not args.no_dashboard:
        visualize.make_dashboard(full)

    # 生成可视化报告（SVG 卡片 + ECharts 交互式 HTML）
    report.make_svg_card(full)
    report.make_html_report(full)
    update_readme_badge(full, db.summary())

    db.close()

    # 控制台摘要
    df = pd.DataFrame(all_records)
    print("\n================ 采集摘要 ================")
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