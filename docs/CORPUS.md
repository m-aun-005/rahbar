# RAHBAR Document Corpus Specification

## 1. Overview and Scale

The RAHBAR document corpus is assembled directly from the publicly accessible institutional repository of the National University of Computer and Emerging Sciences (FAST-NUCES, `nu.edu.pk`). Rather than an arbitrary set of clean text documents, the corpus was engineered deliberately to expose every classic failure mode of a Retrieval-Augmented Generation (RAG) system running on a production cluster.

- **Primary Source**: FAST-NUCES official website (`https://www.nu.edu.pk`)
- **Total Ingested Documents**: 9 documents (7 PDF documents, 2 structured HTML web captures)
- **Total Page Count**: 338 pages (substantially exceeding the minimum 40-page requirement)
- **Scale and Complexity**: The documents span multi-decade institutional policy shifts, scanned non-searchable circulars, dense multi-column tabular fee matrices, and intricate disciplinary codes.

---

## 2. Corpus Properties and Failure Mode Mapping

The table below documents how each required property maps to a concrete document, verified on 1 November 2026, and the specific RAG failure mode it makes reachable:

| # | Required Property | Document(s) Providing It | Verified Evidence & Metadata | RAG Failure Mode Exposed & Mitigated |
|---|---|---|---|---|
| **1** | **Scale**: At least 6 documents and 40 pages in total | Complete corpus (9 documents, 338 pages total) | `corpus/MANIFEST.md` lists all 9 documents with cryptographic SHA-256 digests. | Baseline evaluation scale; ensures realistic vector database ingestion times and memory footprints. |
| **2** | **Version Pair**: At least 2 documents that are different versions of the same policy | 1. *Undergraduate Academic Rules (Aug 2023)*<br>2. *Academic Rules Handbook (Jun 2026)* | `Undergraduate Academic Rules (Aug 2023)` has `doc_version: "2023-08"`, `superseded: true`.<br>`Academic Rules Handbook (Jun 2026)` has `doc_version: "2026-06"`, `superseded: false`. | **Failure Mode E (Outdated Source)**: Semantic similarity alone will retrieve the older 2023 rule because wording matches closely. Without explicit metadata filtering (`superseded: false`), the retriever quotes a repealed policy (e.g. 75% attendance instead of 80%). |
| **3** | **Scanned PDF**: At least 1 image-only PDF with no text layer | *Faculty Entrepreneurship and Technical Start-ups Policy* (`27.pdf?20220530`) | Verified using `pdffonts`: output yields an empty font table (`pdffonts 27.pdf` returns 0 fonts), proving the PDF is purely a scanned image raster. | **Failure Mode A (Bad Extraction)**: Standard PDF text extractors (`pypdf`, `pdfminer`) return 0 characters. If the extraction pipeline lacks OCR (`tesseract-ocr` / `pdf2image`), the document vanishes from the vector store without warning. |
| **4** | **Tabular Data**: At least 1 document with a table carrying real information | 1. *Fee Structure 2026-27* (HTML table)<br>2. *Grading Policy 2026* (HTML table)<br>3. *Annual Report 2019-20 & 2023-24* (Faculty & Grad tables) | HTML tables: Tuition fee per credit hour (PKR 10,000), admission fee (PKR 35,000), grading scale (A: 4.00, A-: 3.67, B+: 3.33, etc.). | **Failure Mode A (Mangled Extraction)**: Naive text extraction strips table column boundaries, interleaving header columns with row data. Markdown table preservation and structured HTML parsing preserve table cell relationships. |
| **5** | **Long Definitions**: At least 1 document with long definitions cut by fixed chunkers | *Student Handbook (Jun 2026)* (62 pages) | Contains multi-section Generative AI ethical guidelines, disciplinary tribunal procedures, and academic misconduct definitions spanning 1,200+ continuous words. | **Failure Mode B (Poor Chunks)**: A naive fixed-size chunker (e.g. 100 tokens) severs the premise of a legal definition from its exceptions and penalties. Structure-aware chunking keeps hierarchical sections intact. |
| **6** | **Deliberately Absent Topic**: Realistic topic intentionally omitted | *Hostel Accommodation and Transport Route Policies* | The *Student Handbook* mentions that hostel facilities exist, but the actual policy document (*Transport and Hostel Facilities*) is deliberately excluded from ingestion. | **Abstention Honesty**: A naive LLM hallucinates hostel booking rules, fees, and curfews. Grounded RAHBAR detects retrieval scores below the relevance floor (`relevance_floor = 0.35`) and declines honestly (`answered_from_context: false`). |
| **7** | **Exact-Term Content**: Exact clause numbers, codes, CGPA thresholds, fees | 1. *Academic Rules Handbook 2026* (Clause 1.21, Clause 5.4)<br>2. *Prospectus 2026* (Clause 1)<br>3. *Fee Structure 2026-27* (PKR 10,000 / cr.hr) | Attendance is designated as **Clause 1.21** in the Handbook but **Clause 1** in the Prospectus. Academic warning threshold is exactly **CGPA < 2.00**. | **Semantic Blur**: Dense embedding vectors blur exact clause numbers ("1.21" vs "5.4") into broad academic context vectors. Hybrid or exact-token preservation ensures accurate clause retrieval. |

