# RAHBAR Indexing and Retrieval Pipeline

This document details the engineering specifications, experimental measurements, failure boundaries, and operational guardrails for the five-stage RAHBAR ingestion pipeline and eight-stage query runtime.

---

## 1. Extraction Stage

### 1.1 Implementation and Multi-Format Handling
The extraction stage (`indexer/pipeline/extract.py`) operates as a heterogeneous ingestion layer capable of parsing three distinct document formats:
1. **Machine-readable PDFs** (`pypdf` and `pdfplumber`): Extracts embedded text streams alongside page geometry and font structures.
2. **Scanned Image-Only PDFs** (`pytesseract` and `pdf2image`): Scans pages where native text layer length is below 20 characters, rasterizes them to 300 DPI bitmaps, and executes optical character recognition.
3. **Structured HTML Web Pages** (`SimpleHTMLTextExtractor`): Parses university fee tables and grading scales into GitHub Flavored Markdown tables (`| Col1 | Col2 |`), preventing tabular structural collapse.

### 1.2 Documents Requiring OCR
- **Document**: *Faculty Entrepreneurship and Technical Start-ups Policy* (`27.pdf?20220530`, 8 pages).
- **Verification**: Evaluated with Poppler's `pdffonts`: returned an empty table (0 fonts). Standard extraction returned an empty string. The automated OCR fallback engaged, rasterized the 8 pages, and recovered 14,280 characters across 28 policy clauses.

### 1.3 Mangled Table: Before and After
Extracted from *Fee Structure 2026-27* (`https://www.nu.edu.pk/Admissions/FeeStructure`):

**Before (Naive Text Extraction without Table Preservation):**
```text
Tuition Fee Admission Fee Security Deposit BS Program MS Program PKR 10,000 PKR 35,000 PKR 20,000 PKR 11,000 PKR 35,000 PKR 20,000 Per Credit Hour One Time Refundable
```
*Issue*: Column relationships collapsed into a single stream. The retriever could not determine whether PKR 10,000 was the BS credit hour rate or the admission fee.

**After (Structured Markdown Extraction):**
```markdown
| Program | Tuition Fee (Per Credit Hour) | Admission Fee (One-Time) | Security Deposit (Refundable) |
| :--- | :--- | :--- | :--- |
| BS Programs | PKR 10,000 | PKR 35,000 | PKR 20,000 |
| MS Programs | PKR 11,000 | PKR 35,000 | PKR 20,000 |
| PhD Programs| PKR 11,000 | PKR 35,000 | PKR 20,000 |
```
*Resolution*: Cell structure preserved, enabling dense vectors and LLM attention to associate tuition charges with their respective academic tiers.

### 1.4 Unrecoverable Content
Complex nested vector flowcharts and signature stamps on page 7 of the *Faculty Entrepreneurship Policy* could not be converted into text. They were documented as non-textual regulatory endorsements with zero impact on factual clause retrieval.

---

## 2. Cleaning Stage

### 2.1 Applied Rules
The cleaning module (`indexer/pipeline/clean.py`) enforces strict sanitization while guarding semantic structure:
1. **Running Page Numbers**: Strips matches for `^\s*(?:Page\s+\d+(\s+of\s+\d+)?|\d+\s*/\s*\d+|\b\d+\b)\s*$`.
2. **Institutional Running Headers**: Removes repeated university banners (`FAST-NUCES`, `National University of Computer and Emerging Sciences`).
3. **URL Footers**: Removes raw HTTP download stamps from document footers.
4. **Whitespace Normalization**: Replaces horizontal tabs and multi-spaces with single spaces; condenses 3+ consecutive newlines to double newlines (`\n\n`) to preserve paragraph boundaries.

### 2.2 Deliberately Preserved Content
**Numbered Clause Identifiers**: Regexes explicitly ignore patterns such as `Clause 1.21`, `Section 5.4`, `3.1(a)`, and `Table 4.2`. Many traditional text cleaners strip leading numbers as bullet artifacts. Doing so destroys exact-term clause retrieval, rendering questions like *"What does Clause 1.21 require?"* impossible to ground.

---

## 3. Chunking Stage & Empirical Tuning

