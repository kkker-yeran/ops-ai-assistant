"""RAG 召回效果评估。

用「问题 → 期望命中 doc_id」的标注集，对比三种召回策略的命中率：
1. 纯向量（vector only）
2. 纯 BM25（bm25 only）
3. 混合 + RRF（hybrid，默认方案）

用法：
    python -m rag.evaluate
    python -m rag.evaluate --top-k 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import get_settings  # noqa: E402
from api.services.embed import Embedder  # noqa: E402
from api.services.retriever import Retriever  # noqa: E402
from api.services.reranker import rrf_fuse  # noqa: E402

# 标注集：query -> 期望命中的 doc_id
EVAL_SET: List[Dict] = [
    {"query": "CPU 突然飙到 100% 怎么排查", "expect": ["man-001", "inc-001"]},
    {"query": "磁盘满了但是 df 看还有空间", "expect": ["man-005", "inc-002"]},
    {"query": "服务频繁被杀掉 Out of memory", "expect": ["man-021", "inc-003"]},
    {"query": "连接数上万 端口不够用了", "expect": ["man-006", "inc-004"]},
    {"query": "CLOSE_WAIT 一直涨", "expect": ["man-023", "inc-005"]},
    {"query": "数据库查询很慢 接口超时", "expect": ["man-020", "inc-006"]},
    {"query": "负载很高但是 CPU 很空闲", "expect": ["man-029", "inc-007"]},
    {"query": "写入延迟高 iostat util 100%", "expect": ["man-003", "inc-008"]},
    {"query": "解析域名超时 接口报错", "expect": ["man-027", "inc-009"]},
    {"query": "云主机周期性卡顿 st 高", "expect": ["man-025", "inc-010"]},
    {"query": "怎么定位哪个进程在写磁盘", "expect": ["man-014", "man-003"]},
    {"query": "nginx 499 是什么问题", "expect": ["man-019"]},
]


def hit_rate_at_k(retriever: Retriever, cases: List[Dict], mode: str, k: int) -> float:
    hits = 0
    for case in cases:
        query, expect = case["query"], case["expect"]
        if mode == "hybrid":
            results = retriever.search(query, top_k=k)
        elif mode == "vector":
            results = retriever._vector_search(query, list(range(len(retriever.docs))), k)
        else:
            results = retriever._bm25_search(query, list(range(len(retriever.docs))), k)

        got = {r.doc_id for r in results}
        if got & set(expect):
            hits += 1
    return hits / len(cases) if cases else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    settings = get_settings()
    embedder = Embedder(
        provider=settings.embedding_provider,
        model=(settings.embedding_model if settings.embedding_provider == "openai"
               else settings.local_embedding_model),
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    retriever = Retriever(settings, embedder)
    retriever.load()

    if not retriever.docs:
        print("语料为空，无法评估")
        return

    print(f"评估集：{len(EVAL_SET)} 条 | Top-K = {args.top_k}")
    print("-" * 46)
    print(f"{'策略':<12}{'Hit@K':>10}")
    print("-" * 46)
    for mode, label in (("vector", "纯向量"), ("bm25", "纯 BM25"), ("hybrid", "混合+RRF")):
        rate = hit_rate_at_k(retriever, EVAL_SET, mode, args.top_k)
        print(f"{label:<12}{rate:>10.1%}")
    print("-" * 46)
    print("说明：无 OPENAI_API_KEY 时向量退化为 hash 向量，纯向量指标会偏低；")
    print("      配置真实 Embedding 后，混合召回通常显著优于任意单路。")


if __name__ == "__main__":
    main()
