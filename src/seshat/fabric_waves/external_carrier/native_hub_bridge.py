"""Host-only native transport. Direct submit is denied without a durable dispatcher claim.

The CLI response is an untrusted locator, never an attestation. NativeHubBridge binds
it through an independently provisioned host authority before dispatcher ACK/ingest.
No host authority, signing key or live authorization is provisioned by this module.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from seshat.fabric_waves.external_carrier.host_dispatcher import validate_exe_path
from seshat.fabric_waves.external_carrier.host_security import (
    ALLOWED_HUB_ROLES,
    HostBoundaryError,
    atomic_write_bytes,
    require_safe_token,
    scan_text,
    sha256_hex,
)
from seshat.fabric_waves.external_carrier.hub_protocol import HubJobSpec, HubTransportError
from seshat.fabric_waves.external_carrier.host_store import HostJobStore

# Match the verified local executor submit parser. The provider comes only from
# the host-persisted spec; the job kind remains fixed by this adapter.
# Exact choices in the pinned executor.py submit parser. An unknown provider must
# fail before the durable launch claim, rather than falling back to Hub routing.
NATIVE_SUBMIT_AGENTS: frozenset[str] = frozenset({
    "claude", "cursor", "codex", "codex2", "opencode", "openrouter",
    "tyumgu", "anthropic",
})
NATIVE_SUBMIT_KIND = "reasoning"
NATIVE_ALLOWED_MODES: frozenset[str] = frozenset({"audit", "code"})
# ``--mode read-only`` is explicitly invalid against the real CLI per the owner
# handoff; this module never emits it (``NATIVE_ALLOWED_MODES`` excludes it) and the
# existing ``HubJobSpec.mode`` sentinel ("read-only") is never forwarded as a flag.
_NATIVE_JOB_ID_PATTERN = re.compile(r"^jx-[0-9a-f]{12}$")


@dataclass(frozen=True)
class NativePythonLauncher:
    """Host-pinned official Python and executor.py; never cmd.exe or shell text.

    Pins must come from the trusted host installation, not a request/model response.
    Dependencies and directory ACLs remain the host publisher's responsibility.
    """

    python: Path
    executor: Path
    python_sha256: str
    executor_sha256: str

    def prefix(self) -> list[str]:
        for path, digest in ((self.python, self.python_sha256),
                             (self.executor, self.executor_sha256)):
            if (not path.is_absolute() or path.is_symlink() or ".." in path.parts
                    or not path.is_file() or sha256_hex(path.read_bytes()) != digest):
                raise HostBoundaryError("NATIVE_LAUNCHER_PIN_MISMATCH")
        if self.python.name.lower() not in {"python", "python3", "python.exe"}:
            raise HostBoundaryError("NATIVE_LAUNCHER_INVALID")
        if self.executor.name != "executor.py":
            raise HostBoundaryError("NATIVE_LAUNCHER_INVALID")
        return [str(self.python), "-E", "-s", str(self.executor)]


@dataclass(frozen=True)
class NativeSubmitResult:
    """Captured only on a clean, parsed success. Never constructed on ambiguity."""

    native_job_id: str
    exit_code: int
    stdout_sha256: str


def build_native_submit_argv(
    *,
    exe: str | Path,
    spec: HubJobSpec,
    prompt_path: Path,
    mode: str,
    client: str,
    project_target: str,
    max_seconds: int,
    decision_id: str | None = None,
) -> list[str]:
    """Build the fixed, owner-specified ``aiye-exec submit`` argv.

    The prompt is never placed in argv (only its file path is); callers must write
    ``prompt_path`` themselves (see ``NativeAiyeExecSubmitter.submit``). Never emits
    ``--provider``, ``--job-id``, ``--budget-usd``, ``--max-tokens``,
    ``--timeout-seconds`` or ``--decision`` -- those are not parameters of this
    function, so they cannot be emitted even by caller error.
    """

    exe_text = validate_exe_path(exe)
    if mode not in NATIVE_ALLOWED_MODES:
        raise HostBoundaryError("NATIVE_SUBMIT_MODE_INVALID")
    role = require_safe_token(spec.role, code="NATIVE_SUBMIT_ROLE_INVALID")
    if role not in ALLOWED_HUB_ROLES:
        raise HostBoundaryError("NATIVE_SUBMIT_ROLE_INVALID")
    ticket = require_safe_token(spec.ticket, code="NATIVE_SUBMIT_TICKET_INVALID")
    provider = require_safe_token(spec.provider, code="NATIVE_SUBMIT_PROVIDER_INVALID")
    if provider not in NATIVE_SUBMIT_AGENTS:
        raise HostBoundaryError("NATIVE_SUBMIT_PROVIDER_UNSUPPORTED")
    model = require_safe_token(spec.model, code="NATIVE_SUBMIT_MODEL_INVALID", extra=":/+")
    client_token = require_safe_token(client, code="NATIVE_SUBMIT_CLIENT_INVALID")
    project_token = require_safe_token(
        project_target, code="NATIVE_SUBMIT_PROJECT_TARGET_INVALID"
    )
    if not isinstance(max_seconds, int) or isinstance(max_seconds, bool) or not (
        1 <= max_seconds <= 3600
    ):
        raise HostBoundaryError("NATIVE_SUBMIT_MAX_SECONDS_INVALID")
    if (
        not prompt_path.is_absolute()
        or "\x00" in str(prompt_path)
        or ".." in prompt_path.parts
    ):
        raise HostBoundaryError("NATIVE_SUBMIT_PROMPT_PATH_INVALID")

    argv = [
        exe_text,
        "submit",
        # The official router's owner pin can replace a named agent and clear
        # its model. Sensitive jobs bypass that override in the pinned parser.
        "--sensitive",
        "--agent",
        provider,
        "--model",
        model,
        "--kind",
        NATIVE_SUBMIT_KIND,
        "--mode",
        mode,
        "--role",
        role,
        "--ticket",
        ticket,
    ]
    if decision_id is not None:
        argv += [
            "--decision-id",
            require_safe_token(decision_id, code="NATIVE_SUBMIT_DECISION_ID_INVALID"),
        ]
    argv += [
        "--prompt-file",
        str(prompt_path),
        "--max-seconds",
        str(max_seconds),
        "--client",
        client_token,
        "--project-target",
        project_token,
    ]
    return argv


def _parse_native_job_id(stdout: bytes) -> str | None:
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        document = json.loads(text)
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    candidate = document.get("job_id")
    if not isinstance(candidate, str) or not _NATIVE_JOB_ID_PATTERN.fullmatch(candidate):
        return None
    return candidate


@dataclass
class NativeAiyeExecSubmitter:
    """Claimed native transport, used only inside the integrated NativeHubBridge.

    Every outcome other than a clean exit-0 with a parseable ``jx-...`` id in stdout
    raises ``HubTransportError``/``HostBoundaryError`` and leaves ``last_result`` unset,
    which is the same conservative AMBIGUOUS classification the rest of this package
    already applies: a nonzero exit, a timeout or an OS-level failure can never be
    read as proof the Hub did not admit the job, so none of them may be retried
    automatically by a caller holding this instance.
    """

    exe: str
    spool_dir: Path
    mode: str
    client: str
    project_target: str
    decision_id: str | None = None
    runner: Callable[..., Any] = subprocess.run
    timeout_margin_seconds: int = 30
    store: HostJobStore | None = None
    launcher: NativePythonLauncher | None = None
    environ: Mapping[str, str] | None = None
    last_result: NativeSubmitResult | None = field(default=None, init=False, repr=False)

    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        try:
            text = prompt.decode("utf-8")
        except UnicodeDecodeError:
            raise HostBoundaryError("NATIVE_SUBMIT_PROMPT_NOT_UTF8") from None
        scan_text(text, direction="OUTBOUND", environ=(
            self.environ if self.environ is not None else os.environ
        ))
        self.last_result = None
        if self.store is None or self.launcher is None:
            raise HostBoundaryError("NATIVE_DISPATCH_CLAIM_REQUIRED")
        if sha256_hex(prompt) != spec.prompt_sha256:
            raise HostBoundaryError("NATIVE_PROMPT_BINDING_MISMATCH")
        if self.mode != "audit":
            raise HostBoundaryError("NATIVE_SUBMIT_MODE_INVALID")
        prefix = self.launcher.prefix()
        host_job_id = require_safe_token(
            spec.host_job_id, code="NATIVE_SUBMIT_HOST_JOB_ID_INVALID"
        )
        prompt_path = Path(self.spool_dir) / f"{host_job_id}.prompt.txt"
        argv = build_native_submit_argv(
            exe=self.exe,
            spec=spec,
            prompt_path=prompt_path,
            mode=self.mode,
            client=self.client,
            project_target=self.project_target,
            max_seconds=spec.max_time_seconds,
            decision_id=self.decision_id,
        )
        # Validate all local inputs before consuming the claim. Once consumed, any
        # failure (including before spawn) requires host recovery, never another send.
        self.store.claim_native_launch(spec.host_job_id, spec_sha256=spec.spec_sha256())
        atomic_write_bytes(prompt_path, prompt)
        argv = prefix + argv[1:]
        try:
            completed = self.runner(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=spec.max_time_seconds + self.timeout_margin_seconds,
            )
        except subprocess.TimeoutExpired:
            raise HubTransportError("SUBMIT_TIMEOUT_AMBIGUOUS") from None
        except OSError:
            raise HubTransportError("SUBMIT_OSERROR_AMBIGUOUS") from None
        stdout_bytes = completed.stdout or b""
        if completed.returncode != 0:
            # Never classify any exit code as proof the Hub did not admit the job: a
            # supervisor-lock failure can surface after real admission ("ghost
            # success"). Every nonzero exit stays AMBIGUOUS.
            raise HubTransportError("SUBMIT_EXIT_AMBIGUOUS")
        native_id = _parse_native_job_id(stdout_bytes)
        if native_id is None:
            raise HubTransportError("SUBMIT_RESPONSE_UNPARSEABLE_AMBIGUOUS")
        self.last_result = NativeSubmitResult(
            native_job_id=native_id,
            exit_code=completed.returncode,
            stdout_sha256=sha256_hex(stdout_bytes),
        )


__all__ = [
    "NATIVE_ALLOWED_MODES",
    "NATIVE_SUBMIT_AGENTS",
    "NATIVE_SUBMIT_KIND",
    "NativeAiyeExecSubmitter",
    "NativeSubmitResult",
    "build_native_submit_argv",
]


class NativeHubBridge:
    """Dispatcher transport with host-only authority and read-only ghost recovery.

    Construct only in a trusted host bootstrap after review. The naked transport
    is never accepted by HostDispatcher. A launch certificate must be independently
    issued for the exact authorization and installation pins before any paid attempt.
    """

    def __init__(self, *, adapter, transport: NativeAiyeExecSubmitter, authority) -> None:
        self.adapter = adapter
        self.transport = transport
        self.authority = authority
        if transport.store is not adapter.store or adapter.native_authority is not authority:
            raise HostBoundaryError("NATIVE_BRIDGE_HOST_MISMATCH")

    def preflight(self, spec: HubJobSpec, authorization: Mapping[str, Any]) -> None:
        from seshat.fabric_waves.external_carrier.contracts import material_hash

        launcher = self.transport.launcher
        if launcher is None:
            raise HostBoundaryError("NATIVE_LAUNCHER_REQUIRED")
        launcher.prefix()
        # Check the exact route while authorization is still unconsumed. The
        # native submitter repeats this check before its durable launch claim.
        if not self.adapter.registry.provider_model_allowed(spec.provider, spec.model):
            raise HostBoundaryError("HUB_PROVIDER_NOT_ALLOWED")
        build_native_submit_argv(
            exe=self.transport.exe, spec=spec,
            prompt_path=Path(self.transport.spool_dir) / f"{spec.host_job_id}.prompt.txt",
            mode=self.transport.mode, client=self.transport.client,
            project_target=self.transport.project_target,
            max_seconds=spec.max_time_seconds, decision_id=self.transport.decision_id,
        )
        cert = self.authority._certificate(spec, "launch")
        if (cert.get("authorization_sha256") != material_hash(dict(authorization))
                or cert.get("python_sha256") != launcher.python_sha256
                or cert.get("executor_sha256") != launcher.executor_sha256
                or cert.get("client") != self.transport.client
                or cert.get("project_target") != self.transport.project_target
                or cert.get("decision_id") != self.transport.decision_id):
            raise HostBoundaryError("NATIVE_LAUNCH_NOT_AUTHORIZED")

    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        self.transport.submit(spec=spec, prompt=prompt)
        result = self.transport.last_result
        if result is None:
            raise HubTransportError("SUBMIT_RESPONSE_UNPARSEABLE_AMBIGUOUS")
        self.recover(spec.host_job_id, native_job_id=result.native_job_id)

    def recover(self, host_job_id: str, *, native_job_id: str | None = None) -> dict:
        """No subprocess, no retry: find only the host-signed original for this claim."""
        job = self.adapter.load_job(host_job_id)
        spec = self.adapter._spec(job)
        rows = self.adapter.store.submissions(host_job_id)
        auth = [r for r in rows if r["kind"] == "LIVE_AUTH_CONSUMED"]
        attempts = [r for r in rows if r["kind"] == "SUBMIT_ATTEMPTED"]
        launches = [r for r in rows if r["kind"] == "NATIVE_LAUNCH_CLAIMED"]
        if len(auth) != 1 or len(attempts) != 1 or len(launches) != 1:
            raise HostBoundaryError("NATIVE_DISPATCH_CLAIM_REQUIRED")
        admission = self.authority.admission(
            spec, nonce=auth[0]["detail"]["nonce"], attempted_at=attempts[0]["at"],
            native_job_id=native_job_id,
        )
        self.adapter.store.bind_native(host_job_id, admission)
        return admission

    def fetch(self, *, hub_job_id: str):
        # Never look up by a caller-controlled filesystem path or CLI job_path.
        for job_id in self.adapter.store.list_job_ids():
            binding = self.adapter.store.native_binding(job_id)
            if binding is not None and binding["native_job_id"] == hub_job_id:
                return self.adapter.native_original(job_id)
        raise HostBoundaryError("NATIVE_JOB_NOT_BOUND")