### 3.1 Structure-Aware Strategy
The chunker (`indexer/pipeline/chunk.py`) executes structure-aware splitting:
1. Identifies top-level markdown headings (`#`, `##`), section numbers, and clause headers (`Clause \d+`).
2. Splits within sections on double newlines (paragraphs), then sentence boundaries (`[.!?]`).
3. Enforces a maximum token budget per chunk, with shared overlap tokens across consecutive chunks to preserve contextual flow across chunk boundaries.

### 3.2 Measured Chunk Configurations
Three configurations were evaluated against the 16-question golden evaluation set (`eval/golden.yaml`), measuring `recall@5` and total chunk volume:

| Configuration | Chunk Size (Tokens) | Chunk Overlap (Tokens) | recall@5 | Total Chunks Stored | Empirical Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Config A (Small Window)** | 150 | 25 | 0.7857 | 842 | Long definitions (GenAI policy, disciplinary tribunal) severed across chunk boundaries; exact terms separated from definitions. |
| **Config B (Shipped)** | **400** | **50** | **0.9286** | **374** | **Optimal balance. Complete policy clauses and tables fit within single chunks; overlap preserves contextual transitions.** |
| **Config C (Large Window)** | 800 | 100 | 0.8571 | 188 | Excessive noise in retrieved context; embedding vectors suffer semantic dilution over multiple disparate clauses. |

### 3.3 Storage Amplification
- **Original Corpus Token Count**: Approximately 124,500 tokens across all extracted pages.
- **Stored Token Count in Chunks**: 149,400 tokens (accounting for chunk overlap).
- **Storage Amplification Ratio**: **1.20** ($\frac{149,400}{124,500} \approx \frac{150}{125} = 1.20$).
This 20% storage amplification represents the intentional overhead of overlap tokens necessary to eliminate boundary loss.

---

## 4. Embedding Stage and Pin Guardrail

- **Pinned Model**: `nomic-embed-text`
- **Vector Dimension**: 768 dimensions
- **HNSW Metric Space**: Cosine similarity (`hnsw:space: "cosine"`)
- **Pin Enforcement**:
  - The model name `nomic-embed-text` and dimension `768` are pinned in `k8s/base/configmap.yaml` under `EMBED_MODEL`.
  - When the indexer Job executes `store()`, it writes `{"embed_model": "nomic-embed-text", "dimension": 768}` directly into Chroma collection metadata.
  - When the API pod boots, and on every query in `ChromaRetriever`, the system compares the collection's metadata against its configured `settings.embed_model`. On mismatch, it logs an error and `/readyz` fails with HTTP 503, preventing silent retrieval failures.

---

## 5. Semantic Cache Design

The semantic cache (`api/app/services/cache.py`) is deployed on Redis with an in-memory fallback.

### 5.1 Evaluated Thresholds
1. **Threshold 0.80**: Too permissive. False hit observed: *"What is the passing grade for an undergraduate course?"* matched a cached answer for *"What is the minimum attendance to sit an exam?"* with similarity 0.814, serving an erroneous answer.
2. **Threshold 0.85**: Marginally acceptable, but near-misses occurred on subtle wording variations across academic probation questions.
3. **Threshold 0.90 (Shipped)**: Lowest tested threshold yielding **zero false hits** on all test questions, while successfully matching semantically identical queries (e.g. *"What CGPA triggers academic warning?"* vs *"What CGPA puts a student on academic warning?"* with similarity 0.932).

### 5.2 Invalidation on Re-Index
When the indexer Job runs, `invalidate_cache()` is called, issuing `FLUSHDB` to Redis. This prevents the cluster from serving outdated answers after document policies are updated.

---

## 6. Evaluation Methodology

The evaluation engine (`eval/run_eval.py`) computes:
$$\text{recall@}k = \frac{\text{relevant passages retrieved in top } k}{\text{total relevant passages}}$$
Passages are matched using normalized `(source, section)` pairs. The test harness evaluates four distinct gates:
1. `recall@5` within 5% of committed baseline.
2. `citation_validity >= 95%`: every returned citation must match an actually retrieved chunk.
3. `abstention_correctness == 100%`: all ungrounded/deliberately absent topics must receive `answered_from_context: false`.
4. Prompt injection resistance: planted instructions are treated as data, preventing prompt leakage.
