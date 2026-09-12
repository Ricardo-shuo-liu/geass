#!/usr/bin/env bash
# 启动 Geass 服务（个人配置在 ~/.geass/env.toml，可用 python -m geass.config set 管理）
# 透传服务参数，例如：./scripts/run.sh --qr
set -u
cd "$(dirname "$0")/.."
exec python -m geass serve "$@"
