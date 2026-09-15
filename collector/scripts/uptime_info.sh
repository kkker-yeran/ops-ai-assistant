#!/usr/bin/env bash
# 运行时长、登录用户与负载概览（output: key=value）
# 用法: bash uptime_info.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

read -r up _ < /proc/uptime
awk -v up="$up" 'BEGIN{
  d=int(up/86400); h=int(up%86400/3600); m=int(up%3600/60);
  printf "uptime_seconds=%d\nuptime_human=%dd%dh%dm\n", up, d,h,m;
}'
echo "hostname=$(hostname 2>/dev/null || echo unknown)"
echo "kernel=$(uname -r 2>/dev/null || echo unknown)"
echo "logged_in_users=$(who 2>/dev/null | wc -l)"
echo "current_time=$(date '+%F %T')"
