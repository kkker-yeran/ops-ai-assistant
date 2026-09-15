"""采集器测试：未知指标、mock 模式、并发聚合。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.services import collector  # noqa: E402


def test_catalog_covers_15_plus_metrics():
    assert len(collector.METRIC_CATALOG) >= 15
    for name, meta in collector.METRIC_CATALOG.items():
        script = collector.SCRIPTS_DIR / meta["script"]
        assert script.exists(), f"{name} 缺少脚本 {script}"


def test_unknown_metric_returns_error_item():
    item = asyncio.run(collector.collect_one("localhost", "not_exist", collect_mode="real"))
    assert item.ok is False
    assert "unknown metric" in (item.error or "")


def test_host_whitelist_blocks_unknown_host():
    item = asyncio.run(collector.collect_one(
        "10.9.9.9", "cpu_usage", override_allowed=["localhost"], collect_mode="real"))
    assert item.ok is False
    assert "whitelist" in (item.error or "")


def test_mock_mode_returns_structured_data():
    item = asyncio.run(collector.collect_one("localhost", "cpu_usage", collect_mode="mock"))
    assert item.ok is True
    assert item.data["cpu_usage"] > 0


def test_collect_many_is_concurrent_and_tolerant():
    metrics = ["cpu_usage", "mem_usage", "disk_usage", "not_exist"]
    items = asyncio.run(collector.collect_many("localhost", metrics, collect_mode="mock"))
    assert len(items) == 4
    assert sum(1 for i in items if i.ok) == 3


def test_parse_table_and_kv():
    rows = collector._parse_table("A B\n1 2\n3 4")
    assert rows == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]

    kv = collector._parse_kv("cpu_usage=12.5\ncores=8\nhost=web-01")
    assert kv["cpu_usage"] == 12.5
    assert kv["cores"] == 8
    assert kv["host"] == "web-01"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
