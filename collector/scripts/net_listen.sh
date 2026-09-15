#!/usr/bin/env bash
# 监听端口与对应进程（output: 表头 + 数据行）
# 用法: bash net_listen.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

if command -v ss >/dev/null 2>&1; then
  ss -lntup 2>/dev/null | awk 'NR==1{ print "PROTO LOCAL_ADDR PORT PROCESS"; next }
  {
    proto=$1; addr=$5; proc="";
    for(i=1;i<=NF;i++) if($i ~ /pid=/){ proc=$i; gsub(/users:|"|pid=|\(|\)|,|fd=/,"",proc); }
    n=split(addr, a, ":"); port=a[n];
    printf "%s %s %s %s\n", proto, addr, port, proc;
  }'
else
  netstat -lntup 2>/dev/null | awk 'NR>2{ printf "%s %s %s\n", $1,$4,$NF }'
fi
