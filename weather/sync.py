# -*- coding: utf-8 -*-
"""output/ → docs/ 同步模块。

背景（2026-11-23 修复）：
    README 里所有图片都引用 ``docs/``，但各生成器只往 ``output/`` 写，
    只有 report/annual/map_view 三个模块各自零散地同步了 4 个文件，
    ``city_duel.png``、``dashboard.png`` 等从来没进过 docs/，
    导致 README 图片从 2025-11-20 起就不再变化。

现在改为：所有产物先在 ``output/`` 落地，main 流程末尾统一调
:func:`sync_docs` 按清单整体镜像到 ``docs/``，单一真相源，不再各写各的。
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
DOCS_DIR = Path("docs")

# README / 报告页会引用到的产物清单。
# 新增产物时往这里加一行即可，不用再改各个生成器。
SYNC_FILES = (
    # SVG 卡片
    "weather_card.svg",
    "duel_dressing.svg",
    "annual_report.svg",
    # 交互式 HTML
    "weather_map.html",
    # Matplotlib 位图
    "city_duel.png",
    "city_comparison.png",
    "dashboard.png",
    "temperature_trend.png",
    "precipitation.png",
)


def write_text_lf(path: Path | str, text: str) -> Path:
    """写文本文件，强制 LF 换行。

    为什么要自己开文件（2026-11-25）：
        ``Path.write_text`` 在 Python 3.9 上没有 ``newline`` 参数，
        默认会把 ``\\n`` 翻成 Windows 的 ``\\r\\n``。于是同一份 SVG
        在本地生成是 CRLF、在 Linux CI 生成是 LF —— 换行符不同，
        字节就不同，``verify_readme.py`` 的逐字节比对会误判，
        git 也会一直报 "CRLF will be replaced by LF"。
        显式指定 ``newline="\\n"`` 后，两边产物完全一致。

        路径里的父目录会自动创建，调用方不用先 mkdir。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


def sync_docs(output_dir: Path | str = OUTPUT_DIR,
              docs_dir: Path | str = DOCS_DIR) -> list[str]:
    """把 output/ 里 README 需要的产物镜像到 docs/。

    返回实际同步的文件名列表（已是最新、内容相同的会跳过）。
    docs/ 下其它文件（如静态的 china.json）不做任何改动。
    """
    src_dir = Path(output_dir)
    dst_dir = Path(docs_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    synced: list[str] = []
    for name in SYNC_FILES:
        src = src_dir / name
        if not src.exists():
            logger.warning("同步跳过：%s 不存在", src)
            continue
        dst = dst_dir / name
        # 内容一致就不覆盖，避免无意义地刷新 mtime
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            if dst.read_bytes() == src.read_bytes():
                continue
        shutil.copy2(src, dst)
        synced.append(name)

    if synced:
        logger.info("docs/ 同步完成：%d 个文件（%s）", len(synced), ", ".join(synced))
    else:
        logger.info("docs/ 已是最新，无需同步")
    return synced


def check_readme_refs(readme: Path | str = Path("README.md")) -> list[str]:
    """检查 README 里引用的本地图片是否都存在，返回缺失路径列表。

    用于 CI 静态自检：防止哪天又出现「README 指向 docs/ 但没人往 docs/ 写」。
    """
    import re

    path = Path(readme)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)

    missing = []
    for ref in refs:
        if ref.startswith(("http://", "https://")):
            continue
        if not Path(ref).exists():
            missing.append(ref)
    return missing
