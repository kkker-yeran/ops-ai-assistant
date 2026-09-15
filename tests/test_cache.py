"""故障指纹与相似故障检索测试（Redis 不可用时自动降级为内存）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings  # noqa: E402
from api.schemas.common import IncidentCreate  # noqa: E402
from api.services.cache import Cache, make_fingerprint  # noqa: E402


@pytest.fixture(scope="module")
def cache():
    return Cache(Settings(redis_host="127.0.0.1", redis_port=6399))  # 端口故意不可达，走内存降级


def test_fingerprint_is_stable_and_bucketed():
    a = make_fingerprint("磁盘写满", "app", {"disk_usage": 96})
    b = make_fingerprint("磁盘写满", "app", {"disk_usage": 99})   # 同区间
    c = make_fingerprint("磁盘写满", "app", {"disk_usage": 20})   # 不同区间
    d = make_fingerprint("磁盘写满", "db", {"disk_usage": 96})    # 不同角色
    assert a == b
    assert a != c
    assert a != d


def test_save_then_similar_hit(cache):
    payload = IncidentCreate(
        symptom="磁盘写满导致服务不可用",
        root_cause="日志未按天轮转，产生海量小文件",
        solution="清理过期文件 + 配置 logrotate",
        host_role="app",
        tags=["磁盘", "日志"],
        key_metrics={"disk_usage": 96},
    )
    record = cache.save_incident(payload)
    assert record.fingerprint

    similar = cache.similar_incidents("磁盘写满导致服务不可用", host_role="app",
                                      key_metrics={"disk_usage": 97}, top_k=3)
    assert similar, "应命中同指纹或关键词相似的故障"
    assert similar[0].root_cause == payload.root_cause


def test_similar_falls_back_to_keyword(cache):
    cache.save_incident(IncidentCreate(
        symptom="CPU 飙高接口超时",
        root_cause="正则回溯",
        solution="修复正则",
        host_role="app",
        key_metrics={"cpu_usage": 95},
    ))
    results = cache.similar_incidents("CPU 飙高 但指标区间完全不同",
                                      host_role="other",
                                      key_metrics={"cpu_usage": 10}, top_k=3)
    assert any("CPU" in r.symptom for r in results)


def test_get_incident_by_id(cache):
    rec = cache.save_incident(IncidentCreate(
        symptom="测试故障", root_cause="测试根因", solution="测试方案",
        host_role="app", key_metrics={"mem_usage": 88},
    ))
    fetched = cache.get_incident(rec.id)
    assert fetched is not None and fetched.id == rec.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
