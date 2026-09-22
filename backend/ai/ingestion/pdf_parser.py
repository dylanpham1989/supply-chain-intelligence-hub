from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ai.ingestion.base import ParsedDoc, ParsedPage, Parser, PermanentError

MAX_PAGES = 200
MAX_TOTAL_CHARS = 2_000_000
# Below this a page is probably a scan or a table pypdf could not read.
THIN_PAGE_CHARS = 30


class PdfParser(Parser):
    def parse(self, path: Path) -> ParsedDoc:
        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError, ValueError) as exc:
            raise PermanentError(f"cannot read pdf: {exc}") from exc

        if reader.is_encrypted:
            raise PermanentError("pdf is password protected")

        total = len(reader.pages)
        if total > MAX_PAGES:
            raise PermanentError(f"pdf has {total} pages, the limit is {MAX_PAGES}")

        pages: list[ParsedPage] = []
        thin_pages: list[int] = []
        chars = 0

        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # pypdf raises a wide range on damaged pages
                raise PermanentError(f"cannot read page {index}: {exc}") from exc

            chars += len(text)
            if chars > MAX_TOTAL_CHARS:
                raise PermanentError("pdf text exceeds the size limit")

            if len(text.strip()) < THIN_PAGE_CHARS:
                thin_pages.append(index)
            pages.append(ParsedPage(page_no=index, text=text))

        if pages and len(thin_pages) == len(pages):
            # Say so plainly rather than index an empty document and let the
            # answers be silently useless.
            raise PermanentError(
                "no selectable text found; the pdf looks scanned and OCR is not supported"
            )

        return ParsedDoc(
            pages=pages,
            meta={"page_count": total, "thin_pages": thin_pages},
        )


def extract_tables(path: Path, page_numbers: list[int]) -> dict[int, list[list[list[str]]]]:
    """pdfplumber is slow, around a second a page, so only thin pages get it."""
    if not page_numbers:
        return {}

    import pdfplumber

    tables: dict[int, list[list[list[str]]]] = {}
    with pdfplumber.open(str(path)) as pdf:
        for number in page_numbers:
            if number > len(pdf.pages):
                continue
            found = pdf.pages[number - 1].extract_tables() or []
            cleaned = [[[cell or "" for cell in row] for row in table] for table in found if table]
            if cleaned:
                tables[number] = cleaned
    return tables
