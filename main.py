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

import pandas as pd

from config import CITIES
from weather import collector, cleaner, storage, visualize

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
    if not args.no_dashboard:
        visualize.make_dashboard(full)

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