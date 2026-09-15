#!/usr/bin/env bash
# TCP 连接状态分布、总数与重传率（output: key=value）
# 用法: bash net_conn.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

total=$(awk 'NR>1' /proc/net/tcp 2>/dev/null | wc -l)
for st in 01 02 03 04 05 06 07 08 09 0A 0B; do
  c=$(awk -v s="$st" 'NR>1 && $4==s' /proc/net/tcp 2>/dev/null | wc -l)
  case $st in
    01) name=ESTABLISHED;; 02) name=SYN_SENT;; 03) name=SYN_RECV;;
    04) name=FIN_WAIT1;;  05) name=FIN_WAIT2;; 06) name=TIME_WAIT;;
    07) name=CLOSE;;      08) name=CLOSE_WAIT;; 09) name=LAST_ACK;;
    0A) name=LISTEN;;     0B) name=CLOSING;;    *) name=UNKNOWN;;
  esac
  echo "${name}=${c}"
done
retrans=$(netstat -s 2>/dev/null | awk '/segments retransmited|retransmitted/{print $1; exit}')
echo "total_conn=${total}"
echo "retransmitted=${retrans:-0}"
