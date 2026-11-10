"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

import hashlib
import re
from .models import Chunk, Document

# Heading and section boundaries pattern
_HEADING_PAT = re.compile(
    r"^(?:#{1,6}\s+.+|(?:\d+\.){1,3}\d*\s+[A-Z].+|Clause\s+\d+(?:\.\d+)*.*|Section\s+\d+.*)$",
    re.MULTILINE,
)

# Sentence boundary pattern
_SENTENCE_PAT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _approx_tokens(text: str) -> int:
    """Approximates token count using character/word heuristic (1 token ~= 4 chars or 0.75 words)."""
    words = text.split()
    return max(1, int(len(text) / 4)) if len(text) > 0 else 0


def _split_into_sentences(text: str) -> list[str]:
    parts = _SENTENCE_PAT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_by_sections(page_text: str) -> list[tuple[str, str]]:
    """Splits text into (section_heading, section_body) pairs."""
    lines = page_text.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "General"
    current_body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _HEADING_PAT.match(stripped):
            if current_body_lines:
                body = "\n".join(current_body_lines).strip()
                if body:
                    sections.append((current_heading, body))
                current_body_lines = []
            current_heading = stripped.lstrip("#").strip()
        else:
            current_body_lines.append(line)

    if current_body_lines:
        body = "\n".join(current_body_lines).strip()
        if body:
            sections.append((current_heading, body))

    if not sections and page_text.strip():
        sections.append(("General", page_text.strip()))

    return sections


def _create_chunks_with_overlap(
    section_name: str,
    text: str,
    source: str,
    page_num: int,
    doc_version: str,
    superseded: bool,
    target_size: int,
    overlap: int,
    base_idx: int,
) -> tuple[list[Chunk], int]:
    """Structure-aware chunking within a section with token overlap."""
    chunks: list[Chunk] = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # Break paragraphs into atomic text units (sentences or small paragraphs)
    units: list[str] = []
    for para in paragraphs:
        if _approx_tokens(para) <= target_size:
            units.append(para)
        else:
            units.extend(_split_into_sentences(para))

    current_tokens = 0
    current_units: list[str] = []
    chunk_idx = base_idx

    for unit in units:
        unit_tokens = _approx_tokens(unit)
        if current_tokens + unit_tokens > target_size and current_units:
            # Emit current chunk
            chunk_text = "\n\n".join(current_units)
            chunk_hash = hashlib.sha256(
                f"{source}:{section_name}:{page_num}:{chunk_idx}".encode()
            ).hexdigest()[:12]
            chunk_id = f"{source[:10]}-p{page_num}-{chunk_idx}-{chunk_hash}"

            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=chunk_text,
                    source=source,
                    section=section_name,
                    page=page_num,
                    doc_version=doc_version,
                    superseded=superseded,
                )
            )
            chunk_idx += 1

            # Retain overlap units from the end of current_units
            overlap_units: list[str] = []
            overlap_tokens = 0
            for u in reversed(current_units):
                u_tok = _approx_tokens(u)
                if overlap_tokens + u_tok <= overlap:
                    overlap_units.insert(0, u)
                    overlap_tokens += u_tok
                else:
                    break

            current_units = list(overlap_units)
            current_tokens = overlap_tokens

        current_units.append(unit)
        current_tokens += unit_tokens

    if current_units:
        chunk_text = "\n\n".join(current_units)
        chunk_hash = hashlib.sha256(
            f"{source}:{section_name}:{page_num}:{chunk_idx}".encode()
        ).hexdigest()[:12]
        chunk_id = f"{source[:10]}-p{page_num}-{chunk_idx}-{chunk_hash}"
        chunks.append(
            Chunk(
                id=chunk_id,
                text=chunk_text,
                source=source,
                section=section_name,
                page=page_num,
                doc_version=doc_version,
                superseded=superseded,
            )
        )
        chunk_idx += 1

    return chunks, chunk_idx


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under

    `size` tokens, with `overlap` tokens shared between neighbours. Every chunk keeps
    the section heading it sits under, its page, doc_version and superseded.
    """
    all_chunks: list[Chunk] = []
    chunk_counter = 0

    for page in doc.pages:
        sections = _split_by_sections(page.text)
        for section_heading, section_text in sections:
            produced, chunk_counter = _create_chunks_with_overlap(
                section_name=section_heading,
                text=section_text,
                source=doc.source,
                page_num=page.page,
                doc_version=doc.doc_version,
                superseded=doc.superseded,
                target_size=size,
                overlap=overlap,
                base_idx=chunk_counter,
            )
            all_chunks.extend(produced)

    return all_chunks
