#!/usr/bin/env bash
# 内存总量 / 已用 / 可用 / 缓存与使用率（output: key=value）
# 用法: bash mem_usage.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

awk '
/MemTotal/     {total=$2}
/MemAvailable/ {avail=$2}
/MemFree/      {free=$2}
/Buffers/      {buf=$2}
/^Cached/      {cache=$2}
END{
  used=total-avail;
  printf "total_mb=%d\nused_mb=%d\navailable_mb=%d\nfree_mb=%d\ncache_mb=%d\nusage_pct=%.1f\n",
         total/1024, used/1024, avail/1024, free/1024, (buf+cache)/1024, used/total*100;
}' /proc/meminfo
