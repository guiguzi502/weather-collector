# -*- coding: utf-8 -*-
"""Star 里程碑自动记录脚本。

监听仓库 star 数，达到里程碑（10/50/100/500/1000）时在
docs/star_milestones.md 追加一行庆祝记录，供 GitHub Actions 提交。
"""
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from weather import clock
from weather.sync import write_text_lf

REPO = "guiguzi502/weather-collector"
MILESTONES = [10, 50, 100, 500, 1000]
FILE = Path("docs/star_milestones.md")

HEADER = """# ⭐ Star 里程碑

记录本仓库达成的重要 Star 节点。每日 08:00 自动检查，达到即记录 🎉

| 里程碑 | 达成时间 | 当时 Star 数 |
|---|---|---|
"""


def get_stars(token: str = "") -> int:
    """调用 GitHub API 获取 star 数。"""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return int(data.get("stargazers_count", 0))


def load_done() -> set[int]:
    """读取已记录的里程碑。"""
    done: set[int] = set()
    if not FILE.exists():
        return done
    for line in FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d+)\s*⭐", line)
        if m:
            done.add(int(m.group(1)))
    return done


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    stars = get_stars(token)
    print(f"当前 Star 数: {stars}")

    done = load_done()
    reached = [m for m in MILESTONES if stars >= m and m not in done]
    if not reached:
        print("无新里程碑需要记录")
        return 0

    FILE.parent.mkdir(parents=True, exist_ok=True)
    if FILE.exists():
        text = FILE.read_text(encoding="utf-8")
    else:
        text = HEADER

    # 里程碑时间按北京时间记录（CI runner 是 UTC，直接 datetime.now() 会差 8 小时）
    now = clock.now().strftime("%Y-%m-%d %H:%M")
    for m in sorted(reached):
        row = f"| {m} ⭐ | {now} | {stars} |\n"
        text += row
        print(f"记录里程碑: {m} ⭐（当时 {stars}）")

    write_text_lf(FILE, text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())