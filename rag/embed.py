"""Embedding 独立封装（便于替换为本地模型 / 批量离线向量化）。

    python -m rag.embed "CPU 飙高怎么排查"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import get_settings  # noqa: E402
from api.services.embed import Embedder  # noqa: E402


def main() -> None:
    text = " ".join(sys.argv[1:]) or "CPU 飙高怎么排查"
    s = get_settings()
    emb = Embedder(
        provider=s.embedding_provider,
        model=(s.embedding_model if s.embedding_provider == "openai" else s.local_embedding_model),
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
    )
    vec = emb.embed([text])[0]
    print(f"text : {text}")
    print(f"dim  : {len(vec)}")
    print(f"head : {[round(v, 4) for v in vec[:8]]}")


if __name__ == "__main__":
    main()
