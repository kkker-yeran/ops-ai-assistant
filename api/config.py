"""全局配置中心。

所有配置项均可通过环境变量或 .env 文件覆盖，便于本地开发 / Docker / 生产三态切换。
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 服务 ----------
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ---------- 采集 ----------
    collect_timeout: int = 10
    collect_allowed_hosts: str = "localhost,127.0.0.1"
    # auto：非 Linux 环境自动使用 mock 数据（便于 Windows / macOS 演示）
    # real：强制真实采集；mock：强制模拟数据
    collect_mode: str = "auto"

    # ---------- Redis ----------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    metric_cache_ttl: int = 60
    incident_ttl: int = 15552000  # 180 天

    # ---------- Embedding ----------
    embedding_provider: str = "openai"  # openai | local_bge
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # ---------- RAG ----------
    rrf_k: int = 60
    vector_top_k: int = 10
    bm25_top_k: int = 10
    final_top_k: int = 5

    # ---------- Dify ----------
    dify_base_url: str = "http://localhost:80/v1"
    dify_api_key: str = ""

    @property
    def allowed_hosts(self) -> List[str]:
        return [h.strip() for h in self.collect_allowed_hosts.split(",") if h.strip()]

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
