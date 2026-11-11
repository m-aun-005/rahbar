"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from .models import Document, Page

# Patterns for repeated running headers and footers
_PAGE_NUM_PAT = re.compile(
    r"^\s*(?:Page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|\b\d+\b)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_HEADER_PAT = re.compile(
    r"^\s*(?:FAST-NUCES|National University of Computer and Emerging Sciences|"
    r"FAST\s+National\s+University|Academic Rules and Regulations Handbook|"
    r"Student Handbook 2026|Undergraduate Rules)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_URL_BANNER_PAT = re.compile(
    r"^\s*https?://(?:www\.)?nu\.edu\.pk[^\s]*\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _clean_page_text(raw_text: str) -> str:
    """Applies cleaning rules while strictly preserving section headings, clause numbers,

    and markdown tables.
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Remove page number lines
    text = _PAGE_NUM_PAT.sub("", text)

    # 2. Remove running institution banners and header stamps
    text = _HEADER_PAT.sub("", text)
    text = _URL_BANNER_PAT.sub("", text)

    # 3. Normalize horizontal whitespace (tabs, consecutive spaces) without mangling newlines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]

    # 4. Collapse 3+ consecutive newlines into 2 (preserving paragraph breaks)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and

    section boundaries, because chunking and citations depend on them.

    DELIBERATELY PRESERVED:
    - Numbered clause identifiers (e.g., '1.21', 'Clause 5.4')
    - Markdown table lines (containing '|')
    - Heading demarcations ('#', '##', 'Section', 'Policy')
    - Bullet points and lettered lists ('-', '*', 'a)')
    """
    cleaned_pages: list[Page] = []
    for page in doc.pages:
        cleaned_text = _clean_page_text(page.text)
        cleaned_pages.append(
            Page(
                source=page.source,
                page=page.page,
                text=cleaned_text,
                ocr=page.ocr,
            )
        )

    return Document(
        source=doc.source,
        doc_version=doc.doc_version,
        superseded=doc.superseded,
        pages=cleaned_pages,
    )
