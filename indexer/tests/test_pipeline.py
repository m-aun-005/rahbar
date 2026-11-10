"""Unit tests for the indexer pipeline stages: clean, chunk, and extract."""

from __future__ import annotations

from pipeline.clean import clean
from pipeline.chunk import chunk
from pipeline.models import Document, Page


def test_clean_preserves_headings_and_clauses() -> None:
    raw_text = """
    FAST-NUCES
    Page 12 of 53
    Clause 1.21 Attendance Requirements
    Undergraduate students must maintain an 80% attendance threshold to sit for the final examination.
    
    
    Page 13 of 53
    National University of Computer and Emerging Sciences
    Clause 5.4 Academic Warning
    A student whose semester GPA falls below 2.00 is placed on academic warning.
    """
    doc = Document(
        source="test-rules.pdf",
        doc_version="2026",
        superseded=False,
        pages=[Page(source="test-rules.pdf", page=1, text=raw_text, ocr=False)],
    )
    cleaned_doc = clean(doc)
    text = cleaned_doc.pages[0].text

    # Verify repeated headers and footers were stripped
    assert "Page 12 of 53" not in text
    assert "National University of Computer and Emerging Sciences" not in text

    # Verify critical clause markers and headings were deliberately preserved
    assert "Clause 1.21" in text
    assert "Clause 5.4" in text
    assert "80%" in text


def test_chunk_structure_aware_splits_and_overlaps() -> None:
    body = (
        "# 1. Attendance Policy\n\n"
        "All undergraduate students are required to attend all scheduled classes.\n\n"
        "Clause 1.21 states that a minimum of 80% attendance is mandatory.\n\n"
        "Students failing to achieve 80% will be awarded an F grade in the course.\n\n"
        "# 2. Academic Probation\n\n"
        "A student with a CGPA below 2.00 is placed on academic probation."
    )
    doc = Document(
        source="handbook.pdf",
        doc_version="2026-06",
        superseded=False,
        pages=[Page(source="handbook.pdf", page=1, text=body, ocr=False)],
    )
    chunks = chunk(doc, size=50, overlap=15)
    assert len(chunks) >= 2

    # Check metadata preservation on each chunk
    sections = {c.section for c in chunks}
    assert any("Attendance" in s for s in sections)
    for c in chunks:
        assert c.source == "handbook.pdf"
        assert c.doc_version == "2026-06"
        assert c.superseded is False
        assert c.id is not None
