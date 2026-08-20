#!/usr/bin/env bash
# Geass 异地访问助手：让手机无需与电脑同一 Wi-Fi 即可控制电脑。
#
# 两种零配置方案：
#   1) Tailscale（推荐）：电脑与手机登录同一账号后获得稳定私网地址；
#   2) Cloudflare 临时隧道 cloudflared：免注册、手机不用装 App，
#      但每次重启 URL 都会变化。
#
# 用法：
#   ./scripts/remote.sh                          # 自动选择
#   ./scripts/remote.sh --provider tailscale
#   ./scripts/remote.sh --provider cloudflared --port 8765
set -u

PORT="${GEASS_PORT:-8765}"
PROVIDER="auto"

usage() {
  cat <<'EOF'
用法: ./scripts/remote.sh [--provider auto|tailscale|cloudflared] [--port 8765]

  --provider   选择远程通道，默认 auto（优先 Tailscale，其次 cloudflared）
  --port       Geass 服务端口，默认 8765
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --port)
      PORT="$2"
      shift 2
      ;;
    --provider)
      PROVIDER="$2"
      shift 2
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

tailscale_ip() {
  command -v tailscale >/dev/null 2>&1 || return 1
  tailscale ip -4 2>/dev/null | head -n1
}

cloudflared_bin() {
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
  elif [ -x "${HOME}/.local/bin/cloudflared" ]; then
    printf '%s\n' "${HOME}/.local/bin/cloudflared"
  else
    return 1
  fi
}

install_cloudflared() {
  local arch dest url
  arch="$(uname -m)"
  case "$arch" in
    x86_64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      echo "不支持的架构: $arch" >&2
      return 1
      ;;
  esac
  dest="${HOME}/.local/bin/cloudflared"
  url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}"
  mkdir -p "${HOME}/.local/bin"
  echo "正在下载 cloudflared（一次性，来自 GitHub）…"
  if ! curl -fL --retry 3 -o "$dest" "$url"; then
    echo "下载失败: $url" >&2
    return 1
  fi
  chmod +x "$dest"
  echo "已安装到 $dest"
}

run_tailscale() {
  local ip
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "未安装 Tailscale，安装方法：" >&2
    echo "  curl -fsSL https://tailscale.com/install.sh | sh" >&2
    echo "  sudo tailscale up" >&2
    echo "手机侧在应用商店安装 Tailscale 并登录同一账号即可。" >&2
    return 1
  fi
  ip="$(tailscale ip -4 2>/dev/null | head -n1)"
  if [ -z "$ip" ]; then
    echo "Tailscale 未登录：先执行 sudo tailscale up 完成登录。" >&2
    return 1
  fi
  echo "✅ 手机（登录同一 Tailscale 账号）打开: http://${ip}:${PORT}"
  echo "   然后输入启动 Geass 时打印的访问 Token。"
  echo "   想启用 HTTPS 可执行: tailscale serve --bg ${PORT}"
  echo "   （Tailscale 网络内地址长期有效，无需重复配置）"
}

run_cloudflared() {
  local bin log pid url
  bin="$(cloudflared_bin)" || {
    echo "未找到 cloudflared。" >&2
    echo "  自动下载: $0 --provider cloudflared 将在询问后安装到 ~/.local/bin" >&2
    return 1
  }
  log="$(mktemp /tmp/geass-cloudflared-XXXXXX.log)"
  echo "启动 Cloudflare 临时隧道…（关闭窗口前隧道保持有效）"
  "$bin" tunnel --url "http://localhost:${PORT}" --no-autoupdate >"$log" 2>&1 &
  pid=$!
  trap 'kill "$pid" 2>/dev/null; rm -f "$log"' EXIT INT TERM

  for _ in $(seq 1 90); do
    url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" 2>/dev/null | head -n1 || true)"
    if [ -n "$url" ]; then
      echo ""
      echo "✅ 手机在任意网络打开: $url"
      echo "   然后输入启动 Geass 时打印的访问 Token。"
      echo "   按 Ctrl+C 关闭隧道。"
      wait "$pid"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "cloudflared 启动失败：" >&2
      cat "$log" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "等待隧道地址超时：" >&2
  cat "$log" >&2
  return 1
}

main() {
  case "$PROVIDER" in
    tailscale)
      run_tailscale
      ;;
    cloudflared)
      if ! cloudflared_bin >/dev/null 2>&1; then
        local ans
        read -r -p "未找到 cloudflared，是否下载到 ~/.local/bin？[y/N] " ans
        if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
          exit 0
        fi
        install_cloudflared || exit 1
      fi
      run_cloudflared
      ;;
    auto)
      if [ -n "$(tailscale_ip 2>/dev/null || true)" ]; then
        run_tailscale
      elif cloudflared_bin >/dev/null 2>&1; then
        run_cloudflared
      else
        echo "未检测到 Tailscale / cloudflared，请选择一种方案："
        echo ""
        echo "  1) Tailscale（推荐，长期稳定）："
        echo "       curl -fsSL https://tailscale.com/install.sh | sh"
        echo "       sudo tailscale up    # 手机也装 Tailscale 并登录同一账号"
        echo "       之后运行: $0 --provider tailscale"
        echo ""
        echo "  2) Cloudflare 临时隧道（免注册、手机免装 App，URL 每次重启变化）："
        local ans
        read -r -p "     现在下载 cloudflared 到 ~/.local/bin？[y/N] " ans
        if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
          install_cloudflared && run_cloudflared
        fi
      fi
      ;;
    *)
      echo "未知 provider: $PROVIDER" >&2
      exit 2
      ;;
  esac
}

main
