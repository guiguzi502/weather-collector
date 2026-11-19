# -*- coding: utf-8 -*-
"""报告生成模块：SVG 天气卡片 + ECharts 交互式 HTML 报告。"""
import json
import logging
from pathlib import Path

import pandas as pd

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


def make_svg_card(records: list[dict]) -> Path:
    """生成 12 城今日天气总览 SVG 卡片（宽 720，GitHub 原生渲染）。"""
    _ensure_dir()
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过 SVG 卡片")
        return OUTPUT_DIR / "weather_card.svg"

    latest = df["date"].max()
    today = df[df["date"] == latest].sort_values("city")
    return _write_native_svg(today, latest)

def _write_native_svg(today: pd.DataFrame, latest: str) -> Path:
    """用原生 SVG 元素绘制（兼容 GitHub 渲染器）。"""
    y = 78
    parts = []
    for _, r in today.iterrows():
        t = r["temp_avg"] if pd.notna(r["temp_avg"]) else None
        color = _temp_color(t)
        bar_w = max(8, min(420, (t + 15) * 9)) if t is not None else 8
        parts.append(
            f'<text x="24" y="{y + 12}" font-size="13" font-weight="600" fill="#282E3A">{r["city"]}</text>'
            f'<rect x="76" y="{y}" width="420" height="14" rx="7" fill="#EFF2F6"/>'
            f'<rect x="76" y="{y}" width="{bar_w:.0f}" height="14" rx="7" fill="{color}"/>'
            f'<text x="508" y="{y + 12}" font-size="13" font-weight="700" fill="{color}">{t:.1f}°C</text>'
            f'<text x="566" y="{y + 12}" font-size="12" fill="#8A94A6">降水 {r["precip"]:.1f}mm</text>'
        )
        y += 34

    height = y + 30
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}">
  <rect width="720" height="{height}" rx="12" fill="#FFFFFF" stroke="#E4E8EE" stroke-width="1.5"/>
  <text x="24" y="34" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="18" font-weight="700" fill="#1F4E79">🌤 12 城天气总览</text>
  <text x="24" y="58" font-family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, sans-serif" font-size="12" fill="#8A94A6">数据日期：{latest} · 每日 08:00 自动更新 · 数据源 Open-Meteo</text>
  {''.join(parts)}
</svg>'''
    path = OUTPUT_DIR / "weather_card.svg"
    path.write_text(svg, encoding="utf-8")
    logger.info("SVG 天气卡已生成：%s", path)
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
<h1>🌤 12 城天气数据可视化报告</h1>
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
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    path = OUTPUT_DIR / "weather_report.html"
    path.write_text(html, encoding="utf-8")
    logger.info("HTML 报告已生成：%s", path)
    return path