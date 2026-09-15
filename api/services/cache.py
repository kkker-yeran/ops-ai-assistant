"""Redis 缓存层：指标短期缓存 + 历史故障指纹索引。

设计要点：
1. **降级可用**：Redis 不可用时自动切换为进程内字典，接口行为一致，
   保证本地 demo / 单测不依赖外部组件。
2. **故障指纹**：`故障类型 + 主机角色 + 关键指标区间` 生成指纹，
   相似故障先查指纹再查语义，做到毫秒级命中。
3. **TTL**：指标缓存 60s（避免多轮追问重复采集），故障记录 180 天。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Settings
from ..schemas.common import IncidentCreate, IncidentRecord

logger = logging.getLogger(__name__)

# 指标区间分桶：把连续值离散化，让"相近但不相等"的故障落到同一个指纹
BUCKETS = [(90, "critical"), (75, "high"), (50, "medium"), (0, "normal")]


def _bucket(value: float) -> str:
    for threshold, name in BUCKETS:
        if value >= threshold:
            return name
    return "normal"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def make_fingerprint(symptom: str, host_role: str, key_metrics: Dict[str, Any]) -> str:
    """生成故障指纹：症状关键词 + 主机角色 + 关键指标分桶。"""
    metric_part = "|".join(
        f"{k}:{_bucket(float(v))}"
        for k, v in sorted(key_metrics.items(), key=lambda kv: kv[0])
        if _is_number(v)
    )
    raw = f"{_normalize(symptom)}#{host_role}#{metric_part}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _is_number(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


class Cache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._redis = None
        self._memory: Dict[str, str] = {}
        self._connect()

    # ---------------- 底层 ---------------- #
    def _connect(self) -> None:
        try:
            import redis  # 延迟导入

            client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                password=self.settings.redis_password or None,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            client.ping()
            self._redis = client
            logger.info("Redis 已连接：%s:%s", self.settings.redis_host, self.settings.redis_port)
        except Exception as exc:  # noqa: BLE001
            self._redis = None
            logger.warning("Redis 不可用（%s），降级为进程内缓存", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def _get(self, key: str) -> Optional[str]:
        if self._redis is not None:
            try:
                return self._redis.get(key)
            except Exception:  # noqa: BLE001
                self._redis = None
        return self._memory.get(key)

    def _set(self, key: str, value: str, ttl: int) -> None:
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, value)
                return
            except Exception:  # noqa: BLE001
                self._redis = None
        self._memory[key] = value

    def _delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
                return
            except Exception:  # noqa: BLE001
                self._redis = None
        self._memory.pop(key, None)

    def _keys(self, pattern: str) -> List[str]:
        if self._redis is not None:
            try:
                return list(self._redis.keys(pattern))
            except Exception:  # noqa: BLE001
                self._redis = None
        import fnmatch

        return [k for k in self._memory if fnmatch.fnmatch(k, pattern)]

    def _incr(self, key: str) -> int:
        if self._redis is not None:
            try:
                return int(self._redis.incr(key))
            except Exception:  # noqa: BLE001
                self._redis = None
        val = int(self._memory.get(key, 0)) + 1
        self._memory[key] = str(val)
        return val

    # ---------------- 指标缓存 ---------------- #
    def metric_key(self, host: str, metric: str, window: str) -> str:
        return f"ops:metric:{host}:{metric}:{window}"

    def get_metric(self, host: str, metric: str, window: str) -> Optional[Dict[str, Any]]:
        raw = self._get(self.metric_key(host, metric, window))
        return json.loads(raw) if raw else None

    def set_metric(self, host: str, metric: str, window: str, value: Dict[str, Any]) -> None:
        self._set(self.metric_key(host, metric, window), json.dumps(value, ensure_ascii=False),
                  self.settings.metric_cache_ttl)

    # ---------------- 故障记录 ---------------- #
    def save_incident(self, payload: IncidentCreate) -> IncidentRecord:
        fp = make_fingerprint(payload.symptom, payload.host_role, payload.key_metrics)
        incident_id = f"{fp}-{int(datetime.now().timestamp())}"
        record = IncidentRecord(
            id=incident_id,
            fingerprint=fp,
            created_at=datetime.now().isoformat(timespec="seconds"),
            hit_count=0,
            **payload.model_dump(),
        )
        self._set(f"ops:incident:{incident_id}", record.model_dump_json(), self.settings.incident_ttl)
        # 指纹倒排：同指纹的故障 id 列表
        idx_key = f"ops:fp:{fp}"
        existing = self._get(idx_key)
        ids = json.loads(existing) if existing else []
        ids.append(incident_id)
        self._set(idx_key, json.dumps(ids), self.settings.incident_ttl)
        return record

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        raw = self._get(f"ops:incident:{incident_id}")
        return IncidentRecord.model_validate_json(raw) if raw else None

    def similar_incidents(self, symptom: str, host_role: str = "unknown",
                          key_metrics: Optional[Dict[str, Any]] = None,
                          top_k: int = 3) -> List[IncidentRecord]:
        """先按指纹精确命中，未命中再退化为「同指纹前缀 + 关键词」模糊扫描。"""
        key_metrics = key_metrics or {}
        fp = make_fingerprint(symptom, host_role, key_metrics)

        results: List[IncidentRecord] = []
        for inc_id in json.loads(self._get(f"ops:fp:{fp}") or "[]"):
            rec = self.get_incident(inc_id)
            if rec:
                results.append(rec)

        if len(results) < top_k:
            # 退化：扫描全部故障，用关键词重合度打分
            keyword_hits = []
            tokens = set(re.findall(r"[\u4e00-\u9fff]{2}|[a-zA-Z]{3,}", symptom))
            for key in self._keys("ops:incident:*"):
                rec = self.get_incident(key.split("ops:incident:")[-1])
                if not rec or rec in results:
                    continue
                overlap = len(tokens & set(re.findall(r"[\u4e00-\u9fff]{2}|[a-zA-Z]{3,}", rec.symptom)))
                if overlap:
                    keyword_hits.append((overlap, rec))
            keyword_hits.sort(key=lambda x: x[0], reverse=True)
            results += [r for _, r in keyword_hits[: top_k - len(results)]]

        for rec in results:
            self._incr(f"ops:hit:{rec.id}")
        return results[:top_k]
