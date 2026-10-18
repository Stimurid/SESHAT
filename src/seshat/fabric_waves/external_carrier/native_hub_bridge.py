"""Reviewable OUTBOUND half of a real AORUS Hub issuer bridge. NOT WIRED IN.

Status (2026-10-19): this module is a standalone, independently unit-tested
implementation of the "trusted official Hub caller" vertical (G1 requirement 2 in
docs/G1_HUB_BRIDGE_VERTICAL_20261019.md). It is deliberately **not** imported by
``host_cli.py`` or ``host_dispatcher.HostDispatcher``. Two independent gates already
refuse any live native submission today:

* ``host_dispatcher.AiyeExecSubmitter.submit`` unconditionally raises
  ``PROTOCOL_UNVERIFIED``.
* ``host_dispatcher.HostDispatcher.dispatch`` refuses *any* ``isinstance(submitter,
  AiyeExecSubmitter)`` before calling ``.submit`` at all (see
  ``test_live_dispatch_fails_closed_when_caller_protocol_unverified``), independent of
  environment variables or constructor arguments.

This module does not touch either gate and is not reachable from any existing code
path. The exact ``aiye-exec submit`` flag set implemented below (``--agent auto --kind
reasoning --mode audit|code --role <analyze|classify> --ticket ... [--decision-id ...]
--prompt-file ... --max-seconds N --client ... --project-target ...``) was supplied
directly by the task owner in the G1 handoff; it was **not** independently
re-confirmed against ``CALLER_PROTOCOL.md`` or a live ``aiye-exec submit --help`` in
this authoring session, because that file lives outside this worktree's permitted
read scope (see docs/G1_HUB_BRIDGE_VERTICAL_20261019.md, "What was NOT verified").
A coordinator with independent access to CALLER_PROTOCOL.md must confirm the flag set
before anyone wires this module into ``host_cli.py``.

This module also does not implement the INBOUND/verification half (reading a real
``spec.json`` / ``status.json`` / ``receipt.json`` / ``stdout.log`` under the host-owned
jobs root and mapping it onto ``HubJobRecord``): that mapping is security-sensitive and
guessing its field names would be worse than leaving it undone. See the open-questions
doc for what a future ``NativeHubFetcher`` needs.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
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

# Fixed by the owner-supplied contract; never taken from caller input so no argument
# can select a different agent or job kind.
NATIVE_SUBMIT_AGENT = "auto"
NATIVE_SUBMIT_KIND = "reasoning"
NATIVE_ALLOWED_MODES: frozenset[str] = frozenset({"audit", "code"})
# ``--mode read-only`` is explicitly invalid against the real CLI per the owner
# handoff; this module never emits it (``NATIVE_ALLOWED_MODES`` excludes it) and the
# existing ``HubJobSpec.mode`` sentinel ("read-only") is never forwarded as a flag.
_NATIVE_JOB_ID_PATTERN = re.compile(r"^jx-[0-9a-f]{6,40}$")


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
        "--agent",
        NATIVE_SUBMIT_AGENT,
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
    candidate = document.get("job_id", document.get("jx_id"))
    if not isinstance(candidate, str) or not _NATIVE_JOB_ID_PATTERN.fullmatch(candidate):
        return None
    return candidate


@dataclass
class NativeAiyeExecSubmitter:
    """Real ``aiye-exec submit`` caller. NOT wired into HostDispatcher -- see module docstring.

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
    last_result: NativeSubmitResult | None = field(default=None, init=False, repr=False)

    def submit(self, *, spec: HubJobSpec, prompt: bytes) -> None:
        try:
            text = prompt.decode("utf-8")
        except UnicodeDecodeError:
            raise HostBoundaryError("NATIVE_SUBMIT_PROMPT_NOT_UTF8") from None
        scan_text(text, direction="OUTBOUND")
        host_job_id = require_safe_token(
            spec.host_job_id, code="NATIVE_SUBMIT_HOST_JOB_ID_INVALID"
        )
        prompt_path = Path(self.spool_dir) / f"{host_job_id}.prompt.txt"
        atomic_write_bytes(prompt_path, prompt)
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
    "NATIVE_SUBMIT_AGENT",
    "NATIVE_SUBMIT_KIND",
    "NativeAiyeExecSubmitter",
    "NativeSubmitResult",
    "build_native_submit_argv",
]
