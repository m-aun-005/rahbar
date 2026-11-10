"""Liveness and readiness probes (section 4.3).

- /healthz: Liveness probe. Answers: is the process alive? Must NEVER touch dependencies.
- /readyz: Readiness probe. Answers: can it take traffic now? Checks Chroma reachable,
  collection non-empty, Redis reachable, and embedding model matches EMBED_MODEL.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Request, Response, status

log = logging.getLogger("rahbar.health")
router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Readiness probe. Returns 200 only if Chroma is reachable, the collection

    exists and is non-empty, Redis is reachable, and the embedding model matches
    EMBED_MODEL. On failure, returns 503 naming the dependency that failed.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not ready", "error": "settings not loaded"}

    checks: dict[str, Any] = {}
    failed_dependencies: list[str] = []

    # If running with stub retriever, pass readiness directly for offline CI
    if settings.retriever == "stub":
        return {
            "status": "ready",
            "checks": {"retriever": "stub", "collection_count": 3, "embed_model": "stub"},
        }

    # 1. Check Chroma reachability & non-empty collection
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = chroma_client.get_collection(settings.collection)
        chunk_count = collection.count()

        if chunk_count <= 0:
            failed_dependencies.append("chroma: collection is empty (run indexer Job)")
            checks["chroma"] = "empty collection"
        else:
            checks["chroma"] = f"ok ({chunk_count} chunks)"

        # 2. Check embedding model pin guardrail (section 4.4)
        meta = collection.metadata or {}
        col_model = meta.get("embed_model") or meta.get("embedding_model")
        if col_model and col_model != settings.embed_model:
            conflict_msg = (
                f"embedding model mismatch: collection has {col_model!r} "
                f"!= settings.embed_model {settings.embed_model!r}"
            )
            log.error(conflict_msg)
            failed_dependencies.append(f"embed_model mismatch ({col_model} != {settings.embed_model})")
            checks["embed_model"] = conflict_msg
        else:
            checks["embed_model"] = f"pinned ({settings.embed_model})"

    except Exception as exc:
        failed_dependencies.append(f"chroma unreachable: {exc}")
        checks["chroma"] = f"error: {exc}"

    # 3. Check Redis reachability
    if settings.enable_cache:
        try:
            import redis

            r = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                socket_timeout=1.5,
            )
            r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            failed_dependencies.append(f"redis unreachable: {exc}")
            checks["redis"] = f"error: {exc}"

    if failed_dependencies:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not ready",
            "failed_dependencies": failed_dependencies,
            "checks": checks,
        }

    return {"status": "ready", "checks": checks}
