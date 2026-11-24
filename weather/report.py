# -*- coding: utf-8 -*-
"""报告生成模块：SVG 天气卡片 + ECharts 交互式 HTML 报告。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from config import CITIES
from weather.sync import write_text_lf

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


def _ensure_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- SVG 卡片
def _temp_color(t: float) -> str:
    """气温 -> 颜色映射（冷蓝到暖橙）。"""
    if t is None:
        return "#9AA5B1"
    if t <= 0:
        return "#3B82C4"
    if t <= 10:
        return "#2E86AB"
    if t <= 20:
        return "#E6A817"
    return "#E05E2B"


def _trend_arrow(today: float, yesterday: float | None) -> tuple[str, str]:
    """对比昨日气温，返回 (箭头文本, 颜色)。▼/▲ 已表方向，数值取绝对值。"""
    if yesterday is None:
        return "—", "#C0C8D4"
    diff = today - yesterday
    if diff >= 0.5:
        return f"▲{diff:+.1f}", "#E05E2B"
    if diff <= -0.5:
        return f"▼{abs(diff):.1f}", "#3B82C4"
    return f"▸{abs(diff):.1f}", "#9AA5B1"


def dressing_advice(temp: float, precip: float) -> str:
    """根据气温与降水生成穿衣建议。"""
    if temp is None:
        return "数据缺失，出门看天"
    if temp >= 30:
        return "短袖短裤，注意防晒"
    if temp >= 26:
        return "短袖，空调房备薄外套"
    if temp >= 22:
        return "短袖或薄长袖"
    if temp >= 17:
        return "长袖T恤 + 薄外套"
    if temp >= 12:
        return "卫衣 / 毛衣 + 外套"
    if temp >= 7:
        return "厚外套 + 毛衣"
    if temp >= 2:
        return "羽绒服 + 保暖内衣"
    return "厚羽绒服，帽子围巾手套"


def dressing_suffix(precip: float) -> str:
    """降水附加建议。"""
    if precip >= 10:
        return "，带伞！雨不小"
    if precip >= 1:
        return "，记得带伞"
    return ""


def make_svg_card(records: list[dict]) -> Path:
    """生成全城今日天气总览 SVG 卡片（温差箭头 + 穿衣建议 + 趣味榜单）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过 SVG 卡片")
        return OUTPUT_DIR / "weather_card.svg"

    df["date"] = df["date"].astype(str)
    latest = df["date"].max()
    prev = sorted(df["date"].unique())[-2] if df["date"].nunique() >= 2 else None
    today = df[df["date"] == latest].sort_values("city")
    yesterday = df[df["date"] == prev].set_index("city")["temp_avg"] if prev else None

    path = _write_native_svg(today, latest, yesterday)
    # 同步到 docs/ 由 weather/sync.py 统一处理，此处不再各写各的
    return path


def _fun_facts(today: pd.DataFrame) -> list[str]:
    """生成趣味榜单：最热 / 最冷 / 降水最多。"""
    facts = []
    if today.empty:
        return facts
    valid = today[today["temp_avg"].notna()]
    if not valid.empty:
        hot = valid.loc[valid["temp_avg"].idxmax()]
        cold = valid.loc[valid["temp_avg"].idxmin()]
        facts.append(f"🔥 今日最热：{hot['city']} {hot['temp_avg']:.1f}°C")
        facts.append(f"🧊 今日最冷：{cold['city']} {cold['temp_avg']:.1f}°C")
    rain = today[today["precip"].notna()]
    if not rain.empty:
        wettest = rain.loc[rain["precip"].idxmax()]
        facts.append(f"🌧 降水最多：{wettest['city']} {wettest['precip']:.1f}mm")
    return facts


