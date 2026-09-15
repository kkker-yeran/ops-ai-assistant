#!/usr/bin/env bash
# 系统日志近期 ERROR/WARN 摘要（output: 原始日志行）
# 用法: bash sys_errors.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

if command -v journalctl >/dev/null 2>&1; then
  journalctl -p warning -b --no-pager -n 30 --output=short 2>/dev/null
else
  tail -n 500 /var/log/syslog 2>/dev/null | grep -iE "error|warn|fail" | tail -n 30 \
    || tail -n 500 /var/log/messages 2>/dev/null | grep -iE "error|warn|fail" | tail -n 30
fi
echo "[sys_errors scanned at $(date '+%F %T')]"
