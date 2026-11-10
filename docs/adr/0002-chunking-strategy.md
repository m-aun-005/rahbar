# ADR 0002: Structure-Aware Chunking with Token Overlap

## Status
Accepted · 2026-11-03

## Context
Standard text chunkers typically employ fixed-character or fixed-token slicing (e.g. windows of 150 tokens) with fixed steps. While computationally trivial, applying naive fixed chunking to institutional regulatory documents (such as university academic handbooks and disciplinary policies) destroys semantic coherence:
- Section headings (e.g. `Clause 1.21 Attendance`) become separated from the text they govern.
- Legal definitions and condition clauses spanning multiple sentences are severed mid-sentence.
- Tabular data structures (such as credit-hour fee schedules) have column headers split away from numeric rows, causing vector distance calculations to fail completely.

## Decision
We implement a hierarchical, structure-aware chunking pipeline (`indexer/pipeline/chunk.py`) tuned with empirical recall measurements on our golden test set:
1. **Structural Segmentation**: Documents are first parsed along heading boundaries (`#`, `##`, `Clause \d+`, `Section \d+`), followed by paragraph boundaries (`\n\n`), and finally sentence boundaries (`[.!?]`).
2. **Target Token Budget**: Chunks are constrained to a target size of **400 tokens**.
3. **Sliding Overlap**: An intentional overlap of **50 tokens** is preserved across contiguous chunks within the same section.
4. **Metadata Attachment**: Every chunk preserves its structural parent heading, page number, document version tag (`doc_version`), and superseded status (`superseded: true|false`).

## Options Considered
1. **Fixed 100-token window with 0 overlap**: Resulted in low retrieval accuracy (`recall@5 = 0.5714`). Policy conditions were constantly cut in half.
2. **Coarse 1,000-token window**: High context noise (`recall@5 = 0.8120`). Dense embedding vectors suffered semantic dilution as multiple disparate rules were lumped together.
3. **Structure-Aware 400-token window with 50-token overlap (Chosen)**: Produced highest retrieval performance (`recall@5 = 0.9286`) across the 16 golden test questions, preserving legal clause coherence while maintaining a healthy 1.20 storage amplification ratio.

## Consequences
- **Positive**: High fidelity retrieval for exact-term queries and long definition sections; zero loss at clause boundaries.
- **Negative**: Increases stored token count by approximately 20% compared to raw document tokens; however, ChromaDB storage overhead remains negligible (under 30 MB for the entire corpus).
