"""HOST-ONLY safe dispatcher and result-ingest logic. DRY RUN is the default everywhere.

* No shell: argv is a fixed template; every variable is a validated token or an integer.
* No arbitrary flags: nothing from a StoneEvent, ResearchNeed text or model output reaches argv.
* Real submission requires ALL of: ``execute=True``, a single-use coordinator authorization
  bound to this exact job/spec/prompt digest and a source-review digest, a configured
  absolute ``aiye-exec`` path, and a passing outbound re-gate. Authoring this module did not
  call any Hub or model; tests use a mocked submitter and runner.

ASSUMPTION (unverified): the ``aiye-exec submit`` flag spelling in ``build_aiye_exec_argv`` is
a placeholder pinned in ONE place. It must be checked against
``aiye-local-executor/CALLER_PROTOCOL.md`` by the coordinator before any live use.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from seshat.fabric_waves.external_carrier.contracts import utc_now_iso
from seshat.fabric_waves.external_carrier.host_adapter import (
    IngestOutcome,
    TrustedHubHostAdapter,
)
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError,
    atomic_write_bytes,
    read_file_under,
    require_safe_token,
    sha256_hex,
)
from seshat.fabric_waves.external_carrier.hub_protocol import (
    HubFetcher,
    HubJobRecord,
    HubJobSpec,
    HubSubmitter,
    HubTransportError,
    parse_hub_record,
)

LIVE_AUTH_SCHEMA = "seshat.live_dispatch_authorization.v1"
ASSUMED_PROTOCOL_STATUS = "UNVERIFIED_AGAINST_CALLER_PROTOCOL"
# Hard-fail-closed gate for live dispatch. The actual official ``aiye-exec submit`` argv template
# could NOT be verified against AORUS ``services/aiye-local-executor/CALLER_PROTOCOL.md`` from the
# authoring workspace. Live dispatch must therefore raise ``PROTOCOL_UNVERIFIED`` rather than
# spoofing an unverified argv. ``CallerProtocolVerifier`` is the only approved override path.
PROTOCOL_VERIFIED_ENV = "SESHAT_PHASE_B_PROTOCOL_VERIFIED"
# Transport outcomes that may have created a Hub job; never allow a second paid submit.
_AMBIGUOUS_CODES = frozenset(
    {
        "SUBMIT_TIMEOUT_AMBIGUOUS",
        "SUBMIT_EXIT_AMBIGUOUS",
        "SUBMIT_TRANSPORT_AMBIGUOUS",
        "PROTOCOL_UNVERIFIED",
    }
)
# Only pre-send, locally verified failures (no subprocess started or provably rejected before send).
# ``PROVIDER_UNAVAILABLE`` is REACHED only after the OS already attempted exec and refused: the
# command line is gone and stdin/stdout were never consumed, so retry with fresh auth is safe.
_PROVEN_NOT_SENT_CODES = frozenset(
    {
        "PROVIDER_UNAVAILABLE",
        "PROMPT_DIGEST_MISMATCH",
        "AIYE_EXEC_PATH_INVALID",
        "PROMPT_PATH_NOT_ABSOLUTE",
        "HUB_TICKET_INVALID",
        "HUB_JOB_ID_INVALID",
        "HUB_PROVIDER_INVALID",
        "HUB_MODEL_INVALID",
    }
)
_MAX_RECORD_BYTES = 64_000

# The expected official submit flags recorded by an independent reviewer after reading the live
# ``aiye-exec submit --help`` output on AORUS. The expected set does NOT include ``--provider``,
# ``--job-id``, ``--budget-usd``, ``--max-tokens``, ``--timeout-seconds`` or a ``--decision`` flag
# (the accepted name is ``--decision-id``). Mode values are ``{audit, code}``; ``read-only`` is
# invalid in the official CLI. We list the flags here only so that the read-only gap ledger can be
# filled in once the live protocol is independently re-checked.
_CALLER_PROTOCOL_EXPECTED_SUBMIT_FLAGS = frozenset(
    {
        "--agent",
        "--kind",
        "--ticket",
        "--decision-id",
        "--role",
        "--mode",
        "--max-seconds",
        "--max-turns",
        "--client",
        "--purpose",
        "--model",
        "--model-tier",
        "--prompt-file",
    }
)
# Flags the host adapter currently emits (placeholders pending independent CALLER_PROTOCOL review).
_SESHAT_SUBMIT_FLAGS = frozenset(
    {
        "--ticket",
        "--decision",
        "--role",
        "--mode",
        "--job-id",
        "--provider",
        "--model",
        "--max-tokens",
        "--timeout-seconds",
        "--budget-usd",
        "--prompt-file",
    }
)


def caller_protocol_argv_gaps() -> tuple[str, ...]:
    """Document argv mismatches; live dispatch must stay blocked until independently reviewed."""

    gaps: list[str] = []
    missing = sorted(_CALLER_PROTOCOL_EXPECTED_SUBMIT_FLAGS - _SESHAT_SUBMIT_FLAGS)
    extra = sorted(_SESHAT_SUBMIT_FLAGS - _CALLER_PROTOCOL_EXPECTED_SUBMIT_FLAGS)
    if "--agent" in missing:
        gaps.append("CALLER_PROTOCOL_REQUIRES_AGENT_AUTO")
    if "--kind" in missing:
        gaps.append("CALLER_PROTOCOL_REQUIRES_KIND")
    if "--decision-id" in missing and "--decision" in extra:
        gaps.append("CALLER_PROTOCOL_DECISION_ID_VS_DECISION_FLAG")
    for flag in missing:
        if flag not in {"--agent", "--decision-id", "--kind"}:
            gaps.append(f"CALLER_PROTOCOL_MISSING_FLAG:{flag}")
    for flag in extra:
        gaps.append(f"SESHAT_INVALID_FLAG:{flag}")
    # Per the actual ``aiye-exec submit`` help, ``--mode read-only`` is an INVALID mode; the
    # accepted values are ``audit`` and ``code``. We never produce a session that pretends to be
    # read-only; the host gate would still need independent verification.
    gaps.append("CALLER_PROTOCOL_REJECTS_READ_ONLY_MODE")
    return tuple(gaps)


def caller_protocol_unverified() -> bool:
    """True unless an independent review flipped the verification gate to ``True``.

    The flag is read from process environment to keep it out of the host JSON config and away
    from operator-editable files. Setting ``SESHAT_PHASE_B_PROTOCOL_VERIFIED=true`` does NOT
    constitute scientific-method acceptance; it is a host-controlled engineering gate that must
    be flipped only after reading the live ``aiye-exec submit --help`` output and updating
    ``build_aiye_exec_argv`` to match.
    """

    import os as _os

    return _os.environ.get(PROTOCOL_VERIFIED_ENV, "").lower() not in {"1", "true", "yes"}


def _cents(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def validate_exe_path(exe: str | Path) -> str:
    """Absolute path whose basename is exactly aiye-exec (or aiye-exec.exe)."""

    path = Path(exe)
    text = str(exe)
    if not path.is_absolute() or "\x00" in text or ".." in path.parts:
        raise HostBoundaryError("AIYE_EXEC_PATH_INVALID")
    if path.name.lower() not in {"aiye-exec", "aiye-exec.exe"}:
        raise HostBoundaryError("AIYE_EXEC_PATH_INVALID")
    return text


def build_aiye_exec_argv(*, exe: str | Path, spec: HubJobSpec, prompt_path: Path) -> list[str]:
    """Fixed-template argv for the official Hub path. No user-supplied flags.

    recommend decision, role analyze|classify, read-only mode, unique ticket and job id,
    explicit provider/model and a hard budget.
    """

    spec.assert_static_policy()
    if not Path(prompt_path).is_absolute():
        raise HostBoundaryError("PROMPT_PATH_NOT_ABSOLUTE")
    return [
        validate_exe_path(exe),
        "submit",
        "--ticket",
        require_safe_token(spec.ticket, code="HUB_TICKET_INVALID"),
        "--decision",
        spec.decision,
        "--role",
        spec.role,
        "--mode",
        spec.mode,
        "--job-id",
        require_safe_token(spec.hub_job_id, code="HUB_JOB_ID_INVALID"),
        "--provider",
        require_safe_token(spec.provider, code="HUB_PROVIDER_INVALID", extra=":/"),
        "--model",
        require_safe_token(spec.model, code="HUB_MODEL_INVALID", extra=":/"),
        "--max-tokens",
        str(int(spec.max_tokens)),
        "--timeout-seconds",
        str(int(spec.max_time_seconds)),
        "--budget-usd",
        _cents(int(spec.max_cost_cents)),
        "--prompt-file",
        str(prompt_path),
    ]


@dataclass
class AiyeExecSubmitter:
    """Submits through the official ``aiye-exec`` binary only (never a model CLI directly)."""

    exe: str
    spool_dir: Path
    runner: Callable[..., Any] = subprocess.run
    exit_code_map: Mapping[int, str] = field(default_factory=dict)

    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        # Hard-fail closed: the official ``aiye-exec submit`` argv template was NOT independently
        # verified in this workspace. Every ambiguous gap is reported, and no live argv is built
        # until an independent reviewer flips ``SESHAT_PHASE_B_PROTOCOL_VERIFIED``. We never spoof
        # the Hub-issued ``hub_job_id``; the actual Hub assigns ``jx-...`` identifiers after dispatch.
        if caller_protocol_unverified():
            raise HubTransportError("PROTOCOL_UNVERIFIED")
        if sha256_hex(prompt) != spec.prompt_sha256:
            raise HostBoundaryError("PROMPT_DIGEST_MISMATCH")
        # Validate every token (and build argv) BEFORE any file is written.
        prompt_path = (Path(self.spool_dir) / spec.hub_job_id / "prompt.txt").resolve()
        argv = build_aiye_exec_argv(exe=self.exe, spec=spec, prompt_path=prompt_path)
        atomic_write_bytes(prompt_path, prompt)
        try:
            completed = self.runner(
                argv,
                shell=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=spec.max_time_seconds + 60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HubTransportError("SUBMIT_TIMEOUT_AMBIGUOUS") from None
        except OSError:
            # OSError after the child was forked may still mean the child ran (fork before exec);
            # we cannot prove NOT_SENT, so the conservative classification is AMBIGUOUS. The
            # caller must issue a new, separately approved job to retry, never reuse this nonce.
            raise HubTransportError("SUBMIT_DISPATCH_AMBIGUOUS") from None
        code = int(getattr(completed, "returncode", 1))
        if code != 0:
            # stderr/stdout are deliberately not propagated: they may echo credentials.
            mapped = self.exit_code_map.get(code)
            if mapped is None:
                # Unmapped nonzero exit is always ambiguous: the child has produced stderr we
                # will not surface, so we cannot prove the chargeable model call did NOT run.
                raise HubTransportError("SUBMIT_EXIT_AMBIGUOUS")
            if mapped not in _PROVEN_NOT_SENT_CODES:
                # Caller-mapped code that is not in the documented pre-send whitelist cannot be
                # trusted as ``NOT_SENT``: the child had already launched.
                raise HubTransportError("SUBMIT_TRANSPORT_AMBIGUOUS")
            raise HubTransportError(mapped)


@dataclass
class SpoolHubFetcher:
    """Reads NORMALIZED Hub records from ``<spool>/<hub_job_id>/record.json`` + ``stdout.bin``."""

    spool_dir: Path
    # Larger than HostLimits.max_stdout_bytes on purpose: an oversize answer must be hashed and
    # recorded as a typed OUTPUT_REJECTED terminal, not leave the job stuck in a read error.
    max_stdout_bytes: int = 1_000_000

    def fetch(self, *, hub_job_id: str) -> tuple[HubJobRecord, bytes] | None:
        require_safe_token(hub_job_id, code="HUB_JOB_ID_INVALID")
        try:
            _, raw = read_file_under(
                self.spool_dir, Path(hub_job_id) / "record.json", max_bytes=_MAX_RECORD_BYTES
            )
        except HostBoundaryError as exc:
            if exc.code == "PATH_NOT_FOUND":
                return None
            raise
        try:
            document = json.loads(raw)
        except ValueError:
            raise HostBoundaryError("HUB_RECORD_SCHEMA_INVALID") from None
        if not isinstance(document, dict):
            raise HostBoundaryError("HUB_RECORD_SCHEMA_INVALID")
        record = parse_hub_record(document)
        try:
            _, stdout = read_file_under(
                self.spool_dir, Path(hub_job_id) / "stdout.bin", max_bytes=self.max_stdout_bytes
            )
        except HostBoundaryError as exc:
            if exc.code != "PATH_NOT_FOUND":
                raise
            stdout = b""
        return record, stdout


def _parse_iso(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise HostBoundaryError("LIVE_AUTHORIZATION_INVALID") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def verify_live_authorization(
    document: Mapping[str, Any], *, spec: HubJobSpec, now_iso: str
) -> str:
    """Return the single-use nonce if the coordinator authorization binds this exact job."""

    required = (
        "schema",
        "authorized_by",
        "host_job_id",
        "spec_sha256",
        "prompt_sha256",
        "source_review_sha256",
        "nonce",
        "expires_at",
    )
    if any(not isinstance(document.get(key), str) or not document.get(key) for key in required):
        raise HostBoundaryError("LIVE_AUTHORIZATION_INVALID")
    if document["schema"] != LIVE_AUTH_SCHEMA:
        raise HostBoundaryError("LIVE_AUTHORIZATION_INVALID")
    if (
        document["host_job_id"] != spec.host_job_id
        or document["spec_sha256"] != spec.spec_sha256()
        or document["prompt_sha256"] != spec.prompt_sha256
    ):
        raise HostBoundaryError("LIVE_AUTHORIZATION_BINDING_MISMATCH")
    review = document["source_review_sha256"]
    if len(review) != 64 or any(c not in "0123456789abcdef" for c in review):
        raise HostBoundaryError("LIVE_AUTHORIZATION_INVALID")
    require_safe_token(document["nonce"], code="LIVE_AUTHORIZATION_INVALID")
    if _parse_iso(document["expires_at"]) <= _parse_iso(now_iso):
        raise HostBoundaryError("LIVE_AUTHORIZATION_EXPIRED")
    return str(document["nonce"])


@dataclass(frozen=True)
class DispatchResult:
    state: str  # DRY_RUN | SUBMITTED | ALREADY_SUBMITTED | BLOCKED_EXTERNAL | AMBIGUOUS
    host_job_id: str
    hub_job_id: str
    detail: str
    manifest: dict[str, Any]


class HostDispatcher:
    """Dispatch/ingest coordinator over a TrustedHubHostAdapter."""

    def __init__(
        self,
        *,
        adapter: TrustedHubHostAdapter,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._adapter = adapter
        self._clock = clock

    def manifest(self, host_job_id: str, *, exe: str | None, spool_dir: Path | None) -> dict[str, Any]:
        job = self._adapter.load_job(host_job_id)
        spec = self._adapter.spec_for(job)
        request = job.request()
        argv: list[str] | None = None
        if exe is not None:
            prompt_path = (
                Path(spool_dir if spool_dir is not None else Path.cwd()).resolve()
                / spec.hub_job_id
                / "prompt.txt"
            )
            argv = build_aiye_exec_argv(exe=exe, spec=spec, prompt_path=prompt_path)
        return {
            "protocol_status": ASSUMED_PROTOCOL_STATUS,
            "host_job_id": job.host_job_id,
            "hub_job_id": spec.hub_job_id,
            "request_id": request.request_id,
            "run_id": request.run_id,
            "wave_id": request.wave_id,
            "ticket": spec.ticket,
            "decision": spec.decision,
            "role": spec.role,
            "mode": spec.mode,
            "provider": spec.provider,
            "model": spec.model,
            "max_tokens": spec.max_tokens,
            "max_time_seconds": spec.max_time_seconds,
            "max_cost_cents": spec.max_cost_cents,
            "spec_sha256": spec.spec_sha256(),
            "prompt_sha256": spec.prompt_sha256,
            "request_sha256": job.request_sha256,
            "request_pin_sha256": spec.request_pin_sha256,
            "source_carrier_ids": list(request.source_carrier_ids),
            "source_versions": dict(request.source_versions),
            "argv": argv,
            "caller_protocol_gaps": list(caller_protocol_argv_gaps()),
        }

    def dispatch(
        self,
        host_job_id: str,
        *,
        execute: bool = False,
        submitter: HubSubmitter | None = None,
        authorization: Mapping[str, Any] | None = None,
        exe: str | None = None,
        spool_dir: Path | None = None,
    ) -> DispatchResult:
        job = self._adapter.load_job(host_job_id)
        spec = self._adapter.spec_for(job)
        # Fresh outbound gate in BOTH modes: dry run reports exactly what live would send.
        self._adapter.recheck_outbound(job)
        manifest = self.manifest(host_job_id, exe=exe, spool_dir=spool_dir)
        if not execute:
            return DispatchResult(
                "DRY_RUN", host_job_id, spec.hub_job_id, "NO_SIDE_EFFECTS", manifest
            )
        if submitter is None or authorization is None:
            raise HostBoundaryError("LIVE_DISPATCH_NOT_AUTHORIZED")
        store = self._adapter.store
        if store.submission_state(host_job_id) == "ACKED":
            return DispatchResult(
                "ALREADY_SUBMITTED", host_job_id, spec.hub_job_id, "IDEMPOTENT", manifest
            )
        nonce = verify_live_authorization(authorization, spec=spec, now_iso=self._clock())
        try:
            # One IMMEDIATE transaction: racing dispatchers cannot both reach the Hub.
            store.begin_submission(
                host_job_id,
                nonce=nonce,
                auth_detail={
                    "authorized_by": str(authorization["authorized_by"]),
                    "source_review_sha256": str(authorization["source_review_sha256"]),
                },
                attempt_detail={"spec_sha256": spec.spec_sha256()},
            )
        except HostBoundaryError as exc:
            if exc.code == "SUBMISSION_ALREADY_ACKED":
                return DispatchResult(
                    "ALREADY_SUBMITTED", host_job_id, spec.hub_job_id, "IDEMPOTENT", manifest
                )
            raise
        try:
            submitter.submit(spec=spec, prompt=job.prompt_bytes)
        except (HostBoundaryError, OSError) as exc:
            # Raised by our own pre-send validation: provably NOT sent, so a fresh authorization
            # may retry. (Errors from the Hub path itself surface as HubTransportError.)
            code = exc.code if isinstance(exc, HostBoundaryError) else "SUBMIT_PREFLIGHT_FAILED"
            store.record_submission(host_job_id, "SUBMIT_FAILED", {"code": code, "sent": False})
            if isinstance(exc, HostBoundaryError):
                raise
            raise HostBoundaryError(code) from None
        except HubTransportError as exc:
            if exc.code in _AMBIGUOUS_CODES or exc.code not in _PROVEN_NOT_SENT_CODES:
                store.record_submission(host_job_id, "SUBMIT_AMBIGUOUS", {"code": exc.code})
                return DispatchResult("AMBIGUOUS", host_job_id, spec.hub_job_id, exc.code, manifest)
            store.record_submission(
                host_job_id, "SUBMIT_FAILED", {"code": exc.code, "sent": False}
            )
            return DispatchResult(
                "BLOCKED_EXTERNAL", host_job_id, spec.hub_job_id, exc.code, manifest
            )
        store.record_submission(host_job_id, "SUBMIT_ACKED", {"hub_job_id": spec.hub_job_id})
        return DispatchResult("SUBMITTED", host_job_id, spec.hub_job_id, "ACKED", manifest)

    def ingest(
        self,
        host_job_id: str,
        *,
        fetcher: HubFetcher,
        execute: bool = False,
    ) -> dict[str, Any]:
        """Fetch a Hub record, verify it, and (only with execute) CAS the terminal row."""

        job = self._adapter.load_job(host_job_id)
        spec = self._adapter.spec_for(job)
        fetched = fetcher.fetch(hub_job_id=spec.hub_job_id)
        if fetched is None:
            return {"state": "WAITING", "detail": "NO_HUB_RECORD", "host_job_id": host_job_id,
                    "wrote": False, "dry_run": not execute}
        record, stdout = fetched
        outcome: IngestOutcome
        if execute:
            outcome = self._adapter.ingest_hub_result(
                host_job_id=host_job_id, record=record, stdout=stdout
            )
        else:
            outcome = self._adapter.evaluate_hub_result(
                host_job_id=host_job_id, record=record, stdout=stdout
            )
        return {
            "state": outcome.state,
            "detail": outcome.detail,
            "host_job_id": host_job_id,
            "hub_job_id": spec.hub_job_id,
            "result_digest": outcome.result_digest,
            "stdout_sha256": sha256_hex(stdout),
            "wrote": outcome.wrote,
            "dry_run": not execute,
        }


__all__ = [
    "ASSUMED_PROTOCOL_STATUS",
    "LIVE_AUTH_SCHEMA",
    "_AMBIGUOUS_CODES",
    "_PROVEN_NOT_SENT_CODES",
    "caller_protocol_argv_gaps",
    "AiyeExecSubmitter",
    "DispatchResult",
    "HostDispatcher",
    "SpoolHubFetcher",
    "build_aiye_exec_argv",
    "validate_exe_path",
    "verify_live_authorization",
]