---

## 3. Analysis of Specific Documents

### 3.1 The Version Pair (Failure Mode E)
The university updated its academic regulations between 2023 and 2026:
- Under the **2023 Academic Rules** (`doc_version: "2023-08"`, `superseded: true`), academic probation and warning rules allowed a different threshold (1.80 CGPA for initial semesters), and attendance requirements were set at 75%.
- In the **2026 Handbook** (`doc_version: "2026-06"`, `superseded: false`), Clause 1.21 establishes a strict 80% attendance mandate to be eligible for terminal examinations, and Clause 5.4 mandates an academic warning whenever a student's semester or cumulative CGPA drops below 2.00.

Because both documents exist in the public domain and share extensive vocabulary, dense embedding models score both passages with near-identical cosine similarity. RAHBAR resolves this deterministically by injecting metadata filters into Chroma queries (`where={"superseded": False}`), ensuring repealed regulations are excluded unless the user explicitly inquires about historical policies.

### 3.2 Scanned PDF Inspection (Failure Mode A)
The *Faculty Entrepreneurship and Technical Start-ups Policy* was inspected using standard Poppler utilities:
```bash
pdffonts corpus/raw/faculty-entrepreneurship.pdf
```
The resulting table had zero font descriptors. A standard text dump returned an empty string. RAHBAR's extraction stage flags any page yielding fewer than 20 characters as requiring optical character recognition, routing it to `pytesseract` via `pdf2image` with pre-processed binarization.

### 3.3 Deliberately Absent Topic (Section 3.4 Abstention)
When prospective students consult the university portal, one of the most common inquiries concerns on-campus hostel allotment, mess charges, and transport routes. By excluding the *Transport and Hostel Facilities* prospectus document while retaining the *Student Handbook* (which contains only a single passing remark: *"Hostel facilities are available for outstation students subject to availability"*), questions such as *"What are the hostel room allotment rules and monthly charges?"* cannot be answered from the corpus. RAHBAR enforces honest abstention:
```json
{
  "answer": "The provided corpus does not contain information to answer this question.",
  "citations": [],
  "answered_from_context": false,
  "confidence": "low"
}
```

---

## 4. Ingestion and Fetch Pipeline

The fetch tool `corpus/fetch.py` executes rate-limited, polite downloads with a 2.0-second delay between consecutive requests, utilizing an informative user-agent string. All source URLs and cryptographic SHA-256 digests are pinned in `corpus/MANIFEST.md` and configured via `corpus/sources.yaml`. The vector store indexer Job reads `corpus/raw/_index.json` to assign verified metadata tags to every extracted chunk.