def _write_native_svg(today: pd.DataFrame, latest: str,
                      yesterday: pd.Series | None = None) -> Path:
    """用原生 SVG 元素绘制（兼容 GitHub 渲染器）。"""
    y = 78
    parts = []
    for _, r in today.iterrows():
        t = r["temp_avg"] if pd.notna(r["temp_avg"]) else None
        color = _temp_color(t)
        bar_w = max(8, min(350, (t + 15) * 7.5)) if t is not None else 8

        # 温差箭头
        yt = yesterday.get(r["city"]) if yesterday is not None else None
        if yt is not None and pd.notna(yt) and t is not None:
            arrow, acolor = _trend_arrow(t, float(yt))
        else:
            arrow, acolor = "—", "#C0C8D4"

        # 穿衣建议
        advice = dressing_advice(t, float(r["precip"]) if pd.notna(r["precip"]) else 0)
        advice += dressing_suffix(float(r["precip"]) if pd.notna(r["precip"]) else 0)

        parts.append(
            f'<text x="20" y="{y + 12}" font-size="13" font-weight="600" fill="#282E3A">{r["city"]}</text>'
            f'<rect x="82" y="{y}" width="350" height="14" rx="7" fill="#EFF2F6"/>'
            f'<rect x="82" y="{y}" width="{bar_w:.0f}" height="14" rx="7" fill="{color}"/>'
            f'<text x="442" y="{y + 12}" font-size="13" font-weight="700" fill="{color}">{t:.1f}°C</text>'
            f'<text x="512" y="{y + 12}" font-size="12" font-weight="600" fill="{acolor}">{arrow}</text>'
            f'<text x="566" y="{y + 12}" font-size="12" fill="#8A94A6">降水 {r["precip"]:.1f}mm</text>'
            f'<text x="20" y="{y + 30}" font-size="11" fill="#A0A8B4">👕 {advice}</text>'
        )
        y += 52

    # 趣味榜单
    facts = _fun_facts(today)
    if facts:
        y += 6
        parts.append(
            f'<line x1="20" y1="{y - 10}" x2="740" y2="{y - 10}" stroke="#E4E8EE" stroke-width="1"/>'
            f'<text x="20" y="{y + 8}" font-size="13" font-weight="700" fill="#1F4E79">今日趣味榜单</text>'
        )
        y += 26
        for fact in facts:
            parts.append(
                f'<text x="20" y="{y}" font-size="12" fill="#454D5C">{fact}</text>'
            )
            y += 22

    height = y + 24
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}" viewBox="0 0 760 {height}">
  <rect width="760" height="{height}" rx="12" fill="#FFFFFF" stroke="#E4E8EE" stroke-width="1.5"/>
  <text x="20" y="34" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="18" font-weight="700" fill="#1F4E79">🌤 {len(CITIES)} 城天气总览</text>
  <text x="20" y="58" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="12" fill="#8A94A6">数据日期：{latest} · 每日 08:00 自动更新 · 数据源 Open-Meteo · ▲/▼ 较昨日温差</text>
  {''.join(parts)}
