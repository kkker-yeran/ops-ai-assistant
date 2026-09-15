"""混合召回复用与打分逻辑测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings  # noqa: E402
from api.schemas.common import RagHit  # noqa: E402
from api.services.embed import Embedder  # noqa: E402
from api.services.reranker import rrf_fuse  # noqa: E402
from api.services.retriever import Retriever  # noqa: E402


def _hit(doc_id: str, score: float, recall_type: str) -> RagHit:
    return RagHit(doc_id=doc_id, source="manual", title=doc_id, content="x",
                  score=score, recall_type=recall_type)


def test_rrf_prefers_docs_ranked_in_both_lists():
    vector = [_hit("a", 0.9, "vector"), _hit("b", 0.8, "vector")]
    bm25 = [_hit("b", 5.0, "bm25"), _hit("c", 4.0, "bm25")]
    fused = rrf_fuse([(vector, 1.0), (bm25, 1.0)], k=60, top_k=3)
    assert fused[0].doc_id == "b"          # 双路都命中，排第一
    assert fused[0].recall_type == "hybrid"
    assert {h.doc_id for h in fused} == {"a", "b", "c"}


def test_rrf_scores_are_descending():
    vector = [_hit(f"d{i}", 1.0 - i * 0.1, "vector") for i in range(5)]
    fused = rrf_fuse([(vector, 1.0)], k=10, top_k=5)
    scores = [h.score for h in fused]
    assert scores == sorted(scores, reverse=True)


def test_retriever_loads_bundled_corpus():
    s = Settings(embedding_provider="openai", openai_api_key="")
    r = Retriever(s, Embedder(provider="openai", api_key=""))
    r.load()
    assert len(r.docs) >= 40                       # 30 手册 + 10 案例
    sources = {d["source"] for d in r.docs}
    assert {"manual", "incident"} <= sources


def test_hybrid_search_returns_relevant_doc():
    s = Settings(embedding_provider="openai", openai_api_key="", final_top_k=5)
    r = Retriever(s, Embedder(provider="openai", api_key=""))
    r.load()
    hits = r.search("磁盘写满导致服务不可用", top_k=5)
    assert hits, "至少应召回一条"
    assert any(h.doc_id in {"man-005", "inc-002"} for h in hits)


def test_search_can_be_scoped_by_source():
    s = Settings(embedding_provider="openai", openai_api_key="")
    r = Retriever(s, Embedder(provider="openai", api_key=""))
    r.load()
    hits = r.search("OOM", top_k=5, source="manual")
    assert all(h.source == "manual" for h in hits)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
