#!/usr/bin/env bash
# CPU 占用 Top-N 进程（output: 表头 + 数据行）
# 用法: bash cpu_top.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

N=${1:-10}
N=${N//[^0-9]/}
N=${N:-10}
ps -eo pcpu,pid,user,comm --sort=-pcpu --no-headers 2>/dev/null | head -n "$N" | awk '
BEGIN{ print "CPU PID USER COMMAND" }
{ printf "%s %s %s %s\n", $1,$2,$3,$4 }'
