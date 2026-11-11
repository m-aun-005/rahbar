# RAHBAR Failure Mode Analysis

In distributed AI engineering, fluency is not factuality, and silent degradations are catastrophic. To validate RAHBAR's observability and fault-isolation architecture, we deliberately broke four of the six pipeline stages one at a time, analyzed the symptoms from telemetry and logs, and verified the remedy.

As emphasized in the RAG lecture: **only Stage F is the language model's fault; always diagnose stages A through E first.**

---

## 1. Stage A · Extraction Failure

### 1.1 What We Broke
In `indexer/pipeline/extract.py`, we disabled the OCR branch (`pytesseract` and `pdf2image`) when extracting text from scanned documents, forcing the extractor to rely solely on native PDF text extraction. We then re-indexed the corpus containing the image-only *Faculty Entrepreneurship and Technical Start-ups Policy* (`27.pdf?20220530`).

### 1.2 Symptom
When asking: *"What equity share does the university retain under the Faculty Technical Start-ups Policy?"*, the system failed to answer and honestly declined (`answered_from_context: false`), or served a generic hallucination if the relevance floor was bypassed. In `eval/run_eval.py`, `recall@5` for policy questions dropped from 1.00 to 0.00.

### 1.3 Diagnosis (As If Not Caused on Purpose)
1. First checked indexer logs:
   ```bash
   kubectl logs job/indexer -n rahbar | grep "27.pdf"
   ```
   Log revealed: `{"msg": "chunked", "source": "27.pdf", "chunks": 1}`. A 8-page official policy produced only one empty stub chunk of 0 characters.
2. Inspected the document font table:
   ```bash
   pdffonts corpus/raw/27.pdf
   ```
   The font list was completely empty.
3. Inspected Prometheus metrics:
   `rahbar_abstentions_total` increased monotonically for all queries regarding entrepreneurship.
4. Concluded: The PDF had no embedded text layer. Extraction silently dumped an empty string because the OCR stage was omitted.

### 1.4 Remedy
Restored automated OCR fallback in `extract.py`:
```python
if len(page_text.strip()) < 20:
    images = convert_from_path(str(file_path), first_page=idx, last_page=idx)
    page_text = pytesseract.image_to_string(images[0])
```
Re-running the indexer Job generated 24 high-density text chunks from the scanned document, restoring `recall@5` to 1.00.

---

## 2. Stage B · Chunking Failure

### 2.1 What We Broke
In `indexer/pipeline/chunk.py`, we replaced structure-aware heading-based splitting with a naive, fixed-size window of 100 tokens with **0 overlap** (`size=100`, `overlap=0`), discarding section boundary awareness.

### 2.2 Symptom
On complex queries involving definitions and multi-clause rules (e.g. *"What are the ethical guidelines for Generative AI in programming assignments, and what exceptions exist?"*), the model began generating answers missing critical exceptions. Golden set `recall@5` plummeted from **0.9286 down to 0.5714**.

### 2.3 Diagnosis (As If Not Caused on Purpose)
1. Examined retrieval telemetry in the API structured logs:
   ```json
   {"logger": "rahbar.answer", "msg": "answered", "chunk_ids": ["doc-p12-04-a1b2", ...], "scores": [0.68, 0.64, 0.61]}
   ```
   Inspecting chunk `doc-p12-04-a1b2` in Chroma revealed that the sentence began mid-definition: *"tools are strictly prohibited unless the instructor..."*, while the preceding chunk ended with *"For all undergraduate computing courses, Generative AI..."*. The condition and the rule were cleaved across chunk boundaries.
2. In `eval/run_eval.py`, exact clause matching failed because clause identifiers were separated from their operative paragraphs.

### 2.4 Remedy
Reinstated structure-aware hierarchical chunking with a 400-token budget and 50-token overlap:
```python
doc = clean(extract(str(path), doc_version, superseded))
pieces = chunk(doc, size=400, overlap=50)
```
This ensured that headings, clause numbers, and full conditional statements remained bound together within single retrieval chunks.

---

## 3. Stage C · Retrieval & Embedding Pin Failure

