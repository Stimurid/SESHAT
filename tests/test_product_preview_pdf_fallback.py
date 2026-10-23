"""Synthetic PDF extractor-fallback tests for product preview intake.

All PDFs are invented in-memory fixtures. No private/original source bytes.
"""
from __future__ import annotations

import hashlib
import re
import sys
import types
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from seshat.product_preview import ingest_sources

_PAGE_BANNER_RE = re.compile(r"===\s*PAGE\s+\d+\s*===", re.IGNORECASE)
_FALLBACK_BODY = "SYNTHETIC_PYMUPDF_FALLBACK_BODY"
_PYPDF_BODY = "SYNTHETIC_PYPDF_BODY"


def _pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 10 260 Td ({text}) Tj ET".encode("latin-1"))
    stream_ref = writer._add_object(stream)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    page[NameObject("/Contents")] = stream_ref
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _ingest(tmp_path, raw: bytes) -> tuple[dict, str]:
    path = tmp_path / "carrier.pdf"
    path.write_bytes(raw)
    records = ingest_sources(
        {
            "sources": [{
                "source_id": "src-pdf", "study_id": "study-pdf",
                "source_kind": "D", "version": "1", "path": "carrier.pdf",
            }],
        },
        tmp_path,
    )
    return records[0], hashlib.sha256(raw).hexdigest()


def _install_fake_pymupdf(monkeypatch, body: str, pages: int = 1) -> None:
    fake = types.ModuleType("pymupdf")

    class _Page:
        def get_text(self) -> str:
            return body

    class _Doc:
        page_count = pages

        def __iter__(self):
            return iter([_Page() for _ in range(pages)])

        def close(self) -> None:
            return None

    fake.open = lambda *args, **kwargs: _Doc()
    monkeypatch.setitem(sys.modules, "pymupdf", fake)
    monkeypatch.setitem(sys.modules, "fitz", fake)


def _fail_pypdf_reader(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise UnicodeDecodeError("utf-16-be", b"3", 0, 1, "truncated data")

    monkeypatch.setattr("pypdf.PdfReader", _boom)


def _empty_pypdf_reader(monkeypatch) -> None:
    class _EmptyPage:
        def extract_text(self) -> str:
            return ""

    class _EmptyReader:
        def __init__(self, *args, **kwargs) -> None:
            self.pages = [_EmptyPage()]

    monkeypatch.setattr("pypdf.PdfReader", _EmptyReader)


def _hide_pymupdf(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pymupdf", None)
    monkeypatch.setitem(sys.modules, "fitz", None)


def test_ordinary_pypdf_pdf_keeps_page_markers_and_sha(tmp_path):
    record, digest = _ingest(tmp_path, _pdf_with_text(_PYPDF_BODY))
    assert record["status"] == "WORKS"
    assert record["text_extraction"] == "TEXT_EXTRACTED"
    assert record["byte_sha256"] == digest
    assert record["page_count"] == 1
    assert "=== PAGE 1 ===" in record["text"]
    assert _PYPDF_BODY in record["text"]


def test_pypdf_unicode_decode_error_falls_back_to_pymupdf(tmp_path, monkeypatch):
    _fail_pypdf_reader(monkeypatch)
    _install_fake_pymupdf(monkeypatch, _FALLBACK_BODY)
    record, digest = _ingest(tmp_path, _pdf_with_text(_PYPDF_BODY))
    assert record["status"] == "WORKS"
    assert record["text_extraction"] == "TEXT_EXTRACTED"
    assert record["byte_sha256"] == digest
    assert record["page_count"] == 1
    assert "=== PAGE 1 ===" in record["text"]
    assert _FALLBACK_BODY in record["text"]


def test_pypdf_empty_body_falls_back_to_pymupdf(tmp_path, monkeypatch):
    _empty_pypdf_reader(monkeypatch)
    _install_fake_pymupdf(monkeypatch, _FALLBACK_BODY)
    record, digest = _ingest(tmp_path, _pdf_with_text(_PYPDF_BODY))
    assert record["status"] == "WORKS"
    assert record["byte_sha256"] == digest
    assert _FALLBACK_BODY in record["text"]
    assert "=== PAGE 1 ===" in record["text"]
    body = _PAGE_BANNER_RE.sub(" ", record["text"])
    assert _FALLBACK_BODY in body


def test_parser_failure_preserves_sha_when_fallback_unavailable(tmp_path, monkeypatch):
    _fail_pypdf_reader(monkeypatch)
    _hide_pymupdf(monkeypatch)
    record, digest = _ingest(tmp_path, _pdf_with_text(_PYPDF_BODY))
    assert record["status"] == "PARTIAL"
    assert record["text_extraction"] == "FAILED"
    assert record["byte_sha256"] == digest
    assert record["byte_length"] == len(_pdf_with_text(_PYPDF_BODY))
    assert record["text"] == ""
    assert any("UnicodeDecodeError" in item for item in record["limitations"])


def test_blank_pdf_is_partial_without_invented_text(tmp_path, monkeypatch):
    _hide_pymupdf(monkeypatch)
    raw = _blank_pdf()
    record, digest = _ingest(tmp_path, raw)
    assert record["byte_sha256"] == digest
    assert record["status"] == "PARTIAL"
    assert record["text_extraction"] == "PARTIAL_NO_EXTRACTED_TEXT"
    body = _PAGE_BANNER_RE.sub(" ", record["text"])
    assert body.strip() == ""
