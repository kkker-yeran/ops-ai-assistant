#!/usr/bin/env bash
# 僵尸进程与不可中断睡眠进程（output: 表头 + 数据行）
# 用法: bash zombie_proc.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

ps -eo stat,pid,ppid,user,comm --no-headers 2>/dev/null | awk '
BEGIN{ print "STATE PID PPID USER COMMAND"; n=0 }
$1 ~ /Z/ || $1 ~ /^D/ { printf "%s %s %s %s %s\n", $1,$2,$3,$4,$5; n++ }
END{ printf "zombie_or_dstate_count=%d\n", n > "/dev/stderr" }'
