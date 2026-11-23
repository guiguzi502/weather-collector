# -*- coding: utf-8 -*-
"""CI 自检：workflow YAML 必须能被严格解析，且触发器等关键结构齐全。

2026-11-23 踩过的坑：
    run: bash xxx.sh "chore: daily update"
                                    ^ ": " 让 YAML 当成新映射键
    -> GitHub 解析失败，name 回退成文件路径，workflow_dispatch 消失，
       dispatch API 返回 422，push 触发时 total_count=0（建 run 但无 job）。

本地用 PowerShell 肉眼检查是看不出来的——必须真正解析一遍。

用法:
    python verify_workflows.py
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 PyYAML：pip install pyyaml")
    raise SystemExit(2)

WF_DIR = Path(".github/workflows")


def check(path: Path) -> list[str]:
    """返回问题列表，空列表表示通过。"""
    problems = []
    raw = path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("文件含 UTF-8 BOM（GitHub 能接受，但建议去掉）")
        raw = raw[3:]
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        problems.append("文件是 UTF-16 编码，GitHub 只接受 UTF-8")
        return problems

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        problems.append(f"不是合法 UTF-8：{exc}")
        return problems

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # 只报第一行错误，后面的都是噪音
        msg = str(exc).split("\n")
        problems.append("YAML 解析失败：" + " ".join(msg[:3]))
        return problems

    if not isinstance(doc, dict):
        problems.append("顶层不是 mapping")
        return problems

    # 关键：YAML 1.1 把裸 on 解析成 True，两种都要兼容
    triggers = doc.get("on", doc.get(True))
    if triggers is None:
        problems.append("缺少 on: 触发器")
    elif isinstance(triggers, str):
        problems.append(f"on: 只有一个触发器 {triggers!r}，scheduled workflow 应有 dict")
    elif isinstance(triggers, dict):
        if "schedule" in triggers:
            sched = triggers["schedule"]
            if not isinstance(sched, list) or not sched:
                problems.append("schedule 格式错误，应为列表")
            else:
                for item in sched:
                    if not isinstance(item, dict) or "cron" not in item:
                        problems.append("schedule 项缺少 cron 字段")
        if "workflow_dispatch" not in triggers:
            problems.append("缺少 workflow_dispatch（无法手动触发）")

    if "jobs" not in doc or not isinstance(doc.get("jobs"), dict):
        problems.append("缺少 jobs")
        return problems

    for job_name, job in doc["jobs"].items():
        steps = (job or {}).get("steps")
        if not isinstance(steps, list) or not steps:
            problems.append(f"job {job_name!r} 没有 steps")
            continue
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                problems.append(f"job {job_name!r} 第 {i} 步不是 mapping")
                continue
            if "uses" not in step and "run" not in step:
                problems.append(
                    f"job {job_name!r} 第 {i} 步既无 uses 也无 run")

    return problems


def main() -> int:
    if not WF_DIR.is_dir():
        print(f"找不到 {WF_DIR}")
        return 1

    files = sorted(WF_DIR.glob("*.yml")) + sorted(WF_DIR.glob("*.yaml"))
    if not files:
        print("没有 workflow 文件")
        return 1

    failed = False
    for f in files:
        problems = check(f)
        if problems:
            failed = True
            print(f"[FAIL] {f}")
            for p in problems:
                print(f"    - {p}")
        else:
            print(f"[ OK ] {f}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
