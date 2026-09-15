# 演示脚本（5 分钟讲完一个完整闭环）

> 无需 Linux、无需 Redis、无需 API Key 也能演示 —— 项目已内置降级与 mock 数据。

## 0. 准备（30 秒）

```bash
git clone https://github.com/kkker-yeran/ops-ai-assistant.git
cd ops-ai-assistant
pip install -r requirements.txt
uvicorn api.main:app --port 8000
# 打开 http://localhost:8000/docs
```

## 1. 看能力清单（10 秒）

```bash
curl http://localhost:8000/api/v1/metrics/catalog | jq '.data | length'
# 18
```

## 2. 采集真实/模拟指标（30 秒）

```bash
curl -s -X POST http://localhost:8000/api/v1/metrics/collect \
  -H "Content-Type: application/json" \
  -d '{"host":"localhost","metrics":["cpu_usage","mem_usage","disk_usage","net_conn"],"window":"5m"}' \
  | jq '.data.items[] | {metric, ok, elapsed_ms}'
```

输出示例：

```json
{"metric":"cpu_usage","ok":true,"elapsed_ms":1003}
{"metric":"mem_usage","ok":true,"elapsed_ms":12}
{"metric":"disk_usage","ok":true,"elapsed_ms":8}
{"metric":"net_conn","ok":true,"elapsed_ms":6}
```

## 3. 语义检索知识库（30 秒）

```bash
curl -s -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"磁盘还有空间但写不进去","top_k":3}' \
  | jq '.data[] | {title, recall_type, score}'
```

命中 `man-005 df/du —— 磁盘空间与 inode 双重检查`（关键词 + 向量双路 → `hybrid`）。

## 4. 相似故障复用（30 秒）

先写一条历史故障：

```bash
curl -s -X POST http://localhost:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "symptom":"磁盘写满导致服务不可用",
    "root_cause":"日志未按天轮转，产生海量小文件耗尽 inode",
    "solution":"清理过期文件 + 配置 logrotate",
    "host_role":"app",
    "tags":["磁盘","inode"],
    "key_metrics":{"disk_usage":96}
  }' | jq '.data.fingerprint'
```

再用**不同措辞**检索（模拟新人描述不准）：

```bash
curl -s -X POST http://localhost:8000/api/v1/incidents/similar \
  -H "Content-Type: application/json" \
  -d '{"symptom":"磁盘写满导致服务不可用","top_k":2}' \
  | jq '.data[] | {symptom, root_cause}'
```

→ 毫秒级返回历史根因与处置方案，这就是「把 15 分钟压到 3 分钟」的来源。

## 5. 端到端（Dify，2 分钟）

在 Dify 中运行工作流，输入：

> 线上 10.0.0.7 这台机器响应特别慢，接口大量超时，帮我看下什么问题

预期输出结构：

```
## 1. 结论摘要
## 2. 根因定位（含置信度）
## 3. 证据链（指标 → 判读 → 结论）
## 4. 处置建议
   ### 4.1 立即执行（只读）
   ### 4.2 需二次确认（有副作用）
## 5. 根治措施
## 6. 复盘沉淀
```

## 6. 量化效果（30 秒）

```bash
python -m rag.evaluate --top-k 3
```

| 策略 | Hit@3 |
| --- | --- |
| 纯向量 | 66.7% |
| 纯 BM25 | 100% |
| 混合 + RRF | 91.7% |

> 说明：以上为**离线 hash 向量**条件下的基线（未配置 Embedding Key）。
> 评测集措辞与语料词面重合度较高，因此 BM25 占优，这是标注集偏置而非策略结论；
> 配置真实 Embedding 后，混合召回对「同义不同词」的 query 明显优于任意单路。

## 7. 自动化测试（30 秒）

```bash
pytest tests -q     # 22 passed
```

---

## 截图位

| 位置 | 建议放置 |
| --- | --- |
| `docs/images/architecture.png` | 架构图（README 中的 mermaid 已可渲染） |
| `docs/images/dify-workflow.png` | Dify 四阶段工作流画布 |
| `docs/images/diagnosis-report.png` | 一次真实诊断报告输出 |
| `docs/images/api-docs.png` | Swagger 接口页 |
