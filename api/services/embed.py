"""Embedding 适配层。

统一 `embed(texts) -> List[List[float]]` 签名，支持：
- `openai`：调用 OpenAI 兼容接口（含各类中转 / 本地 vLLM / Ollama 的 OpenAI 兼容端点）
- `local_bge`：使用 sentence-transformers 加载本地中文向量模型

没有配置 Key 或依赖缺失时，降级为 **哈希向量（hashing trick）**，
保证项目在离线环境依然能跑通完整链路（召回质量下降，但管道不中断）。
"""

from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)

HASH_DIM = 256


class Embedder:
    def __init__(self, provider: str = "openai", model: str = "", api_key: str = "", base_url: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._client = None
        self._local_model = None

    # ---------------- 公开接口 ---------------- #
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            if self.provider == "local_bge":
                return self._embed_local(texts)
            if self.provider == "openai" and self.api_key:
                return self._embed_openai(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding via %s failed (%s)，降级为 hash 向量", self.provider, exc)
        return [self._hash_vector(t) for t in texts]

    def dim(self) -> int:
        if self.provider == "local_bge":
            return 512
        if self.provider == "openai" and self.api_key:
            return 1536
        return HASH_DIM

    # ---------------- 各实现 ---------------- #
    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        from openai import OpenAI  # 延迟导入，离线环境无需安装

        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        from sentence_transformers import SentenceTransformer  # 延迟导入

        if self._local_model is None:
            self._local_model = SentenceTransformer(self.model)
        return self._local_model.encode(texts, normalize_embeddings=True).tolist()

    @staticmethod
    def _hash_vector(text: str) -> List[float]:
        """基于词袋 + 哈希技巧的轻量向量，用于离线兜底。"""
        vec = [0.0] * HASH_DIM
        tokens = _tokenize(text)
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % HASH_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _tokenize(text: str) -> List[str]:
    """中英文混排分词：英文按词，中文按 2-gram。"""
    tokens: List[str] = []
    buf = ""
    for ch in text.lower():
        if ch.isalnum():
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
    if buf:
        tokens.append(buf)

    cn_tokens: List[str] = []
    cn_buf = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
    for i in range(len(cn_buf) - 1):
        cn_tokens.append(cn_buf[i : i + 2])
    return tokens + cn_tokens


@lru_cache
def get_embedder(provider: str, model: str, api_key: str, base_url: str) -> Embedder:
    return Embedder(provider=provider, model=model, api_key=api_key, base_url=base_url)
