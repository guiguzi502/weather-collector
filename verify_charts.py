# -*- coding: utf-8 -*-
"""CI 自检：图表里的中文必须真的能渲染出来。

背景（2026-11-25 修复）：
    ubuntu-latest runner 默认没装中文字体。matplotlib 会把每个汉字
    画成方框（tofu），只在日志里留 36 条 ``Glyph ... missing from
    font(s) DejaVu Sans`` 的 UserWarning —— 画图步骤照样 exit 0，
    CI 一路绿，README 上的图却全是方块。

    这个脚本做两件事：
    1. 断言 ``weather.visualize.CJK_FONT`` 非空
    2. 实际渲染一段中文，捕获字体缺失警告（其它 UserWarning 不算）

用法:
    python verify_charts.py

退出码 0 = 中文字体正常，1 = 缺字体或渲染有缺字（CI 直接红）。
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _glyph_warnings() -> list[str]:
    """渲染一段中文，收集 matplotlib 的缺字警告。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from weather import visualize

    fig, ax = plt.subplots(figsize=(3, 1.2), dpi=80)
    ax.set_title("长沙 北京 太原 武汉 气温 降水 城市 趋势")
    ax.set_ylabel("气温（℃）")
    ax.axis("off")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig.canvas.draw()
    plt.close(fig)

    return [str(w.message) for w in caught
            if "missing from font" in str(w.message).lower()]


def main() -> int:
    from weather import visualize

    problems: list[str] = []

    if not visualize.CJK_FONT:
        problems.append("未探测到任何中文字体（weather.visualize.CJK_FONT 为 None）")
    else:
        print("[ OK ] 中文字体：%s" % visualize.CJK_FONT)

    glyphs = _glyph_warnings()
    if glyphs:
        problems.append("渲染有 %d 个缺字警告，示例：%s"
                        % (len(glyphs), glyphs[0][:120]))

    if problems:
        for p in problems:
            print("[FAIL] %s" % p)
        print("\n修复方式：在 CI 里 apt-get install fonts-noto-cjk，"
              "或把中文字体文件放进仓库由 visualize.py 用 addfont 加载。")
        return 1

    print("[ OK ] 图表中文渲染正常，无缺字警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())