#!/usr/bin/env bash
# Geass 一键安装脚本：按 geass.yml 创建/更新 conda 环境，并安装项目本体。
#
# 默认只处理 conda 环境 + `pip install -e .`：
#   ./scripts/install.sh
#
# 连系统依赖一起装（会调用 sudo，按需提示密码）：
#   ./scripts/install.sh --system
#
# 连前端 npm 依赖一起装（web/dist 已预构建，日常使用通常不需要）：
#   ./scripts/install.sh --web
#
# 全部依赖一起装：
#   ./scripts/install.sh --all
#
# 更多选项见 `./scripts/install.sh --help`。
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
YML_FILE="${ROOT_DIR}/geass.yml"
ENV_NAME="${GEASS_ENV_NAME:-geass}"
INSTALL_SYSTEM=0
INSTALL_WEB=0
PRUNE=1

usage() {
  cat <<'EOF'
用法: ./scripts/install.sh [选项]

选项:
  --name NAME         conda 环境名，默认 geass（可用 GEASS_ENV_NAME 覆盖）
  --system            同时安装 Linux 系统依赖（需要 sudo，会提示密码）
  --web               同时安装 web/ 的 npm 依赖
  --all               等价于 --system --web
  --no-prune          更新已有环境时不删除不在 geass.yml 中的包
  -h, --help          显示帮助
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --name)
      if [ $# -lt 2 ]; then
        echo "缺少 --name 的值" >&2
        exit 2
      fi
      ENV_NAME="$2"
      shift 2
      ;;
    --system)
      INSTALL_SYSTEM=1
      shift
      ;;
    --web)
      INSTALL_WEB=1
      shift
      ;;
    --all)
      INSTALL_SYSTEM=1
      INSTALL_WEB=1
      shift
      ;;
    --no-prune)
      PRUNE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$YML_FILE" ]; then
  echo "找不到环境文件: $YML_FILE" >&2
  exit 1
fi

conda_bin() {
  if [ -n "${CONDA_EXE:-}" ] && [ -x "${CONDA_EXE}" ]; then
    printf '%s\n' "$CONDA_EXE"
    return 0
  fi
  if command -v conda >/dev/null 2>&1; then
    command -v conda
    return 0
  fi
  for candidate in \
    "${HOME:-}/miniconda3/bin/conda" \
    "${HOME:-}/anaconda3/bin/conda" \
    "${HOME:-}/miniforge3/bin/conda"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

CONDA_BIN="$(conda_bin)" || {
  echo "未找到 conda，请先安装 Miniconda/Anaconda 并把 conda 加入 PATH。" >&2
  exit 1
}
echo "[1/4] 使用 Conda: $CONDA_BIN"

if "$CONDA_BIN" env list 2>/dev/null | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "[2/4] 环境 $ENV_NAME 已存在，按 $YML_FILE 更新…"
  if [ "$PRUNE" -eq 1 ]; then
    "$CONDA_BIN" env update -n "$ENV_NAME" -f "$YML_FILE" --prune
  else
    "$CONDA_BIN" env update -n "$ENV_NAME" -f "$YML_FILE"
  fi
else
  echo "[2/4] 创建环境 $ENV_NAME（来自 $YML_FILE）…"
  "$CONDA_BIN" env create -n "$ENV_NAME" -f "$YML_FILE"
fi

echo "[3/4] 安装 Geass 本体（editable，不重新解析依赖）…"
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install \
  -e "$ROOT_DIR" --no-deps --no-build-isolation

if [ "$INSTALL_WEB" -eq 1 ]; then
  echo "[web] 安装前端依赖…"
  "$CONDA_BIN" run -n "$ENV_NAME" npm \
    --prefix "$ROOT_DIR/web" install \
    --registry=https://registry.npmmirror.com
fi

if [ "$INSTALL_SYSTEM" -eq 1 ]; then
  echo "[system] 安装 Linux 系统依赖…"
  if command -v apt-get >/dev/null 2>&1; then
    packages="util-linux xclip xsel python3-pyatspi"
    if ! command -v x-terminal-emulator >/dev/null 2>&1; then
      packages="$packages x-terminal-emulator"
    fi
    # shellcheck disable=SC2086
    sudo apt-get update && sudo apt-get install -y $packages
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y util-linux xclip xsel python3-pyatspi
    echo "提示：请确认已安装可用的 X11 桌面和终端模拟器。" >&2
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm util-linux xclip xsel python-pyatspi
  else
    echo "未识别出 apt-get/dnf/pacman，跳过系统依赖安装。" >&2
    echo "请手动安装: util-linux、xclip 或 xsel、python3-pyatspi、" >&2
    echo "以及 X11 桌面与终端模拟器。" >&2
  fi
fi

echo "[4/4] 运行环境自检…"
if (
  cd "$ROOT_DIR"
  "$CONDA_BIN" run -n "$ENV_NAME" python -m geass.check
); then
  echo ""
  echo "✅ 安装完成，环境完整。"
else
  echo ""
  echo "⚠ 依赖已安装，但环境自检还有未就绪项；按上方提示补齐配置后重跑："
  echo "  conda run -n $ENV_NAME python -m geass.check"
fi

echo "下一步: 配置 API Key/模型后启动"
echo "  conda run -n $ENV_NAME python -m geass.config set SK-xxx https://api.deepseek.com deepseek-v4-flash"
echo "  ./run.sh"
