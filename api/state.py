"""服务状态容器。

把 Retriever / Cache / Embedder 做成惰性单例，避免每次请求重复建索引。
"""

from __future__ import annotations

from .config import Settings, get_settings
from .services.cache import Cache
from .services.embed import Embedder
from .services.retriever import Retriever

_retriever: Retriever | None = None
_cache: Cache | None = None
_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(settings())
    return _cache


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        s = settings()
        embedder = Embedder(
            provider=s.embedding_provider,
            model=(s.embedding_model if s.embedding_provider == "openai" else s.local_embedding_model),
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
        )
        _retriever = Retriever(s, embedder)
    return _retriever
