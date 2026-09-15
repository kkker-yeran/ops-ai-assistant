# 指标采集脚本集

17 个纯 Shell 采集脚本，**零依赖、可直接 `bash xxx.sh` 运行**，运维同学脱离本项目也能单独使用。

## 契约

- **入参**：`$1` = 时间窗口（如 `5m` / `1h` / `24h`），缺省时脚本内部取默认值。
- **出参**：标准输出，三种格式之一，由 `api/services/collector.py` 解析：
  1. `key=value` 逐行 → 解析为 dict（数值型会自动转 JSON 数字）
  2. 首行表头 + 后续数据行（空格分隔）→ 解析为 `rows` 列表
  3. 原始日志文本 → 保留为 `raw` 字段，交给 LLM 总结
- **退出码**：0 正常；非零且无标准输出时视为采集失败，接口返回 `ok=false`。

## 指标清单

| 分类 | 脚本 | 指标名 | 输出格式 |
| --- | --- | --- | --- |
| CPU | `cpu_usage.sh` | `cpu_usage` | kv |
| CPU | `load_avg.sh` | `load_avg` | kv |
| CPU | `cpu_top.sh` | `cpu_top` | table |
| 内存 | `mem_usage.sh` | `mem_usage` | kv |
| 内存 | `mem_top.sh` | `mem_top` | table |
| 内存 | `swap_usage.sh` | `swap_usage` | kv |
| 内存 | `oom_events.sh` | `oom_events` | raw |
| 磁盘 | `disk_usage.sh` | `disk_usage` | table |
| 磁盘 | `disk_inode.sh` | `disk_inode` | table |
| 磁盘 | `disk_io.sh` | `disk_io` | kv |
| 磁盘 | `big_dirs.sh` | `big_dirs` | table |
| 网络 | `net_conn.sh` | `net_conn` | kv |
| 网络 | `net_bandwidth.sh` | `net_bandwidth` | kv |
| 网络 | `net_listen.sh` | `net_listen` | table |
| 系统 | `uptime_info.sh` | `uptime_info` | kv |
| 系统 | `zombie_proc.sh` | `zombie_proc` | table |
| 系统 | `sys_errors.sh` | `sys_errors` | raw |
| 系统 | `service_alive.sh` | `service_alive` | table |

## 新增一个指标

1. 在 `scripts/` 下新增 `xxx.sh`，按上述契约输出；
2. 在 `api/services/collector.py` 的 `METRIC_CATALOG` 中加一行；
3. 若是表格/日志类输出，把指标名加进对应的 `TABLE_METRICS` / `KV_METRICS` / `RAW_METRICS`。

无需改动路由、Schema 或 Agent 侧代码 —— `/api/v1/metrics/catalog` 与 Function Schema 会自动包含新指标。

## 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `BIG_DIR_ROOT` | `big_dirs.sh` 扫描根目录 | `/` |
| `NET_IFACE` | `net_bandwidth.sh` 目标网卡 | `/proc/net/dev` 第一个非 lo 网卡 |
| `CHECK_SERVICES` | `service_alive.sh` 检测的服务列表 | `sshd nginx redis-server mysql docker` |

## 权限与远程执行

- 本地执行：需要目标机器上有 `procps` / `iproute2` / `sysstat`（Dockerfile 已装）。
- 远程执行：`collector.py` 通过 `ssh <host> bash -s` **把脚本内容走 stdin 传过去**，
  因此目标机无需预置脚本；建议提前配置 SSH 免密，并遵守 `COLLECT_ALLOWED_HOSTS` 白名单。
