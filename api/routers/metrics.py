"""指标采集接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import Settings
from ..schemas.common import ApiResponse, MetricRequest, MetricResponse
from ..services import collector

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


def _settings() -> Settings:
    from ..config import get_settings

    return get_settings()


@router.get("/catalog")
async def get_catalog() -> ApiResponse:
    """返回全部可用指标及其说明，供 Agent 侧动态生成 Function Schema。"""
    return ApiResponse(data=collector.catalog())


@router.post("/collect", response_model=ApiResponse[MetricResponse])
async def collect(req: MetricRequest) -> ApiResponse[MetricResponse]:
    """并发采集指定指标，单项失败不影响整体返回。"""
    if not req.metrics:
        raise HTTPException(status_code=400, detail="metrics 不能为空")

    items = await collector.collect_many(
        host=req.host,
        metrics=req.metrics,
        window=req.window,
        timeout=_settings().collect_timeout,
        allowed_hosts=_settings().allowed_hosts,
        collect_mode=_settings().collect_mode,
    )
    return ApiResponse(
        data=MetricResponse(
            host=req.host,
            window=req.window,
            total=len(items),
            succeeded=sum(1 for i in items if i.ok),
            failed=sum(1 for i in items if not i.ok),
            items=items,
        )
    )
