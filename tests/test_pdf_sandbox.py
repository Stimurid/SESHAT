"""Synthetic PDF sandbox tests. Mocked subprocess tests do not prove OS isolation."""

from __future__ import annotations

import hashlib
import json
import os
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import seshat.pdf_sandbox as sandbox
from seshat.contracts import RawAccessPolicy, SourceCarrier, SourceContent
from seshat.runtime import RuntimeSourceAccess


@pytest.fixture(autouse=True)
def _synthetic_image_env(monkeypatch, request):
    if (not request.node.get_closest_marker("docker")
            and not os.environ.get("SESHAT_SYNTHETIC_PDF_TEST_IMAGE")):
        monkeypatch.setenv("SESHAT_SYNTHETIC_PDF_TEST_IMAGE", "synthetic:test")


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
    complete: bool = True, padding: int = 0,
) -> RuntimeSourceAccess:
    pdf = _pdf() + b" " * padding
    digest = hashlib.sha256(pdf).hexdigest()
    carrier = SourceCarrier(
        carrier_id="invented-sandbox-fixture",
        source_identity="invented-sandbox-fixture", version="v1",
        media_type=media, content_sha256=digest, byte_length=len(pdf),
    )
    content = SourceContent(
        carrier_id="invented-sandbox-fixture", source_version="v1", media_type=media,
        content=pdf, content_sha256=digest, byte_length=len(pdf),
        authorized=authorized, complete=complete,
    )
    return RuntimeSourceAccess(
        policy=policy, carriers=(carrier,), content_provider=_Provider(content),
        carrier_ids=("invented-sandbox-fixture",),
    )


def _mocked_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "_preflight", lambda *_args, **_kwargs: None)


@pytest.mark.parametrize("policy", [RawAccessPolicy.NEVER, RawAccessPolicy.DRILLBACK])
def test_policy_denied_before_parser(monkeypatch, policy) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNREADABLE_SOURCE"):
        sandbox._check_synthetic_pdf_fixture(
            _access(policy=policy), "invented-sandbox-fixture", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test",
        )


@pytest.mark.parametrize("kw", [
    {"media": "text/plain"}, {"authorized": False}, {"complete": False},
])
def test_unadmitted_source_denied(monkeypatch, kw) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNREADABLE_SOURCE"):
        sandbox._check_synthetic_pdf_fixture(
            _access(**kw), "invented-sandbox-fixture", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test",
        )


def test_unpinned_image_refused_before_docker(monkeypatch) -> None:
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="UNSUPPORTED_SANDBOX"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented-sandbox-fixture", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )


def test_public_api_has_no_test_only_escape() -> None:
    with pytest.raises(TypeError):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), "invented-sandbox-fixture", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test", test_only=True,
        )


def test_private_fixture_entrypoint_requires_marker_and_exact_env(monkeypatch) -> None:
    monkeypatch.setenv("SESHAT_SYNTHETIC_PDF_TEST_IMAGE", "different:test")
    with pytest.raises(sandbox.PdfSandboxError, match="UNSUPPORTED_SANDBOX"):
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test",
        )


def test_sandbox_input_limit_before_docker(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: pytest.fail("ran"))
    with pytest.raises(sandbox.PdfSandboxError, match="SANDBOX_INPUT_LIMIT"):
        sandbox._check_synthetic_pdf_fixture(
            _access(padding=sandbox.MAX_SANDBOX_PDF_BYTES),
            "invented-sandbox-fixture", page_number=1,
            expected_excerpt="Alpha", image="synthetic:test",
        )


def test_docker_absent_fails_closed(monkeypatch) -> None:
    def absent(*_args, **_kwargs):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(sandbox.subprocess, "run", absent)
    with pytest.raises(sandbox.PdfSandboxError, match="UNSUPPORTED_SANDBOX"):
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )


