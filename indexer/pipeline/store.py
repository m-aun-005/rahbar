"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

import os
from typing import Any
import redis

from .config import IndexerSettings
from .models import Chunk


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def invalidate_cache(settings: IndexerSettings) -> None:
    """Invalidates the semantic cache upon successful re-indexing to prevent serving stale answers."""
    try:
        redis_host = os.environ.get("REDIS_HOST", "redis")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        r = redis.Redis(host=redis_host, port=redis_port, socket_timeout=2.0)
        r.flushdb()
    except Exception:
        pass


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model

    and vector dimension in the collection metadata (section 4.4). Return the count.
    """
    if not chunks:
        return 0

    client = get_client(settings)
    dimension = len(vectors[0]) if vectors else 768

    # Rebuild collection cleanly or upsert
    try:
        client.delete_collection(settings.collection)
    except Exception:
        pass

    collection = client.create_collection(
        name=settings.collection,
        metadata={
            "hnsw:space": "cosine",
            "embed_model": settings.embed_model,
            "dimension": dimension,
        },
    )

    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        chunk_batch = chunks[i : i + batch_size]
        vector_batch = vectors[i : i + batch_size]
        collection.add(
            ids=[c.id for c in chunk_batch],
            documents=[c.text for c in chunk_batch],
            embeddings=vector_batch,
            metadatas=[c.metadata() for c in chunk_batch],
        )

    # Invalidate semantic cache so new index is served immediately
    invalidate_cache(settings)

    return int(collection.count())
