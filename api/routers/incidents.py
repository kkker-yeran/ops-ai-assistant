"""历史故障 / 相似案例接口（Redis 指纹索引）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.common import ApiResponse, IncidentCreate, IncidentRecord, SimilarIncidentRequest
from ..state import get_cache

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.post("", response_model=ApiResponse[IncidentRecord])
async def create_incident(payload: IncidentCreate) -> ApiResponse[IncidentRecord]:
    """写入一条故障处置记录，自动生成指纹并建倒排索引。"""
    record = get_cache().save_incident(payload)
    return ApiResponse(message="incident saved", data=record)


@router.get("/{incident_id}", response_model=ApiResponse[IncidentRecord])
async def get_incident(incident_id: str) -> ApiResponse[IncidentRecord]:
    record = get_cache().get_incident(incident_id)
    if not record:
        raise HTTPException(status_code=404, detail="incident not found")
    return ApiResponse(data=record)


@router.post("/similar", response_model=ApiResponse[list[IncidentRecord]])
async def similar(req: SimilarIncidentRequest) -> ApiResponse[list[IncidentRecord]]:
    """检索相似历史故障：先指纹精确命中，再关键词模糊兜底。"""
    results = get_cache().similar_incidents(req.symptom, top_k=req.top_k)
    return ApiResponse(data=results)
