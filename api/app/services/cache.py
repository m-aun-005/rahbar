"""Semantic cache implementation for RAHBAR (section 3.3).

Uses Redis for persistence across pod restarts, with a local in-memory fallback.
Matches incoming queries using cosine similarity against cached question embeddings.
Strictly implements never-cache rules: follow-ups, abstentions, and fallback responses
are never stored or served from cache.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any
import redis

from ..config import Settings
from ..retrieval.chroma import embed_query
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class SemanticCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.threshold = settings.cache_threshold
        self._memory_cache: list[dict[str, Any]] = []
        self._redis_client: Any = None

        if settings.enable_cache:
            try:
                self._redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    socket_timeout=1.0,
                    decode_responses=True,
                )
                self._redis_client.ping()
            except Exception:
                self._redis_client = None

    def invalidate_cache(self) -> None:
        """Flushes the semantic cache upon index rebuild."""
        self._memory_cache.clear()
        if self._redis_client is not None:
            try:
                self._redis_client.flushdb()
                log.info("semantic cache invalidated successfully")
            except Exception as exc:
                log.warning("failed to flush redis cache", extra={"error": str(exc)})

    def clear_cache(self) -> None:
        self.invalidate_cache()

    def is_followup(self, question: str) -> bool:
        """Determines if a question is a contextual follow-up, which must skip cache."""
        follow_up_tokens = {"it", "they", "them", "that", "those", "above", "mentioned", "previous"}
        words = set(question.lower().split())
        return bool(words.intersection(follow_up_tokens)) and len(words) < 7

    def lookup(self, question: str) -> AskResponse | None:
        """Checks for a semantic cache hit with similarity >= settings.cache_threshold."""
        if not self.settings.enable_cache or self.is_followup(question):
            return None

        query_vec = embed_query(question, self.settings)

        # Check Redis entries first
        if self._redis_client is not None:
            try:
                keys = self._redis_client.keys("cache:q:*")
                best_sim = -1.0
                best_resp_json = None

                for k in keys:
                    raw = self._redis_client.get(k)
                    if not raw:
                        continue
                    entry = json.loads(raw)
                    cached_vec = entry.get("embedding", [])
                    sim = cosine_similarity(query_vec, cached_vec)
                    if sim > best_sim:
                        best_sim = sim
                        best_resp_json = entry.get("response")

                if best_sim >= self.threshold and best_resp_json:
                    log.info("semantic cache hit in redis", extra={"similarity": round(best_sim, 4)})
                    return AskResponse.model_validate(best_resp_json)
            except Exception as exc:
                log.warning("redis cache lookup failed, falling back to memory", extra={"error": str(exc)})

        # Check memory cache fallback
        best_sim = -1.0
        best_resp = None
        for entry in self._memory_cache:
            sim = cosine_similarity(query_vec, entry["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_resp = entry["response"]

        if best_sim >= self.threshold and best_resp is not None:
            log.info("semantic cache hit in memory", extra={"similarity": round(best_sim, 4)})
            return best_resp

        return None

    def store(self, question: str, response: AskResponse) -> None:
        """Stores entry only if it passes never-cache safety rules."""
        # Never-cache rules: never cache follow-ups, abstentions, or fallbacks
        if not self.settings.enable_cache:
            return
        if self.is_followup(question):
            return
        if not response.answered_from_context:
            return
        if response.confidence == "low":
            return
        if "canned fallback" in response.answer.lower():
            return

        query_vec = embed_query(question, self.settings)
        resp_data = response.model_dump()

        entry = {
            "question": question,
            "embedding": query_vec,
            "response": resp_data,
        }

        # Store in Redis
        if self._redis_client is not None:
            try:
                key = f"cache:q:{hash(question)}"
                self._redis_client.set(key, json.dumps(entry), ex=86400)
            except Exception:
                pass

        # Also store in local memory
        self._memory_cache.append(
            {"question": question, "embedding": query_vec, "response": response}
        )
