# -*- coding: utf-8 -*-
"""数据清洗模块。

- 剔除超出物理合理范围的气温（-40 ~ 45℃）
- 湿度超出 0~100 视为异常置空
- 降水量 < 0 视为异常置 0
- 清洗结果打印统计信息
"""
import logging

logger = logging.getLogger(__name__)

TEMP_LIMIT = (-40.0, 45.0)


def clean(records: list[dict]) -> list[dict]:
    """清洗记录列表，返回新列表（不修改原数据）。"""
    cleaned = []
    dropped_temp = 0
    fixed_hum = 0
    fixed_prec = 0

    for r in records:
        rec = dict(r)

        tmax, tmin, tavg = rec["temp_max"], rec["temp_min"], rec["temp_avg"]
        vals = [v for v in (tmax, tmin, tavg) if v is not None]
        if vals and not (TEMP_LIMIT[0] <= min(vals) and max(vals) <= TEMP_LIMIT[1]):
            dropped_temp += 1
            continue

        hum = rec.get("humidity")
        if hum is not None and not (0 <= hum <= 100):
            rec["humidity"] = None
            fixed_hum += 1

        prec = rec.get("precip")
        if prec is not None and prec < 0:
            rec["precip"] = 0.0
            fixed_prec += 1

        cleaned.append(rec)

    logger.info(
        "清洗完成：共 %d 条，剔除异常气温 %d 条，修正湿度 %d 条，修正降水 %d 条",
        len(records), dropped_temp, fixed_hum, fixed_prec,
    )
    return cleaned