"""统一响应模型。"""
from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class MetricRequest(BaseModel):
    host: str = Field(..., description="目标主机 IP 或主机名")
    metrics: List[str] = Field(..., description="指标名列表，见 /api/v1/metrics/catalog")
    window: str = Field("5m", description="时间窗口，如 5m / 1h / 24h")
    use_cache: bool = Field(True, description="是否读取 Redis 中的近期缓存")


class MetricItem(BaseModel):
    metric: str
    ok: bool
    host: str
    collected_at: str
    elapsed_ms: int
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class MetricResponse(BaseModel):
    host: str
    window: str
    total: int
    succeeded: int
    failed: int
    items: List[MetricItem]


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source: Optional[str] = Field(None, description="限定语料来源：manual / incident")


class RagHit(BaseModel):
    doc_id: str
    source: str
    title: str
    content: str
    score: float
    recall_type: str  # vector | bm25 | hybrid


class IncidentCreate(BaseModel):
    symptom: str
    root_cause: str
    solution: str
    host_role: str = "unknown"
    tags: List[str] = Field(default_factory=list)
    key_metrics: Dict[str, Any] = Field(default_factory=dict)


class IncidentRecord(IncidentCreate):
    id: str
    fingerprint: str
    created_at: str
    hit_count: int = 0


class SimilarIncidentRequest(BaseModel):
    symptom: str
    top_k: int = 3
