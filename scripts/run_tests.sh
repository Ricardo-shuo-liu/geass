#!/usr/bin/env bash
# 运行全部测试，并把完整输出记录到 test.log（含失败信息与日志）
set -u
cd "$(dirname "$0")/.."
python -m pytest "$@" 2>&1 | tee test.log
exit "${PIPESTATUS[0]}"
