#!/usr/bin/env bash
# Geass 初始化脚本：必要时 clone GitHub 仓库，然后交给 scripts/install.sh
# 完成 conda 环境与项目依赖配置。
#
# 在已经 clone 的仓库里运行（默认配置当前仓库）：
#   ./scripts/setup.sh --all
#
# 从任意位置 clone 并安装（默认放到 ~/geass）：
#   ./scripts/setup.sh --dir ~/geass --all
#
# 从零开始（尚未拿到本仓库时，下载后运行）：
#   curl -fsSL https://raw.githubusercontent.com/Ricardo-shuo-liu/geass/master/scripts/setup.sh \
#     -o /tmp/geass-setup.sh
#   bash /tmp/geass-setup.sh --all
set -euo pipefail

REPO_URL="${GEASS_REPO_URL:-https://github.com/Ricardo-shuo-liu/geass.git}"
BRANCH="${GEASS_BRANCH:-master}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR=""
PASSTHROUGH=()

usage() {
  cat <<'EOF'
用法: ./scripts/setup.sh [选项] [传给 install.sh 的参数]

选项:
  --dir DIR           clone 目标目录；在仓库内运行时仍强制 clone 到该目录
  --branch BRANCH     要 clone 的分支，默认 master
  --url URL           Git 仓库地址，默认本项目 GitHub 地址
  -h, --help          显示帮助

其余参数原样传给 scripts/install.sh，例如 --all、--system、--web、
--name myenv、--no-prune。
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      if [ $# -lt 2 ]; then
        echo "缺少 --dir 的值" >&2
        exit 2
      fi
      TARGET_DIR="$2"
      shift 2
      ;;
    --branch)
      if [ $# -lt 2 ]; then
        echo "缺少 --branch 的值" >&2
        exit 2
      fi
      BRANCH="$2"
      shift 2
      ;;
    --url)
      if [ $# -lt 2 ]; then
        echo "缺少 --url 的值" >&2
        exit 2
      fi
      REPO_URL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      PASSTHROUGH+=("$1")
      shift
      ;;
  esac
done

is_repo_root() {
  [ -f "$1/geass.yml" ] && [ -x "$1/scripts/install.sh" ]
}

if [ -z "$TARGET_DIR" ] && is_repo_root "$SCRIPT_DIR/.."; then
  REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
  echo "检测到已在 Geass 仓库内，将直接配置: $REPO_ROOT"
else
  if [ -z "$TARGET_DIR" ]; then
    TARGET_DIR="${HOME:-.}/geass"
  fi
  REPO_ROOT="$(cd -- "$(dirname -- "$TARGET_DIR")" 2>/dev/null && pwd || true)"
  if [ -z "$REPO_ROOT" ]; then
    echo "clone 目标目录不存在: $TARGET_DIR" >&2
    exit 1
  fi
  REPO_ROOT="${REPO_ROOT}/$(basename -- "$TARGET_DIR")"

  if [ -d "$REPO_ROOT/.git" ]; then
    echo "检测到已有仓库，直接复用（不会覆盖本地修改）: $REPO_ROOT"
  elif [ -e "$REPO_ROOT" ]; then
    echo "目标目录已存在但不是 Git 仓库，拒绝覆盖: $REPO_ROOT" >&2
    exit 1
  else
    echo "clone $REPO_URL (分支 $BRANCH) → $REPO_ROOT"
    git clone --branch "$BRANCH" "$REPO_URL" "$REPO_ROOT"
  fi
fi

if ! is_repo_root "$REPO_ROOT"; then
  echo "clone 完成但仓库结构异常: $REPO_ROOT" >&2
  exit 1
fi

echo "开始配置环境: $REPO_ROOT"
cd "$REPO_ROOT"
exec "$REPO_ROOT/scripts/install.sh" "${PASSTHROUGH[@]}"
