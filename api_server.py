# -*- coding: utf-8 -*-
"""天气数据 API 服务（零依赖，标准库 HTTP）。

把 SQLite 里的天气数据暴露成 REST 接口，供网页/小程序/脚本调用。

用法:
    python api_server.py            # 默认 127.0.0.1:8000
    python api_server.py --port 9000
    python api_server.py --host 0.0.0.0

接口:
    GET /api/weather/长沙            # 某城全部记录（默认最近 30 天）
    GET /api/weather/长沙?days=90   # 最近 90 天
    GET /api/weather/长沙?start=2026-10-01&end=2026-10-31
    GET /api/cities                 # 城市列表 + 数据范围
    GET /api/health                 # 健康检查
    GET /                          # 简易 API 文档页
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import urllib.parse
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("api")

DB_PATH = Path("data/weather.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query_weather(city: str, days: int | None = None,
                  start: str | None = None, end: str | None = None) -> list[dict]:
    """查询天气记录，按参数过滤。"""
    if not start:
        end = end or date.today().isoformat()
        days = days or 30
        start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT city, date, temp_max, temp_min, temp_avg, humidity, precip "
            "FROM weather_records WHERE city = ? AND date >= ? AND date <= ? "
            "ORDER BY date",
            (city, start, end),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_cities() -> list[dict]:
    """城市列表 + 数据范围 + 记录数。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT city, COUNT(*) AS cnt, MIN(date) AS d0, MAX(date) AS d1 "
            "FROM weather_records GROUP BY city ORDER BY city"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "WeatherAPI/1.0"

    def _send(self, code: int, payload: dict, pretty: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False,
                          indent=2 if pretty else None).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        pretty = "pretty" in qs

        if path == "/" or path == "/index.html":
            self._send_docs()
            return
        if path == "/api/health":
            self._send(200, {"status": "ok",
                             "db": str(DB_PATH),
                             "exists": DB_PATH.exists()})
            return
        if path == "/api/cities":
            self._send(200, {"count": len(list_cities()),
                             "cities": list_cities()}, pretty)
            return
        m = re.fullmatch(r"/api/weather/([^/]+)", path)
        if m:
            city = urllib.parse.unquote(m.group(1))
            try:
                days = int(qs.get("days", [""])[0]) if qs.get("days") else None
            except ValueError:
                self._send(400, {"error": "days 参数必须是整数"})
                return
            start = qs.get("start", [None])[0]
            end = qs.get("end", [None])[0]
            if start and end and start > end:
                self._send(400, {"error": "start 不能晚于 end"})
                return
            records = query_weather(city, days=days, start=start, end=end)
            if not records:
                self._send(404, {"error": f"暂无 {city} 的天气数据",
                                 "hint": "先运行 python main.py 采集数据"})
                return
            self._send(200, {"city": city, "count": len(records),
                             "records": records}, pretty)
            return
        self._send(404, {"error": "接口不存在，访问 / 查看文档"})

    def _send_docs(self):
        """简单 API 文档页（JSON 返回 + HTML 说明）。"""
        html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>天气数据 API</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;
padding:0 16px;color:#282E3A}h1{color:#1F4E79}code{background:#F0F3F8;
padding:2px 6px;border-radius:4px}pre{background:#0E1B2E;color:#E8F0FE;
padding:16px;border-radius:8px;overflow-x:auto}</style></head><body>
<h1>🌤 天气数据 API</h1>
<p>本项目通过 GitHub Actions 每日自动采集天气数据，本服务把这些数据暴露为 JSON 接口。</p>
<h2>接口列表</h2>
<ul>
<li><code>GET /api/weather/长沙</code> — 最近 30 天（默认）</li>
<li><code>GET /api/weather/长沙?days=90</code> — 最近 90 天</li>
<li><code>GET /api/weather/长沙?start=2026-10-01&amp;end=2026-10-31</code> — 日期范围</li>
<li><code>GET /api/cities</code> — 城市列表</li>
<li><code>GET /api/health</code> — 健康检查</li>
</ul>
<h2>示例</h2>
<pre>curl "http://127.0.0.1:8000/api/weather/长沙?days=3"</pre>
<p>支持 CORS，可直接被浏览器页面调用。</p>
</body></html>"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)


def main():
    p = argparse.ArgumentParser(description="天气数据 API 服务")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    if not DB_PATH.exists():
        logger.warning("数据库不存在：%s，请先运行 python main.py 采集", DB_PATH)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("天气 API 服务已启动：http://%s:%d", args.host, args.port)
    logger.info("接口文档：http://%s:%d/", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()