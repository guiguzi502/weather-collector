# -*- coding: utf-8 -*-
"""SQLite 存储模块。

- 按 (city, date) 唯一约束，重复采集自动去重（INSERT OR REPLACE）
- 支持按城市、日期范围查询
"""
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_records (
    city       TEXT NOT NULL,
    date       TEXT NOT NULL,
    temp_max   REAL,
    temp_min   REAL,
    temp_avg   REAL,
    humidity   REAL,
    precip     REAL,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (city, date)
);
"""


class Storage:
    def __init__(self, db_path: str = "data/weather.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def upsert_many(self, records: list[dict]) -> int:
        """写入/更新记录，返回受影响行数。"""
        if not records:
            return 0
        rows = [
            (
                r["city"], r["date"], r["temp_max"], r["temp_min"],
                r["temp_avg"], r.get("humidity"), r.get("precip"),
            )
            for r in records
            if r.get("date") and r.get("city")
        ]
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO weather_records
                (city, date, temp_max, temp_min, temp_avg, humidity, precip)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        logger.info("写入 %d 条记录到 %s", len(rows), self.db_path)
        return len(rows)

    def query(self, city: str | None = None,
              start: str | None = None, end: str | None = None) -> list[dict]:
        """按条件查询记录。"""
        sql = "SELECT city, date, temp_max, temp_min, temp_avg, humidity, precip FROM weather_records WHERE 1=1"
        params: list = []
        if city:
            sql += " AND city = ?"
            params.append(city)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY date"
        cur = self._conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def summary(self) -> dict:
        """数据库概况。"""
        cur = self._conn.execute(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT city) AS cities, MIN(date) AS d0, MAX(date) AS d1 FROM weather_records"
        )
        row = cur.fetchone()
        return {
            "total": row[0],
            "cities": row[1],
            "date_from": row[2],
            "date_to": row[3],
        }

    def close(self):
        self._conn.close()