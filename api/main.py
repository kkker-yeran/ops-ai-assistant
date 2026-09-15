"""Ops AI Assistant · FastAPI 采集与检索服务。

启动：
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import incidents, metrics, rag
from .state import get_cache, get_retriever, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ops-ai-assistant")

@asynccontextmanager
async def lifespan(_: FastAPI):
    s = settings()
    logger.info("启动环境=%s，Redis 后端=%s", s.app_env, get_cache().backend)
    # 预热 RAG 索引，避免首个请求抖动
    retriever = get_retriever()
    retriever.load()
    logger.info("RAG 语料 %d 条（source 分布见 /api/v1/rag/stats）", len(retriever.docs))
    yield
    logger.info("服务已停止")


app = FastAPI(
    title="Ops AI Assistant API",
    description="智能运维故障分析助手 · 指标采集 / RAG 检索 / 历史故障复用",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics.router)
app.include_router(rag.router)
app.include_router(incidents.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings().app_env,
        "redis": get_cache().backend,
        "rag_docs": len(get_retriever().docs),
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "name": "Ops AI Assistant",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "GET  /api/v1/metrics/catalog",
            "POST /api/v1/metrics/collect",
            "POST /api/v1/rag/search",
            "GET  /api/v1/rag/stats",
            "POST /api/v1/incidents",
            "POST /api/v1/incidents/similar",
        ],
    }
