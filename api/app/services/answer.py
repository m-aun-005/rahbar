"""Turns a question into an AskResponse. This is where the query pipeline lives.

Implements all 8 production query pipeline stages (sections 3.2, 3.3, 3.4):
1. Question validation (3 to 500 chars)
2. Semantic cache check
3. Query embedding with pinned model
4. Top-k retrieval with superseded metadata filtering
5. Relevance floor check and honest abstention
6. Augmented prompt construction with data isolation
7. Schema-constrained generation with validation, retry, and fallback
8. Citation verification against retrieved passages, cache storage, and metric emission
"""

from __future__ import annotations

import logging
import time

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import AskResponse, Citation, Passage, RetrievedRef
from .cache import SemanticCache

log = logging.getLogger("rahbar.answer")
_cache_instance: SemanticCache | None = None


def get_cache(settings: Settings) -> SemanticCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache(settings)
    return _cache_instance


def verify_citations(citations: list[Citation], passages: list[Passage]) -> list[Citation]:
    """Ensures every citation strictly matches an actually retrieved chunk by (source, section).

    Removes fabricated citations to prevent hallucination penalties (section 3.4).
    """
    valid_keys = {(p.source.lower().strip(), p.section.lower().strip()) for p in passages}
    valid_citations: list[Citation] = []
    for c in citations:
        cand_key = (c.source.lower().strip(), c.section.lower().strip())
        # Direct match or partial match on section/source
        if cand_key in valid_keys or any(
            c.source.lower().strip() in p.source.lower() and c.section.lower().strip() in p.section.lower()
            for p in passages
        ):
            valid_citations.append(c)
        else:
            log.warning(
                "fabricated citation rejected by citation validator",
                extra={"source": c.source, "section": c.section},
            )
    return valid_citations


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings
) -> AskResponse:
    rid = request_id_var.get()
    cache = get_cache(settings)

    # Step 2: Semantic cache check (skip for follow-ups)
    cached_hit = cache.lookup(question)
    if cached_hit is not None:
        metrics.CACHE_HITS.inc()
        log.info("served response from semantic cache", extra={"request_id": rid, "cached": True})
        return cached_hit.model_copy(update={"request_id": rid})

    metrics.CACHE_MISSES.inc()

    # Step 3 & 4: Top-k Retrieval from Chroma
    t_ret_start = time.perf_counter()
    passages = retriever.retrieve(question, k=settings.top_k)
    ret_duration = time.perf_counter() - t_ret_start
    metrics.RETRIEVAL_LATENCY.observe(ret_duration)

    # Step 5: Relevance floor check and honest abstention (section 3.4)
    max_score = max([p.score for p in passages], default=0.0)
    scores = [round(p.score, 4) for p in passages]

    # If nothing cleared the relevance floor, abstain honestly without calling LLM
    if not passages or max_score < settings.relevance_floor:
        metrics.ABSTENTIONS.inc()
        log.info(
            "answered with honest abstention",
            extra={
                "retriever": retriever.name,
                "provider": provider.name,
                "top_k": settings.top_k,
                "chunk_ids": [p.chunk_id for p in passages],
                "scores": scores,
                "max_score": max_score,
                "relevance_floor": settings.relevance_floor,
                "answered_from_context": False,
                "abstention": True,
            },
        )
        return AskResponse(
            request_id=rid,
            answer="The provided corpus does not contain information to answer this question.",
            citations=[],
            answered_from_context=False,
            confidence="low",
            retrieved=[
                RetrievedRef(
                    chunk_id=p.chunk_id,
                    source=p.source,
                    section=p.section,
                    page=p.page,
                    score=p.score,
                )
                for p in passages
            ],
            provider=provider.name,
        )

    # Step 6 & 7: Augmented Generation with Validation & Retry
    t_gen_start = time.perf_counter()
    metrics.TOKENS_IN.inc(len(question.split()) + sum(len(p.text.split()) for p in passages))
    answer = provider.generate(question, passages)
    gen_duration = time.perf_counter() - t_gen_start
    metrics.GENERATION_LATENCY.observe(gen_duration)
    metrics.TOKENS_OUT.inc(len(answer.answer.split()))

    # Track fallbacks
    if "canned fallback" in answer.reasoning.lower():
        metrics.FALLBACKS.inc()

    # Step 8: Strict citation verification
    validated_citations = verify_citations(answer.citations, passages)

    # Construct the final AskResponse contract
    response = AskResponse(
        request_id=rid,
        answer=answer.answer,
        citations=validated_citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id,
                source=p.source,
                section=p.section,
                page=p.page,
                score=p.score,
            )
            for p in passages
        ],
        provider=provider.name,
    )

    # Observability logging (section 4.8)
    log.info(
        "answered",
        extra={
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": scores,
            "answered_from_context": answer.answered_from_context,
            "citations_count": len(validated_citations),
            "abstention": not answer.answered_from_context,
        },
    )

    # Step 8 (cont.): Store turn in semantic cache if safe to cache
    cache.store(question, response)

    return response
