# -*- coding: utf-8 -*-
"""可视化模块：基于 SQLite 数据生成图表。"""
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无界面渲染，适配 CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from config import CHART_STYLE

# 中文字体（Windows / Linux CI 双兼容）
from matplotlib import font_manager
_CJK_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",     # Windows 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu Noto
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
for _f in _CJK_FONTS:
    if Path(_f).exists():
        font_manager.fontManager.addfont(_f)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_f).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def _ensure_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def plot_daily_temperature(records: list[dict], city: str, days: int = 60) -> Path:
    """近 N 天日均气温趋势折线图。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据可绘图：%s", city)
        return OUTPUT_DIR / "temperature_trend.png"
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").tail(days)

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=130)
    ax.plot(df["date"], df["temp_avg"], color=CHART_STYLE["primary"],
            linewidth=2, label="日均气温")
    ax.fill_between(df["date"], df["temp_min"], df["temp_max"],
                    color=CHART_STYLE["secondary"], alpha=0.18, label="温度区间")
    ax.set_title(f"{city} 近 {len(df)} 天日均气温趋势", fontsize=13, pad=12)
    ax.set_ylabel("气温（℃）")
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.tight_layout()
    path = OUTPUT_DIR / "temperature_trend.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info("图表已生成：%s", path)
    return path


def plot_monthly_precipitation(records: list[dict], months: int = 6) -> Path:
    """近 N 个月降水量对比柱状图（全国汇总）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据可绘图：precipitation")
        return OUTPUT_DIR / "precipitation.png"
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["precip"].sum().tail(months)

    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=130)
    colors = [CHART_STYLE["warm"] if v < monthly.median() else CHART_STYLE["primary"]
              for v in monthly.values]
    bars = ax.bar(monthly.index, monthly.values, color=colors, width=0.6)
    ax.bar_label(bars, fmt="%.0f", padding=2, fontsize=9)
    ax.set_title("全国 12 城近 %d 个月降水量汇总（毫米）" % len(monthly), fontsize=13, pad=12)
    ax.set_ylabel("降水量（mm）")
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    fig.tight_layout()
    path = OUTPUT_DIR / "precipitation.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info("图表已生成：%s", path)
    return path


def plot_city_duel(records: list[dict], city_a: str, city_b: str, days: int = 60) -> Path:
    """双城对比：长沙 vs 太原（温度叠加 + 降水 + 温差统计）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        return OUTPUT_DIR / "city_duel.png"
    df["date"] = pd.to_datetime(df["date"])
    a = df[df["city"] == city_a].sort_values("date").tail(days)
    b = df[df["city"] == city_b].sort_values("date").tail(days)
    if a.empty or b.empty:
        logger.warning("双城对比缺数据：%s(%d条) %s(%d条)", city_a, len(a), city_b, len(b))
        return OUTPUT_DIR / "city_duel.png"

    # 对齐日期
    common = a["date"].isin(b["date"].values)
    a, b = a[common], b[b["date"].isin(a["date"].values)]

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), dpi=130,
                             gridspec_kw={"height_ratios": [2, 1]})

    # 上：日均气温对比 + 温差距
    ax = axes[0]
    ax.plot(a["date"], a["temp_avg"], label=city_a, color=CHART_STYLE["warm"], linewidth=2)
    ax.plot(b["date"], b["temp_avg"], label=city_b, color=CHART_STYLE["primary"], linewidth=2)
    a_avg = a["temp_avg"].to_numpy()
    b_avg = b["temp_avg"].to_numpy()
    dates = a["date"].to_numpy()
    ax.fill_between(dates, a_avg, b_avg,
                    where=a_avg >= b_avg,
                    color=CHART_STYLE["warm"], alpha=0.12, label=f"{city_a} 更暖")
    ax.fill_between(dates, a_avg, b_avg,
                    where=a_avg < b_avg,
                    color=CHART_STYLE["primary"], alpha=0.12, label=f"{city_b} 更暖")
    ax.set_title(f"{city_a} vs {city_b} · 近 {len(a)} 天日均气温对比", fontsize=14, pad=12)
    ax.set_ylabel("日均气温（℃）")
    ax.grid(alpha=0.3, linestyle="--")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))

    # 下：两城降水对比（分日柱状）
    ax2 = axes[1]
    width = pd.Timedelta(hours=9)
    ax2.bar(a["date"], a["precip"], width=width, color=CHART_STYLE["warm"],
            alpha=0.85, label=city_a)
    ax2.bar(b["date"], b["precip"], width=width, color=CHART_STYLE["primary"],
            alpha=0.85, label=city_b)
    ax2.set_title("每日降水量对比（mm）", fontsize=11, pad=8)
    ax2.set_ylabel("降水量（mm）")
    ax2.grid(axis="y", alpha=0.3, linestyle="--")
    ax2.legend(loc="upper right", framealpha=0.9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))

    fig.tight_layout()
    path = OUTPUT_DIR / "city_duel.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info("双城对比图已生成：%s", path)

    # 温差统计（控制台 + 返回路径）
    diff = (a["temp_avg"] - b["temp_avg"]).dropna()
    if len(diff):
        logger.info(
            "%s 平均比 %s %+.1f℃（近 %d 天）", city_a, city_b, diff.mean(), len(diff))
    return path


def plot_city_comparison(records: list[dict]) -> Path:
    """各城市近 30 天平均气温对比（横向条形图）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        return OUTPUT_DIR / "city_comparison.png"
    df["date"] = pd.to_datetime(df["date"])
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=30)]
    city_avg = recent.groupby("city")["temp_avg"].mean().sort_values()

    fig, ax = plt.subplots(figsize=(7, 6), dpi=130)
    bars = ax.barh(city_avg.index, city_avg.values, color=CHART_STYLE["secondary"])
    ax.bar_label(bars, fmt="%.1f℃", padding=3, fontsize=9)
    ax.set_title("近 30 天各城市平均气温对比", fontsize=13, pad=12)
    ax.set_xlabel("日均气温（℃）")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    fig.tight_layout()
    path = OUTPUT_DIR / "city_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    logger.info("图表已生成：%s", path)
    return path


def make_dashboard(records: list[dict]) -> Path:
    """生成 README 用仪表盘拼图（2x2 网格）。"""
    _ensure_dir()
    paths = [
        plot_daily_temperature(records, "长沙", days=60),
        plot_monthly_precipitation(records, months=6),
        plot_city_comparison(records),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), dpi=110)
    for ax, p in zip(axes.flat[:3], paths):
        img = plt.imread(p)
        ax.imshow(img)
        ax.axis("off")
    axes.flat[3].axis("off")
    fig.tight_layout()
    path = OUTPUT_DIR / "dashboard.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("仪表盘已生成：%s", path)
    return path