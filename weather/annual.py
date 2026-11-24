# -*- coding: utf-8 -*-
"""年度天气账单：网易云音乐年度报告风格的 SVG 长图。

统计当前库内全部记录，生成仪式感长图：最热/最冷/雨水/城市榜/双城彩蛋。
适合 README 展示与转发传播。每日 Actions 重跑时内容不变则无提交。
"""
import html
import logging
from pathlib import Path

import pandas as pd

from weather.sync import write_text_lf

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
W = 760
BG = "#0E1B2E"      # 深空夜底色
TEXT = "#F2F5FA"
MUTED = "#8FA3BF"
RAIN = "#5B8DEF"    # 主蓝
ACCENT = "#FFB84D"  # 热橙
COLD = "#6FC3FF"    # 冷蓝
GOLD = "#E8C46A"    # 金


def _e(s) -> str:
    """SVG 文本转义（保留中文）。"""
    return html.escape(str(s), quote=False)


def _sec(y: int, label: str) -> tuple[int, str]:
    """小节标题，返回 (新y, svg片段)。"""
    y += 6
    seg = (f'<text x="40" y="{y}" font-size="15" font-weight="700" fill="{RAIN}">'
           f'{_e(label)}</text>')
    y += 34
    return y, seg


def make_annual_report(records: list[dict]) -> Path:
    """生成年度天气账单 SVG，并同步到 docs/。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过年度账单")
        return OUTPUT_DIR / "annual_report.svg"
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    dmax, dmin = df["date"].max(), df["date"].min()
    span = f"{dmin:%Y-%m-%d} ~ {dmax:%Y-%m-%d}"
    ndays = df["date"].nunique()
    year = dmax.year
    title = f"{year} 年度天气账单" if ndays >= 60 else "📅 天气账单（累计）"
    hot = df.loc[df["temp_avg"].idxmax()]
    cold = df.loc[df["temp_avg"].idxmin()]
    rainy = df[df["precip"] >= 1.0].groupby("city")["precip"].count().sort_values(ascending=False)
    rain_sum = df.groupby("city")["precip"].sum().sort_values(ascending=False)
    city_avg = df.groupby("city")["temp_avg"].mean().sort_values(ascending=False)
    top3, bot3 = city_avg.head(3), city_avg.tail(3).sort_values()

    # 双城彩蛋
    duel_lines = []
    g = df.groupby("city")
    if "长沙" in g.groups and "太原" in g.groups:
        both = g.get_group("长沙")[["date", "temp_avg"]].merge(
            g.get_group("太原")[["date", "temp_avg"]], on="date", suffixes=("_a", "_b"))
        both = both.dropna()
        if not both.empty:
            diff = both["temp_avg_a"] - both["temp_avg_b"]
            warm_a = int((diff > 0).sum())
            md = both.loc[diff.abs().idxmax()]
            duel_lines.append(
                f"长沙比太原暖的日子有 {warm_a} 天（共 {len(both)} 天）")
            duel_lines.append(
                f"温差最大一天：长沙 {md['temp_avg_a']:.1f}°C vs 太原 {md['temp_avg_b']:.1f}°C"
                f"，差 {abs(diff).max():.1f}°C（{md['date']:%m-%d}）")

    parts = []
    y = 0

    # ---------- 封面 ----------
    y = 88
    parts.append(
        f'<text x="40" y="{y - 40}" font-size="12" font-weight="700" letter-spacing="3" '
        f'fill="{GOLD}">NATIONAL WEATHER ANNUAL REPORT</text>'
        f'<text x="40" y="{y}" font-size="30" font-weight="800" fill="{TEXT}">{_e(title)}</text>'
        f'<text x="40" y="{y + 30}" font-size="13" fill="{MUTED}">数据区间 {_e(span)} · 共 {ndays} 天 · 采集 {df["city"].nunique()} 城</text>'
    )
    y += 58
    parts.append(f'<line x1="40" y1="{y}" x2="720" y2="{y}" stroke="#27405F" stroke-width="1"/>')
    y += 26

    # ---------- 最热 / 最冷 ----------
    y, s = _sec(y, "🔥 这一年，最热与最冷")
    parts.append(s)
    parts.append(
        f'<text x="40" y="{y}" font-size="13" fill="{MUTED}">全年最热</text>'
        f'<text x="40" y="{y + 34}" font-size="40" font-weight="800" fill="{ACCENT}">{hot["temp_avg"]:.1f}°C</text>'
        f'<text x="40" y="{y + 58}" font-size="13" fill="{MUTED}">{_e(hot["city"])} · {hot["date"]:%m-%d} 那天你肯定开空调了</text>'
        f'<text x="412" y="{y}" font-size="13" fill="{MUTED}">全年最冷</text>'
        f'<text x="412" y="{y + 34}" font-size="40" font-weight="800" fill="{COLD}">{cold["temp_avg"]:.1f}°C</text>'
        f'<text x="412" y="{y + 58}" font-size="13" fill="{MUTED}">{_e(cold["city"])} · {cold["date"]:%m-%d} 羽绒服焊在身上</text>'
    )
    y += 84

    # ---------- 雨水 ----------
    y, s = _sec(y, "🌧 雨水都下在了哪儿")
    parts.append(s)
    if not rain_sum.empty:
        r1 = rain_sum.index[0]
        parts.append(
            f'<text x="40" y="{y}" font-size="13" fill="{MUTED}">累计降水最多的城</text>'
            f'<text x="40" y="{y + 30}" font-size="24" font-weight="700" fill="{TEXT}">{_e(r1)}</text>'
            f'<text x="40" y="{y + 54}" font-size="13" fill="{MUTED}">累计 {rain_sum.iloc[0]:.0f} mm</text>')
    if not rainy.empty:
        r2 = rainy.index[0]
        parts.append(
            f'<text x="412" y="{y}" font-size="13" fill="{MUTED}">下雨天数最多的城</text>'
            f'<text x="412" y="{y + 30}" font-size="24" font-weight="700" fill="{TEXT}">{_e(r2)}</text>'
            f'<text x="412" y="{y + 54}" font-size="13" fill="{MUTED}">{int(rainy.iloc[0])} 天雨 ≥ 1mm，太阳流浪记</text>')
    y += 80

    # ---------- 城市温度榜 ----------
    y, s = _sec(y, "🌡 城市温度榜")
    parts.append(s)
    for i, (city, v) in enumerate(top3.items()):
        parts.append(
            f'<text x="40" y="{y}" font-size="13" fill="{MUTED}">🥇🥈🥉 最暖</text>' if i == 0 else "")
        parts.append(
            f'<text x="40" y="{y + 26 + i * 28}" font-size="13" fill="{TEXT}">{_e(city)}</text>'
            f'<text x="220" y="{y + 26 + i * 28}" font-size="13" fill="{ACCENT}">{v:.1f}°C</text>')
    for i, (city, v) in enumerate(bot3.items()):
        parts.append(
            f'<text x="412" y="{y}" font-size="13" fill="{MUTED}">❄️ 最凉</text>' if i == 0 else "")
        parts.append(
            f'<text x="412" y="{y + 26 + i * 28}" font-size="13" fill="{TEXT}">{_e(city)}</text>'
            f'<text x="592" y="{y + 26 + i * 28}" font-size="13" fill="{COLD}">{v:.1f}°C</text>')
    y += 26 + 3 * 28 + 8

    # ---------- 双城彩蛋 ----------
    if duel_lines:
        y, s = _sec(y, "🏮 长沙 · 太原 南北对望")
        parts.append(s)
        for i, line in enumerate(duel_lines):
            parts.append(
                f'<text x="40" y="{y + i * 26}" font-size="13" fill="{TEXT}">· {_e(line)}</text>')
        y += len(duel_lines) * 26 + 6

    # ---------- 页脚 ----------
    y += 14
    parts.append(f'<line x1="40" y1="{y}" x2="720" y2="{y}" stroke="#27405F" stroke-width="1"/>')
    parts.append(
        f'<text x="40" y="{y + 26}" font-size="12" fill="{MUTED}">数据来自 Open-Meteo · '
        f'每日 08:00 自动更新</text>'
        f'<text x="40" y="{y + 44}" font-size="12" fill="{GOLD}">明天，也要记得看天气 ☀️</text>')
    y += 64

    height = y
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">
  <rect width="{W}" height="{height}" rx="14" fill="{BG}"/>
  {''.join(parts)}
</svg>'''
    path = OUTPUT_DIR / "annual_report.svg"
    write_text_lf(path, svg)
    logger.info("年度天气账单已生成：%s（%d 行高）", path, height)
    return path