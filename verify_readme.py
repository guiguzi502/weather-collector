# -*- coding: utf-8 -*-
"""CI 自检：README 引用的图片必须存在，且 docs/ 必须与 output/ 同源。

检查两件事：
1. README 里 ``![](docs/xxx.png)`` 引用的文件都真实存在
2. ``docs/`` 里每个同步产物的内容与 ``output/`` 里的**逐字节相同**

第 2 条是 2026-11-23 那次故障的直接防线：
    daily.yml 只 git add 了 data/ output/ README.md，漏掉 docs/，
    导致 output/ 天天更新而 docs/ 冻在 2025-11-20，
    README 图片永远停在旧数据，看起来就像"自动更新坏了"。

第 3 条（2026-11-25 加）：``output/weather_report.html`` 里不能残留
    模板标记 —— 那次线上页面有 54 处字面 ``{{ }}``，整页 JS 语法错误。

用法:
    python verify_readme.py

退出码 0 = 通过，1 = 有问题（CI 直接红）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from weather.sync import SYNC_FILES, check_readme_refs  # noqa: E402

OUTPUT_DIR = Path("output")
DOCS_DIR = Path("docs")


def diff_docs_vs_output() -> list[str]:
    """列出 docs/ 与 output/ 内容不一致的文件名。"""
    stale = []
    for name in SYNC_FILES:
        out = OUTPUT_DIR / name
        doc = DOCS_DIR / name
        if not out.exists():
            continue          # 本地产物缺失不算错，跳过
        if not doc.exists():
            stale.append(f"{name}（docs/ 缺失）")
            continue
        if out.read_bytes() != doc.read_bytes():
            stale.append(f"{name}（内容不一致）")
    return stale


def check_html_report(path: Path | str = Path("output/weather_report.html")) -> list[str]:
    """检查生成的 HTML 报告里没有未替换的模板标记。

    2026-11-25 修复：模板用 ``{{ }}`` 做 .format 转义，但代码只做了
    ``.replace("__DATA__")``，线上页面出现 54 处字面双花括号 ——
    整页 JS 语法错误，四张图全不渲染。这里把它变成 CI 硬失败。

    注意：只检查**注入数据之前**就该消失的标记。JSON 里的嵌套对象
    天然以 ``}}`` 结尾，不能当作残留。
    """
    p = Path(path)
    if not p.exists():
        return ["%s 不存在" % p]

    text = p.read_text(encoding="utf-8")
    problems = []
    for marker in ("{date_from}", "{date_to}", "{total}", "__DATA__",
                   "{city_count}", "{{", "\n}}" ):
        if marker in text:
            problems.append("%s 存在未替换标记 %r" % (p, marker))
    return problems


def main() -> int:
    failed = False

    missing = check_readme_refs()
    if missing:
        failed = True
        print("README 引用的图片缺失：")
        for m in missing:
            print(f"  - {m}")
        print("  → 检查 weather/sync.py 的 SYNC_FILES 清单是否漏了这些产物。\n")

    stale = diff_docs_vs_output()
    if stale:
        failed = True
        print("docs/ 与 output/ 不一致（README 会显示旧图）：")
        for s in stale:
            print(f"  - {s}")
        print("  → 确认 main.py 里调用过 sync.sync_docs()，"
              "且 CI 的 git add 包含 docs/。\n")

    if failed:
        return 1

    print(f"README 图片引用完整；docs/ 与 output/ 内容一致（{len(SYNC_FILES)} 个产物）")

    # HTML 报告另算：它是 README 之外的独立页面，不受 SYNC_FILES 管理
    html_problems = check_html_report()
    if html_problems:
        print("HTML 报告存在模板残留：")
        for p in html_problems:
            print(f"  - {p}")
        return 1
    print("HTML 报告模板标记已全部展开")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
