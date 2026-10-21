"""Synthetic PDF sandbox tests. Mocked subprocess tests do not prove OS isolation."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import seshat.pdf_sandbox as sandbox
from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.runtime import RuntimeSourceAccess


def _pdf() -> bytes:
    writer = PdfWriter()
    for word in ("Alpha", "Bravo"):
        page = writer.add_blank_page(width=300, height=300)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 18 Tf 10 250 Td ({word}) Tj ET".encode())
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): writer._add_object(font),
            }),
        })
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class _Provider:
    def __init__(self, content: SourceContent) -> None:
        self.content = content

    def open_content(self, carrier_id: str) -> SourceContent:
        return self.content


def _access(
    *, policy: RawAccessPolicy = RawAccessPolicy.FULL_REQUIRED,
    media: str = "application/pdf", authorized: bool = True,
    complete: bool = True,
) -> RuntimeSourceAccess:
    pdf = _pdf()
    digest = hashlib.sha256(pdf).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented", source_identity="invented", version="v1",
        media_type=media, content_sha256=digest, byte_length=len(pdf),
    )
    content = SourceContent(
        carrier_id="invented", source_version="v1", media_type=media,
        content=pdf, content_sha256=digest, byte_length=len(pdf),
        authorized=authorized, complete=complete,
    )
    return RuntimeSourceAccess(
        policy=policy, carriers=(carrier,), content_provider=_Provider(content),
        carrier_ids=("invented",),
    )


def _mocked_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "_preflight", lambda *_args, **_kwargs: None)


@pytest.mark.parametrize("policy", [RawAccessPolicy.NEVER, RawAccessPolicy.DRILLBACK])
def test_policy_denied_before_parser(monkeypatch, policy) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNREADABLE_SOURCE"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(policy=policy), "invented", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test", test_only=True,
        )


@pytest.mark.parametrize("kw", [
    {"media": "text/plain"}, {"authorized": False}, {"complete": False},
])
def test_unadmitted_source_denied(monkeypatch, kw) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNREADABLE_SOURCE"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(**kw), "invented", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test", test_only=True,
        )


def test_unpinned_image_refused_before_docker(monkeypatch) -> None:
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNSUPPORTED_SANDBOX"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )


def test_docker_absent_fails_closed(monkeypatch) -> None:
    def absent(*_args, **_kwargs):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(sandbox.subprocess, "run", absent)
    with pytest.raises(sandbox.PdfSandboxError, match="UNSUPPORTED_SANDBOX"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test", test_only=True,
        )


@pytest.mark.parametrize("raw", [b"not json", b'{"error":"NOT_VERIFIED"}', b"{}"])
def test_malformed_or_denied_child_response(monkeypatch, raw) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: raw)
    with pytest.raises(sandbox.PdfSandboxError, match="PROCESS_CRASH"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test", test_only=True,
        )


def test_child_stdout_cannot_escape_in_error(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: b"secret-quote")
    with pytest.raises(sandbox.PdfSandboxError) as caught:
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test", test_only=True,
        )
    assert str(caught.value) == "PROCESS_CRASH"
    assert "secret-quote" not in str(caught.value)


def test_host_rebinds_full_receipt_and_refuses_wrong_page_or_quote(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    def fake_worker(_image, payload, **_kwargs):
        request = json.loads(payload)
        pdf = __import__("base64").b64decode(request["pdf_b64"])
        return json.dumps({
            "carrier_id": "invented", "source_version": "v1",
            "source_access_policy": "FULL_REQUIRED",
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "pdf_byte_length": len(pdf), "page_number": 2, "page_count": 2,
            "page_text_sha256": "1" * 64,
            "excerpt_sha256": hashlib.sha256(b"Bravo").hexdigest(),
            "offset": 0, "length": 5,
            "extractor_name": "pypdf", "extractor_version": "6.21.1",
        }).encode()
    monkeypatch.setattr(sandbox, "_run_container", fake_worker)
    with pytest.raises(sandbox.PdfSandboxError, match="PROCESS_CRASH"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test", test_only=True,
        )


def test_mocked_argv_timeout_cleanup_and_no_source_in_commands(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    commands = []
    class Hung:
        stdin = SimpleNamespace(write=lambda _data: None, close=lambda: None)
        stdout = BytesIO()
        stderr = BytesIO()
        returncode = None

        def poll(self):
            return None

        def kill(self):
            self.returncode = -9

        def wait(self, timeout):
            return -9

    def popen(argv, **_kwargs):
        commands.append(argv)
        return Hung()
    def run(argv, **_kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"")
    monkeypatch.setattr(sandbox.subprocess, "Popen", popen)
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    with pytest.raises(sandbox.PdfSandboxError, match="TIMEOUT"):
        sandbox._run_container("synthetic:test", b"private-pdf-and-quote", timeout_seconds=0.01)
    launch, cleanup, inspection = commands
    assert "--network" in launch and "none" in launch
    assert launch[launch.index("--pull") + 1] == "never"
    for flag in ("--read-only", "--pids-limit", "--memory", "--memory-swap",
                 "--cpus", "--cap-drop", "--security-opt", "--tmpfs"):
        assert flag in launch
    assert "-t" not in launch and "--env" not in launch and "--mount" not in launch
    assert cleanup[:3] == ["docker", "rm", "--force"]
    assert cleanup[-1] == launch[launch.index("--name") + 1]
    assert inspection[:3] == ["docker", "ps", "-a"]
    assert all("private-pdf-and-quote" not in str(command) for command in commands)


@pytest.mark.parametrize(("exit_code", "expected"), [
    (137, "MEMORY_LIMIT"), (2, "PROCESS_CRASH"),
])
def test_mocked_container_failure_force_removes_unique_name(
    monkeypatch, exit_code, expected,
) -> None:
    commands = []

    class Finished:
        stdin = SimpleNamespace(write=lambda _data: None, close=lambda: None)
        stdout = BytesIO()
        stderr = BytesIO(b"secret-parser-stderr")
        returncode = exit_code

        def poll(self):
            return exit_code

    def popen(argv, **_kwargs):
        commands.append(argv)
        return Finished()

    def run(argv, **_kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(sandbox.subprocess, "Popen", popen)
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    with pytest.raises(sandbox.PdfSandboxError) as caught:
        sandbox._run_container("synthetic:test", b"private-pdf", timeout_seconds=1)
    assert str(caught.value) == expected
    assert "secret-parser-stderr" not in str(caught.value)
    assert commands[1][-1] == commands[0][commands[0].index("--name") + 1]


@pytest.mark.docker
def test_actual_offline_docker_synthetic_two_pages() -> None:
    """Run only in CI with reviewed local image and functioning Linux Docker daemon."""
    import os
    image = os.environ.get("SESHAT_SYNTHETIC_PDF_TEST_IMAGE")
    if not image:
        pytest.skip("Docker smoke image not configured")
    receipt = sandbox.check_pdf_page_excerpt_sandboxed(
        _access(), "invented", page_number=2, expected_excerpt="Bravo",
        image=image, test_only=True,
    )
    assert receipt.page_number == 2
    assert receipt.rights_independently_attested == "NO"
    assert receipt.human_acceptance == "NOT_ASSERTED"
    for page, excerpt in ((1, "Bravo"), (3, "Alpha")):
        with pytest.raises(sandbox.PdfSandboxError):
            sandbox.check_pdf_page_excerpt_sandboxed(
                _access(), "invented", page_number=page,
                expected_excerpt=excerpt, image=image, test_only=True,
            )
