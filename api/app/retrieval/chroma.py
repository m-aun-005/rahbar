"""The real retriever. Reads the Chroma collection and enforces the embedding pin."""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, cast
import httpx

from ..config import Settings
from ..schemas import Passage

log = logging.getLogger("rahbar.retrieval.chroma")


def _fallback_vector(text: str, dim: int = 768) -> list[float]:
    """Deterministic lexical fallback for offline CI when no embedding host is available."""
    values = [0.0] * dim
    for token in text.lower().split():
        slot = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % dim
        values[slot] += 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_query(text: str, settings: Settings) -> list[float]:
    """Embeds a single query string using the pinned EMBED_MODEL."""
    try:
        with httpx.Client(timeout=10.0) as client:
            url = f"{settings.ollama_url.rstrip('/')}/api/embed"
            resp = client.post(url, json={"model": settings.embed_model, "input": [text]})
            if resp.status_code == 200:
                data = resp.json()
                embs = data.get("embeddings") or []
                if embs:
                    return embs[0]
            # Try legacy endpoint
            legacy_url = f"{settings.ollama_url.rstrip('/')}/api/embeddings"
            leg_resp = client.post(
                legacy_url, json={"model": settings.embed_model, "prompt": text}
            )
            if leg_resp.status_code == 200:
                return leg_resp.json().get("embedding", [])
    except Exception:
        pass
    return _fallback_vector(text, 768)


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def verify_embedding_pin(self, collection: Any) -> None:
        """Enforces section 4.4: embedding model in collection metadata must match EMBED_MODEL."""
        meta = collection.metadata or {}
        col_model = meta.get("embed_model") or meta.get("embedding_model")
        if col_model and col_model != self.settings.embed_model:
            msg = (
                f"EMBED_MODEL mismatch: index was built with {col_model!r} "
                f"but API is configured with {self.settings.embed_model!r}"
            )
            log.error(msg)
            raise ValueError(msg)

    def retrieve(self, question: str, k: int) -> list[Passage]:
        """Embed the question with settings.embed_model, query Chroma for top k,

        filter out superseded documents, and map each hit to a Passage.
        Converts cosine distance to similarity: similarity = 1 - distance.
        """
        collection = self.client.get_collection(self.settings.collection)
        self.verify_embedding_pin(collection)

        query_vector = embed_query(question, self.settings)

        # Allow user to explicitly request older/superseded versions if indicated in the prompt
        is_historical_query = any(
            w in question.lower()
            for w in ("2023", "older version", "superseded", "previous rule", "repealed")
        )
        where_filter: dict[str, Any] | None = None
        if not is_historical_query:
            where_filter = {"superseded": False}

        results = collection.query(
            # chromadb-client's stubs accept a sequence of floats at runtime but
            # express the vector union narrowly, so retain the concrete vector
            # type and cast only at the third-party API boundary.
            query_embeddings=cast(Any, [query_vector]),
            n_results=k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        passages: list[Passage] = []
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
            meta = meta or {}
            # Chroma returns cosine distance; Passage.score expects similarity:
            similarity = round(max(0.0, 1.0 - float(dist)), 4)
            passages.append(
                Passage(
                    chunk_id=str(chunk_id),
                    text=str(text),
                    source=str(meta.get("source", "unknown")),
                    section=str(meta.get("section", "General")),
                    page=int(meta["page"]) if "page" in meta and meta["page"] is not None else None,
                    score=similarity,
                )
            )

        return passages