</svg>'''
    path = OUTPUT_DIR / "weather_card.svg"
    write_text_lf(path, svg)
    logger.info("SVG 天气卡已生成：%s", path)
    return path


# ------------------------------------------------------ 双城穿衣对比卡
def make_duel_dressing_card(records: list[dict],
                            city_a: str = "长沙",
                            city_b: str = "太原") -> Path:
    """生成长沙 vs 太原 双城穿衣对比 SVG 卡（并排、加粗胜负对比）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过双城穿衣卡")
        return OUTPUT_DIR / "duel_dressing.svg"

    df["date"] = df["date"].astype(str)
    latest = df["date"].max()
    prev = sorted(df["date"].unique())[-2] if df["date"].nunique() >= 2 else None
    today = df[df["date"] == latest]
    yesterday = df[df["date"] == prev].set_index("city")["temp_avg"] if prev else None

    def city_block(city: str, x: int) -> str:
        row = today[today["city"] == city]
        if row.empty:
            return (f'<text x="{x}" y="92" font-size="16" font-weight="700" fill="#454D5C">{city}</text>'
                    f'<text x="{x}" y="120" font-size="13" fill="#A0A8B4">暂无数据</text>')
        r = row.iloc[0]
        t = r["temp_avg"] if pd.notna(r["temp_avg"]) else None
        p = float(r["precip"]) if pd.notna(r["precip"]) else 0.0
        color = _temp_color(t)
        # 温差箭头
        yt = yesterday.get(city) if yesterday is not None else None
        if yt is not None and pd.notna(yt) and t is not None:
            arrow, acolor = _trend_arrow(t, float(yt))
        else:
            arrow, acolor = "—", "#C0C8D4"
        advice = dressing_advice(t, p) + dressing_suffix(p)
        lines = [
            f'<text x="{x}" y="96" font-size="20" font-weight="800" fill="{color}">{t:.1f}°C</text>'
            f'<text x="{x + 92}" y="96" font-size="14" font-weight="700" fill="{acolor}">{arrow}</text>',
            f'<text x="{x}" y="122" font-size="13" fill="#8A94A6">降水 {p:.1f}mm</text>',
            f'<text x="{x}" y="152" font-size="14" font-weight="700" fill="#282E3A">今日穿搭</text>',
            f'<text x="{x}" y="176" font-size="13" fill="#454D5C">👕 {advice}</text>',
        ]
        return "\n".join(lines)

    left = city_block(city_a, 40)
    right = city_block(city_b, 400)

    # 温差总结（热 VS 冷）
    ta = today[today["city"] == city_a]["temp_avg"]
    tb = today[today["city"] == city_b]["temp_avg"]
    summary = ""
    if not ta.empty and not tb.empty and pd.notna(ta.iloc[0]) and pd.notna(tb.iloc[0]):
        diff = float(ta.iloc[0]) - float(tb.iloc[0])
        if diff > 0:
            summary = f"今日 {city_a} 比 {city_b} 暖 {diff:.1f}°C 🧣"
        elif diff < 0:
            summary = f"今日 {city_b} 比 {city_a} 暖 {abs(diff):.1f}°C 🧣"
        else:
            summary = f"今日两城同温 {float(ta.iloc[0]):.1f}°C"
    summary_line = (f'<text x="40" y="232" font-size="14" font-weight="700" '
                    f'fill="#1F4E79">{summary}</text>' if summary else "")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="268" viewBox="0 0 760 268">
  <rect width="760" height="268" rx="12" fill="#FFFFFF" stroke="#E4E8EE" stroke-width="1.5"/>
  <text x="40" y="36" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="18" font-weight="700" fill="#1F4E79">🥋 双城今日穿搭对比</text>
  <text x="40" y="60" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="12" fill="#8A94A6">数据日期：{latest} · 每日 08:00 自动更新 · 数据源 Open-Meteo</text>
  <line x1="380" y1="78" x2="380" y2="210" stroke="#E4E8EE" stroke-width="1.5" stroke-dasharray="4 4"/>
  <text x="40" y="88" font-size="14" font-weight="700" fill="#1F4E79">{city_a} 🌶</text>
  <text x="400" y="88" font-size="14" font-weight="700" fill="#1F4E79">{city_b} 🧣</text>
  {left}
  {right}
  {summary_line}
</svg>'''
    path = OUTPUT_DIR / "duel_dressing.svg"
    write_text_lf(path, svg)
    # 同步到 docs/ 由 weather/sync.py 统一处理
    logger.info("双城穿衣对比卡已生成：%s", path)
    return path


