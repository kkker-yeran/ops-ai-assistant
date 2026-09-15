"""召回结果融合重排。

采用 **RRF（Reciprocal Rank Fusion）**：

    score(d) = Σ_r  w_r / (k + rank_r(d))

优点：不需要各路的原始分数在同一量纲（余弦相似度与 BM25 分数不可直接相加），
只依赖排名，稳定且无需调参。
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ..schemas.common import RagHit


def rrf_fuse(
    ranked_lists: Sequence[Tuple[Sequence[RagHit], float]],
    k: int = 60,
    top_k: int = 5,
) -> List[RagHit]:
    """把多路召回结果融合。

    :param ranked_lists: [(该路召回结果按分数降序, 该路权重), ...]
    :param k: RRF 平滑常数，越大越弱化头部优势
    :param top_k: 最终返回条数
    """
    fused: Dict[str, float] = {}
    hit_map: Dict[str, RagHit] = {}

    for hits, weight in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            fused[hit.doc_id] = fused.get(hit.doc_id, 0.0) + weight / (k + rank)
            # 保留首次出现的 hit，再补记召回来源
            if hit.doc_id not in hit_map:
                hit_map[hit.doc_id] = hit
            elif hit.recall_type not in hit_map[hit.doc_id].recall_type:
                hit_map[hit.doc_id] = hit_map[hit.doc_id].model_copy(
                    update={"recall_type": "hybrid"}
                )

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    result: List[RagHit] = []
    for doc_id, score in ordered:
        hit = hit_map[doc_id].model_copy(update={"score": round(score, 6)})
        if len([h for h, _ in ranked_lists if any(x.doc_id == doc_id for x in h)]) > 1:
            hit = hit.model_copy(update={"recall_type": "hybrid"})
        result.append(hit)
    return result
