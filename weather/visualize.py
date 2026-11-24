# -*- coding: utf-8 -*-
"""可视化模块：基于 SQLite 数据生成图表。"""
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无界面渲染，适配 CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from config import CHART_STYLE, CITIES

# 中文字体（Windows / Linux CI 双兼容）
#
# 修复（2026-11-25）：原来只探测 Ubuntu 的 noto / wqy 两个绝对路径，
# 但 ubuntu-latest runner 默认没装中文字体 —— 36 条
# ``Glyph ... missing from font(s) DejaVu Sans`` 警告，图里中文全是方框。
# 现在按「本机已知路径 → 系统已注册字体」两级探测，并通过
# strict=True 让缺字体在 CI 直接失败，而不是悄悄出方框图。
from matplotlib import font_manager

_CJK_FONT_PATHS = (
    r"C:\Windows\Fonts\msyh.ttc",                          # Windows 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",                        # Windows 黑体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)

# 系统里已注册的中文字体族名（CI 用 apt 装过字体后走这条）
_CJK_FAMILIES = (
    "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans SC",
    "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
    "Droid Sans Fallback", "Microsoft YaHei", "SimHei",
    "PingFang SC", "Source Han Sans SC",
)


def _pick_cjk_font() -> str | None:
    """返回可用的中文字体族名；一个都没有时返回 None。"""
    for path in _CJK_FONT_PATHS:
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
                return font_manager.FontProperties(fname=path).get_name()
            except (RuntimeError, OSError, ValueError):
                continue

    installed = {f.name for f in font_manager.fontManager.ttflist}
    for family in _CJK_FAMILIES:
        if family in installed:
            return family
    return None


CJK_FONT = _pick_cjk_font()
if CJK_FONT:
    plt.rcParams["font.family"] = CJK_FONT
    plt.rcParams["font.sans-serif"] = [CJK_FONT] + list(
        plt.rcParams.get("font.sans-serif", []))
plt.rcParams["axes.unicode_minus"] = False

logger = logging.getLogger(__name__)
if CJK_FONT:
    logger.debug("已选用中文字体：%s", CJK_FONT)
else:
    logger.warning("未找到任何中文字体，图表中文会显示为方框")

OUTPUT_DIR = Path("output")


def _ensure_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def plot_daily_temperature(records: list[dict], city: str, days: int = 60) -> Path:
    """近 N 天日均气温趋势折线图（单一城市）。

    修复（2026-11-25）：原实现忘了按 ``city`` 过滤，把 13 个城市的记录
    全画进了同一条折线 —— 同一天有 13 个点，图上是来回锯齿，
    而且 ``tail(days)`` 取的是全表最后 N 行而不是该城最后 N 天。
    """
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据可绘图：%s", city)
        return OUTPUT_DIR / "temperature_trend.png"

    df = df[df["city"] == city]
    if df.empty:
        logger.warning("无 %s 的数据可绘图", city)
        return OUTPUT_DIR / "temperature_trend.png"

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date", keep="last").tail(days)

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
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=10))
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
    ax.set_title("全国 %d 城近 %d 个月降水量汇总（毫米）"
                 % (len(CITIES), len(monthly)), fontsize=13, pad=12)
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