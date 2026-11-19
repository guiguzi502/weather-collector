# -*- coding: utf-8 -*-
"""单元测试：清洗 / 存储 / 可视化 / 报告 / 年度账单 / API。

运行: python -m pytest tests/ -v
CI:   .github/workflows/daily.yml 中 pytest 步骤
"""
import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weather import cleaner, storage  # noqa: E402


# ------------------------------------------------ 清洗
class TestCleaner:
    def test_normal_record_passes(self):
        rec = {"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
               "temp_min": 7.0, "temp_avg": 11.5,
               "humidity": 60.0, "precip": 0.0}
        out = cleaner.clean([rec])
        assert len(out) == 1
        assert out[0]["temp_avg"] == 11.5

    def test_outlier_temp_dropped(self):
        rec = {"city": "长沙", "date": "2026-11-19", "temp_max": 99.0,
               "temp_min": -80.0, "temp_avg": 55.0,
               "humidity": 60.0, "precip": 0.0}
        out = cleaner.clean([rec])
        assert len(out) == 0

    def test_humidity_out_of_range_set_none(self):
        rec = {"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
               "temp_min": 7.0, "temp_avg": 11.5,
               "humidity": 150.0, "precip": 1.0}
        out = cleaner.clean([rec])
        assert out[0]["humidity"] is None

    def test_negative_precip_zeroed(self):
        rec = {"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
               "temp_min": 7.0, "temp_avg": 11.5,
               "humidity": 60.0, "precip": -3.0}
        out = cleaner.clean([rec])
        assert out[0]["precip"] == 0.0


# ------------------------------------------------ 存储
class TestStorage:
    @pytest.fixture()
    def db(self, tmp_path):
        path = tmp_path / "test.db"
        return storage.Storage(str(path))

    def test_upsert_and_query(self, db):
        recs = [{"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
                 "temp_min": 7.0, "temp_avg": 11.5, "humidity": 60.0, "precip": 0.0}]
        assert db.upsert_many(recs) == 1
        rows = db.query(city="长沙")
        assert len(rows) == 1
        assert rows[0]["temp_avg"] == 11.5

    def test_dedup_by_city_date(self, db):
        base = {"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
                "temp_min": 7.0, "temp_avg": 11.5, "humidity": 60.0, "precip": 0.0}
        db.upsert_many([dict(base)])
        db.upsert_many([dict(base, temp_avg=12.8)])  # 同 key 覆盖
        rows = db.query(city="长沙")
        assert len(rows) == 1
        assert rows[0]["temp_avg"] == 12.8

    def test_summary(self, db):
        recs = [{"city": "长沙", "date": f"2026-11-{d:02d}", "temp_max": 16.0,
                 "temp_min": 7.0, "temp_avg": 11.0, "humidity": 60.0, "precip": 0.0}
                for d in range(1, 4)]
        db.upsert_many(recs)
        summary = db.summary()
        assert summary["total"] == 3
        assert summary["cities"] == 1
        assert summary["date_from"] == "2026-11-01"

    def test_query_with_date_range(self, db):
        recs = [{"city": "上海", "date": f"2026-10-{d:02d}", "temp_max": 20.0,
                 "temp_min": 15.0, "temp_avg": 17.5, "humidity": 60.0, "precip": 0.0}
                for d in (5, 10, 20)]
        db.upsert_many(recs)
        rows = db.query(city="上海", start="2026-10-06", end="2026-10-15")
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-10-10"


# ------------------------------------------------ API
class TestAPIServer:
    """用临时 db + 内置服务实测 API 查询逻辑。"""

    @pytest.fixture()
    def api(self, tmp_path):
        """起一个真实 HTTP 服务，指向临时数据库。"""
        import threading
        from http.server import ThreadingHTTPServer

        db_path = tmp_path / "api_test.db"
        db = storage.Storage(str(db_path))
        db.upsert_many([
            {"city": "长沙", "date": "2026-11-19", "temp_max": 16.0,
             "temp_min": 7.0, "temp_avg": 11.1, "humidity": 71.9, "precip": 0.0},
            {"city": "太原", "date": "2026-11-19", "temp_max": 6.0,
             "temp_min": -2.0, "temp_avg": 0.3, "humidity": 50.0, "precip": 1.2},
        ])
        db.close()

        # 复用 api_server.Handler，但指向临时 db
        import api_server
        orig_db = api_server.DB_PATH
        api_server.DB_PATH = db_path

        server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.shutdown()
            api_server.DB_PATH = orig_db  # 请求全部结束后再恢复

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_health(self, api):
        data = self._get(f"{api}/api/health")
        assert data["status"] == "ok"

    def test_weather_query(self, api):
        import urllib.parse
        city = urllib.parse.quote("长沙")
        data = self._get(f"{api}/api/weather/{city}?days=30")
        assert data["city"] == "长沙"
        assert data["count"] >= 1
        # API 按日期升序返回，最后一条是最新数据
        assert data["records"][-1]["temp_avg"] == 11.1

    def test_unknown_city_404(self, api):
        import urllib.error
        import urllib.parse
        city = urllib.parse.quote("不存在城")
        with pytest.raises(urllib.error.HTTPError) as ei:
            self._get(f"{api}/api/weather/{city}")
        assert ei.value.code == 404

    def test_cities_list(self, api):
        data = self._get(f"{api}/api/cities")
        names = {c["city"] for c in data["cities"]}
        assert {"长沙", "太原"} <= names