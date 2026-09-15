"""知识库检索接口（向量 + BM25 + RRF）。"""
from __future__ import annotations

from fastapi import APIRouter

from ..schemas.common import ApiResponse, RagHit, RagSearchRequest
from ..state import get_retriever

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/search", response_model=ApiResponse[list[RagHit]])
async def search(req: RagSearchRequest) -> ApiResponse[list[RagHit]]:
    hits = get_retriever().search(req.query, top_k=req.top_k, source=req.source)
    return ApiResponse(data=hits)


@router.get("/stats")
async def stats() -> ApiResponse:
    retriever = get_retriever()
    if not retriever.loaded:
        retriever.load()
    by_source: dict[str, int] = {}
    for d in retriever.docs:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
    return ApiResponse(
        data={"total_docs": len(retriever.docs), "by_source": by_source, "loaded": retriever.loaded}
    )
