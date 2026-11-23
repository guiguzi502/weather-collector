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

from weather import cleaner, storage, sync  # noqa: E402


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


# ------------------------------------------------ 同步（回归测试）
class TestSyncDocs:
    """锁定 2026-11-23 的 bug：README 引用 docs/，但没人往 docs/ 写。

    真实症状：daily.yml 只 git add data/ output/ README.md，
    docs/ 从 11-20 起冻住，README 图片永远停在旧数据。
    """

    def test_sync_copies_all_listed_files(self, tmp_path):
        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        for name in sync.SYNC_FILES:
            (out / name).write_bytes(b"data-" + name.encode())

        synced = sync.sync_docs(out, docs)

        assert set(synced) == set(sync.SYNC_FILES)
        for name in sync.SYNC_FILES:
            assert (docs / name).exists(), f"{name} 没被同步到 docs/"

    def test_sync_skips_identical_content(self, tmp_path):
        """内容相同不重复覆盖，避免无意义刷新 mtime。"""
        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        docs.mkdir()
        name = sync.SYNC_FILES[0]
        (out / name).write_bytes(b"same")
        sync.sync_docs(out, docs)

        second = sync.sync_docs(out, docs)
        assert second == [], "内容未变时应跳过"

    def test_sync_overwrites_changed_content(self, tmp_path):
        """内容变了必须覆盖——这正是之前 docs/ 冻住的原因。"""
        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        docs.mkdir()
        name = sync.SYNC_FILES[0]
        (out / name).write_bytes(b"old")
        sync.sync_docs(out, docs)
        assert (docs / name).read_bytes() == b"old"

        (out / name).write_bytes(b"new-content")
        synced = sync.sync_docs(out, docs)

        assert name in synced
        assert (docs / name).read_bytes() == b"new-content"

    def test_sync_missing_source_is_skipped(self, tmp_path):
        """产物缺失时跳过而不是崩溃（单城市跑等场景）。"""
        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        name = sync.SYNC_FILES[0]
        (out / name).write_bytes(b"x")

        synced = sync.sync_docs(out, docs)

        assert synced == [name]
        assert not (docs / sync.SYNC_FILES[1]).exists()

    def test_sync_preserves_unrelated_docs_files(self, tmp_path):
        """docs/china.json 是静态资源，不能被同步逻辑动到。"""
        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        docs.mkdir()
        static = docs / "china.json"
        static.write_bytes(b'{"type":"FeatureCollection"}')

        sync.sync_docs(out, docs)

        assert static.exists()
        assert static.read_bytes() == b'{"type":"FeatureCollection"}'

    def test_sync_list_covers_readme_images(self, tmp_path, monkeypatch):
        """README 里引用的 docs/ 图片必须在 SYNC_FILES 清单里。

        这是最直接的一条防线：清单漏了哪个文件，这个测试就红。
        """
        readme = Path(__file__).resolve().parents[1] / "README.md"
        if not readme.exists():
            pytest.skip("README.md 不存在")

        import re
        text = readme.read_text(encoding="utf-8")
        refs = [r for r in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
                if not r.startswith(("http://", "https://"))]

        listed = set(sync.SYNC_FILES)
        missing_from_list = [
            Path(r).name for r in refs
            if str(Path(r).parent).replace("\\", "/") == "docs"
            and Path(r).name not in listed
        ]
        assert not missing_from_list, (
            f"README 引用但 SYNC_FILES 未列出的文件：{missing_from_list}"
        )

    def test_check_readme_refs_reports_missing(self, tmp_path):
        """check_readme_refs 能抓出指向不存在文件的引用。"""
        readme = tmp_path / "README.md"
        readme.write_text(
            "# t\n\n"
            "![a](docs/present.png)\n"
            "![b](docs/absent.png)\n"
            "![c](https://example.com/remote.png)\n",
            encoding="utf-8",
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "present.png").write_bytes(b"x")

        cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_path)
            missing = sync.check_readme_refs(readme)
        finally:
            os.chdir(cwd)

        assert missing == ["docs/absent.png"], "远程 URL 不该算缺失，存在的不该报"


class TestVerifyReadme:
    """锁定「docs/ 与 output/ 不同步」这个故障的直接防线。

    2026-11-23 事故：output/ 天天更新，docs/ 冻在 2025-11-20，
    README 图片永远显示旧数据。verify_readme.py 必须能抓出这种漂移。
    """

    @pytest.fixture()
    def sandbox(self, tmp_path, monkeypatch):
        """临时工作目录：output/ + docs/ 各放一份相同产物。"""
        import verify_readme

        out = tmp_path / "output"
        docs = tmp_path / "docs"
        out.mkdir()
        docs.mkdir()
        name = sync.SYNC_FILES[0]
        (out / name).write_bytes(b"fresh-data")
        (docs / name).write_bytes(b"fresh-data")

        monkeypatch.setattr(verify_readme, "OUTPUT_DIR", out)
        monkeypatch.setattr(verify_readme, "DOCS_DIR", docs)
        return verify_readme, out, docs, name

    def test_consistent_state_passes(self, sandbox):
        mod, out, docs, name = sandbox
        assert mod.diff_docs_vs_output() == []

    def test_detects_stale_docs(self, sandbox):
        """docs/ 落后于 output/ ——正是事故现场。"""
        mod, out, docs, name = sandbox
        (docs / name).write_bytes(b"old-stale")

        stale = mod.diff_docs_vs_output()

        assert stale, "docs/ 落后时必须报出来"
        assert name in stale[0]

    def test_detects_missing_in_docs(self, sandbox):
        mod, out, docs, name = sandbox
        (docs / name).unlink()

        stale = mod.diff_docs_vs_output()

        assert stale
        assert "缺失" in stale[0]

    def test_missing_output_is_not_an_error(self, sandbox):
        """本地只跑单城市时某些产物不存在，不该判失败。"""
        mod, out, docs, name = sandbox
        (out / name).unlink()
        (docs / name).unlink()

        assert mod.diff_docs_vs_output() == []


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