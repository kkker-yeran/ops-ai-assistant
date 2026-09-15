# 部署手册

## 1. 环境要求

| 组件 | 版本 | 必需 |
| --- | --- | --- |
| Python | 3.10+ | 是 |
| Redis | 7.x | 否（缺失时自动降级为内存缓存） |
| Docker / Compose | 20.10+ | 否（推荐） |
| Linux 主机 | 任意发行版 | 采集真实指标时需要 |
| Dify | 任意版本 | Agent 编排时需要 |

## 2. 本地开发

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

uvicorn api.main:app --reload --port 8000
# 打开 http://localhost:8000/docs
```

Windows / macOS 上 `COLLECT_MODE=auto` 会自动使用 mock 指标，方便调试 UI 与 Agent 链路。

## 3. Docker Compose（推荐）

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f api
curl http://localhost:8000/health
```

停止：`docker compose down`（`-v` 会清空 Redis 数据卷）。

## 4. 生产部署清单

- [ ] `.env` 中 `APP_ENV=prod`、`LOG_LEVEL=INFO`
- [ ] `COLLECT_ALLOWED_HOSTS` 明确列出允许采集的主机，**不要使用 `*`**
- [ ] `COLLECT_MODE=real`
- [ ] Redis 开启持久化（compose 已启用 AOF）并设置密码
- [ ] 配置 `OPENAI_API_KEY` 或使用 `EMBEDDING_PROVIDER=local_bge` 本地向量模型
- [ ] Nginx 反向代理 + HTTPS（见下方示例）
- [ ] 为 `/api/v1/incidents` 写入口配置鉴权（生产环境不应裸奔）

### Nginx 示例

```nginx
server {
    listen 443 ssl;
    server_name ops-ai.example.com;

    ssl_certificate     /etc/nginx/cert/fullchain.pem;
    ssl_certificate_key /etc/nginx/cert/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;   # 采集接口较慢，适当放宽
    }
}
```

## 5. 接入 Dify

1. 启动 Dify（官方 docker compose 即可）；
2. 工作室 → 导入 DSL → 选择 `agent/dify_workflow.yml`；
3. 配置环境变量 `API_BASE_URL`：
   - Dify 与本项目同在 Docker 网络：`http://ops-ai-api:8000`
   - Dify 在 Docker、本项目在宿主机：`http://host.docker.internal:8000`
4. 在模型供应商中填入自己的 API Key；
5. 右上角发布 → 运行，输入「10.0.0.7 这台机器很卡，帮我看看」。

## 6. 采集远程主机

```bash
# 1) 在采集机生成密钥
ssh-keygen -t ed25519 -C "ops-ai"

# 2) 分发公钥到目标机
ssh-copy-id ops@10.0.0.7

# 3) 配置白名单
echo "COLLECT_ALLOWED_HOSTS=localhost,10.0.0.7,10.0.0.8" >> .env
```

远程执行通过 `ssh <host> bash -s` 传输脚本内容，目标机**无需预置任何文件**。

## 7. 验证清单

```bash
pytest tests -q                          # 22 项单测
python -m rag.build_index --stats        # 语料统计
python -m rag.evaluate --top-k 3         # 召回命中率
curl localhost:8000/health               # 健康检查
```

## 8. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Redis 连接失败但服务正常 | 未装 / 未启动 Redis | 预期行为，已降级为内存缓存 |
| 采集全部 `ok=false` | 非 Linux 且强制 `real` 模式 | 改 `COLLECT_MODE=auto` |
| `host not in whitelist` | 未在白名单中 | 加进 `COLLECT_ALLOWED_HOSTS` |
| 检索结果为空 | 语料未加载 | 检查 `data/` 目录与 `rag.stats` |
| 向量召回质量差 | 未配置 Embedding Key | 配 `OPENAI_API_KEY` 或改用 `local_bge` |
