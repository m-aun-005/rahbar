# ADR 0003: Redis as Persistent Semantic Cache Store

## Status
Accepted · 2026-11-04

## Context
Production question-answering systems experience significant read latency (2 to 5 seconds per query) during vector retrieval and language model generation. An effective semantic cache intercepts repeated or semantically equivalent questions, returning verified answers with sub-10ms response times.

The cache store requires:
1. Low-latency persistence across pod restarts and rolling updates.
2. Fast vector similarity matching or key-value retrieval.
3. Clean cache invalidation semantics when re-indexing occurs.
4. Strict never-cache enforcement for abstentions and follow-up queries.

## Decision
We select **Redis** (`redis:7.4-alpine`) deployed as a Kubernetes Deployment with a 2 GiB PersistentVolumeClaim (`k8s/base/redis-deployment.yaml`) as the primary semantic cache store, backed by an in-memory fallback.

Key architectural behaviors:
1. **Cosine Similarity Threshold**: Configured at `cache_threshold = 0.90` in `k8s/base/configmap.yaml`. This was chosen empirically as the lowest threshold with zero false positives.
2. **Never-Cache Guardrails**: The cache layer (`api/app/services/cache.py`) strictly declines to store:
   - Follow-up questions containing pronominal ambiguities (`it`, `they`, `above`).
   - Honest abstentions (`answered_from_context: false`).
   - Responses generated via the canned schema-failure fallback.
3. **Invalidation on Re-index**: The indexer Job invokes `invalidate_cache()` immediately after successfully writing to Chroma, flushing Redis (`FLUSHDB`) to ensure stale answers are never served over updated policy documents.

## Options Considered
1. **Secondary ChromaDB Collection for Cache**: Rejected due to unnecessary write overhead and lock contention on vector indexes when frequently inserting new user query vectors.
2. **Local In-Memory Cache on API Pods**: Rejected because an in-memory dictionary does not share state across the 3 API replicas, causing cache misses when requests balance across different pods, and vanishes entirely on rolling restarts.
3. **Dedicated Redis Instance with PVC (Chosen)**: Delivers sub-millisecond lookups, cluster-wide cache sharing across all 3 API replicas, and atomic cache flushing.

## Consequences
- **Positive**: Eliminates redundant LLM generation cycles, reducing cluster CPU load and hosted API billing.
- **Negative**: Adds a Redis service and persistent volume to the Kubernetes cluster architecture, requiring a readiness dependency check in `/readyz`.
