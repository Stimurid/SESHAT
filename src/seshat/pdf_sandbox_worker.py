"""One-shot container worker. Never invoke this module on untrusted bytes outside a sandbox."""

from __future__ import annotations

import base64
import hashlib
import json
import sys

from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.pdf_page_evidence import PdfPageEvidenceError, check_pdf_page_excerpt
from seshat.runtime import RuntimeSourceAccess

MAX_SANDBOX_PDF_BYTES = 8 * 1024 * 1024
MAX_ENVELOPE = 12 * 1024 * 1024
MAX_EXCERPT = 4096


class _Provider:
    def __init__(self, content: SourceContent) -> None:
        self.content = content

    def open_content(self, carrier_id: str) -> SourceContent:
        if carrier_id != self.content.carrier_id:
            raise ValueError("carrier mismatch")
        return self.content


def _run(data: bytes) -> dict[str, object]:
    request = json.loads(data)
    if not isinstance(request, dict) or set(request) != {
        "pdf_b64", "carrier_id", "source_version", "page_number", "expected_excerpt"
    }:
        raise ValueError("invalid envelope")
    carrier_id = request["carrier_id"]
    version = request["source_version"]
    page = request["page_number"]
    excerpt = request["expected_excerpt"]
    if (
        not isinstance(carrier_id, str) or not 0 < len(carrier_id) <= 256
        or not isinstance(version, str) or not 0 < len(version) <= 256
        or type(page) is not int or page < 1
        or not isinstance(excerpt, str) or not 0 < len(excerpt) <= MAX_EXCERPT
        or not isinstance(request["pdf_b64"], str)
    ):
        raise ValueError("invalid fields")
    pdf = base64.b64decode(request["pdf_b64"], validate=True)
    if not 0 < len(pdf) <= MAX_SANDBOX_PDF_BYTES:
        raise ValueError("invalid PDF size")
    digest = hashlib.sha256(pdf).hexdigest()
    carrier = SourceCarrier(
        carrier_id=carrier_id, source_identity="sandbox-local-copy", version=version,
        media_type="application/pdf", content_sha256=digest, byte_length=len(pdf),
    )
    content = SourceContent(
        carrier_id=carrier_id, source_version=version, media_type="application/pdf",
        content=pdf, content_sha256=digest, byte_length=len(pdf), complete=True,
        authorized=True,
    )
    access = RuntimeSourceAccess(
        policy=RawAccessPolicy.FULL_REQUIRED, carriers=(carrier,),
        content_provider=_Provider(content), carrier_ids=(carrier_id,),
    )
    receipt = check_pdf_page_excerpt(
        access, carrier_id, page_number=page, expected_excerpt=excerpt,
    )
    # The child copy's local F07 receipt is not a rights assertion. Parent replaces it.
    return receipt.model_dump(
        mode="json", exclude={"source_access_full_receipt_sha256", "sandbox_child_observation_provenance"},
    )


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_ENVELOPE + 1)
        if len(data) > MAX_ENVELOPE:
            raise ValueError("envelope too large")
        result = _run(data)
        encoded = json.dumps(result, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 8192:
            raise ValueError("receipt too large")
        sys.stdout.buffer.write(encoded)
        return 0
    except PdfPageEvidenceError as exc:
        if exc.code == "PATHOLOGICAL_SIZE":
            sys.stdout.buffer.write(b'{"error":"EXTRACTOR_TEXT_LIMIT"}')
            return 0
        sys.stdout.buffer.write(b'{"error":"NOT_VERIFIED"}')
        return 0
    except Exception:  # noqa: BLE001 - never print a parser exception or input
        sys.stdout.buffer.write(b'{"error":"NOT_VERIFIED"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
