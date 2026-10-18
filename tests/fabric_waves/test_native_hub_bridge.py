"""Unit tests for the standalone, NOT-WIRED-IN native Hub submit bridge.

These tests exercise ``native_hub_bridge`` directly -- never through
``HostDispatcher``/``host_cli`` -- because that module is deliberately not reachable
from any existing dispatch path (see its module docstring). A fake ``runner`` stands in
for ``subprocess.run``; nothing here spawns a real process or contacts a Hub.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from seshat.fabric_waves.external_carrier.host_security import HostBoundaryError
from seshat.fabric_waves.external_carrier.hub_protocol import HubTransportError
from seshat.fabric_waves.external_carrier.native_hub_bridge import (
    NATIVE_SUBMIT_AGENT,
    NATIVE_SUBMIT_KIND,
    NativeAiyeExecSubmitter,
    build_native_submit_argv,
)

from .phase_b_harness import make_harness


def _exe(tmp_path: Path) -> Path:
    return tmp_path / "aiye-exec"


def test_argv_matches_owner_contract_and_omits_banned_flags(tmp_path):
    h = make_harness(tmp_path)
    argv = build_native_submit_argv(
        exe=_exe(tmp_path),
        spec=h.spec,
        prompt_path=tmp_path / "spool" / "p.txt",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        max_seconds=120,
    )
    assert argv[0] == str(_exe(tmp_path))
    assert argv[1] == "submit"
    pairs = dict(zip(argv[2::2], argv[3::2], strict=True))
    assert pairs["--agent"] == NATIVE_SUBMIT_AGENT == "auto"
    assert pairs["--kind"] == NATIVE_SUBMIT_KIND == "reasoning"
    assert pairs["--mode"] == "audit"
    assert pairs["--role"] == h.spec.role == "analyze"
    assert pairs["--ticket"] == h.spec.ticket
    assert pairs["--prompt-file"] == str(tmp_path / "spool" / "p.txt")
    assert pairs["--max-seconds"] == "120"
    assert pairs["--client"] == "SESHAT_CARPET"
    assert pairs["--project-target"] == "SESHAT"
    assert "--decision-id" not in pairs
    for banned in (
        "--provider",
        "--job-id",
        "--budget-usd",
        "--max-tokens",
        "--timeout-seconds",
        "--decision",
    ):
        assert banned not in argv


def test_decision_id_included_only_when_given(tmp_path):
    h = make_harness(tmp_path)
    argv = build_native_submit_argv(
        exe=_exe(tmp_path),
        spec=h.spec,
        prompt_path=tmp_path / "spool" / "p.txt",
        mode="code",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        max_seconds=60,
        decision_id="rec-0001",
    )
    i = argv.index("--decision-id")
    assert argv[i + 1] == "rec-0001"


def test_read_only_and_unknown_modes_refused(tmp_path):
    h = make_harness(tmp_path)
    for bad_mode in ("read-only", "", "ADMIN", "audit; rm -rf"):
        with pytest.raises(HostBoundaryError, match="NATIVE_SUBMIT_MODE_INVALID"):
            build_native_submit_argv(
                exe=_exe(tmp_path),
                spec=h.spec,
                prompt_path=tmp_path / "spool" / "p.txt",
                mode=bad_mode,
                client="SESHAT_CARPET",
                project_target="SESHAT",
                max_seconds=60,
            )


def test_unsafe_client_and_project_target_tokens_refused(tmp_path):
    h = make_harness(tmp_path)
    for field_name, value, code in (
        ("client", "--provider=evil", "NATIVE_SUBMIT_CLIENT_INVALID"),
        ("client", "a b", "NATIVE_SUBMIT_CLIENT_INVALID"),
        ("project_target", "../../etc/passwd", "NATIVE_SUBMIT_PROJECT_TARGET_INVALID"),
    ):
        kwargs = {
            "exe": _exe(tmp_path),
            "spec": h.spec,
            "prompt_path": tmp_path / "spool" / "p.txt",
            "mode": "audit",
            "client": "SESHAT_CARPET",
            "project_target": "SESHAT",
            "max_seconds": 60,
        }
        kwargs[field_name] = value
        with pytest.raises(HostBoundaryError, match=code):
            build_native_submit_argv(**kwargs)


def test_relative_exe_and_prompt_path_refused(tmp_path):
    h = make_harness(tmp_path)
    with pytest.raises(HostBoundaryError, match="AIYE_EXEC_PATH_INVALID"):
        build_native_submit_argv(
            exe="aiye-exec",
            spec=h.spec,
            prompt_path=tmp_path / "p.txt",
            mode="audit",
            client="c",
            project_target="p",
            max_seconds=60,
        )
    with pytest.raises(HostBoundaryError, match="NATIVE_SUBMIT_PROMPT_PATH_INVALID"):
        build_native_submit_argv(
            exe=_exe(tmp_path),
            spec=h.spec,
            prompt_path=Path("relative/p.txt"),
            mode="audit",
            client="c",
            project_target="p",
            max_seconds=60,
        )


def test_max_seconds_bounds_and_bool_rejected(tmp_path):
    h = make_harness(tmp_path)
    for bad in (0, -1, 3601, True, False):
        with pytest.raises(HostBoundaryError, match="NATIVE_SUBMIT_MAX_SECONDS_INVALID"):
            build_native_submit_argv(
                exe=_exe(tmp_path),
                spec=h.spec,
                prompt_path=tmp_path / "p.txt",
                mode="audit",
                client="c",
                project_target="p",
                max_seconds=bad,
            )


def test_submit_writes_prompt_file_and_never_puts_prompt_text_in_argv(tmp_path):
    h = make_harness(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"job_id": "jx-abc123"}).encode("utf-8"),
            stderr=b"",
        )

    submitter = NativeAiyeExecSubmitter(
        exe=str(_exe(tmp_path)),
        spool_dir=tmp_path / "spool",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        runner=runner,
    )
    secret_free_prompt = b"Reconcile campus and meteorology branch divergence."
    submitter.submit(spec=h.spec, prompt=secret_free_prompt)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert all(secret_free_prompt.decode() not in token for token in argv)
    prompt_arg = Path(argv[argv.index("--prompt-file") + 1])
    assert prompt_arg.read_bytes() == secret_free_prompt
    assert prompt_arg.is_absolute()
    assert submitter.last_result is not None
    assert submitter.last_result.native_job_id == "jx-abc123"
    assert submitter.last_result.exit_code == 0


def test_submit_refuses_secret_bearing_prompt_before_any_subprocess_call(tmp_path):
    h = make_harness(tmp_path)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        raise AssertionError("must not be called once a secret is detected")

    submitter = NativeAiyeExecSubmitter(
        exe=str(_exe(tmp_path)),
        spool_dir=tmp_path / "spool",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        runner=runner,
    )
    with pytest.raises(HostBoundaryError, match="OUTBOUND_SECRET_DETECTED"):
        submitter.submit(spec=h.spec, prompt=b"sk-abcdefghijklmnopqrstuvwxyz123456")
    assert calls == []
    assert not (tmp_path / "spool").exists() or list((tmp_path / "spool").iterdir()) == []


@pytest.mark.parametrize(
    "runner_factory, expected_code",
    [
        (
            lambda: (lambda argv, **kw: SimpleNamespace(returncode=1, stdout=b"{}", stderr=b"")),
            "SUBMIT_EXIT_AMBIGUOUS",
        ),
        (
            lambda: (lambda argv, **kw: SimpleNamespace(returncode=0, stdout=b"not json", stderr=b"")),
            "SUBMIT_RESPONSE_UNPARSEABLE_AMBIGUOUS",
        ),
        (
            lambda: (lambda argv, **kw: SimpleNamespace(
                returncode=0, stdout=json.dumps({"job_id": "not-a-jx-id"}).encode(), stderr=b""
            )),
            "SUBMIT_RESPONSE_UNPARSEABLE_AMBIGUOUS",
        ),
    ],
)
def test_every_non_clean_outcome_is_ambiguous_never_a_silent_success(
    tmp_path, runner_factory, expected_code
):
    h = make_harness(tmp_path)
    submitter = NativeAiyeExecSubmitter(
        exe=str(_exe(tmp_path)),
        spool_dir=tmp_path / "spool",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        runner=runner_factory(),
    )
    with pytest.raises(HubTransportError, match=expected_code):
        submitter.submit(spec=h.spec, prompt=b"no secrets here")
    assert submitter.last_result is None


def test_timeout_and_oserror_are_ambiguous(tmp_path):
    h = make_harness(tmp_path)

    def timeout_runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))

    submitter = NativeAiyeExecSubmitter(
        exe=str(_exe(tmp_path)),
        spool_dir=tmp_path / "spool",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        runner=timeout_runner,
    )
    with pytest.raises(HubTransportError, match="SUBMIT_TIMEOUT_AMBIGUOUS"):
        submitter.submit(spec=h.spec, prompt=b"no secrets here")
    assert submitter.last_result is None

    def oserror_runner(argv, **kwargs):
        raise OSError("child status unknown")

    submitter2 = NativeAiyeExecSubmitter(
        exe=str(_exe(tmp_path)),
        spool_dir=tmp_path / "spool",
        mode="audit",
        client="SESHAT_CARPET",
        project_target="SESHAT",
        runner=oserror_runner,
    )
    with pytest.raises(HubTransportError, match="SUBMIT_OSERROR_AMBIGUOUS"):
        submitter2.submit(spec=h.spec, prompt=b"no secrets here")
    assert submitter2.last_result is None
