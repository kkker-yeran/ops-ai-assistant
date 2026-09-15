#!/usr/bin/env bash
# 1/5/15 分钟系统负载与 CPU 核数（output: key=value）
# 用法: bash load_avg.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

CORES=$(nproc 2>/dev/null || echo 1)
read -r l1 l5 l15 _ < /proc/loadavg
awk -v l1="$l1" -v l5="$l5" -v l15="$l15" -v c="$CORES" 'BEGIN{
  printf "load1=%s\nload5=%s\nload15=%s\ncores=%d\nload_per_core=%.2f\n", l1,l5,l15,c, l1/c;
}'