# ------------------------------------------------------------ ECharts HTML
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>天气数据可视化报告</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background: #F5F7FA; margin: 0; padding: 24px; }}
  h1 {{ color: #1F4E79; font-size: 22px; }}
  .meta {{ color: #8A94A6; font-size: 13px; margin-bottom: 18px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .panel {{ background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .panel h3 {{ margin: 4px 0 8px; color: #282E3A; font-size: 15px; }}
  .chart {{ width: 100%; height: 340px; }}
  .full {{ grid-column: 1 / -1; }}
  footer {{ margin-top: 18px; color: #B0B8C4; font-size: 12px; }}
</style>
</head>
<body>
<h1>🌤 {city_count} 城天气数据可视化报告</h1>
<div class="meta">数据区间：{date_from} ~ {date_to} · 记录数：{total} · 每日 08:00 由 GitHub Actions 自动更新</div>
<div class="grid">
  <div class="panel"><h3>各城市平均气温（最新一天）</h3><div id="c1" class="chart"></div></div>
  <div class="panel"><h3>长沙近 60 天日均气温</h3><div id="c2" class="chart"></div></div>
  <div class="panel"><h3>近 6 个月降水量汇总（mm）</h3><div id="c3" class="chart"></div></div>
  <div class="panel full"><h3>各城市每日气温热力图（近 30 天）</h3><div id="c4" class="chart" style="height:420px"></div></div>
</div>
<footer>数据源：Open-Meteo Archive API · 项目：guiguzi502/weather-collector</footer>
<script>
const DATA = __DATA__;
// c1: 城市平均气温横向条形
(function() {{
  const d = DATA.latest.filter(x => x.temp_avg != null).sort((a,b) => a.temp_avg - b.temp_avg);
  echarts.init(document.getElementById('c1')).setOption({{
    grid: {{ left: 60, right: 40, top: 10, bottom: 30 }},
    xAxis: {{ type: 'value', name: '°C' }},
    yAxis: {{ type: 'category', data: d.map(x => x.city) }},
    series: [{{
      type: 'bar', data: d.map(x => ({{
        value: x.temp_avg,
        itemStyle: {{ color: x.temp_avg <= 0 ? '#3B82C4' : x.temp_avg <= 10 ? '#2E86AB' : x.temp_avg <= 20 ? '#E6A817' : '#E05E2B' }}
      }})),
      label: {{ show: true, position: 'right', formatter: '{{c}}°C' }}
    }}]
  }});
}})();
// c2: 长沙气温折线
(function() {{
  const d = DATA.changsha_trend;
  echarts.init(document.getElementById('c2')).setOption({{
    tooltip: {{ trigger: 'axis' }},
    grid: {{ left: 50, right: 20, top: 20, bottom: 40 }},
    xAxis: {{ type: 'category', data: d.map(x => x.date.slice(5)) }},
    yAxis: {{ type: 'value', name: '°C' }},
    series: [
      {{ name: '最高', type: 'line', smooth: true, data: d.map(x => x.temp_max), lineStyle: {{ color: '#E05E2B' }} }},
      {{ name: '日均', type: 'line', smooth: true, data: d.map(x => x.temp_avg), lineStyle: {{ color: '#1F4E79' }} }},
      {{ name: '最低', type: 'line', smooth: true, data: d.map(x => x.temp_min), lineStyle: {{ color: '#3B82C4' }} }}
    ]
  }});
}})();
// c3: 月降水
(function() {{
  const d = DATA.monthly_precip;
  echarts.init(document.getElementById('c3')).setOption({{
    tooltip: {{ trigger: 'axis' }},
    grid: {{ left: 60, right: 20, top: 10, bottom: 40 }},
    xAxis: {{ type: 'category', data: d.map(x => x.month) }},
    yAxis: {{ type: 'value', name: 'mm' }},
    series: [{{ type: 'bar', data: d.map(x => x.precip), itemStyle: {{ color: '#2E86AB' }}, label: {{ show: true, position: 'top' }} }}]
  }});
}})();
// c4: 热力图
(function() {{
  const cities = DATA.heat.cities, days = DATA.heat.days;
  const values = DATA.heat.values;
  echarts.init(document.getElementById('c4')).setOption({{
    tooltip: {{ position: 'top' }},
    grid: {{ left: 60, right: 30, top: 10, bottom: 60 }},
    xAxis: {{ type: 'category', data: days, splitArea: {{ show: true }} }},
    yAxis: {{ type: 'category', data: cities, splitArea: {{ show: true }} }},
    visualMap: {{ min: -5, max: 35, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
      inRange: {{ color: ['#3B82C4', '#E6A817', '#E05E2B'] }} }},
    series: [{{
      type: 'heatmap', data: values,
      label: {{ show: false }},
      emphasis: {{ itemStyle: {{ shadowBlur: 6, shadowColor: 'rgba(0,0,0,.3)' }} }}
    }}]
  }});
}})();
</script>
</body>
</html>"""


def make_html_report(records: list[dict]) -> Path:
    """生成自包含 ECharts 交互式报告。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过 HTML 报告")
        return OUTPUT_DIR / "weather_report.html"

    df["date"] = pd.to_datetime(df["date"])
    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date].to_dict("records")
    for r in latest:
        r["date"] = str(r["date"])[:10]

    changsha = df[df["city"] == "长沙"].sort_values("date").tail(60)
    changsha_trend = changsha.to_dict("records")
    for r in changsha_trend:
        r["date"] = str(r["date"])[:10]

    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["precip"].sum().tail(6)
    monthly_precip = [{"month": m, "precip": round(v, 1)} for m, v in monthly.items()]

    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=30)]
    cities = sorted(recent["city"].unique())
    days = [d.strftime("%m-%d") for d in
            pd.date_range(recent["date"].min(), recent["date"].max(), freq="D")]
    day_set = set(d.strftime("%Y-%m-%d") for d in
                  pd.date_range(recent["date"].min(), recent["date"].max(), freq="D"))
    pivot = recent.pivot(index="city", columns="date", values="temp_avg")
    heat_values = []
    for c in cities:
        for d in day_set:
            dt = pd.Timestamp(d)
            val = pivot.loc[c, dt] if c in pivot.index and dt in pivot.columns else None
            if val is not None and pd.notna(val):
                heat_values.append([cities.index(c), days.index(dt.strftime("%m-%d")), round(float(val), 1)])

    data = {
        "latest": latest,
        "changsha_trend": changsha_trend,
        "monthly_precip": monthly_precip,
        "heat": {"cities": cities, "days": days, "values": heat_values},
    }

    # 修复（2026-11-25）：模板里的 CSS/JS 花括号全部写成 {{ }}（.format 转义写法），
    # 但原实现只做了 .replace("__DATA__")，于是线上页面渲染成字面 {{ }}——
    # 54 处双花括号 = 整页 JS 语法错误，4 张图全不渲染；
    # 而 {date_from}/{total} 也原样输出在页面上。
    # 现在先 format 补齐元信息，再注入 JSON 数据。
    city_count = len({r["city"] for r in records})
    rendered = HTML_TEMPLATE.format(
        city_count=city_count,
        date_from=str(df["date"].min())[:10],
        date_to=str(df["date"].max())[:10],
        total=len(df),
    )

    # 转义检查必须在注入 JSON **之前**做：JSON 的嵌套对象本身就以 }} 结尾，
    # 混在一起判会让正常输出也报错。
    # __DATA__ 不在此列 —— 它按设计留到下一步才替换。
    leftover = [t for t in ("{{", "}}", "{date_from}", "{date_to}",
                            "{total}", "{city_count}")
                if t in rendered]
    if leftover:
        logger.error("HTML 模板仍有未替换标记：%s", ", ".join(leftover))
        return OUTPUT_DIR / "weather_report.html"

    html = rendered.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    if "__DATA__" in html:
        logger.error("HTML 模板 __DATA__ 未注入")
        return OUTPUT_DIR / "weather_report.html"

    path = OUTPUT_DIR / "weather_report.html"
    write_text_lf(path, html)
    logger.info("HTML 报告已生成：%s（%d 城 / %d 条）", path, city_count, len(df))
    return path