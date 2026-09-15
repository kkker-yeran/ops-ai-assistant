#!/usr/bin/env bash
# 磁盘 IOPS / 吞吐 / 读写延迟（output: key=value）
# 用法: bash disk_io.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

SEC=2
read_ios() { awk '{ for(i=1;i<=NF;i++) if($i ~ /^[a-z]+[0-9]+$/ || $i ~ /^(sd|nvme|vd|xvd)/) print $i }' /proc/partitions 2>/dev/null | head -n 5 | tr '\n' ',' ; }
DEVICES=$(read_ios)

a=$(awk '/^ /{print}' /proc/diskstats 2>/dev/null | head -n 40)
sleep "$SEC"
b=$(awk '/^ /{print}' /proc/diskstats 2>/dev/null | head -n 40)

awk -v a="$a" -v b="$b" -v sec="$SEC" '
BEGIN{
  na=split(a, A, "\n"); nb=split(b, B, "\n");
  for(i=1;i<=na;i++){ split(A[i],x," "); ka=x[3]; ra[ka]=x[6]; wa[ka]=x[10]; ta[ka]=x[13]; }
  tr=0; tw=0; tt=0;
  for(i=1;i<=nb;i++){
    split(B[i],y," "); kb=y[3]; if(!(kb in ra)) continue;
    dr=(y[6]-ra[kb]); dw=(y[10]-wa[kb]); dt=(y[13]-ta[kb]);
    if(dr<0||dw<0||dt<0) continue;
    tr+=dr; tw+=dw; tt+=dt;
  }
  printf "read_iops=%.1f\nwrite_iops=%.1f\nread_mbps=%.2f\nwrite_mbps=%.2f\nutil_pct=%.1f\nsample_sec=%d\ndevices=%s\n",
         tr/sec, tw/sec, tr*512/sec/1024/1024, tw*512/sec/1024/1024, tt/sec/10, sec, ENVIRON["DEV"];
}' DEV="$DEVICES"
