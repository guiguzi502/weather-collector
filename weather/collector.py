# -*- coding: utf-8 -*-
"""Open-Meteo API 数据采集模块。

- 无需 API Key
- 指数退避重试
- 输出标准化的记录列表
"""
import logging
import time

import requests

from config import CITIES, TIMEOUT, RETRY_TIMES, RETRY_BACKOFF

logger = logging.getLogger(__name__)

API_URL = "https://archive-api.open-meteo.com/v1/archive"

# 需要采集的指标（Open-Meteo 字段名）
HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
]


def _fetch_city(lat: float, lon: float, start: str, end: str) -> dict | None:
    """抓取单个城市指定日期范围的逐小时数据，失败重试。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(HOURLY_FIELDS),
        "timezone": "Asia/Shanghai",
    }
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("城市(%.2f,%.2f) 第 %d 次请求失败: %s", lat, lon, attempt, exc)
            if attempt < RETRY_TIMES:
                time.sleep(RETRY_BACKOFF ** attempt)
    return None


def _hourly_to_daily(hourly: dict) -> list[dict]:
    """把逐小时数据聚合成逐日记录。

    返回 [{"date": "2025-08-29", "temp_max": 33.2, "temp_min": 26.4,
            "temp_avg": 29.8, "humidity": 78.0, "precip": 0.0}, ...]
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    hums = hourly.get("relative_humidity_2m", [])
    precs = hourly.get("precipitation", [])

    daily = {}
    for i, t in enumerate(times):
        date = t[:10]  # "2025-08-29T08:00" -> "2025-08-29"
        rec = daily.setdefault(date, {"temps": [], "hums": [], "prec": 0.0})
        rec["temps"].append(temps[i])
        rec["hums"].append(hums[i])
        rec["prec"] += precs[i]

    result = []
    for date, rec in daily.items():
        temps_ok = [v for v in rec["temps"] if v is not None]
        hums_ok = [v for v in rec["hums"] if v is not None]
        if not temps_ok:
            continue
        result.append({
            "date": date,
            "temp_max": max(temps_ok),
            "temp_min": min(temps_ok),
            "temp_avg": round(sum(temps_ok) / len(temps_ok), 1),
            "humidity": round(sum(hums_ok) / len(hums_ok), 1) if hums_ok else None,
            "precip": round(rec["prec"], 1),
        })
    return result


def collect(city: str, start: str, end: str) -> list[dict]:
    """采集一个城市 [start, end] 区间的数据，返回标准记录列表。"""
    lat, lon = CITIES[city]
    logger.info("采集 %s (%s ~ %s) ...", city, start, end)
    payload = _fetch_city(lat, lon, start, end)
    if payload is None or "hourly" not in payload:
        logger.error("采集 %s 失败：无有效数据", city)
        return []

    records = _hourly_to_daily(payload["hourly"])
    for r in records:
        r["city"] = city
    logger.info("采集 %s 成功：%d 天", city, len(records))
    return records