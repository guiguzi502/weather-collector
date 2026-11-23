#!/usr/bin/env bash
# 提交并推送自动生成的产物；push 被拒时用「本地产物覆盖远端」的方式重建提交。
#
# 为什么不用 git pull --rebase（2026-11-23 生产踩过的坑）：
#   data/weather.db 是 SQLite 二进制、output/*.png 是位图。
#   rebase 遇到二进制冲突无法自动合并，一次冲突就留下
#     CONFLICT (content): Merge conflict in data/weather.db
#     fatal: You are not currently on a branch.       ← detached HEAD
#     error: Pulling is not possible because you have unmerged files.
#   后续所有重试都在这个烂状态上打转，任务必然失败。
#
# 为什么不用 git reset --soft origin/main：
#   CI 的 checkout 通常落后远端。reset --soft 只移动 HEAD、不动索引，
#   远端新增的文件在索引里会显示成「删除」，提交上去就把别人的文件删了。
#
# 这里的语义：产物每次都是全量重新生成的，本地就是权威版本。
#   1. 把产物复制到临时目录（物理保留，绕开所有 git 索引语义）
#   2. git reset --hard origin/main —— 干净对齐远端，含远端新增文件
#   3. 把产物复制回去覆盖 —— 只有我们关心的路径被改，其它文件原样保留
#   4. commit → 必然 fast-forward，push 必成
#
# 用法（仓库根目录）：
#   bash scripts/commit_artifacts.sh "提交信息" "data/ output/ docs/ README.md"
set -uo pipefail

MSG="${1:?缺少提交信息}"
PATHS="${2:-data/ output/ docs/ README.md}"

BRANCH="${GITHUB_REF_NAME:-main}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

commit_and_push() {
  # 逐个 add：某个路径不存在时不要让整个 add 失败
  # （单城市跑 / 首次运行时 output/ 可能为空，git add 会报 pathspec 错误）
  local added=0
  for p in $PATHS; do
    if [ -e "$p" ]; then
      git add -f "$p" && added=1
    fi
  done

  local dirty=0
  if [ $added -eq 1 ] && ! git diff --cached --quiet; then
    git commit -m "$MSG"
    echo "已提交：$(git rev-parse --short HEAD)"
    dirty=1
  fi

  # 没有新提交，但可能存在之前未推送的提交（调用方已 commit 的场景）
  local ahead=0
  if git rev-parse --verify --quiet "origin/$BRANCH" >/dev/null; then
    ahead=$(git rev-list --count "origin/$BRANCH"..HEAD 2>/dev/null || echo 0)
  else
    ahead=1     # 远端分支还不存在，总要推
  fi

  if [ $dirty -eq 0 ] && [ "$ahead" -eq 0 ]; then
    echo "无变更，跳过提交"
    return 10
  fi

  if git push; then
    echo "推送成功"
    return 0
  fi
  return 11
}

# 第一次尝试：本地不落后时直接成功
commit_and_push
rc=$?
[ $rc -eq 0 ] && exit 0
[ $rc -eq 10 ] && exit 0

for attempt in 1 2 3; do
  echo "推送被拒（第 $attempt 次），改用以本地产物为准重建提交..."

  if ! git fetch origin "$BRANCH"; then
    echo "fetch 失败，等待后重试"
    sleep 5
    continue
  fi

  # 1. 物理保留产物（避开 git 索引/树语义的所有边界情况）
  mkdir -p "$TMP/save"
  for p in $PATHS; do
    if [ -e "$p" ]; then
      mkdir -p "$TMP/save/$(dirname "$p")"
      cp -a "$p" "$TMP/save/$p"
    fi
  done

  # 2. 硬对齐远端（远端新增文件、他人改动全部拿到手）
  if ! git reset --hard "origin/$BRANCH"; then
    echo "reset 失败，跳过本轮"
    sleep 5
    continue
  fi

  # 3. 产物覆盖回来（目录用 /. 保证合并而非嵌套）
  for p in $PATHS; do
    [ -e "$TMP/save/$p" ] || continue
    if [ -d "$TMP/save/$p" ]; then
      mkdir -p "$p"
      cp -a "$TMP/save/$p/." "$p/"
    else
      cp -a "$TMP/save/$p" "$p"
    fi
  done

  # 4. 重新提交
  commit_and_push
  rc=$?
  [ $rc -eq 0 ] && exit 0
  [ $rc -eq 10 ] && { echo "远端已包含相同内容，无需再推"; exit 0; }
  sleep 3
done

echo "推送最终失败"
exit 1
