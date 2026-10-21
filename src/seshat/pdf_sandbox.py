"""Ephemeral Docker resource barrier for already admitted PDF bytes.

Docker daemon and the reviewed image remain trusted host components. A nonroot
container UID alone does not establish a rootless daemon or source rights.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import threading
import time
import uuid
from typing import Literal

from seshat.contracts import RawAccessPolicy, SourceAccessStatus
from seshat.pdf_page_evidence import MAX_PDF_BYTES, PdfPageEvidenceReceipt
from seshat.runtime import RuntimeSourceAccess

_PIN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:\-]*@sha256:[0-9a-f]{64}$")
_TEST_TAG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:\-]*:[a-zA-Z0-9._\-]+$")
MAX_OUTPUT = 8192
MAX_EXCERPT = 4096


class PdfSandboxError(RuntimeError):
    """Safe failure code; never includes input, parser output or stderr."""

    def __init__(self, code: Literal[
        "TIMEOUT", "MEMORY_LIMIT", "PROCESS_CRASH", "UNSUPPORTED_SANDBOX",
        "UNREADABLE_SOURCE", "EXTRACTOR_TEXT_LIMIT",
    ]) -> None:
        super().__init__(code)
        self.code = code


def _preflight(image: str, *, test_only: bool) -> None:
    if not isinstance(image, str) or not (
        _TEST_TAG.fullmatch(image) if test_only else _PIN.fullmatch(image)
    ):
        raise PdfSandboxError("UNSUPPORTED_SANDBOX")
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{json .}}"],
            capture_output=True, timeout=10, check=True,
        )
        if len(info.stdout) > 65536 or len(info.stderr) > 4096:
            raise ValueError("unbounded preflight")
        details = json.loads(info.stdout)
        if details.get("OSType") != "linux":
            raise ValueError("Linux containers required")
        inspected = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}}"],
            capture_output=True, timeout=10, check=True,
        )
        if len(inspected.stdout) > 65536 or len(inspected.stderr) > 4096:
            raise ValueError("unbounded image preflight")
        digests = json.loads(inspected.stdout)
        if not test_only and image not in digests:
            raise ValueError("image digest unavailable locally")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
        raise PdfSandboxError("UNSUPPORTED_SANDBOX") from None


def _run_container(image: str, payload: bytes, *, timeout_seconds: float) -> bytes:
    name = f"seshat-pdf-{uuid.uuid4().hex}"
    argv = [
        "docker", "run", "--rm", "-i", "--pull", "never", "--name", name,
        "--network", "none",
        "--read-only", "--user", "65532:65532", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "32",
        "--memory", "256m", "--memory-swap", "256m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m", image,
        "python", "-m", "seshat.pdf_sandbox_worker",
    ]
    process = None
    failed = True
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
        )
        output = bytearray()
        stderr = bytearray()
        overflow = threading.Event()

        def read_bounded(pipe, target: bytearray) -> None:
            while chunk := pipe.read(4096):
                if len(target) + len(chunk) > MAX_OUTPUT:
                    overflow.set()
                    return
                target.extend(chunk)

        def write_payload() -> None:
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except OSError:
                pass

        threads = [
            threading.Thread(target=read_bounded, args=(process.stdout, output), daemon=True),
            threading.Thread(target=read_bounded, args=(process.stderr, stderr), daemon=True),
            threading.Thread(target=write_payload, daemon=True),
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout_seconds
        while any(thread.is_alive() for thread in threads) or process.poll() is None:
            if overflow.is_set():
                raise PdfSandboxError("PROCESS_CRASH")
            if time.monotonic() >= deadline:
                raise PdfSandboxError("TIMEOUT")
            time.sleep(0.01)
        if overflow.is_set():
            raise PdfSandboxError("PROCESS_CRASH")
        if process.returncode == 137:
            raise PdfSandboxError("MEMORY_LIMIT")
        if process.returncode != 0:
            raise PdfSandboxError("PROCESS_CRASH")
        failed = False
        return bytes(output)
    except OSError:
        raise PdfSandboxError("UNSUPPORTED_SANDBOX") from None
    finally:
        if failed:
            if process is not None and process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            # docker client death does not guarantee container death. The name
            # is generated by this process and never derived from source data.
            try:
                subprocess.run(
                    ["docker", "rm", "--force", name],
                    capture_output=True, timeout=5, check=False,
                )
                remaining = subprocess.run(
                    ["docker", "ps", "-a", "--filter", f"name=^/{name}$",
                     "--format", "{{.Names}}"],
                    capture_output=True, timeout=5, check=True,
                )
                if remaining.stdout.strip():
                    raise PdfSandboxError("UNSUPPORTED_SANDBOX")
            except (OSError, subprocess.SubprocessError):
                raise PdfSandboxError("UNSUPPORTED_SANDBOX") from None


def check_pdf_page_excerpt_sandboxed(
    source_access: RuntimeSourceAccess,
    carrier_id: str,
    *,
    page_number: int,
    expected_excerpt: str,
    image: str,
    timeout_seconds: float = 15,
    test_only: bool = False,
) -> PdfPageEvidenceReceipt:
    """Return owner-private hash receipt; fail closed if Docker isolation fails.

    ``test_only`` permits a reviewed local image tag for invented fixtures only.
    Production callers must supply an externally pinned image digest.
    """
    if (
        source_access.policy is not RawAccessPolicy.FULL_REQUIRED
        or not isinstance(carrier_id, str) or not 0 < len(carrier_id) <= 256
        or type(page_number) is not int or page_number < 1
        or not isinstance(expected_excerpt, str)
        or not 0 < len(expected_excerpt) <= MAX_EXCERPT
        or not isinstance(timeout_seconds, (int, float))
        or not 0 < timeout_seconds <= 60
    ):
        raise PdfSandboxError("UNREADABLE_SOURCE")
    _preflight(image, test_only=test_only)
    try:
        pdf, declared, actual, version, full = source_access.read_full_with_metadata(carrier_id)
        digest = hashlib.sha256(pdf).hexdigest()
        if (
            declared != "application/pdf" or actual != "application/pdf"
            or full.status is not SourceAccessStatus.VERIFIED
            or full.read_kind != "FULL" or full.carrier_id != carrier_id
            or full.source_version != version or full.content_sha256 != digest
            or full.byte_length != len(pdf) or not 0 < len(pdf) <= MAX_PDF_BYTES
            or not pdf.startswith(b"%PDF-")
        ):
            raise PdfSandboxError("UNREADABLE_SOURCE")
    except Exception:  # noqa: BLE001 - never leak source-provider exception text
        raise PdfSandboxError("UNREADABLE_SOURCE") from None
    full_digest = hashlib.sha256(json.dumps(
        full.model_dump(mode="json", exclude_none=True), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    payload = json.dumps({
        "pdf_b64": base64.b64encode(pdf).decode("ascii"),
        "carrier_id": carrier_id, "source_version": version,
        "page_number": page_number, "expected_excerpt": expected_excerpt,
    }, separators=(",", ":")).encode("utf-8")
    raw = _run_container(image, payload, timeout_seconds=timeout_seconds)
    if len(raw) > MAX_OUTPUT:
        raise PdfSandboxError("PROCESS_CRASH")
    try:
        fields = json.loads(raw)
        if isinstance(fields, dict) and fields.get("error") == "EXTRACTOR_TEXT_LIMIT":
            raise PdfSandboxError("EXTRACTOR_TEXT_LIMIT")
        if not isinstance(fields, dict) or "source_access_full_receipt_sha256" in fields:
            raise ValueError("invalid response")
        receipt = PdfPageEvidenceReceipt.model_validate({
            **fields, "source_access_full_receipt_sha256": full_digest,
        })
        if (
            receipt.carrier_id != carrier_id or receipt.source_version != version
            or receipt.pdf_sha256 != digest or receipt.pdf_byte_length != len(pdf)
            or receipt.page_number != page_number
            or receipt.excerpt_sha256 != hashlib.sha256(expected_excerpt.encode()).hexdigest()
            or receipt.length != len(expected_excerpt)
            or receipt.extractor_name != "pypdf" or receipt.extractor_version != "6.21.1"
            or receipt.source_access_policy != "FULL_REQUIRED"
        ):
            raise ValueError("receipt binding mismatch")
        return receipt
    except PdfSandboxError:
        raise
    except Exception:  # noqa: BLE001 - child data and errors are untrusted
        raise PdfSandboxError("PROCESS_CRASH") from None
