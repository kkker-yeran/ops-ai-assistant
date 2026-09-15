"""指标采集调度器。

职责：
1. 把「指标名」映射到具体的 Shell 脚本并安全执行（本地 / SSH 远程）；
2. 并发采集 + 超时熔断，单个指标失败不影响整体；
3. 把脚本的原始文本输出解析成结构化 dict；
4. 结果写入 Redis 短期缓存，避免 Agent 多轮追问时重复采集。

设计取舍：
- 采集脚本保持「纯 Shell、零依赖、可直接 bash 运行」，运维同学单独使用也看得懂；
- 结构化解析放在 Python 侧，脚本升级不需要改 Python，反之亦然。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..schemas.common import MetricItem

logger = logging.getLogger(__name__)

# api/services/collector.py -> parents: [0]=services [1]=api [2]=项目根
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "collector" / "scripts"

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


# --------------------------------------------------------------------------- #
# 指标目录：新增一个指标 = 加一个脚本 + 加一行配置，无需改动其它代码
# --------------------------------------------------------------------------- #
METRIC_CATALOG: Dict[str, Dict[str, str]] = {
    # CPU
    "cpu_usage": {"script": "cpu_usage.sh", "category": "CPU", "desc": "CPU 整体使用率与 user/system/idle 分布"},
    "load_avg": {"script": "load_avg.sh", "category": "CPU", "desc": "1/5/15 分钟负载与 CPU 核数"},
    "cpu_top": {"script": "cpu_top.sh", "category": "CPU", "desc": "CPU 占用 Top-N 进程"},
    # 内存
    "mem_usage": {"script": "mem_usage.sh", "category": "内存", "desc": "内存总量/已用/可用/缓存与使用率"},
    "mem_top": {"script": "mem_top.sh", "category": "内存", "desc": "内存占用 Top-N 进程"},
    "swap_usage": {"script": "swap_usage.sh", "category": "内存", "desc": "Swap 使用量与换入换出趋势"},
    "oom_events": {"script": "oom_events.sh", "category": "内存", "desc": "近期 OOM Killer 事件"},
    # 磁盘
    "disk_usage": {"script": "disk_usage.sh", "category": "磁盘", "desc": "各分区容量使用率"},
    "disk_inode": {"script": "disk_inode.sh", "category": "磁盘", "desc": "各分区 inode 使用率"},
    "disk_io": {"script": "disk_io.sh", "category": "磁盘", "desc": "磁盘 IOPS、吞吐与读写延迟"},
    "big_dirs": {"script": "big_dirs.sh", "category": "磁盘", "desc": "占用空间最大的目录 Top-N"},
    # 网络
    "net_conn": {"script": "net_conn.sh", "category": "网络", "desc": "TCP 连接状态分布与重传率"},
    "net_bandwidth": {"script": "net_bandwidth.sh", "category": "网络", "desc": "网卡实时带宽与丢包"},
    "net_listen": {"script": "net_listen.sh", "category": "网络", "desc": "监听端口与对应进程"},
    # 系统
    "uptime_info": {"script": "uptime_info.sh", "category": "系统", "desc": "运行时长、登录用户、系统负载概览"},
    "zombie_proc": {"script": "zombie_proc.sh", "category": "系统", "desc": "僵尸进程与孤儿进程统计"},
    "sys_errors": {"script": "sys_errors.sh", "category": "系统", "desc": "系统日志近期 ERROR/WARN 摘要"},
    "service_alive": {"script": "service_alive.sh", "category": "系统", "desc": "关键服务存活状态"},
}


class CollectorError(Exception):
    """采集失败。"""


def _build_command(host: str, script: str, args: Optional[List[str]] = None) -> List[str]:
    """构造执行命令：本地直接 bash，远程走 ssh。"""
    args = args or []
    remote = host not in LOCAL_HOSTS
    script_path = shlex.quote(str(SCRIPTS_DIR / script))
    arg_str = " ".join(shlex.quote(a) for a in args)

    if remote:
        # 通过 stdin 把脚本内容送过去，目标机无需预置脚本
        local_content = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
        cmd = f"bash -s -- {arg_str}"
        return ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", host, cmd], local_content
    return ["bash", script_path, *args], None


def _run_sync(host: str, script: str, args: List[str], timeout: int) -> Tuple[str, int]:
    argv, stdin_data = _build_command(host, script, args)
    if stdin_data is not None:
        proc = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", host, "bash -s -- " + " ".join(shlex.quote(a) for a in args)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    else:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 and not proc.stdout:
        raise CollectorError(proc.stderr.strip() or f"script exited with {proc.returncode}")
    return proc.stdout, int(timeout * 1000)


def _parse_kv(raw: str) -> Dict[str, Any]:
    """解析 `key=value` 形式的输出，值为 JSON 时自动反序列化。"""
    result: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        try:
            result[k] = json.loads(v)
        except (ValueError, TypeError):
            result[k] = v
    return result


def _parse_table(raw: str) -> List[Dict[str, str]]:
    """解析首行为表头、其余为数据行的文本表格。"""
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split()
    rows = []
    for ln in lines[1:]:
        cols = ln.split()
        if len(cols) < len(header):
            cols += [""] * (len(header) - len(cols))
        rows.append(dict(zip(header, cols[: len(header)])))
    return rows


TABLE_METRICS = {"cpu_top", "mem_top", "disk_usage", "disk_inode", "big_dirs", "net_listen", "zombie_proc", "service_alive"}
KV_METRICS = {"cpu_usage", "load_avg", "mem_usage", "swap_usage", "disk_io", "net_conn", "net_bandwidth", "uptime_info"}
RAW_METRICS = {"oom_events", "sys_errors"}


def parse_metric(metric: str, raw: str) -> Dict[str, Any]:
    """把脚本原始输出结构化。"""
    if metric in TABLE_METRICS:
        return {"rows": _parse_table(raw)}
    if metric in KV_METRICS:
        return _parse_kv(raw)
    # 日志类指标保留原文，交给 LLM  summarization
    return {"raw": raw.strip()}


async def collect_one(
    host: str,
    metric: str,
    window: str = "5m",
    timeout: int = 10,
    override_allowed: Optional[List[str]] = None,
    collect_mode: str = "auto",
) -> MetricItem:
    """采集单个指标，永不抛异常（失败体现在 ok / error 字段上）。"""
    started = time.perf_counter()
    collected_at = datetime.now().isoformat(timespec="seconds")

    if metric not in METRIC_CATALOG:
        return MetricItem(
            metric=metric, ok=False, host=host, collected_at=collected_at, elapsed_ms=0,
            error=f"unknown metric '{metric}'，可用指标见 /api/v1/metrics/catalog",
        )

    if _should_mock(collect_mode):
        return MetricItem(
            metric=metric, ok=True, host=host, collected_at=collected_at,
            elapsed_ms=1, data=mock_metric(metric), error=None,
        )

    allowed = override_allowed
    if allowed is not None and "*" not in allowed and host not in allowed and host not in LOCAL_HOSTS:
        return MetricItem(
            metric=metric, ok=False, host=host, collected_at=collected_at, elapsed_ms=0,
            error=f"host '{host}' not in whitelist",
        )

    script = METRIC_CATALOG[metric]["script"]
    try:
        raw, _ = await asyncio.wait_for(
            asyncio.to_thread(_run_sync, host, script, [window], timeout),
            timeout=timeout + 2,
        )
        data = parse_metric(metric, raw)
        ok = True
        error = None
    except asyncio.TimeoutError:
        data, ok, error = {}, False, f"采集超时（>{timeout}s），已熔断"
    except FileNotFoundError:
        data, ok, error = {}, False, f"脚本缺失：{SCRIPTS_DIR / script}"
    except Exception as exc:  # noqa: BLE001 - 采集侧必须兜住所有异常
        data, ok, error = {}, False, f"{type(exc).__name__}: {exc}"
        logger.warning("collect %s@%s failed: %s", metric, host, exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return MetricItem(metric=metric, ok=ok, host=host, collected_at=collected_at,
                      elapsed_ms=elapsed_ms, data=data, error=error)


async def collect_many(
    host: str,
    metrics: List[str],
    window: str = "5m",
    timeout: int = 10,
    allowed_hosts: Optional[List[str]] = None,
    collect_mode: str = "auto",
) -> List[MetricItem]:
    """并发采集多个指标。"""
    tasks = [collect_one(host, m, window, timeout, allowed_hosts, collect_mode) for m in metrics]
    return list(await asyncio.gather(*tasks))


# --------------------------------------------------------------------------- #
# Mock 数据：Windows / macOS 上演示时，Shell 脚本依赖的 /proc 不存在，
# 用固定分布的模拟数据让整条链路（采集 → 分析 → 报告）依旧可跑通。
# --------------------------------------------------------------------------- #
def _should_mock(mode: str) -> bool:
    if mode == "mock":
        return True
    if mode == "real":
        return False
    return os.name != "posix" or not Path("/proc/stat").exists()


def mock_metric(metric: str) -> Dict[str, Any]:
    table = {
        "cpu_usage": {"cpu_usage": 87.4, "user": 62.1, "system": 19.8, "idle": 12.6, "cores": 8},
        "load_avg": {"load1": 11.32, "load5": 9.87, "load15": 8.44, "cores": 8, "load_per_core": 1.42},
        "mem_usage": {"total_mb": 16384, "used_mb": 14960, "available_mb": 1424,
                      "free_mb": 512, "cache_mb": 3088, "usage_pct": 91.3},
        "swap_usage": {"swap_total_mb": 4096, "swap_used_mb": 2872, "swap_free_mb": 1224, "swap_usage_pct": 70.1},
        "disk_io": {"read_iops": 42.5, "write_iops": 1180.0, "read_mbps": 3.2,
                    "write_mbps": 186.4, "util_pct": 96.2, "sample_sec": 2, "devices": "sda,nvme0n1,"},
        "net_conn": {"ESTABLISHED": 1842, "TIME_WAIT": 6310, "SYN_RECV": 128,
                     "CLOSE_WAIT": 96, "LISTEN": 14, "total_conn": 8386, "retransmitted": 2147},
        "net_bandwidth": {"iface": "eth0", "rx_mbps": 42.18, "tx_mbps": 118.62,
                          "rx_pps": 38120, "tx_pps": 92440, "rx_dropped": 0, "tx_dropped": 12, "sample_sec": 2},
        "uptime_info": {"uptime_seconds": 7354821, "uptime_human": "85d2h20m",
                        "hostname": "prod-app-07", "kernel": "5.10.0-26-amd64",
                        "logged_in_users": 2, "current_time": datetime.now().strftime("%F %T")},
    }
    rows = {
        "cpu_top": {"rows": [
            {"CPU": "63.2", "PID": "28451", "USER": "app", "COMMAND": "java"},
            {"CPU": "18.7", "PID": "31204", "USER": "app", "COMMAND": "python3"},
            {"CPU": "4.1", "PID": "1042", "USER": "root", "COMMAND": "containerd"},
        ]},
        "mem_top": {"rows": [
            {"MEM_PCT": "42.1", "RSS_KB": "6893568", "PID": "28451", "USER": "app", "COMMAND": "java"},
            {"MEM_PCT": "12.4", "RSS_KB": "2031616", "PID": "31204", "USER": "app", "COMMAND": "python3"},
        ]},
        "disk_usage": {"rows": [
            {"FILESYSTEM": "/dev/sda1", "SIZE": "98G", "USED": "94G", "AVAIL": "0", "USE_PCT": "100%", "MOUNTPOINT": "/"},
            {"FILESYSTEM": "/dev/sdb1", "SIZE": "500G", "USED": "312G", "AVAIL": "188G", "USE_PCT": "63%", "MOUNTPOINT": "/data"},
        ]},
        "disk_inode": {"rows": [
            {"FILESYSTEM": "/dev/sda1", "INODES": "6.2M", "IUSED": "6.1M", "IFREE": "98K", "IUSE_PCT": "99%", "MOUNTPOINT": "/"},
        ]},
        "big_dirs": {"rows": [
            {"SIZE_KB": "52428800", "PATH": "/var/log"},
            {"SIZE_KB": "18874368", "PATH": "/data/app/tmp"},
        ]},
        "net_listen": {"rows": [
            {"PROTO": "tcp", "LOCAL_ADDR": "0.0.0.0:80", "PORT": "80", "PROCESS": "nginx"},
            {"PROTO": "tcp", "LOCAL_ADDR": "0.0.0.0:8080", "PORT": "8080", "PROCESS": "java"},
        ]},
        "zombie_proc": {"rows": [{"STATE": "Z", "PID": "31877", "PPID": "28451", "USER": "app", "COMMAND": "sh"}]},
        "service_alive": {"rows": [
            {"SERVICE": "sshd", "ACTIVE": "active", "STATUS": "enabled"},
            {"SERVICE": "nginx", "ACTIVE": "active", "STATUS": "enabled"},
            {"SERVICE": "mysql", "ACTIVE": "failed", "STATUS": "enabled"},
        ]},
    }
    raw = {
        "oom_events": {"raw": "[mock] Out of memory: Killed process 31204 (python3) total-vm:8123456kB"},
        "sys_errors": {"raw": "[mock] ERROR disk I/O error on /dev/sda1 | WARN mysql connect timeout"},
    }
    return table.get(metric) or rows.get(metric) or raw.get(metric, {})


def catalog() -> List[Dict[str, str]]:
    return [
        {"metric": name, "category": meta["category"], "description": meta["desc"]}
        for name, meta in METRIC_CATALOG.items()
    ]
