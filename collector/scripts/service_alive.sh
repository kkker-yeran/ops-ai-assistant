#!/usr/bin/env bash
# 关键服务存活状态（output: 表头 + 数据行）
# 用法: bash service_alive.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

SERVICES=${CHECK_SERVICES:-"sshd nginx redis-server mysql docker"}
echo "SERVICE ACTIVE STATUS"
for s in $SERVICES; do
  if command -v systemctl >/dev/null 2>&1; then
    st=$(systemctl is-active "$s" 2>/dev/null || echo "not-found")
    sub=$(systemctl is-enabled "$s" 2>/dev/null || echo "unknown")
    echo "$s $st $sub"
  else
    if pgrep -x "$s" >/dev/null 2>&1; then echo "$s running manual"; else echo "$s stopped unknown"; fi
  fi
done
