#!/usr/bin/env bash
# Swap 使用量与换入换出速率（output: key=value）
# 用法: bash swap_usage.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

awk '
/SwapTotal/{st=$2} /SwapFree/{sf=$2}
END{
  used=st-sf;
  pct=(st>0)? used/st*100 : 0;
  printf "swap_total_mb=%d\nswap_used_mb=%d\nswap_free_mb=%d\nswap_usage_pct=%.1f\n", st/1024, used/1024, sf/1024, pct;
}' /proc/meminfo
