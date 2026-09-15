#!/usr/bin/env bash
# 各分区 inode 使用率（output: 表头 + 数据行）
# 用法: bash disk_inode.sh [window]   —— 输出为结构化文本，由 api/services/collector.py 解析
set -euo pipefail

df -hiP -x tmpfs -x devtmpfs -x overlay 2>/dev/null | awk '
NR==1 { print "FILESYSTEM INODES IUSED IFREE IUSE_PCT MOUNTPOINT"; next }
{ printf "%s %s %s %s %s %s\n", $1,$2,$3,$4,$5,$6 }'
