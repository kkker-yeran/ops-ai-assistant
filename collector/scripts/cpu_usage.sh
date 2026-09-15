#!/usr/bin/env bash
# CPU 整体使用率与 user/system/idle 分布（output: key=value）
# 用法: bash cpu_usage.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

snap() { awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8+$9+$10, $5+$6, $4, $9}' /proc/stat; }
export CORES
CORES=$(nproc 2>/dev/null || echo 1)
a=($(snap)); sleep 1; b=($(snap))

awk -v at="${a[0]}" -v ai="${a[1]}" -v au="${a[2]}" -v as="${a[3]}" \
    -v bt="${b[0]}" -v bi="${b[1]}" -v bu="${b[2]}" -v bs="${b[3]}" \
    -v cores="$CORES" 'BEGIN{
  dt=bt-at; if(dt<=0) dt=1;
  printf "cpu_usage=%.1f\nuser=%.1f\nsystem=%.1f\nidle=%.1f\ncores=%d\n",
         (dt-(bi-ai))/dt*100, (bu-au)/dt*100, (bs-as)/dt*100, (bi-ai)/dt*100, cores;
}'
