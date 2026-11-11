# ADR 0001: Vector Ingestion as an Independent Batch Job

## Status
Accepted · 2026-11-02

## Context
A question-answering RAG service operating on a production Kubernetes cluster requires an indexed vector store in ChromaDB. In early laptop prototypes, indexing is often executed during application startup inside FastAPI's `lifespan` hook. 

However, running indexing during API startup across a production deployment with 3 replicas introduces fatal architectural race conditions:
1. **PVC Write Contention**: The 3 concurrent API pods race to write simultaneously to a single shared persistent volume claim attached to Chroma. Multiple concurrent writers corrupt collection metadata and produce inconsistent vector spaces.
2. **Cascade Restart Storms**: Any pod restart (triggered by an OOMKill, node drain, configuration reload, or rolling deployment) would trigger the entire corpus extraction and embedding pipeline anew, incurring massive compute delays and Ollama token costs.
3. **Dishonest Readiness**: If the pod reports ready before indexing completes, it serves empty retrievals and false abstentions. If readiness waits for indexing, the probe times out, causing Kubernetes to kill the pod in a `CrashLoopBackOff`, effectively swapping healthy old pods with unbootable new ones.
4. **Configuration Coupling**: It becomes impossible to re-index changed policy documents without rebuilding and redeploying the API container image (the "Friday failure" from Lecture 05).

## Decision
We decouple indexing completely from the API lifecycle. Ingestion is executed exclusively as an independent, one-shot Kubernetes `Job` (`k8s/base/indexer-job.yaml`) and scheduled via a weekly `CronJob` (`k8s/base/reindex-cronjob.yaml`).

The API Deployment (`k8s/base/api-deployment.yaml`) operates strictly as a read-only client. The API's readiness probe (`/readyz`) verifies that Chroma is reachable and that the collection exists and is non-empty (`collection.count() > 0`). If the index does not exist, the API simply reports not ready (HTTP 503) and is withheld from the Service load balancer until the indexer Job successfully finishes.

Manual re-indexing is triggered on-demand with zero API downtime:
```bash
kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar
```

## Options Considered
1. **Indexing during FastAPI startup hook**: Rejected due to multi-replica write race conditions, readiness probe timeouts, and coupled deployments.
2. **Kubernetes InitContainer on API pods**: Rejected because each of the 3 API replicas would still execute the init container simultaneously against the single Chroma volume on every rollout or replica scaling event.
3. **Decoupled batch Job and CronJob (Chosen)**: Guarantees single-writer isolation, allows fine-grained batch resource allocations (2 GiB memory limit), and enables re-indexing without touching running API pods.

## Consequences
- **Positive**: Complete write-isolation on the vector database; 3 API replicas can scale horizontally without touching disk writes; zero-downtime rolling updates.
- **Positive**: The API image remains lightweight, omitting heavy PDF OCR binaries and Poppler libraries.
- **Negative / Operational Watch**: When spinning up a fresh cluster from scratch, the indexer Job must complete before the API Deployment becomes ready. This order must be explicitly documented in the deployment guide.