@pytest.mark.parametrize("raw", [b"not json", b'{"error":"NOT_VERIFIED"}', b"{}"])
def test_malformed_or_denied_child_response(monkeypatch, raw) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: raw)
    expected = "NOT_VERIFIED" if raw == b'{"error":"NOT_VERIFIED"}' else "PROCESS_CRASH"
    with pytest.raises(sandbox.PdfSandboxError, match=expected):
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )


def test_child_stdout_cannot_escape_in_error(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    monkeypatch.setattr(sandbox, "_run_container", lambda *_a, **_k: b"secret-quote")
    with pytest.raises(sandbox.PdfSandboxError) as caught:
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )
    assert str(caught.value) == "PROCESS_CRASH"
    assert "secret-quote" not in str(caught.value)


def test_host_rebinds_full_receipt_and_refuses_wrong_page_or_quote(monkeypatch) -> None:
    _mocked_preflight(monkeypatch)
    def fake_worker(_image, payload, **_kwargs):
        request = json.loads(payload)
        pdf = __import__("base64").b64decode(request["pdf_b64"])
        return json.dumps({
            "carrier_id": "invented-sandbox-fixture", "source_version": "v1",
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
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=1, expected_excerpt="Alpha",
            image="synthetic:test",
        )


@pytest.mark.parametrize("changes", [
    {"page_count": 1}, {"offset": 4294967295},
    {"page_text_sha256": "not-a-sha"}, {"extra": "covert"},
    {"extractor_version": "6.21.2"},
])
def test_host_rejects_unbounded_or_extra_child_observations(monkeypatch, changes) -> None:
    _mocked_preflight(monkeypatch)
    def fake_worker(_image, payload, **_kwargs):
        request = json.loads(payload)
        pdf = __import__("base64").b64decode(request["pdf_b64"])
        fields = {
            "carrier_id": "invented-sandbox-fixture", "source_version": "v1",
            "source_access_policy": "FULL_REQUIRED",
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "pdf_byte_length": len(pdf), "page_number": 2, "page_count": 2,
            "page_text_sha256": "1" * 64,
            "excerpt_sha256": hashlib.sha256(b"Bravo").hexdigest(),
            "offset": 0, "length": 5,
            "extractor_name": "pypdf", "extractor_version": "6.21.1",
            "rights_independently_attested": "NO",
            "human_acceptance": "NOT_ASSERTED", "acceptance": "PROPOSED",
        }
        fields.update(changes)
        return json.dumps(fields).encode()
    monkeypatch.setattr(sandbox, "_run_container", fake_worker)
    with pytest.raises(sandbox.PdfSandboxError, match="PROCESS_CRASH"):
        sandbox._check_synthetic_pdf_fixture(
            _access(), "invented-sandbox-fixture", page_number=2,
            expected_excerpt="Bravo", image="synthetic:test",
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
    # Exact production argv values are the OS resource *contract*.
    # A changed flag value (root user, unlimited memory/PIDs, etc.) must fail.
    values = {
        "--pull": "never", "--network": "none",
        "--user": "65532:65532", "--cap-drop": "ALL",
        "--security-opt": "no-new-privileges",
        "--pids-limit": "32", "--memory": "256m",
        "--memory-swap": "256m", "--cpus": "1",
        "--tmpfs": "/tmp:rw,nosuid,nodev,size=16m",
        "--log-driver": "none",
    }
    # Docker uses last-option-wins: duplicates defeat first-occurrence tests.
    expected_launch_prefix = [
        "docker", "run", "--rm", "-i", "--pull", "never", "--name",
        launch[launch.index("--name") + 1],
        "--log-driver", "none", "--network", "none", "--read-only",
        "--user", "65532:65532", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "32",
        "--memory", "256m", "--memory-swap", "256m",
        "--cpus", "1", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
        "synthetic:test", "python", "-m", "seshat.pdf_sandbox_worker",
    ]
    assert launch == expected_launch_prefix
    for option, expected in values.items():
        assert launch.count(option) == 1
        assert launch[launch.index(option) + 1] == expected
    assert launch.count("--read-only") == 1
    for unsafe in (
        "--privileged", "--cap-add", "--volume", "-v", "--device",
        "--pid", "--userns", "--ipc", "--env", "--mount", "-t",
    ):
        assert unsafe not in launch
    assert cleanup[:3] == ["docker", "rm", "--force"]
    assert cleanup[-1] == launch[launch.index("--name") + 1]
    assert inspection[:3] == ["docker", "ps", "-a"]
    assert all("private-pdf-and-quote" not in str(command) for command in commands)


@pytest.mark.parametrize(("exit_code", "expected"), [
    (137, "MEMORY_LIMIT"), (2, "PROCESS_CRASH"),
    (125, "UNSUPPORTED_SANDBOX"), (126, "UNSUPPORTED_SANDBOX"),
    (127, "UNSUPPORTED_SANDBOX"),
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


def test_cleanup_timeout_preserves_original_failure_and_blocks_next_call(monkeypatch, capsys) -> None:
    class Hung:
        stdin = SimpleNamespace(write=lambda _data: None, close=lambda: None)
        stdout = BytesIO()
        stderr = BytesIO()
        returncode = None
        def poll(self):
            return self.returncode
        def kill(self):
            self.returncode = -9
        def wait(self, timeout):
            return -9
    monkeypatch.setattr(sandbox.subprocess, "Popen", lambda *_a, **_k: Hung())
    def run(argv, **_kwargs):
        if argv[:3] == ["docker", "rm", "--force"]:
            raise __import__("subprocess").TimeoutExpired(argv, 5)
        return SimpleNamespace(returncode=0, stdout=b"")
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    try:
        with pytest.raises(sandbox.PdfSandboxError, match="TIMEOUT"):
            sandbox._run_container("synthetic:test", b"private-pdf", timeout_seconds=0.01)
        assert "PDF_SANDBOX_CLEANUP_UNCONFIRMED name=seshat-pdf-" in capsys.readouterr().err
        assert sandbox._CLEANUP_UNCERTAIN.is_set()
    finally:
        sandbox._CLEANUP_UNCERTAIN.clear()


@pytest.mark.docker
def test_actual_offline_docker_synthetic_two_pages() -> None:
    """Run only in CI with reviewed local image and functioning Linux Docker daemon."""
    import os
    image = os.environ.get("SESHAT_SYNTHETIC_PDF_TEST_IMAGE")
    if not image:
        if os.environ.get("SESHAT_DOCKER_SMOKE_REQUIRED") == "1":
            pytest.fail("REQUIRED_DOCKER_SMOKE_IMAGE_MISSING")
        pytest.skip("Docker smoke image not configured")
    receipt = sandbox._check_synthetic_pdf_fixture(
        _access(), "invented-sandbox-fixture", page_number=2, expected_excerpt="Bravo",
        image=image,
    )
    assert receipt.page_number == 2
    assert receipt.rights_independently_attested == "NO"
    assert receipt.human_acceptance == "NOT_ASSERTED"
    for page, excerpt in ((1, "Bravo"), (3, "Alpha")):
        with pytest.raises(sandbox.PdfSandboxError, match="NOT_VERIFIED"):
            sandbox._check_synthetic_pdf_fixture(
                _access(), "invented-sandbox-fixture", page_number=page,
                expected_excerpt=excerpt, image=image,
            )



def test_missing_required_docker_fixture_never_passes_green_via_skip(monkeypatch) -> None:
    """CI must fail if its mandatory real-Docker smoke loses the image binding."""
    monkeypatch.setenv("SESHAT_DOCKER_SMOKE_REQUIRED", "1")
    monkeypatch.delenv("SESHAT_SYNTHETIC_PDF_TEST_IMAGE", raising=False)
    with pytest.raises(pytest.fail.Exception, match="REQUIRED_DOCKER_SMOKE_IMAGE_MISSING"):
        test_actual_offline_docker_synthetic_two_pages()


@pytest.mark.parametrize("input_name", ["carrier", "excerpt"])
def test_lone_surrogate_input_fails_closed_without_docker(input_name) -> None:
    candidate_carrier = chr(0xD800) if input_name == "carrier" else "invented-sandbox-fixture"
    candidate_excerpt = chr(0xD800) if input_name == "excerpt" else "Alpha"
    with pytest.raises(sandbox.PdfSandboxError, match="UNREADABLE_SOURCE"):
        sandbox.check_pdf_page_excerpt_sandboxed(
            _access(), candidate_carrier, page_number=1,
            expected_excerpt=candidate_excerpt,
            image="source.example/seshat@sha256:" + "1" * 64,
        )


def test_sandbox_returns_host_bound_observation_without_child_side_channel(
    monkeypatch,
) -> None:
    """An unreviewed child can fabricate page text, but must not export it."""
    _mocked_preflight(monkeypatch)

    def forged_child(_image, _payload, **_kwargs):
        from seshat.pdf_page_evidence import check_pdf_page_excerpt

        valid = check_pdf_page_excerpt(
            _access(), "invented-sandbox-fixture",
            page_number=2, expected_excerpt="Bravo",
        ).model_dump(
            mode="json",
            exclude={"source_access_full_receipt_sha256",
                     "sandbox_child_observation_provenance"},
        )
        # Arbitrary child-reported page metadata must NOT reach callers.
        original_pdf = __import__("base64").b64decode(
            json.loads(_payload)["pdf_b64"]
        )
        valid["pdf_sha256"] = hashlib.sha256(original_pdf).hexdigest()
        valid["pdf_byte_length"] = len(original_pdf)
        valid["page_count"] = 10000
        valid["page_text_sha256"] = "f" * 64
        valid["offset"] = 999977
        return json.dumps(valid).encode()

    monkeypatch.setattr(sandbox, "_run_container", forged_child)
    result = sandbox._check_synthetic_pdf_fixture(
        _access(), "invented-sandbox-fixture",
        page_number=2, expected_excerpt="Bravo", image="synthetic:test",
    )
    assert result.status == "CHILD_REPORTED_MATCH_UNATTESTED"
    assert result.sandbox_child_observation_provenance == "CHILD_ASSERTED_UNATTESTED"
    assert result.rights_independently_attested == "NO"
    dumped = result.model_dump_json()
    assert "page_count" not in dumped and "page_text_sha256" not in dumped
    assert "offset" not in dumped and "f" * 64 not in dumped
    assert "999977" not in dumped
    assert result.excerpt_sha256 == hashlib.sha256(b"Bravo").hexdigest()


def _bridge_candidate() -> dict:
    return {
        "schema": "seshat.pdf_claims.v1",
        "method_id": "synthetic-method",
        "source_id": "invented-sandbox-fixture",
        "source_version": "v1",
        "run_scope": "SYNTHETIC_QA",
        "evidence": [
            {"claim": "Page one", "page": 1, "excerpt": "Alpha",
             "kind": "SOURCE_STATED"},
            {"claim": "Page two", "page": 2, "excerpt": "Bravo",
             "kind": "SOURCE_STATED"},
        ],
        "unknowns": ["External truth not assessed"],
        "rights_independently_attested": "NO",
        "scientific_acceptance": "NOT_ASSERTED",
        "customer_release": "NOT_AUTHORIZED",
    }


def _bridge_run(candidate, *, access=None, image="synthetic:test"):
    from seshat.pdf_isolated_bridge import verify_synthetic_claims_in_sandbox
    return verify_synthetic_claims_in_sandbox(
        access=access or _access(), carrier_id="invented-sandbox-fixture",
        response_json=json.dumps(candidate).encode("utf-8"), image=image,
    )


def test_bridge_synthetic_child_success_is_unattested_not_verified(monkeypatch):
    import seshat.pdf_isolated_bridge as bridge

    def child(access, carrier_id, *, page_number, expected_excerpt, **kwargs):
        pdf, _, _, version, _ = access.read_full_with_metadata(carrier_id)
        return sandbox.SandboxQuoteObservation(
            carrier_id=carrier_id, source_version=version,
            source_access_full_receipt_sha256=__import__(
                "seshat.pdf_page_evidence", fromlist=["_full_receipt_sha256"]
            )._full_receipt_sha256(access.read_full_with_metadata(carrier_id)[4]),
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            pdf_byte_length=len(pdf), page_number=page_number,
            excerpt_sha256=hashlib.sha256(expected_excerpt.encode()).hexdigest(),
        )

    monkeypatch.setattr(bridge, "_check_synthetic_pdf_fixture", child)
    private = _bridge_run(_bridge_candidate())
    assert private.status == "UNATTESTED_CHILD_OBSERVATIONS"
    assert private.code == "ALL_CHILD_OBSERVATIONS_UNATTESTED"
    assert len(private.observations) == 2
    public = private.public_view()
    assert public.admitted_quote_count == 0
    assert public.semantic_entailment == "NOT_ASSESSED"
    assert public.scientific_acceptance == "NOT_ASSERTED"
    assert public.customer_release == "NOT_AUTHORIZED"
    assert "invented-sandbox-fixture" not in public.model_dump_json()
    assert "f" * 64 not in public.model_dump_json()


def test_bridge_two_of_four_child_quotes_is_atomic_rejection(monkeypatch):
    import seshat.pdf_isolated_bridge as bridge

    candidate = _bridge_candidate()
    candidate["evidence"] += [
        {"claim": "Fabricated", "page": 1, "excerpt": "Not present",
         "kind": "SOURCE_STATED"},
        {"claim": "Also fabricated", "page": 2, "excerpt": "Never present",
         "kind": "SOURCE_STATED"},
    ]
    count = [0]

    def child(access, carrier_id, *, page_number, expected_excerpt, **kwargs):
        count[0] += 1
        if expected_excerpt in {"Not present", "Never present"}:
            raise sandbox.PdfSandboxError("NOT_VERIFIED")
        pdf, _, _, version, _ = access.read_full_with_metadata(carrier_id)
        return sandbox.SandboxQuoteObservation(
            carrier_id=carrier_id, source_version=version,
            source_access_full_receipt_sha256=__import__(
                "seshat.pdf_page_evidence", fromlist=["_full_receipt_sha256"]
            )._full_receipt_sha256(access.read_full_with_metadata(carrier_id)[4]),
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            pdf_byte_length=len(pdf), page_number=page_number,
            excerpt_sha256=hashlib.sha256(expected_excerpt.encode()).hexdigest(),
        )

    monkeypatch.setattr(bridge, "_check_synthetic_pdf_fixture", child)
    result = _bridge_run(candidate)
    assert result.status == "REJECTED"
    assert result.code == "SANDBOX_NOT_VERIFIED"
    assert result.public_view().admitted_quote_count == 0
    assert count[0] == 3  # Stops on first false citation; never accepts partial.


@pytest.mark.parametrize("alter", [
    lambda c: c.update(source_version="v2"),
    lambda c: c.update(source_id="forged-source"),
    lambda c: c["evidence"][1].update(page=1, excerpt="Alpha"),
    lambda c: c.update(rights_independently_attested="YES"),
    lambda c: c.update(scientific_acceptance="ACCEPTED"),
])
def test_bridge_invalid_candidate_never_invokes_child(monkeypatch, alter):
    import seshat.pdf_isolated_bridge as bridge
    monkeypatch.setattr(
        bridge, "_check_synthetic_pdf_fixture",
        lambda *_a, **_k: pytest.fail("child must not run"),
    )
    candidate = _bridge_candidate()
    alter(candidate)
    receipt = _bridge_run(candidate)
    assert receipt.status != "UNATTESTED_CHILD_OBSERVATIONS"
    assert receipt.public_view().admitted_quote_count == 0


@pytest.mark.parametrize("policy", [RawAccessPolicy.NEVER, RawAccessPolicy.DRILLBACK])
def test_bridge_no_full_rights_never_invokes_child(monkeypatch, policy):
    import seshat.pdf_isolated_bridge as bridge
    monkeypatch.setattr(
        bridge, "_check_synthetic_pdf_fixture",
        lambda *_a, **_k: pytest.fail("child must not run"),
    )
    result = _bridge_run(_bridge_candidate(), access=_access(policy=policy))
    assert result.status == "BLOCKED"


def test_bridge_overlarge_pdf_never_invokes_child(monkeypatch):
    import seshat.pdf_isolated_bridge as bridge
    monkeypatch.setattr(
        bridge, "_check_synthetic_pdf_fixture",
        lambda *_a, **_k: pytest.fail("child must not run"),
    )
    result = _bridge_run(
        _bridge_candidate(),
        access=_access(padding=sandbox.MAX_SANDBOX_PDF_BYTES),
    )
    assert result.status == "BLOCKED"
    assert result.code == "PDF_INPUT_LIMIT"


def test_bridge_missing_sandbox_fails_closed(monkeypatch):
    import seshat.pdf_isolated_bridge as bridge
    monkeypatch.setattr(
        bridge, "_check_synthetic_pdf_fixture",
        lambda *_a, **_k: (_ for _ in ()).throw(
            sandbox.PdfSandboxError("UNSUPPORTED_SANDBOX")
        ),
    )
    result = _bridge_run(_bridge_candidate())
    assert result.status == "BLOCKED"
    assert result.code == "SANDBOX_UNAVAILABLE"


@pytest.mark.docker
def test_real_docker_isolated_bridge_synthetic_full_chain():
    """Real Linux smoke: read F07, run child per claim, never mint verified."""
    image = os.environ.get("SESHAT_SYNTHETIC_PDF_TEST_IMAGE")
    if not image:
        if os.environ.get("SESHAT_DOCKER_SMOKE_REQUIRED") == "1":
            pytest.fail("REQUIRED_DOCKER_SMOKE_IMAGE_MISSING")
        pytest.skip("synthetic Docker image not configured")
    positive = _bridge_candidate()
    result = _bridge_run(positive, image=image)
    assert result.status == "UNATTESTED_CHILD_OBSERVATIONS"
    assert result.public_view().admitted_quote_count == 0
    bad = _bridge_candidate()
    bad["evidence"][1]["excerpt"] = "Nonexistent fabricated sentence"
    failure = _bridge_run(bad, image=image)
    assert failure.status == "REJECTED"
    assert failure.code == "SANDBOX_NOT_VERIFIED"


def test_bridge_rejects_drifted_child_f07_receipt_even_with_same_pdf_sha(monkeypatch):
    import seshat.pdf_isolated_bridge as bridge

    def child(access, carrier_id, *, page_number, expected_excerpt, **kwargs):
        pdf, _, _, version, _ = access.read_full_with_metadata(carrier_id)
        return sandbox.SandboxQuoteObservation(
            carrier_id=carrier_id, source_version=version,
            source_access_full_receipt_sha256="0" * 64,
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            pdf_byte_length=len(pdf), page_number=page_number,
            excerpt_sha256=hashlib.sha256(expected_excerpt.encode()).hexdigest(),
        )

    monkeypatch.setattr(bridge, "_check_synthetic_pdf_fixture", child)
    receipt = _bridge_run(_bridge_candidate())
    assert receipt.status == "BLOCKED"
    assert receipt.code == "F07_DENIED_OR_DRIFTED"
    assert receipt.public_view().admitted_quote_count == 0


@pytest.mark.parametrize("drift", ["revoked", "changed_bytes"])
def test_bridge_fresh_provider_read_rejects_revocation_or_drift_before_docker(
    monkeypatch, drift,
):
    access = _access()
    original = access._content_provider.content

    class ChangingProvider:
        calls = 0

        def open_content(self, _carrier_id):
            self.calls += 1
            if self.calls == 1:
                return original
            if drift == "revoked":
                return original.model_copy(update={"authorized": False})
            changed = original.content + b"drifted"
            return original.model_copy(update={
                "content": changed, "byte_length": len(changed),
                "content_sha256": hashlib.sha256(changed).hexdigest(),
            })

    provider = ChangingProvider()
    access._content_provider = provider
    monkeypatch.setattr(sandbox, "_preflight", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sandbox, "_run_container",
        lambda *_a, **_k: pytest.fail("Docker ran after provider changed"),
    )
    result = _bridge_run(_bridge_candidate(), access=access)
    assert result.status == "BLOCKED"
    assert result.code == "SANDBOX_UNAVAILABLE"
    assert provider.calls == 2
    assert result.public_view().admitted_quote_count == 0


def test_bridge_provider_revoked_between_first_and_second_child(monkeypatch):
    import seshat.pdf_page_evidence as pages

    access = _access()
    original = access._content_provider.content

    class MidBatchProvider:
        calls = 0

        def open_content(self, _carrier_id):
            self.calls += 1
            if self.calls <= 2:
                return original
            return original.model_copy(update={"authorized": False})

    provider = MidBatchProvider()
    access._content_provider = provider
    monkeypatch.setattr(sandbox, "_preflight", lambda *_a, **_k: None)
    launched = []

    def synthetic_worker(_image, payload, **_kwargs):
        request = json.loads(payload)
        launched.append(request["page_number"])
        proof = pages.check_pdf_page_excerpt(
            _access(), "invented-sandbox-fixture",
            page_number=request["page_number"],
            expected_excerpt=request["expected_excerpt"],
        )
        return json.dumps(proof.model_dump(
            mode="json",
            exclude={
                "source_access_full_receipt_sha256",
                "sandbox_child_observation_provenance",
            },
        )).encode("utf-8")

    monkeypatch.setattr(sandbox, "_run_container", synthetic_worker)
    result = _bridge_run(_bridge_candidate(), access=access)
    assert result.status == "BLOCKED"
    assert result.code == "SANDBOX_UNAVAILABLE"
    assert provider.calls == 3
    assert launched == [1]
    assert result.public_view().admitted_quote_count == 0


def test_lower_rights_projection_is_constant_across_private_failure_causes():
    from seshat.pdf_isolated_bridge import IsolatedBridgeReceipt

    states = [
        ("REJECTED", "INVALID_CANDIDATE", 0),
        ("BLOCKED", "F07_DENIED_OR_DRIFTED", 2),
        ("REJECTED", "SANDBOX_NOT_VERIFIED", 4),
        ("BLOCKED", "SANDBOX_UNAVAILABLE", 2),
        ("UNATTESTED_CHILD_OBSERVATIONS",
         "ALL_CHILD_OBSERVATIONS_UNATTESTED", 2),
    ]
    public = []
    for status, code, count in states:
        receipt = IsolatedBridgeReceipt(
            status=status, code=code, response_sha256="a" * 64,
            source_id="hidden-source", source_version="private-version",
            method_id="private-method", claim_count=count,
        )
        public.append(receipt.public_view().model_dump_json())
    assert len(set(public)) == 1
    assert '"claim_count":0' in public[0]
    assert "hidden-source" not in public[0]
    assert "F07_DENIED_OR_DRIFTED" not in public[0]
    assert "ALL_CHILD_OBSERVATIONS_UNATTESTED" not in public[0]
