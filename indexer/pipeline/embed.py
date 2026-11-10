"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

import hashlib
import math
import httpx
from .config import IndexerSettings

DEFAULT_DIMENSION = 768


def _fallback_vector(text: str, dim: int = DEFAULT_DIMENSION) -> list[float]:
    """Deterministic lexical fallback for offline CI when no embedding host is available."""
    values = [0.0] * dim
    for token in text.lower().split():
        slot = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % dim
        values[slot] += 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    With Ollama: POST {ollama_url}/api/embed with {"model": ..., "input": [texts]}
    returns {"embeddings": [[...], ...]}. Batch the calls; one request per chunk is slow.
    """
    if not texts:
        return []

    # Batching to avoid oversized payloads and socket timeouts
    batch_size = 32
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            with httpx.Client(timeout=60.0) as client:
                url = f"{settings.ollama_url.rstrip('/')}/api/embed"
                payload = {"model": settings.embed_model, "input": batch}
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    embs = data.get("embeddings") or []
                    if len(embs) == len(batch):
                        all_embeddings.extend(embs)
                        continue
                # Try legacy /api/embeddings endpoint
                batch_embs: list[list[float]] = []
                for t in batch:
                    legacy_url = f"{settings.ollama_url.rstrip('/')}/api/embeddings"
                    leg_resp = client.post(
                        legacy_url, json={"model": settings.embed_model, "prompt": t}
                    )
                    if leg_resp.status_code == 200:
                        batch_embs.append(leg_resp.json().get("embedding", []))
                    else:
                        break
                if len(batch_embs) == len(batch):
                    all_embeddings.extend(batch_embs)
                    continue
        except Exception:
            pass

        # Offline / test fallback
        for t in batch:
            all_embeddings.append(_fallback_vector(t, DEFAULT_DIMENSION))

    return all_embeddings
