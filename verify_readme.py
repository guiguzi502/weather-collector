# -*- coding: utf-8 -*-
"""CI 自检：README 引用的本地图片必须全部存在。

用法:
    python verify_readme.py

退出码 0 = 通过，1 = 有缺失（CI 直接红）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from weather.sync import check_readme_refs  # noqa: E402


def main() -> int:
    missing = check_readme_refs()
    if missing:
        print("README 引用的图片缺失：")
        for m in missing:
            print(f"  - {m}")
        print("\n检查 SYNC_FILES 清单是否漏掉了这些产物。")
        return 1
    print("README 图片引用完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
