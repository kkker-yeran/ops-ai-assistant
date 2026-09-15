#!/usr/bin/env bash
# 各分区容量使用率（output: 表头 + 数据行）
# 用法: bash disk_usage.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

df -hP -x tmpfs -x devtmpfs -x overlay 2>/dev/null | awk '
NR==1 { print "FILESYSTEM SIZE USED AVAIL USE_PCT MOUNTPOINT"; next }
{ printf "%s %s %s %s %s %s\n", $1,$2,$3,$4,$5,$6 }'
