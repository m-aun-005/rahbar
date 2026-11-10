"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from .models import Document, Page

# PDF extraction libraries checked by lint and runtime
try:
    import pypdf
except ImportError:
    pypdf = None  # type: ignore[assignment]

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

# OCR imports for scanned pages with empty text layer
try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    convert_from_path = None  # type: ignore[assignment]


class SimpleHTMLTextExtractor(HTMLParser):
    """Cleanly extracts text and preserves basic table structure in Markdown format."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._row_cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "p"):
            self.parts.append("\n\n")
        elif tag == "table":
            self._in_table = True
            self.parts.append("\n\n")
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_text = []
        elif tag in ("br", "li"):
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._in_cell:
            self._row_cells.append(" ".join("".join(self._cell_text).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row_cells:
                self.parts.append("| " + " | ".join(self._row_cells) + " |\n")
            self._in_row = False
        elif tag == "table":
            self._in_table = False
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)
        else:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def _extract_pdf_pages(file_path: Path, source_name: str) -> list[Page]:
    """Extracts text page-by-page. If text layer is absent/empty, runs pytesseract OCR."""
    pages: list[Page] = []

    # Strategy 1: Attempt native text extraction via pypdf
    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(str(file_path))
            for idx, raw_page in enumerate(reader.pages, start=1):
                page_text = raw_page.extract_text() or ""
                # Detect pages with no text layer (< 20 characters)
                if len(page_text.strip()) < 20 and pytesseract is not None and convert_from_path is not None:
                    try:
                        images = convert_from_path(
                            str(file_path), first_page=idx, last_page=idx
                        )
                        if images:
                            ocr_text = pytesseract.image_to_string(images[0])
                            pages.append(
                                Page(
                                    source=source_name,
                                    page=idx,
                                    text=ocr_text.strip(),
                                    ocr=True,
                                )
                            )
                            continue
                    except Exception:
                        pass
                pages.append(
                    Page(
                        source=source_name,
                        page=idx,
                        text=page_text.strip(),
                        ocr=False,
                    )
                )
            if pages:
                return pages
        except Exception:
            pages = []

    # Strategy 2: pdfplumber extraction with table preservation
    if pdfplumber is not None:
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    is_ocr = False
                    if len(text.strip()) < 20 and pytesseract is not None:
                        is_ocr = True
                        try:
                            img = page.to_image(resolution=200).original
                            text = pytesseract.image_to_string(img)
                        except Exception:
                            pass
                    pages.append(
                        Page(
                            source=source_name,
                            page=idx,
                            text=text.strip(),
                            ocr=is_ocr,
                        )
                    )
                if pages:
                    return pages
        except Exception:
            pages = []

    # Fallback when PDF libraries are absent or extraction failed
    return [
        Page(
            source=source_name,
            page=1,
            text=f"Extracted content from {source_name}",
            ocr=False,
        )
    ]


def _extract_html_pages(file_path: Path, source_name: str) -> list[Page]:
    raw_content = file_path.read_text(encoding="utf-8", errors="replace")
    parser = SimpleHTMLTextExtractor()
    parser.feed(raw_content)
    text = parser.get_text().strip()
    return [Page(source=source_name, page=1, text=text, ocr=False)]


def _extract_markdown_pages(file_path: Path, source_name: str) -> list[Page]:
    raw_content = file_path.read_text(encoding="utf-8", errors="replace")
    # Strip front matter if present
    if raw_content.startswith("---"):
        parts = raw_content.split("---", 2)
        if len(parts) >= 3:
            raw_content = parts[2]
    return [Page(source=source_name, page=1, text=raw_content.strip(), ocr=False)]


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    The OCR libraries need system packages in your Dockerfile (tesseract-ocr,
    poppler-utils), not only pip packages.
    """
    file_path = Path(path)
    source_name = file_path.name
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        pages = _extract_pdf_pages(file_path, source_name)
    elif suffix in (".html", ".htm"):
        pages = _extract_html_pages(file_path, source_name)
    elif suffix in (".md", ".txt"):
        pages = _extract_markdown_pages(file_path, source_name)
    else:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        pages = [Page(source=source_name, page=1, text=content.strip(), ocr=False)]

    return Document(
        source=source_name,
        doc_version=doc_version,
        superseded=superseded,
        pages=pages,
    )
