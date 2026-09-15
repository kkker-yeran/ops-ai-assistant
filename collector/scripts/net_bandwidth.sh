#!/usr/bin/env bash
# 网卡实时带宽、丢包与错误包（output: key=value）
# 用法: bash net_bandwidth.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

IFACE=${NET_IFACE:-$(awk 'NR>2{print $1; exit}' /proc/net/dev 2>/dev/null | tr -d ':')}
IFACE=${IFACE:-eth0}
SEC=2
grab() { awk -v i="$IFACE" '$1==i":" || $1==i {print $2,$3,$4,$10,$11,$12}' /proc/net/dev 2>/dev/null; }
a=$(grab); sleep "$SEC"; b=$(grab)
awk -v a="$a" -v b="$b" -v sec="$SEC" -v ifc="$IFACE" '
BEGIN{
  split(a,x," "); split(b,y," ");
  rb=y[1]-x[1]; pb=y[2]-x[2]; tb=y[4]-x[4]; pd=y[5]-x[5];
  if(rb<0) rb=0; if(tb<0) tb=0; if(pb<0) pb=0; if(pd<0) pd=0;
  printf "iface=%s\nrx_mbps=%.2f\ntx_mbps=%.2f\nrx_pps=%d\ntx_pps=%d\nrx_dropped=%d\ntx_dropped=%d\nsample_sec=%d\n",
         ifc, rb/sec/1024/1024, tb/sec/1024/1024, pb/sec, pd/sec, x[3], x[6], sec;
}'
