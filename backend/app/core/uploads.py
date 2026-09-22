import csv
import re
from uuid import UUID

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import BadRequestError, PayloadTooLargeError
from app.models.enums import DocType

CHUNK_BYTES = 1024 * 1024
PDF_MAGIC = b"%PDF-"
SNIFF_BYTES = 8192

EXTENSIONS = {DocType.CONTRACT: ".pdf", DocType.INVOICE: ".pdf", DocType.MANIFEST: ".csv"}
CONTENT_TYPES = {".pdf": "application/pdf", ".csv": "text/csv"}


async def read_and_validate(upload: UploadFile, doc_type: DocType) -> tuple[bytes, str]:
    """Read the upload, size-capped, and check what it actually is.

    The declared content type is whatever the client felt like sending, so a pdf
    has to start with %PDF- and a csv has to parse as one.
    """
    data = bytearray()
    while chunk := await upload.read(CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise PayloadTooLargeError(
                f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB"
            )
    await upload.seek(0)

    if not data:
        raise BadRequestError("File is empty")

    extension = EXTENSIONS[doc_type]
    if extension == ".pdf":
        if not bytes(data[:5]) == PDF_MAGIC:
            raise BadRequestError("File is not a valid pdf")
    else:
        _require_csv(bytes(data[:SNIFF_BYTES]))

    return bytes(data), CONTENT_TYPES[extension]


def _require_csv(head: bytes) -> None:
    try:
        text = head.decode("utf-8", errors="replace")
        csv.Sniffer().sniff(text, delimiters=",;\t|")
    except csv.Error as exc:
        raise BadRequestError("File does not look like a csv") from exc


def build_key(tenant_id: UUID, document_id: UUID, doc_type: DocType) -> str:
    """Server-generated. The client's filename never reaches the object store."""
    return f"{tenant_id}/{document_id}{EXTENSIONS[doc_type]}"


def safe_filename(name: str | None) -> str:
    cleaned = re.sub(r"[^\w.\- ]", "_", (name or "upload").strip())[:255]
    return cleaned or "upload"
