#!/usr/bin/env bash
# 安装 git 钩子：把 scripts/pre-push 链接到 .git/hooks/pre-push。
#
# 用法：bash scripts/install_hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

HOOKS_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS_DIR"

cp scripts/pre-push "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"

echo "已安装 pre-push 钩子到 $HOOKS_DIR/pre-push"
echo "  推送前会自动校验 workflow YAML 与 README 资源"
echo "  紧急跳过：git push --no-verify"
