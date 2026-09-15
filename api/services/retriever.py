"""RAG 混合召回：向量检索（语义）+ BM25（关键词）+ RRF 融合。

语料来源：
- `data/linux_manual/*.jsonl` —— Linux 命令手册（200+ 条，仓库内置 30 条示例）
- `data/incidents/*.jsonl`    —— 历史故障处置案例（50+ 场景，仓库内置 10 条示例）

召回策略为什么是混合的：
纯向量对 "机器卡" 这类极短 query 容易漂移到语义相近但不相关的条目；
纯 BM25 对 "CPU 飙高" 与 "处理器使用率过高" 这种同义表达无能为力。
两路召回 + RRF 融合，实测命中率明显高于任何单路。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..config import Settings
from ..schemas.common import RagHit
from .embed import Embedder
from .reranker import rrf_fuse

logger = logging.getLogger(__name__)

# api/services/retriever.py -> parents: [0]=services [1]=api [2]=项目根
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class CorpusDoc(Dict):
    """语料条目：doc_id / title / content / source / tags"""


class Retriever:
    def __init__(self, settings: Settings, embedder: Embedder):
        self.settings = settings
        self.embedder = embedder
        self.docs: List[CorpusDoc] = []
        self.vectors: Optional[np.ndarray] = None
        self._bm25 = None
        self._tokenized: List[List[str]] = []
        self.loaded = False

    # ---------------- 构建索引 ---------------- #
    def load(self) -> None:
        self.docs = self._read_corpus()
        if not self.docs:
            logger.warning("未加载到任何语料，RAG 检索将返回空结果")
            self.loaded = True
            return

        texts = [f"{d['title']}\n{d['content']}" for d in self.docs]
        vectors = self.embedder.embed(texts)
        self.vectors = np.asarray(vectors, dtype="float32")
        # 归一化，便于点积即余弦；全零向量（空文本）避免除零
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        self.vectors = self.vectors / np.where(norms == 0, 1.0, norms)

        self._tokenized = [_tokenize(t) for t in texts]
        try:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi(self._tokenized)
        except ImportError:
            logger.warning("rank_bm25 未安装，关键词召回降级为词频打分")
            self._bm25 = None

        self.loaded = True
        logger.info("RAG 索引就绪：%d 条语料，向量维度 %s", len(self.docs), self.vectors.shape[1])

    @staticmethod
    def _read_corpus() -> List[CorpusDoc]:
        docs: List[CorpusDoc] = []
        for pattern in ("linux_manual/*.jsonl", "incidents/*.jsonl"):
            for path in sorted(DATA_DIR.glob(pattern)):
                with path.open("r", encoding="utf-8") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        item = json.loads(line)
                        docs.append(
                            CorpusDoc(
                                doc_id=item["doc_id"],
                                title=item["title"],
                                content=item["content"],
                                source=item.get("source", path.parent.name),
                                tags=item.get("tags", []),
                            )
                        )
        return docs

    # ---------------- 检索 ---------------- #
    def search(self, query: str, top_k: Optional[int] = None, source: Optional[str] = None) -> List[RagHit]:
        if not self.loaded:
            self.load()
        if not self.docs:
            return []

        top_k = top_k or self.settings.final_top_k
        pool = self.docs if source is None else [d for d in self.docs if d["source"] == source]
        if not pool:
            return []

        idx_map = {d["doc_id"]: i for i, d in enumerate(self.docs)}
        pool_idx = [idx_map[d["doc_id"]] for d in pool]

        vector_hits = self._vector_search(query, pool_idx, self.settings.vector_top_k)
        bm25_hits = self._bm25_search(query, pool_idx, self.settings.bm25_top_k)

        return rrf_fuse(
            [(vector_hits, 1.0), (bm25_hits, 1.0)],
            k=self.settings.rrf_k,
            top_k=top_k,
        )

    def _vector_search(self, query: str, pool_idx: List[int], top_k: int) -> List[RagHit]:
        if self.vectors is None:
            return []
        q = np.asarray(self.embedder.embed([query])[0], dtype="float32")
        q = q / (np.linalg.norm(q) or 1.0)
        sub = self.vectors[pool_idx]
        scores = sub @ q
        order = np.argsort(-scores)[:top_k]
        return [
            RagHit(
                doc_id=self.docs[pool_idx[i]]["doc_id"],
                source=self.docs[pool_idx[i]]["source"],
                title=self.docs[pool_idx[i]]["title"],
                content=self.docs[pool_idx[i]]["content"],
                score=float(scores[i]),
                recall_type="vector",
            )
            for i in order
            if scores[i] > 0
        ]

    def _bm25_search(self, query: str, pool_idx: List[int], top_k: int) -> List[RagHit]:
        tokens = _tokenize(query)
        if not tokens:
            return []

        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokens)
        else:  # 降级：词频打分
            scores = np.array(
                [sum(doc.count(t) for t in tokens) / (len(doc) + 1) for doc in self._tokenized],
                dtype="float32",
            )

        sub = [(i, float(scores[i])) for i in pool_idx]
        sub.sort(key=lambda x: x[1], reverse=True)
        return [
            RagHit(
                doc_id=self.docs[i]["doc_id"],
                source=self.docs[i]["source"],
                title=self.docs[i]["title"],
                content=self.docs[i]["content"],
                score=round(s, 6),
                recall_type="bm25",
            )
            for i, s in sub[:top_k]
            if s > 0
        ]


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_./\-]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def build_index(settings: Settings, embedder: Embedder) -> Retriever:
    r = Retriever(settings, embedder)
    r.load()
    return r
