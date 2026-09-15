#!/usr/bin/env bash
# 近期 OOM Killer 事件（output: 原始日志行）
# 用法: bash oom_events.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

if command -v journalctl >/dev/null 2>&1; then
  journalctl -k --no-pager -g "Out of memory|oom-kill|Killed process" --since "-${1:-24h}" 2>/dev/null | tail -n 20
else
  dmesg 2>/dev/null | grep -iE "out of memory|oom-kill|killed process" | tail -n 20
fi
echo "[oom_events scanned at $(date '+%F %T')]"
