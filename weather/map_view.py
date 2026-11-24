# -*- coding: utf-8 -*-
"""全国天气地图：ECharts 中国省级地图（交互式 HTML）。

- 城市 -> 省份聚合（同省多城取均值/总量），色阶显示最新一天气温
- geoJSON 从 docs/china.json 读取并内嵌到 HTML（CI 无需联网下载）
- 浏览器打开 HTML 即可交互（hover 显示详情 / 缩放 / 切换温度与降水）
"""
from __future__ import annotations

import html
import json
import logging
from pathlib import Path

import pandas as pd

from weather.sync import write_text_lf

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
DOCS_DIR = Path("docs")
GEO_FILE = DOCS_DIR / "china.json"

# 城市 -> 省份
CITY_PROVINCE = {
    "北京": "北京市", "上海": "上海市", "重庆": "重庆市",
    "广州": "广东省", "深圳": "广东省",
    "长沙": "湖南省", "武汉": "湖北省",
    "成都": "四川省", "西安": "陕西省",
    "杭州": "浙江省", "南京": "江苏省",
    "沈阳": "辽宁省", "太原": "山西省",
}

ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"


def _e(s) -> str:
    return html.escape(str(s), quote=False)


def _load_geo() -> dict | None:
    if not GEO_FILE.exists():
        logger.warning("地图数据不存在：%s", GEO_FILE)
        return None
    try:
        return json.loads(GEO_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("地图 JSON 解析失败：%s", exc)
        return None


def make_weather_map(records: list[dict]) -> Path:
    """生成全国天气交互地图 HTML，并同步 docs/。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("无数据，跳过天气地图")
        return OUTPUT_DIR / "weather_map.html"

    df["date"] = df["date"].astype(str)
    latest = df["date"].max()
    today = df[df["date"] == latest].copy()
    if today.empty:
        logger.warning("无最新日数据，跳过天气地图")
        return OUTPUT_DIR / "weather_map.html"

    geo = _load_geo()
    if geo is None:
        return OUTPUT_DIR / "weather_map.html"

    today["province"] = today["city"].map(CITY_PROVINCE)
    prov = today.groupby("province").agg(
        temp_avg=("temp_avg", "mean"),
        temp_max=("temp_max", "max"),
        temp_min=("temp_min", "min"),
        precip=("precip", "sum"),
        humidity=("humidity", "mean"),
    ).round(1)

    temp_data = [{"name": p, "value": row["temp_avg"]}
                 for p, row in prov.iterrows()]
    precip_data = [{"name": p, "value": round(row["precip"], 1)}
                   for p, row in prov.iterrows()]

    geo_json = json.dumps(geo, ensure_ascii=False)
    chip = _e(f"数据日期 {latest} · {len(prov)} 省份 · 每日 08:00 自动更新 · 数据源 Open-Meteo")

    rows_html = ""
    for p, row in prov.sort_values("temp_avg", ascending=False).iterrows():
        rows_html += (
            f'<tr><td>{_e(p)}</td><td>{row["temp_avg"]:.1f}°C</td>'
            f'<td>{row["temp_max"]:.0f} / {row["temp_min"]:.0f}°C</td>'
            f'<td>{row["precip"]:.1f}mm</td></tr>'
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>全国天气地图 · {latest}</title>
<script src="{ECHARTS_CDN}"></script>
<style>
  body {{ font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #F4F7FB; color: #282E3A; }}
  header {{ background: linear-gradient(135deg, #1F4E79, #2E86AB);
           color: #fff; padding: 18px 28px; }}
  header h1 {{ margin: 0; font-size: 20px; }}
  header p {{ margin: 6px 0 0; font-size: 12px; opacity: .85; }}
  .wrap {{ max-width: 1200px; margin: 20px auto; padding: 0 16px;
           display: grid; grid-template-columns: 1fr 320px; gap: 16px; }}
  #map {{ height: 640px; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(20,40,80,.08); }}
  .panel {{ background: #fff; border-radius: 12px; padding: 16px;
           box-shadow: 0 2px 12px rgba(20,40,80,.08); height: fit-content; }}
  .panel h3 {{ margin: 0 0 10px; font-size: 14px; color: #1F4E79; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ padding: 7px 4px; text-align: left; border-bottom: 1px solid #EEF1F6; }}
  th {{ color: #8A94A6; font-weight: 600; }}
  .seg {{ display: flex; gap: 8px; margin-bottom: 12px; }}
  .seg button {{ flex: 1; padding: 8px 0; border: 1px solid #D5DCE6; border-radius: 8px;
                 background: #fff; cursor: pointer; font-size: 13px; color: #454D5C; }}
  .seg button.on {{ background: #1F4E79; color: #fff; border-color: #1F4E79; }}
  footer {{ text-align: center; color: #A0A8B4; font-size: 12px; padding: 24px 0; }}
</style></head><body>
<header>
  <h1>🗺 全国天气地图（{latest}）</h1>
  <p>{chip}</p>
</header>
<div class="wrap">
  <div>
    <div class="seg">
      <button id="btnTemp" class="on" onclick="switchView('temp')">🌡 平均气温</button>
      <button id="btnPrecip" onclick="switchView('precip')">🌧 降水量</button>
    </div>
    <div id="map"></div>
  </div>
  <div class="panel">
    <h3>📋 省份数据</h3>
    <table>
      <tr><th>省份</th><th>均温</th><th>最高/低</th><th>降水</th></tr>
      {rows_html}
    </table>
  </div>
</div>
<footer>数据来自 Open-Meteo · 由 GitHub Actions 每日自动更新 · <a href="https://github.com/guiguzi502/weather-collector">weather-collector</a></footer>
<script>
const geoJson = {geo_json};
const tempData = {json.dumps(temp_data, ensure_ascii=False)};
const precipData = {json.dumps(precip_data, ensure_ascii=False)};
echarts.registerMap("china", geoJson);
const chart = echarts.init(document.getElementById("map"));
const baseOpt = {{
  tooltip: {{ trigger: "item", formatter: p => p.name + "<br/>" + p.value + (p.seriesName === "平均气温" ? " °C" : " mm") }},
  visualMap: {{ min: 0, max: 30, left: 10, bottom: 20, text: ["热", "冷"],
               inRange: {{ color: ["#3778C2", "#8BB8E8", "#F6E3B4", "#F4A460", "#D64541"] }},
               textStyle: {{ color: "#8A94A6" }} }},
  series: [{{ name: "平均气温", type: "map", map: "china", roam: true,
             label: {{ show: true, fontSize: 9 }},
             emphasis: {{ label: {{ fontSize: 12 }}, itemStyle: {{ shadowBlur: 12, shadowColor: "rgba(0,0,0,.3)" }} }},
             data: tempData }}]
}};
chart.setOption(baseOpt);
function switchView(k) {{
  document.getElementById("btnTemp").className = k === "temp" ? "on" : "";
  document.getElementById("btnPrecip").className = k === "precip" ? "on" : "";
  chart.setOption({{
    series: [{{ name: k === "temp" ? "平均气温" : "降水量",
               data: k === "temp" ? tempData : precipData }}],
    visualMap: k === "temp"
      ? {{ min: 0, max: 30, inRange: {{ color: ["#3778C2", "#8BB8E8", "#F6E3B4", "#F4A460", "#D64541"] }} }}
      : {{ min: 0, max: Math.max(...precipData.map(d => d.value), 1),
           inRange: {{ color: ["#EAF3FB", "#7FB3E8", "#2E6FB7"] }} }}
  }});
}}
window.addEventListener("resize", () => chart.resize());
</script>
</body></html>"""
    path = OUTPUT_DIR / "weather_map.html"
    write_text_lf(path, html_doc)
    # 同步到 docs/ 由 weather/sync.py 统一处理（geoJSON 来源 docs/china.json 保持不变）
    logger.info("全国天气地图已生成：%s", path)
    return path