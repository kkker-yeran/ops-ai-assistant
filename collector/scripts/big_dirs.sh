#!/usr/bin/env bash
# 占用空间最大的目录 Top-N（output: 表头 + 数据行）
# 用法: bash big_dirs.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

N=${1:-10}; N=${N//[^0-9]/}; N=${N:-10}
ROOT=${BIG_DIR_ROOT:-/}
du -x -d 2 "$ROOT" 2>/dev/null | sort -rn | head -n "$N" | awk '
BEGIN{ print "SIZE_KB PATH" }
{ size=$1; $1=""; sub(/^ /,""); printf "%s %s\n", size, $0 }'
