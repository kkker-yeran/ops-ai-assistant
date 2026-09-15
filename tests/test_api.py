"""API 冒烟测试：不依赖外部组件（Redis / Embedding 均可降级）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_lists_endpoints(client):
    r = client.get("/")
    assert r.status_code == 200
    endpoints = r.json()["endpoints"]
    assert any("metrics/collect" in e for e in endpoints)


def test_catalog(client):
    r = client.get("/api/v1/metrics/catalog")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) >= 15


def test_collect_endpoint(client):
    # 非 Linux 环境下 collect_mode=auto 自动走 mock，Windows / macOS 也能跑通
    r = client.post("/api/v1/metrics/collect",
                    json={"host": "localhost", "metrics": ["cpu_usage", "mem_usage"]})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 2
    assert body["succeeded"] + body["failed"] == 2


def test_rag_search(client):
    r = client.post("/api/v1/rag/search", json={"query": "磁盘写满", "top_k": 3})
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 1


def test_rag_stats(client):
    r = client.get("/api/v1/rag/stats")
    assert r.status_code == 200
    assert r.json()["data"]["total_docs"] >= 40


def test_incident_roundtrip(client):
    payload = {
        "symptom": "CPU 飙高至 100%",
        "root_cause": "正则回溯导致死循环",
        "solution": "修复正则并补充压测",
        "host_role": "app",
        "tags": ["CPU"],
        "key_metrics": {"cpu_usage": 96},
    }
    created = client.post("/api/v1/incidents", json=payload)
    assert created.status_code == 200
    inc_id = created.json()["data"]["id"]

    fetched = client.get(f"/api/v1/incidents/{inc_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["root_cause"] == payload["root_cause"]

    similar = client.post("/api/v1/incidents/similar",
                          json={"symptom": "CPU 飙高至 100%", "top_k": 2})
    assert similar.status_code == 200
    assert len(similar.json()["data"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
