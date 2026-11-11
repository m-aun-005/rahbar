"""Prometheus metrics at /metrics (section 4.8).

Exposes request count, request latency, retrieval latency, generation latency,
cache hits/misses, abstention count, fallback count, and token counters.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter()

# Request counts and latencies
REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

RETRIEVAL_LATENCY = Histogram(
    "rahbar_retrieval_seconds",
    "Time spent in vector retrieval",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
GENERATION_LATENCY = Histogram(
    "rahbar_generation_seconds",
    "Time spent in LLM generation",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0),
)

# Semantic cache metrics
CACHE_HITS = Counter("rahbar_cache_hits_total", "Semantic cache hits")
CACHE_MISSES = Counter("rahbar_cache_misses_total", "Semantic cache misses")

# Quality & reliability metrics
ABSTENTIONS = Counter("rahbar_abstentions_total", "Requests where system abstained honestly")
FALLBACKS = Counter("rahbar_fallbacks_total", "Requests that triggered safe canned fallback")

# Token metrics
TOKENS_IN = Counter("rahbar_tokens_in_total", "Estimated prompt tokens sent to provider")
TOKENS_OUT = Counter("rahbar_tokens_out_total", "Estimated completion tokens from provider")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
