# -*- coding: utf-8 -*-
"""2026-11-25 缺陷回归测试：缺口回补 / 图表按城过滤 / HTML 模板。

这三个都是「CI 显示 success 但产物实际是错的」那类静默缺陷，
单独一个文件便于一眼看出防线覆盖了哪些历史事故。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weather import gaps  # noqa: E402


# ------------------------------------------------ 缺口回补
class TestGaps:
    """永久缺口修复的核心逻辑。

    背景：原来每天只采「昨天」一天。2026-11-24 archive-api 抖动，
    杭州、南京连续 3 次超时，窗口第二天滑走 → 11-23 两城永久缺失，
    而 CI 依然 success。现在每次运行回补最近 N 天缺口。
    """

    def test_contiguous_single_day(self):
        assert gaps.contiguous_ranges(["2026-11-23"]) == [("2026-11-23", "2026-11-23")]

    def test_contiguous_merges_run(self):
        got = gaps.contiguous_ranges(["2026-11-21", "2026-11-22", "2026-11-23"])
        assert got == [("2026-11-21", "2026-11-23")]

    def test_contiguous_splits_gap(self):
        got = gaps.contiguous_ranges(["2026-11-18", "2026-11-19", "2026-11-23"])
        assert got == [("2026-11-18", "2026-11-19"), ("2026-11-23", "2026-11-23")]

    def test_contiguous_dedupes_and_sorts(self):
        got = gaps.contiguous_ranges(["2026-11-22", "2026-11-20", "2026-11-22"])
        assert got == [("2026-11-20", "2026-11-20"), ("2026-11-22", "2026-11-22")]

    def test_contiguous_empty(self):
        assert gaps.contiguous_ranges([]) == []

    def test_date_range_inclusive(self):
        got = gaps.date_range("2026-11-21", "2026-11-23")
        assert got == ["2026-11-21", "2026-11-22", "2026-11-23"]

    def test_date_range_single(self):
        assert gaps.date_range("2026-11-23", "2026-11-23") == ["2026-11-23"]

    def test_plan_skips_complete_city(self):
        """完整覆盖的城市不能出现在计划里 —— 否则每天白请求 API。"""
        existing = {"长沙": {"2026-11-21", "2026-11-22", "2026-11-23"}}
        plan = gaps.plan_backfill(["长沙"], existing, "2026-11-21", "2026-11-23")
        assert plan == {}

    def test_plan_fills_hole(self):
        """杭州缺 11-23（真实事故复现），应只补那一天。"""
        existing = {"杭州": {"2026-11-21", "2026-11-22"}}
        plan = gaps.plan_backfill(["杭州"], existing, "2026-11-21", "2026-11-23")
        assert plan == {"杭州": [("2026-11-23", "2026-11-23")]}

    def test_plan_missing_city_gets_full_window(self):
        plan = gaps.plan_backfill(["新城市"], {}, "2026-11-21", "2026-11-23")
        assert plan == {"新城市": [("2026-11-21", "2026-11-23")]}

    def test_plan_two_cities_independent(self):
        existing = {
            "杭州": {"2026-11-22", "2026-11-23"},
            "南京": {"2026-11-23"},
        }
        plan = gaps.plan_backfill(["杭州", "南京"], existing,
                                  "2026-11-21", "2026-11-23")
        assert plan == {
            "杭州": [("2026-11-21", "2026-11-21")],
            "南京": [("2026-11-21", "2026-11-22")],
        }

    def test_plan_normal_day_requests_one_day(self):
        """正常日行为不变：前 6 天都有，只缺昨天 → 只请求昨天那一天。

        CI 用 ``--days 1`` + ``BACKFILL_DAYS=7``，检查窗口共 7 天。
        若不做这一步收敛，每天会白拉 7 天数据（13 城 × 7 天）。
        """
        existing = {"长沙": {"2026-11-17", "2026-11-18", "2026-11-19",
                             "2026-11-20", "2026-11-21", "2026-11-22"}}
        plan = gaps.plan_backfill(["长沙"], existing, "2026-11-17", "2026-11-23")
        assert plan == {"长沙": [("2026-11-23", "2026-11-23")]}

    def test_coverage_counts_complete_only(self):
        days = ["2026-11-21", "2026-11-22", "2026-11-23"]
        existing = {
            "杭州": {"2026-11-21", "2026-11-22", "2026-11-23"},
            "南京": {"2026-11-21", "2026-11-22"},           # 缺一天 = 不完整
        }
        assert gaps.coverage(["杭州", "南京"], existing, days) == (1, 2)

    def test_coverage_all_complete(self):
        days = ["2026-11-22", "2026-11-23"]
        existing = {"杭州": set(days), "南京": set(days)}
        assert gaps.coverage(["杭州", "南京"], existing, days) == (2, 2)


# ------------------------------------------------ 图表按城市过滤
class TestVisualizeFiltering:
    """原实现忘了按 city 过滤，13 城数据全画进同一条折线
    （同一天 13 个点，图上是来回锯齿）。这里锁死「只画目标城市」。
    """

    @pytest.fixture()
    def records(self):
        rows = []
        for city in ("长沙", "北京"):
            for d, t in (("2026-11-21", 10.0), ("2026-11-22", 20.0),
                         ("2026-11-23", 30.0)):
                rows.append({"city": city, "date": d, "temp_max": t + 2,
                             "temp_min": t - 2, "temp_avg": t,
                             "humidity": 50.0, "precip": 0.0})
        return rows

    def test_plot_daily_temperature_produces_file(self, records, tmp_path,
                                                  monkeypatch):
        from weather import visualize
        monkeypatch.setattr(visualize, "OUTPUT_DIR", tmp_path)
        path = visualize.plot_daily_temperature(records, "长沙", days=60)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_plot_unknown_city_does_not_crash(self, records, tmp_path,
                                             monkeypatch):
        from weather import visualize
        monkeypatch.setattr(visualize, "OUTPUT_DIR", tmp_path)
        path = visualize.plot_daily_temperature(records, "不存在城", days=60)
        assert path.name == "temperature_trend.png"

    def test_plot_empty_records_does_not_crash(self, tmp_path, monkeypatch):
        from weather import visualize
        monkeypatch.setattr(visualize, "OUTPUT_DIR", tmp_path)
        path = visualize.plot_daily_temperature([], "长沙", days=60)
        assert path.name == "temperature_trend.png"

    def test_cjk_font_detection_returns_str_or_none(self):
        """CI 上没装中文字体时图里中文全是方框（36 条 Glyph missing 警告）。

        探测函数至少要能返回 str 或 None，不能抛异常。
        """
        from weather import visualize
        assert visualize.CJK_FONT is None or isinstance(visualize.CJK_FONT, str)


# ------------------------------------------------ HTML 报告模板
class TestHtmlReport:
    """模板用 {{ }} 做 .format 转义，但原实现只 replace("__DATA__")，
    线上页面出现 54 处字面双花括号 → 整页 JS 语法错误，4 张图全不渲染。
    """

    @pytest.fixture()
    def records(self):
        rows = []
        for city in ("长沙", "北京", "太原"):
            for d in ("2026-11-21", "2026-11-22", "2026-11-23"):
                rows.append({"city": city, "date": d, "temp_max": 20.0,
                             "temp_min": 10.0, "temp_avg": 15.0,
                             "humidity": 55.0, "precip": 0.0})
        return rows

    def _render(self, records, tmp_path, monkeypatch):
        from weather import report
        monkeypatch.setattr(report, "OUTPUT_DIR", tmp_path)
        return report.make_html_report(records)

    def test_no_double_braces_left(self, records, tmp_path, monkeypatch):
        text = self._render(records, tmp_path, monkeypatch).read_text("utf-8")
        assert "{{" not in text, "模板里的 {{ }} 未展开，JS 会语法错误"
        # 行首的 }} 只可能来自未展开的模板（JSON 里不会换行后紧跟 }}）
        assert "\n}}" not in text

    def test_placeholders_replaced(self, records, tmp_path, monkeypatch):
        text = self._render(records, tmp_path, monkeypatch).read_text("utf-8")
        for marker in ("{date_from}", "{date_to}", "{total}", "__DATA__",
                       "{city_count}"):
            assert marker not in text, "占位符 %s 未替换" % marker

    def test_meta_shows_real_values(self, records, tmp_path, monkeypatch):
        text = self._render(records, tmp_path, monkeypatch).read_text("utf-8")
        assert "数据区间：2026-11-21 ~ 2026-11-23" in text

    def test_city_count_dynamic(self, records, tmp_path, monkeypatch):
        text = self._render(records, tmp_path, monkeypatch).read_text("utf-8")
        assert "3 城天气数据可视化报告" in text

    def test_data_injected(self, records, tmp_path, monkeypatch):
        text = self._render(records, tmp_path, monkeypatch).read_text("utf-8")
        assert "const DATA = {" in text
        assert "长沙" in text

    def test_empty_records_does_not_crash(self, tmp_path, monkeypatch):
        from weather import report
        monkeypatch.setattr(report, "OUTPUT_DIR", tmp_path)
        path = report.make_html_report([])
        assert path.name == "weather_report.html"


# ------------------------------------------------ verify_readme 的 HTML 检查
class TestVerifyReadmeHtml:
    def test_flags_leftover_braces(self, tmp_path):
        import verify_readme
        bad = tmp_path / "bad.html"
        bad.write_text("<div>{{ still }}</div>{total}", encoding="utf-8")
        problems = verify_readme.check_html_report(bad)
        assert problems, "残留双花括号必须被检出"

    def test_flags_missing_file(self, tmp_path):
        import verify_readme
        problems = verify_readme.check_html_report(tmp_path / "nope.html")
        assert problems and "不存在" in problems[0]

    def test_passes_clean_html(self, tmp_path):
        import verify_readme
        good = tmp_path / "good.html"
        good.write_text("<div>数据区间：2026-11-21 ~ 2026-11-23</div>",
                        encoding="utf-8")
        assert verify_readme.check_html_report(good) == []


# ------------------------------------------------ 城市数量单一真相源
class TestCityCount:
    def test_all_cities_counted(self):
        from config import CITIES
        assert len(CITIES) == 13, "config.CITIES 变更时同步更新 README 与各处文案"

    def test_no_hardcoded_12_in_sources(self):
        """代码里不能再出现硬编码「12 城」，否则配置文件加城就不同步了。"""
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for py in root.glob("weather/*.py"):
            for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                if "12 城" in line or "12城" in line:
                    offenders.append("%s:%d" % (py.name, i))
        assert not offenders, "仍有硬编码 12 城：%s" % offenders


# ------------------------------------------------ 业务时区
class TestClock:
    """CI runner 是 UTC，date.today() 在北京 00:00–08:00 之间会算成前一天。

    2026-11-25 00:27（北京）手动 dispatch 那次，徽章写成「运行于 11-24」，
    就是这个问题。所有业务日期必须显式按 Asia/Shanghai 计算。
    """

    def test_now_is_utc_plus_8(self):
        from weather import clock
        n = clock.now()
        assert n.utcoffset() is not None
        assert n.utcoffset().total_seconds() == 8 * 3600

    def test_today_matches_beijing_date(self):
        from datetime import datetime, timedelta, timezone
        from weather import clock
        beijing = datetime.now(timezone(timedelta(hours=8))).date()
        assert clock.today() == beijing

    def test_yesterday_is_today_minus_one(self):
        from datetime import timedelta
        from weather import clock
        assert clock.yesterday() == clock.today() - timedelta(days=1)

    def test_iso_helpers(self):
        from weather import clock
        assert clock.iso_today() == clock.today().isoformat()
        assert clock.iso_yesterday() == clock.yesterday().isoformat()

    def test_tz_fallback_when_zoneinfo_missing(self):
        """Windows 无 tzdata 时应退回固定 +08:00，而不是抛异常。"""
        from datetime import datetime
        from weather import clock
        off = datetime.now(clock._tz()).utcoffset()
        assert off is not None and off.total_seconds() == 8 * 3600

    def test_entry_points_have_no_local_date_today(self):
        """入口脚本不能再用本地 date.today()，否则 CI 上又会差一天。"""
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for name in ("main.py", "api_server.py", "star_milestone.py"):
            path = root / name
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if "date.today()" in line or "datetime.now()" in line:
                    offenders.append("%s:%d" % (name, i))
        assert not offenders, "仍有本地时区调用：%s" % offenders