### 3.1 What We Broke
We changed `EMBED_MODEL` in `k8s/base/configmap.yaml` from `nomic-embed-text` to `all-minilm-l6-v2`, restarted the API Deployment with `kubectl rollout restart deployment/api -n rahbar`, and **deliberately did not re-index Chroma**.

### 3.2 Symptom
The API pod refused to take user traffic and sat at `0/1 READY`. The service was withheld from the Kubernetes Ingress, and no incoming user requests were routed to the broken deployment.

### 3.3 Diagnosis (As If Not Caused on Purpose)
1. Queried pod status:
   ```bash
   kubectl get pods -n rahbar
   # Output: api-7b89d8975b-4x2lm   0/1   Running   0   45s
   ```
2. Inspected pod events and readiness probe failure:
   ```bash
   kubectl describe pod api-7b89d8975b-4x2lm -n rahbar
   # Warning: Unhealthy: Readiness probe failed: HTTP probe failed with statuscode: 503
   ```
3. Queried the readiness endpoint and API container logs:
   ```bash
   curl -s http://localhost:8000/readyz
   # Response: {"status":"not ready","failed_dependencies":["embed_model mismatch (nomic-embed-text != all-minilm-l6-v2)"]}
   ```
   API application log:
   ```json
   {"logger": "rahbar.retrieval.chroma", "level": "ERROR", "msg": "EMBED_MODEL mismatch: index was built with 'nomic-embed-text' but API is configured with 'all-minilm-l6-v2'"}
   ```
   **Why this guardrail matters**: Without this check, the API would have reported ready, embedded user queries with `all-minilm-l6-v2` (384 dimensions) while Chroma held 768-dimensional `nomic-embed-text` vectors. Vector search would have silently returned random nonsense passages without throwing any errors, and the LLM would have hallucinated plausibly-sounding falsehoods to end users.

### 3.4 Remedy
Realigned `EMBED_MODEL` in `configmap.yaml` back to `nomic-embed-text` and executed `kubectl rollout restart deployment/api -n rahbar`. The readiness probe immediately verified that collection metadata matched the application pin, and all 3 replicas returned to `1/1 READY`.

---

## 4. Stage E · Source Versioning Failure

### 4.1 What We Broke
In `api/app/retrieval/chroma.py`, we commented out the metadata filter `where={"superseded": False}`, allowing the retriever to return chunks from both current and superseded documents indiscriminately.

### 4.2 Symptom
When asked: *"What is the minimum attendance required to sit the final examination?"*, the system answered: *"The minimum attendance requirement is 75% [Undergraduate Academic Rules (Aug 2023) / 1.14]"*.
This was an outright factual hallucination regarding current university policy: the 2023 rule (75%) was repealed and superseded by the 2026 Handbook (Clause 1.21, mandating 80%).

### 4.3 Diagnosis (As If Not Caused on Purpose)
1. Run evaluation harness:
   ```bash
   python eval/run_eval.py --api http://rahbar.local
   ```
   Failed check: Question `q09` (`version` type) expected `"80%"`, but the response text contained `"75%"`.
2. Checked retrieved context IDs in the structured JSON log:
   ```json
   {"logger": "rahbar.answer", "msg": "answered", "chunk_ids": ["Academic-Rules-Undergrad-Aug-2023-p12-01-...", ...], "scores": [0.912, 0.898]}
   ```
   The older 2023 chunk achieved a slightly higher cosine similarity score (0.912) than the current 2026 chunk (0.898) because the wording of the prompt happened to match the older phrasing closer.
3. Vector similarity search is inherently agnostic to legal validity and timeline; it retrieves text solely by lexical-semantic proximity. Prompt instructions alone cannot reliably force the LLM to ignore a retrieved repealed rule when both chunks are present in the context.

### 4.4 Remedy
Restored metadata filtering at the retriever query boundary:
```python
is_historical = any(w in question.lower() for w in ("2023", "older version", "superseded", "repealed"))
where_filter = None if is_historical else {"superseded": False}
results = collection.query(query_embeddings=[query_vec], n_results=k, where=where_filter)
```
Repealed clauses are strictly excluded from the retrieved candidate pool by default, guaranteeing that only current binding regulations reach the model context.
