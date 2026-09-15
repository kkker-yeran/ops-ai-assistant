"""构建 / 重建 RAG 索引。

用法：
    python -m rag.build_index --rebuild
    python -m rag.build_index --stats

当前实现使用进程内索引（服务启动时自动 load）。
本脚本用于：
1. 校验语料格式是否合法；
2. 预生成 embedding 缓存到 data/index/embeddings.npy，加速服务冷启动；
3. 输出语料统计，便于评估覆盖度。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import get_settings  # noqa: E402
from api.services.embed import Embedder  # noqa: E402
from api.services.retriever import Retriever, _tokenize  # noqa: E402

INDEX_DIR = ROOT / "data" / "index"


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 RAG 索引")
    parser.add_argument("--rebuild", action="store_true", help="强制重建 embedding 缓存")
    parser.add_argument("--stats", action="store_true", help="只输出语料统计")
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
        print("未找到语料，请检查 data/linux_manual 与 data/incidents 目录")
        return

    # ---------- 统计 ---------- #
    by_source: dict[str, int] = {}
    for d in retriever.docs:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1

    print(f"语料总数：{len(retriever.docs)}")
    for src, cnt in by_source.items():
        print(f"  - {src}: {cnt}")
    avg_len = sum(len(d["content"]) for d in retriever.docs) / len(retriever.docs)
    print(f"平均正文长度：{avg_len:.0f} 字")
    print(f"Embedding 后端：{settings.embedding_provider}（维度 {retriever.vectors.shape[1]}）")

    if args.stats:
        return

    # ---------- 缓存 ---------- #
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    npy_path = INDEX_DIR / "embeddings.npy"
    meta_path = INDEX_DIR / "meta.jsonl"

    if npy_path.exists() and not args.rebuild:
        print(f"索引缓存已存在（{npy_path}），如需重建请加 --rebuild")
        return

    np.save(npy_path, retriever.vectors)
    with meta_path.open("w", encoding="utf-8") as fp:
        for doc, tokens in zip(retriever.docs, [_tokenize(d["title"] + d["content"]) for d in retriever.docs]):
            fp.write(json.dumps({"doc_id": doc["doc_id"], "source": doc["source"],
                                 "title": doc["title"], "n_tokens": len(tokens)},
                                ensure_ascii=False) + "\n")

    print(f"已写入：{npy_path}（{retriever.vectors.shape}）")
    print(f"已写入：{meta_path}")


if __name__ == "__main__":
    main()
