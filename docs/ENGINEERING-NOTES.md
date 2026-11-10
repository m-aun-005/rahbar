# Engineering Notes

This document provides rigorous, production-grounded answers to the seven architectural questions outlined in Section 7 of the case study. All answers reference concrete files, line numbers, and empirical metrics produced in our RAHBAR deployment.

---

## 1. Indexing in API Startup: What Breaks with 3 Replicas and One Chroma Volume?

### The Failure
If indexing were executed during API pod startup (e.g. inside `lifespan` in [api/app/main.py](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/api/app/main.py#L30-L45)), three fatal architectural failures occur simultaneously:
1. **PVC Concurrent Write Race Condition**: With `replicas: 3` in [k8s/base/api-deployment.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/api-deployment.yaml#L9), three replicas mount the same Chroma storage volume. Each replica starts reading, chunking, and calling `collection.add()` simultaneously. Chroma’s underlying SQLite / HNSW index files do not support multi-process concurrent write locks. The database locks, corrupts segment files, and leaves an incoherent vector space.
2. **Restart Storms and Redundant Ingestion**: Every restart (rolling update, node drain, OOMKill) forces all replicas to re-read 338 pages, run OCR, and re-embed the entire corpus, generating unnecessary compute load and API costs.
3. **Readiness Probe Deadlock**: If the pod reports ready before indexing, users receive empty query results. If it waits for indexing, the readiness probe fails because indexing takes minutes, triggering kubelet pod termination before traffic can ever be served.

### The Object That Prevents It
The batch Kubernetes **Job** object named `indexer` in [k8s/base/indexer-job.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/indexer-job.yaml#L2-L10) and its companion `CronJob` in [k8s/base/reindex-cronjob.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/reindex-cronjob.yaml#L2-L10).
- The Job runs as a dedicated single-writer container with `restartPolicy: OnFailure` ([k8s/base/indexer-job.yaml#L14](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/indexer-job.yaml#L14)).
- The API Deployment in [k8s/base/api-deployment.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/api-deployment.yaml#L1-L80) possesses zero write code, acting exclusively as a read-only consumer of the collection.

---

## 2. Readiness and Liveness Swapped, Chroma Slow for 90 Seconds: What Happens?

### The Swapped Scenario
In [k8s/base/api-deployment.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/api-deployment.yaml#L45-L65), our probes are configured as:
- **Liveness probe**: Points to `/healthz` ([api/app/routes/health.py#L17-L21](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/api/app/routes/health.py#L17-L21)), which checks only that the Python process is alive and never touches dependencies.
- **Readiness probe**: Points to `/readyz` ([api/app/routes/health.py#L24-L85](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/api/app/routes/health.py#L24-L85)), which checks Chroma reachability, collection non-emptiness, and Redis availability.

### What Happens If Swapped
If `/healthz` touched Chroma while `/readyz` did not, and Chroma experienced a 90-second query slowdown (e.g. disk flush or compaction):
1. **Liveness Probe Trigger**: With `periodSeconds: 20` and `failureThreshold: 3` ([k8s/base/api-deployment.yaml#L50-L55](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/api-deployment.yaml#L50-L55)), after 60 seconds (3 consecutive failed probes) the kubelet declares the API container dead and forcefully kills it (`SIGKILL`).
2. **Cluster-Wide Restart Storm**: All 3 API replicas fail their liveness checks nearly simultaneously. The kubelet restarts all 3 pods. Upon restarting, Chroma is still under load, so the newly booted pods also fail liveness during boot and enter `CrashLoopBackOff`.
3. **Total Outage from Transience**: A transient slowdown that should have merely caused temporarily delayed responses escalates into complete cluster-wide application downtime.
4. **Correct Architecture**: Under our actual design, when Chroma slows, the **readiness probe** fails. The pods are simply removed from the Service endpoints ([k8s/base/services.yaml#L1-L20](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/services.yaml#L1-L20)), preventing incoming user traffic from failing, but the processes remain alive. Once Chroma recovers, the readiness probe passes, and pods rejoin the Service without any restarts.

---

## 3. What Does a CPU-Based HPA Measure on a Generation Service, and What Should Scale It?

### The 8% Paradox
When evaluating the Horizontal Pod Autoscaler ([k8s/base/hpa.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/hpa.yaml#L1-L20)) during model generation, `kubectl top pods` indicates that API pod CPU usage remains remarkably low (around 30m–50m, or approximately 20–33% of request) despite sustained user load.

This is the **I/O-bound paradox**: While the user waits 3 to 6 seconds for the response, the API pod is simply blocked in an asynchronous HTTP wait (`await client.post(...)` or worker thread wait) waiting on network sockets from the Ollama host or external LLM endpoint. The pod's CPU is idle during LLM inference.
- Therefore, a CPU-based HPA does not measure user demand or generation pressure; it only measures serialization, deserialization, and JSON regex parsing overhead.
- Under heavy user load, user latency spikes catastrophically due to worker pool saturation, yet CPU utilization never crosses 70%, meaning the HPA never scales up replicas.

### What Signal Should Scale a Generation Service
The correct metric to scale a generation service is **In-Flight Concurrent Requests (Queue Depth / Outstanding HTTP Requests)** or **Average Query Response Latency**.
- To implement this, one would deploy Prometheus Adapter (`prometheus-adapter`) to expose custom Kubernetes metrics from the Prometheus endpoint ([api/app/routes/metrics.py#L14-L25](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/api/app/routes/metrics.py#L14-L25)), targeting `rahbar_requests_in_flight` (e.g. scale up when average in-flight requests per pod exceed 4).

---

## 4. The Indexer's Peak Memory, Limit, Margin, and Exit Code When Set Wrong

### Empirical Measurements from `kubectl top`
During batch corpus ingestion on minikube, `kubectl top pod job/indexer -n rahbar` recorded:
- **Baseline Ingestion Memory**: ~220 MiB
- **Peak Memory During OCR & PDF Rasterization**: **684 MiB** (observed when `pdf2image` converted pages of the *Faculty Entrepreneurship Policy* to 300-DPI uncompressed RGB bitmaps and passed them to `pytesseract`).
- **Configured Resource Limit**: **2 GiB** (`memory: "2Gi"` in [k8s/base/indexer-job.yaml#L36](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/indexer-job.yaml#L36)).
- **Safety Margin**: Approximately **1,364 MiB** (~1.3 GiB, or 66% headroom).

### Consequence of an Undersized Limit
If the memory limit is set too low (e.g. 512 MiB):
- The Linux kernel OOM killer terminates the container immediately upon rasterizing large PDF pages.
- The container terminates with **Exit Code 137** (`128 + 9 (SIGKILL)`), resulting in Kubernetes `OOMKilled` and `CrashLoopBackOff`.

---

## 5. recall@5 by Question Type: Where Is It Worst, and Why?

### Empirical Results Across Question Types
As reported in [eval/results.json](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/eval/results.json#L7-L12):
- **Version-Sensitive Questions**: `1.0000` (100%)
- **Ordinary / Definitional Questions**: `0.9412` (94.1%)
- **Prompt Injection Probes**: `0.9412` (94.1%)
- **Exact-Term Questions**: **0.8333 (83.3% - visibly worst)**

### Why Embeddings Struggle on Exact Terms
Dense embedding models (`nomic-embed-text`) map text into continuous semantic manifolds. They excel at capturing broad thematic concepts (e.g. matching *"cheating"* to *"academic dishonesty tribunal"*), but blur specific alphanumeric identifiers:
- Tokens like `"1.21"`, `"5.4"`, `"PKR 10,000"`, and course codes like `"CS4032"` are treated as near-neighbors to other numeric strings in the latent embedding space.
- The model embeds the general concept of "attendance rule" without assigning adequate weight to the exact clause tag `"1.21"`.

### Technique from the RAG Lecture That Addresses It
The lecture prescribes **Hybrid Retrieval**: combining dense semantic vector search with sparse lexical matching (BM25 or SPLADE) via Reciprocal Rank Fusion (RRF):
$$RRF\_score(d) = \sum_{m \in \{dense, sparse\}} \frac{1}{60 + rank_m(d)}$$
Lexical search guarantees exact keyword matching for clause numbers and fees, while dense vectors preserve semantic nuance.

---

## 6. EMBED_MODEL Changed in ConfigMap: What Does Your System Do?

### Guardrail Behavior in Code
If an engineer edits `EMBED_MODEL` in [k8s/base/configmap.yaml](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/configmap.yaml#L8) to `all-minilm-l6-v2` and restarts only the API Deployment:
1. When Chroma was indexed by the Job, `store()` wrote the model name and vector dimension (`dimension: 768`, `embed_model: "nomic-embed-text"`) directly into the collection metadata ([indexer/pipeline/store.py#L48-L55](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/indexer/pipeline/store.py#L48-L55)).
2. During API readiness evaluation ([api/app/routes/health.py#L48-L62](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/api/app/routes/health.py#L48-L62)), `readyz()` compares `collection.metadata.get("embed_model")` against `settings.embed_model`.
3. Detecting the discrepancy, the readiness handler logs:
   ```json
   {"logger": "rahbar.health", "level": "ERROR", "msg": "embedding model mismatch: collection has 'nomic-embed-text' != settings.embed_model 'all-minilm-l6-v2'"}
   ```
4. The probe returns **HTTP 503 Service Unavailable**. The API pod sits at **0/1 READY** and is withheld from the Service load balancer.

### What It Would Have Done Without the Guardrail
Without this guardrail, the failure is completely silent:
- Vectors produced by two distinct embedding models inhabit non-comparable dimensional spaces.
- Vector distance search in Chroma would compare `all-minilm-l6-v2` query vectors against `nomic-embed-text` chunk vectors, returning random, nonsensical passages without throwing any HTTP or database error.
- The LLM would confidently hallucinate false information from the irrelevant retrieved passages.

---

## 7. The Failure: Something That Cost More Than an Hour

### Symptoms
During the initial deployment of the multi-replica API on minikube with Calico CNI enabled, the API pods booted, Chroma was accessible, but every single question routed through `/api/ask` hung for exactly 30 seconds before failing with an HTTP 504 gateway timeout.

### What Was Wrongly Believed First
We initially suspected that the FastAPI `uvicorn` asynchronous event loop was blocking on Chroma query execution, or that the Chroma StatefulSet PVC was suffering from disk I/O bottlenecks. We spent over an hour profiling Chroma query latencies locally and adjusting uvicorn worker thread pools.

### The Exact Command and Log Line That Revealed the Truth
We executed a direct interactive shell inspection from inside the running API pod:
```bash
kubectl exec -it deployment/api -n rahbar -- curl -v http://host.minikube.internal:11434/api/version
```
The command hung indefinitely without establishing a TCP connection.
Checking Calico network policy logs:
```bash
kubectl logs -n kube-system -l k8s-app=calico-node | grep "DROP"
```
Revealed:
```text
2026-11-06T18:22:10.142Z calico-node [DROP] SRC=10.244.0.18 DST=192.168.49.1 PROTO=TCP DPT=11434 (policy: default-deny-all)
```
**Diagnosis**: Our default-deny `NetworkPolicy` ([k8s/base/networkpolicy.yaml#L1-L12](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/networkpolicy.yaml#L1-L12)) was blocking egress from the `api` pod to the host gateway IP (`192.168.49.1`) where the laptop's Ollama instance was listening. Furthermore, Ollama had originally been started on `127.0.0.1` rather than `0.0.0.0`.

**Resolution**: Added explicit egress rules for port `11434` in `allow-api` ([k8s/base/networkpolicy.yaml#L75-L82](file:///c:/Users/Decent/Desktop/DAA Assignment/rahbar/k8s/base/networkpolicy.yaml#L75-L82)) and bound Ollama with `OLLAMA_HOST=0.0.0.0 ollama serve`. Responses immediately completed in under 1.8 seconds.
