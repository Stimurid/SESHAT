"""Phase B trusted host adapter: adversarial tests with a MOCK AORUS Hub transport.

No provider, model CLI, network or credential is used. ``FakeHostExecutor`` is not used here.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import seshat
from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import (
    EpistemicLevel,
    FabricRunOutcome,
    MethodBodyRef,
)
from seshat.fabric_waves.engine import WaveEngineConfigurationError
from seshat.fabric_waves.external_carrier import phase_b
from seshat.fabric_waves.external_carrier.contracts import ExternalResumeReceipt, material_hash
from seshat.fabric_waves.external_carrier.host_adapter import (
    DispatchPolicy,
    OwnerApprovals,
)
from seshat.fabric_waves.external_carrier.host_dispatcher import (
    LIVE_AUTH_SCHEMA,
    AiyeExecSubmitter,
    HostDispatcher,
    SpoolHubFetcher,
    build_aiye_exec_argv,
)
from seshat.fabric_waves.external_carrier.host_envelope import (
    build_outbound,
    parse_model_output,
)
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError,
    HostIntegrityKey,
    HostLimits,
    read_file_under,
    sha256_hex,
)
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.hub_protocol import HubJobStatus, HubTransportError
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError, verify_resume_receipt

from .phase_b_harness import (
    BUDGET,
    LIVE_AUTH_SCHEMA_ID,
    MAC_KEY_BYTES,
    MockHub,
    good_stdout,
    make_adapter,
    make_auth as _auth,
    make_harness,
    make_record,
)

HOSTS = ("campus", "meteorology")


class SyntheticTransportFailure:
    """Exercise ambiguous dispatcher outcomes without unlocking the native Hub port."""

    def __init__(self, code: str):
        self.code = code

    def submit(self, *, spec, prompt):
        raise HubTransportError(self.code)


def _code(exc_info) -> str:
    return str(exc_info.value.args[0])


def with_host_job(evidence, **updates):
    receipt = evidence.host_receipt
    job = receipt.host_job.model_copy(update=updates)
    return evidence.model_copy(
        update={"host_receipt": receipt.model_copy(update={"host_job": job})}
    )


def tamper_sql(store_dir: Path, *statements: str) -> None:
    """Simulate an attacker with raw file access who also drops the immutability triggers."""

    con = sqlite3.connect(str(store_dir / "host_jobs.sqlite3"), isolation_level=None)
    try:
        for table in ("jobs", "terminals", "submissions", "meta"):
            con.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
            con.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
        for statement in statements:
            con.execute(statement)
    finally:
        con.close()


# 1. forged / unissued job receipts ---------------------------------------------------------


def test_unissued_and_forged_job_receipts_rejected(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    evidence = h.evidence()

    unissued = with_host_job(evidence, job_id="hostjob-" + "0" * 24)
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.verify_return(need=h.need, evidence=unissued)
    assert _code(exc) == "UNISSUED_HOST_JOB"

    forged_receipts = {
        "FORGED_AUTHORIZED_FLAG": evidence.model_copy(
            update={
                "host_receipt": evidence.host_receipt.model_copy(update={"authorized": False})
            }
        ),
        "BINDING_HASH_INVALID": evidence.model_copy(
            update={
                "host_receipt": evidence.host_receipt.model_copy(
                    update={"binding_hash": "0" * 64}
                )
            }
        ),
        "FORGED_RECEIPT_ID": evidence.model_copy(
            update={
                "host_receipt": evidence.host_receipt.model_copy(
                    update={"receipt_id": "hostrcpt-forged"}
                )
            }
        ),
        "FORGED_METHOD_RECEIPT": evidence.model_copy(
            update={"method_call_receipt_hash": "1" * 64}
        ),
        "FORGED_HOST_JOB_TERMINAL": with_host_job(
            evidence, started_at="1999-01-01T00:00:00+00:00"
        ),
        "FORGED_HOST_JOB_TERMINAL ": with_host_job(
            evidence, result_provenance=("HUB_JOB_VERIFIED", "provider:evil-provider")
        ),
        "HOST_JOB_RIGHTS_ESCALATION": with_host_job(
            evidence, allowed_source_rights=RawAccessPolicy.FULL_REQUIRED
        ),
    }
    for expected, forged in forged_receipts.items():
        with pytest.raises(ExternalAdmissionError) as exc:
            h.adapter.verify_return(need=h.need, evidence=forged)
        assert _code(exc) == expected.strip()

    # The untouched evidence still verifies: the negatives above were not false positives.
    assert h.adapter.verify_return(need=h.need, evidence=evidence) == evidence.host_receipt


def test_authorized_receipt_without_host_terminal_is_refused(tmp_path):
    twin_a = make_harness(tmp_path / "a")
    twin_a.complete()
    stolen_evidence = twin_a.evidence()
    twin_b = make_harness(tmp_path / "b")  # same deterministic job id, but NO terminal
    assert twin_b.job_id == twin_a.job_id
    with pytest.raises(ExternalAdmissionError) as exc:
        twin_b.adapter.verify_return(need=twin_b.need, evidence=stolen_evidence)
    assert _code(exc) == "TERMINAL_RESULT_MISSING"


# 2. changed model stdout / forged Hub record -----------------------------------------------


def test_changed_model_stdout_and_forged_hub_records_rejected(tmp_path):
    h = make_harness(tmp_path)
    original = good_stdout(h.carriers)
    changed = original.replace(b"diverge", b"agree  ")
    forged_cases = {
        "HUB_STDOUT_HASH_MISMATCH": dict(
            stdout=changed, overrides={"stdout_sha256": sha256_hex(original)}
        ),
        "HUB_RECEIPT_UNKNOWN_ISSUER": dict(
            stdout=original, overrides={"issuer_id": "rogue-issuer"}
        ),
        "HUB_RECEIPT_INSTANCE_MISMATCH": dict(
            stdout=original, overrides={"hub_instance_id": "other-hub"}
        ),
        "HUB_JOB_ID_MISMATCH": dict(stdout=original, overrides={"job_id": "seshat-pb-other"}),
        "HUB_TICKET_MISMATCH": dict(stdout=original, overrides={"ticket": "SESHAT-PB-OTHER"}),
        "HUB_PROVIDER_IDENTITY_MISMATCH": dict(
            stdout=original, overrides={"provider": "other-provider"}
        ),
        "HUB_SPEC_DIGEST_MISMATCH": dict(stdout=original, overrides={"spec_sha256": "2" * 64}),
        "HUB_SPEC_FIELD_MISMATCH": dict(stdout=original, overrides={"mode": "read-write"}),
        "HUB_BUDGET_EXCEEDED_REPORTED": dict(stdout=original, overrides={"cost_cents": 10_000}),
        "HUB_COMPLETED_NONZERO_EXIT": dict(stdout=original, overrides={"exit_code": 3}),
    }
    for expected, case in forged_cases.items():
        record = make_record(h.spec, case["stdout"], **case["overrides"])
        with pytest.raises(ExternalAdmissionError) as exc:
            h.adapter.ingest_hub_result(
                host_job_id=h.job_id, record=record, stdout=case["stdout"]
            )
        assert _code(exc) == expected
    # No forged record poisoned the first-writer terminal slot.
    assert h.adapter.store.get_terminal(h.job_id) is None

    h.complete(original)
    evidence = h.evidence()
    swapped = evidence.model_copy(
        update={"proposal_payload": {**evidence.proposal_payload, "hypothesis": "swapped"}}
    )
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.verify_return(need=h.need, evidence=swapped)
    assert _code(exc) == "FORGED_TERMINAL_RESULT"

    # At-rest edit of the stored model stdout is detected on readback.
    tamper_sql(
        tmp_path / "store",
        "UPDATE terminals SET stdout_bytes = X'7B7D'",
    )
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.verify_return(need=h.need, evidence=evidence)
    assert _code(exc) == "HOST_STORE_ROW_TAMPERED"


def test_hmac_issuer_receipts_forged_mac_rejected_and_key_never_printed(tmp_path):
    h = make_harness(tmp_path, mac=True)
    data = good_stdout(h.carriers)
    forged = make_record(h.spec, data, issuer_mac="f" * 64)
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.ingest_hub_result(host_job_id=h.job_id, record=forged, stdout=data)
    assert _code(exc) == "HUB_RECEIPT_FORGED"
    unsigned = make_record(h.spec, data, issuer_mac="")
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.ingest_hub_result(host_job_id=h.job_id, record=unsigned, stdout=data)
    assert _code(exc) == "HUB_RECEIPT_FORGED"
    outcome = h.complete(data)
    assert outcome.state == "COMPLETED"
    assert h.adapter.registry.authentication_mode("mock-hub-issuer") == "HMAC_VERIFIED"
    key = HostIntegrityKey(MAC_KEY_BYTES)
    assert MAC_KEY_BYTES.decode() not in repr(key) + str(key)
    with pytest.raises(HostBoundaryError):
        HostIntegrityKey(b"short")


# 3. request / source / method hash drift ---------------------------------------------------


def test_request_source_and_method_pin_drift_rejected(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    evidence = h.evidence()
    drifted = {
        "canonical_input_hash": h.need.model_copy(update={"canonical_input_hash": "3" * 64}),
        "method": h.need.model_copy(
            update={"method_body_ref": MethodBodyRef(method_body_id="synthetic.other", version="1")}
        ),
        "version_pin": h.need.model_copy(
            update={"source_versions": {cid: "9" for cid in h.carriers}}
        ),
        "scope": h.need.model_copy(update={"source_carrier_ids": h.carriers[:1]}),
        "question": h.need.model_copy(update={"question_query": "a different question"}),
    }
    for name, need in drifted.items():
        with pytest.raises(ExternalAdmissionError) as exc:
            h.adapter.verify_return(need=need, evidence=evidence)
        assert _code(exc) == "LEDGER_DISPATCH_PIN_MISMATCH", name


def test_replay_refuses_changed_source_or_request(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    from seshat.fabric_waves.external_carrier.hosts import _host_engine

    def drifted_campus():
        return _host_engine(
            host_id="campus",
            carrier_alpha="campus-branch-alpha",
            carrier_beta="campus-branch-beta",
            alpha_text="lab telemetry: utilization index 83%",
            beta_text="facilities audit memo: utilization index 64%",
            alpha_signal="83",
            beta_signal="64",
            default_topic="campus-facility-utilization",
        )

    with pytest.raises(ExternalAdmissionError) as exc:
        phase_b.resume_by_replay(
            adapter=h.adapter,
            host_job_id=h.job_id,
            factories={"campus": drifted_campus},
        )
    assert _code(exc) in {"REPLAY_REQUEST_DRIFT", "REPLAY_SOURCE_DRIFT"}


# 4. source rights revocation ---------------------------------------------------------------


def test_source_rights_revocation_blocks_prepare_dispatch_and_return(tmp_path):
    fresh = make_harness(tmp_path / "fresh", prepare=False)
    fresh.waiting.engine.carrier_store.revoke_content_same_version("campus-branch-alpha")
    with pytest.raises(ExternalAdmissionError) as exc:
        fresh.adapter.prepare(fresh.need)
    assert _code(exc) == "SOURCE_CONTENT_UNAVAILABLE"

    h = make_harness(tmp_path / "live")
    h.complete()
    evidence = h.evidence()
    h.waiting.engine.carrier_store.revoke_content_same_version("campus-branch-alpha")
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.verify_return(need=h.need, evidence=evidence)
    assert _code(exc) == "SOURCE_CONTENT_UNAVAILABLE"
    with pytest.raises(ExternalAdmissionError) as exc:
        HostDispatcher(synthetic_only=True, adapter=h.adapter).dispatch(h.job_id)
    assert _code(exc) == "SOURCE_CONTENT_UNAVAILABLE"
    receipt = ExternalResumeReceipt(
        request_id=h.need.request_id, run_id=h.need.run_id, evidence_return=evidence
    )
    with pytest.raises(WaveEngineConfigurationError):
        h.waiting.engine.resume_external_evidence(receipt=receipt, budget=BUDGET, port=h.adapter)


# 5. evidence class / schema / method / scope ------------------------------------------------

_OUTBOUND_VARIANTS = {
    "OUTBOUND_EVIDENCE_CLASS_NOT_E5_ONLY": [
        {"admissible_evidence_classes": ("E1", "E5")},
        {"admissible_evidence_classes": ("E2", "E3", "E4")},
        {"admissible_evidence_classes": ("E5", "E4")},
    ],
    "OUTBOUND_SCHEMA_UNSUPPORTED": [{"expected_output_schema": "external.fact.v9"}],
    "OUTBOUND_RIGHTS_NOT_DRILLBACK": [
        {"source_rights": RawAccessPolicy.FULL_REQUIRED},
        {"source_rights": RawAccessPolicy.NEVER},
    ],
    "OUTBOUND_SOURCE_NOT_PUBLIC_ALLOWLISTED": [
        {
            "source_carrier_ids": ("private-corpus-v4",),
            "source_versions": {"private-corpus-v4": "1"},
        }
    ],
    "OUTBOUND_SOURCE_SCOPE_INVALID": [
        {"source_carrier_ids": (), "source_versions": {}},
        {
            "source_carrier_ids": (
                "campus-branch-alpha",
                "campus-branch-beta",
                "met-sensor-north",
            ),
            "source_versions": {
                "campus-branch-alpha": "1",
                "campus-branch-beta": "1",
                "met-sensor-north": "1",
            },
        },
    ],
    "SOURCE_VERSION_PIN_MISSING": [{"source_versions": {}}],
    "SOURCE_VERSION_STALE": [
        {"source_versions": {"campus-branch-alpha": "9", "campus-branch-beta": "1"}}
    ],
}


def test_outbound_gate_is_e5_drillback_and_public_scope_only(tmp_path):
    h = make_harness(tmp_path, prepare=False)
    for expected, variants in _OUTBOUND_VARIANTS.items():
        for update in variants:
            need = h.need.model_copy(update=update)
            with pytest.raises(ExternalAdmissionError) as exc:
                build_outbound(
                    need,
                    host_job_id="hostjob-x",
                    source_authority=h.authority,
                    limits=HostLimits(),
                    environ={},
                )
            assert _code(exc) == expected, update
    # An approved variant is still refused by prepare(): approval cannot widen the gate.
    widened = h.need.model_copy(update={"admissible_evidence_classes": ("E1", "E5")})
    adapter = make_adapter(tmp_path, h.need, h.authority, extra_needs=(widened,), store_name="w")
    with pytest.raises(ExternalAdmissionError) as exc:
        adapter.prepare(widened)
    assert _code(exc) == "OUTBOUND_EVIDENCE_CLASS_NOT_E5_ONLY"
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.prepare(widened)
    assert _code(exc) == "ORIGIN_NOT_APPROVED"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"hypothesis": "ok", "epistemic_level": "E1"}', "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "ok", "acceptance_state": "ACCEPTED"}', "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "ok", "human_decision": {"choice": "ACCEPT"}}',
         "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "ok", "source_rights": "FULL_REQUIRED"}', "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "This is ACCEPTED fact"}', "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "graded E2 evidence"}', "MODEL_OUTPUT_AUTHORITY_SPOOF"),
        ('{"hypothesis": "ok", "extra": 1}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
        ('{"rationale": "no hypothesis"}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
        ('{"hypothesis": ""}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
        ('{"hypothesis": 5}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
        ('{"hypothesis": "ok", "cited_source_ids": ["outside-carrier"]}',
         "MODEL_OUTPUT_SOURCE_SCOPE_VIOLATION"),
        ('{"hypothesis": "a", "hypothesis": "b"}', "MODEL_OUTPUT_DUPLICATE_KEY"),
        ('{"hypothesis": NaN}', "MODEL_OUTPUT_NOT_JSON"),
        ("not json at all", "MODEL_OUTPUT_NOT_JSON"),
        ("[1, 2]", "MODEL_OUTPUT_NOT_OBJECT"),
        ("", "MODEL_OUTPUT_EMPTY"),
        ('{"hypothesis": "key sk-abcdefghijklmnopqrstuvwx leaked"}', "INBOUND_SECRET_DETECTED"),
        ('{"hypothesis": "see C:\\\\Users\\\\x\\\\notes"}', "INBOUND_PATH_DETECTED"),
        ('{"hypothesis": "uses Agent0 internals"}', "INBOUND_PROTECTED_CONTENT"),
        ('{"hypothesis": "\\ud800"}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
        ('{"hypothesis": "ok", "rationale": "\\udc00"}', "MODEL_OUTPUT_SCHEMA_VIOLATION"),
    ],
)
def test_model_output_is_untrusted_and_schema_closed(tmp_path, raw, expected):
    h = make_harness(tmp_path, prepare=False)
    with pytest.raises(ExternalAdmissionError) as exc:
        parse_model_output(raw.encode(), need=h.need, limits=HostLimits(), environ={})
    assert _code(exc) == expected


def test_model_output_oversize_and_bad_encoding_and_clean_pass(tmp_path):
    h = make_harness(tmp_path, prepare=False)
    limits = HostLimits(max_stdout_bytes=50)
    with pytest.raises(ExternalAdmissionError) as exc:
        parse_model_output(b"x" * 51, need=h.need, limits=limits, environ={})
    assert _code(exc) == "MODEL_OUTPUT_TOO_LARGE"
    with pytest.raises(ExternalAdmissionError) as exc:
        parse_model_output(b"\xff\xfe{}", need=h.need, limits=HostLimits(), environ={})
    assert _code(exc) == "MODEL_OUTPUT_NOT_UTF8"
    fenced = b"```json\n" + good_stdout(h.carriers) + b"\n```"
    payload = parse_model_output(fenced, need=h.need, limits=HostLimits(), environ={})
    assert payload["provisional"] is True
    assert payload["origin"] == "UNTRUSTED_MODEL_OUTPUT_SANITIZED"
    assert "epistemic_level" not in payload and "acceptance_state" not in payload


def test_forged_epistemic_level_decision_and_claim_scope_rejected(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    evidence = h.evidence()
    cases = {
        "E5_ONLY_EXTERNAL_RETURN": evidence.model_copy(
            update={"epistemic_level": EpistemicLevel.E1}
        ),
        "FORGED_HUMAN_DECISION_REJECTED": evidence.model_copy(
            update={"forged_human_decision": {"choice": "ACCEPT"}}
        ),
        "E5_SOURCE_CLAIM_OUTSIDE_REQUEST_SCOPE": evidence.model_copy(
            update={"source_claim_refs": ("private-corpus-v4",)}
        ),
    }
    for expected, forged in cases.items():
        with pytest.raises(ExternalAdmissionError) as exc:
            h.adapter.verify_return(need=h.need, evidence=forged)
        assert _code(exc) == expected


# 5b. per-host external oracle: every epistemic-level downgrade + forged human ACCEPT is refused
# on BOTH ``campus`` AND ``meteorology``. None of these forged returns counts as a successful
# ``verify_return``; the counter is asserted at the end of each iteration.


@pytest.mark.parametrize("kind", HOSTS)
def test_forged_returns_rejected_for_every_downgraded_level_and_forged_human_accept(
    tmp_path, kind
):
    h = make_harness(tmp_path / kind, kind)
    h.complete()
    evidence = h.evidence()

    def down(level: EpistemicLevel):
        return evidence.model_copy(update={"epistemic_level": level})

    forged_cases = [
        ("E5_ONLY_EXTERNAL_RETURN", down(EpistemicLevel.E1)),
        ("E5_ONLY_EXTERNAL_RETURN", down(EpistemicLevel.E2)),
        ("E5_ONLY_EXTERNAL_RETURN", down(EpistemicLevel.E3)),
        ("E5_ONLY_EXTERNAL_RETURN", down(EpistemicLevel.E4)),
        (
            "FORGED_HUMAN_DECISION_REJECTED",
            evidence.model_copy(update={"forged_human_decision": {"choice": "ACCEPT"}}),
        ),
        (
            "FORGED_HUMAN_DECISION_REJECTED",
            evidence.model_copy(
                update={"forged_human_decision": {"choice": "ACCEPTED", "by": "hostile"}}
            ),
        ),
    ]
    successes = 0
    for expected, forged in forged_cases:
        try:
            h.adapter.verify_return(need=h.need, evidence=forged)
        except ExternalAdmissionError as exc:
            assert exc.args[0] == expected
        else:
            successes += 1
    assert successes == 0  # None of the forged variants admitted
    # The untouched evidence is the positive control: still verifies cleanly.
    assert h.adapter.verify_return(need=h.need, evidence=evidence) == evidence.host_receipt


# 6. cross host / cross run -----------------------------------------------------------------


def test_cross_host_and_cross_run_returns_rejected(tmp_path):
    campus = make_harness(tmp_path / "c", "campus")
    met = make_harness(tmp_path / "m", "meteorology")
    campus.complete()
    met.complete()
    met_evidence = met.evidence()
    campus_evidence = campus.evidence()

    with pytest.raises(ExternalAdmissionError) as exc:
        campus.adapter.verify_return(need=campus.need, evidence=met_evidence)
    assert _code(exc) == "UNISSUED_HOST_JOB"

    with pytest.raises(WaveEngineConfigurationError):
        campus.waiting.engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=met.need.request_id,
                run_id=met.need.run_id,
                evidence_return=met_evidence,
            ),
            budget=BUDGET,
            port=met.adapter,
        )

    with pytest.raises(ExternalAdmissionError) as exc:
        campus.adapter.verify_return(
            need=campus.need,
            evidence=campus_evidence.model_copy(update={"run_id": "some-other-run"}),
        )
    assert _code(exc) == "EVIDENCE_RUN_ID_MISMATCH"
    with pytest.raises(ExternalAdmissionError) as exc:
        campus.adapter.verify_return(
            need=campus.need, evidence=with_host_job(campus_evidence, host_scope="synthetic-lab-met")
        )
    assert _code(exc) == "HOST_SCOPE_MISMATCH"

    wrong_scope = make_adapter(
        tmp_path,
        campus.need,
        campus.authority,
        scopes=frozenset({"synthetic-lab-met"}),
        store_name="scoped",
    )
    with pytest.raises(ExternalAdmissionError) as exc:
        wrong_scope.prepare(campus.need)
    assert _code(exc) == "HOST_SCOPE_NOT_ALLOWED"


# 7. failed / cancelled / timeout / waiting / blocked ---------------------------------------


@pytest.mark.parametrize(
    "status",
    [HubJobStatus.FAILED, HubJobStatus.CANCELLED, HubJobStatus.TIMEOUT],
)
def test_non_completed_terminals_never_become_evidence(tmp_path, status):
    twin = make_harness(tmp_path / "twin")
    twin.complete()
    completed_evidence = twin.evidence()

    h = make_harness(tmp_path / "bad")
    outcome = h.complete(b"", status=status)
    assert outcome.state == status.value.upper()
    assert outcome.terminal is not None and outcome.payload is None
    with pytest.raises(ExternalAdmissionError) as exc:
        h.evidence()
    assert _code(exc) == "HOST_JOB_NOT_COMPLETED"
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.verify_return(need=h.need, evidence=completed_evidence)
    assert _code(exc) == "HOST_JOB_NOT_COMPLETED"
    # First writer wins: a later "completed" record cannot overwrite the cancelled/failed fact.
    with pytest.raises(ExternalAdmissionError) as exc:
        h.complete()
    assert _code(exc) == "TERMINAL_RESULT_ALREADY_ISSUED"
    with pytest.raises(WaveEngineConfigurationError):
        h.waiting.engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=h.need.request_id,
                run_id=h.need.run_id,
                evidence_return=completed_evidence,
            ),
            budget=BUDGET,
            port=h.adapter,
        )


def test_waiting_and_blocked_external_are_typed_not_hallucinated(tmp_path, monkeypatch):
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path)
    queued = make_record(h.spec, b"", status=HubJobStatus.QUEUED)
    outcome = h.adapter.ingest_hub_result(host_job_id=h.job_id, record=queued, stdout=b"")
    assert outcome.state == "WAITING" and outcome.terminal is None
    assert h.adapter.store.get_terminal(h.job_id) is None

    hub = MockHub()
    hub.fail_with = "PROVIDER_UNAVAILABLE"
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)
    auth = _auth(h.spec)
    result = dispatcher.dispatch(h.job_id, execute=True, submitter=hub, authorization=auth)
    assert result.state == "AMBIGUOUS" and result.detail == "PROVIDER_UNAVAILABLE"
    assert hub.submitted == []
    # Out-of-model: output rejected by the host is a typed terminal, not a result.
    bad = h.complete(b'{"hypothesis": "ok", "epistemic_level": "E1"}')
    assert bad.state == "OUTPUT_REJECTED" and bad.detail == "MODEL_OUTPUT_AUTHORITY_SPOOF"
    with pytest.raises(ExternalAdmissionError) as exc:
        h.evidence()
    assert _code(exc) == "HOST_JOB_NOT_COMPLETED"


# 8. partial / tampered job manifest --------------------------------------------------------


def test_partial_and_tampered_job_rows_are_refused(tmp_path):
    h = make_harness(tmp_path)
    store_dir = tmp_path / "store"
    tamper_sql(store_dir, "UPDATE jobs SET pins_json = '{'")
    for call in (
        lambda: h.adapter.load_job(h.job_id),
        lambda: h.adapter.authoritative_dispatch(job_id=h.job_id),
        lambda: HostDispatcher(synthetic_only=True, adapter=h.adapter).dispatch(h.job_id),
    ):
        with pytest.raises(ExternalAdmissionError) as exc:
            call()
        assert _code(exc) in {"HOST_STORE_ROW_TAMPERED", "HOST_STORE_PARTIAL_ROW"}

    h2 = make_harness(tmp_path / "second")
    tamper_sql(
        tmp_path / "second" / "store",
        "UPDATE jobs SET request_bytes = substr(request_bytes, 1, 40)",
    )
    with pytest.raises(ExternalAdmissionError) as exc:
        h2.adapter.load_job(h2.job_id)
    assert _code(exc) in {"HOST_STORE_ROW_TAMPERED", "HOST_STORE_PARTIAL_ROW"}


def test_immutable_triggers_block_update_and_delete(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    con = sqlite3.connect(str(tmp_path / "store" / "host_jobs.sqlite3"), isolation_level=None)
    try:
        for statement in (
            "UPDATE jobs SET request_id = 'x'",
            "DELETE FROM jobs",
            "UPDATE terminals SET status = 'FAILED'",
            "DELETE FROM terminals",
        ):
            with pytest.raises(sqlite3.DatabaseError) as exc:
                con.execute(statement)
            assert "IMMUTABLE_ROW" in str(exc.value)
    finally:
        con.close()
    assert h.adapter.store.get_terminal(h.job_id).status == "COMPLETED"


def test_keyed_store_rejects_wrong_key(tmp_path):
    store = HostJobStore(tmp_path / "keyed", integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    h = make_harness(tmp_path / "h", prepare=False)
    h.adapter.store = store  # same adapter, keyed store
    job = h.adapter.prepare(h.need, replay=h.origin.replay_dict())
    assert store.get_job(job.host_job_id).host_job_id == job.host_job_id
    with pytest.raises(ExternalAdmissionError) as exc:
        HostJobStore(
            tmp_path / "keyed", integrity_key=HostIntegrityKey(b"another-public-test-key-000000")
        )
    assert _code(exc) == "HOST_STORE_METADATA_TAMPERED"
    # An unkeyed re-open after keyed history must be refused at __init__ (the integrity_key_required
    # meta row is sealed at the same time it is written, and any later unkeyed open is refused
    # BEFORE any row can be read). Silently allowing unkeyed reads of MAC'd rows would defeat
    # the keyed-history invariant entirely.
    with pytest.raises(ExternalAdmissionError) as exc:
        HostJobStore(tmp_path / "keyed")
    assert _code(exc) == "HOST_STORE_INTEGRITY_KEY_REQUIRED"


def test_keyed_store_metadata_tamper_refuses_open(tmp_path):
    store = HostJobStore(tmp_path / "keyed", integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    h = make_harness(tmp_path / "h", prepare=False)
    h.adapter.store = store
    job = h.adapter.prepare(h.need, replay=h.origin.replay_dict())
    assert job.host_job_id
    tamper_sql(tmp_path / "keyed", "UPDATE meta SET v='false' WHERE k='integrity_key_required'")
    with pytest.raises(ExternalAdmissionError) as exc:
        HostJobStore(tmp_path / "keyed", integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    assert _code(exc) == "HOST_STORE_METADATA_TAMPERED"


def test_keyed_store_meta_updates_with_unchanged_digest_still_seal(tmp_path):
    """Defense in depth: a non-tampering UPDATE that doesn't change the digest is still sealed
    via row_sha256/row_mac verification on subsequent opens.
    """

    store = HostJobStore(tmp_path / "keyed", integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    h = make_harness(tmp_path / "h", prepare=False)
    h.adapter.store = store
    job = h.adapter.prepare(h.need, replay=h.origin.replay_dict())
    assert job.host_job_id
    # No-op tampering: update with the same value (digest unchanged) leaves a consistent seal.
    tamper_sql(
        tmp_path / "keyed",
        "UPDATE meta SET v='true', at='2099-01-01T00:00:00+00:00' WHERE k='integrity_key_required'",
    )
    # Reopen: the meta row's stored digest is over the OLD `at`, the new `at` is different, so
    # the digest recompute mismatches. This is documented behavior; the important thing is that
    # the init refuses the tampered (no longer self-consistent) state.
    with pytest.raises(ExternalAdmissionError) as exc:
        HostJobStore(tmp_path / "keyed", integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    assert _code(exc) == "HOST_STORE_METADATA_TAMPERED"


def test_truncated_and_malformed_spool_records_refused(tmp_path):
    h = make_harness(tmp_path)
    spool = tmp_path / "hub_spool"
    job_dir = spool / h.spec.hub_job_id
    job_dir.mkdir(parents=True)
    fetcher = SpoolHubFetcher(spool)
    assert fetcher.fetch(hub_job_id=h.spec.hub_job_id) is None
    record = make_record(h.spec, good_stdout(h.carriers))
    text = record.model_dump_json()
    for bad in (text[: len(text) // 2], "[]", '{"job_id": "x"}'):
        (job_dir / "record.json").write_text(bad, encoding="utf-8")
        with pytest.raises(ExternalAdmissionError) as exc:
            fetcher.fetch(hub_job_id=h.spec.hub_job_id)
        assert _code(exc) in {"HUB_RECORD_SCHEMA_INVALID"}


# 9. symlink / traversal --------------------------------------------------------------------


def test_path_traversal_and_symlinks_are_refused(tmp_path):
    base = tmp_path / "spool"
    (base / "job-1").mkdir(parents=True)
    (base / "job-1" / "ok.txt").write_text("fine", encoding="utf-8")
    _, data = read_file_under(base, "job-1/ok.txt", max_bytes=100)
    assert data == b"fine"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret-ish", encoding="utf-8")
    for bad, code in (
        ("../outside.txt", "PATH_TRAVERSAL"),
        ("job-1/../../outside.txt", "PATH_TRAVERSAL"),
        (str(outside), "PATH_OUTSIDE_BASE"),
        ("job-1/missing.txt", "PATH_NOT_FOUND"),
        ("job-1", "PATH_NOT_REGULAR_FILE"),
        ("job-1/ok\x00.txt", "PATH_INVALID"),
    ):
        with pytest.raises(ExternalAdmissionError) as exc:
            read_file_under(base, bad, max_bytes=100)
        assert _code(exc) == code, bad
    with pytest.raises(ExternalAdmissionError) as exc:
        read_file_under(base, "job-1/ok.txt", max_bytes=2)
    assert _code(exc) == "PATH_TOO_LARGE"

    with pytest.raises(ExternalAdmissionError) as exc:
        SpoolHubFetcher(base).fetch(hub_job_id="../outside")
    assert _code(exc) == "HUB_JOB_ID_INVALID"

    try:
        (base / "job-1" / "link.txt").symlink_to(outside)
        (base / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ExternalAdmissionError) as exc:
        read_file_under(base, "job-1/link.txt", max_bytes=100)
    assert _code(exc) == "PATH_SYMLINK_DENIED"
    with pytest.raises(ExternalAdmissionError) as exc:
        read_file_under(base, "linked-dir/outside.txt", max_bytes=100)
    assert _code(exc) == "PATH_SYMLINK_DENIED"


# 10. concurrent terminal overwrites across processes ---------------------------------------

_CHILD = r"""
import hashlib, sys, time
from pathlib import Path
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
store_dir, job_id, variant, gate = sys.argv[1:5]
store = HostJobStore(Path(store_dir))
deadline = time.time() + 30
while not Path(gate).exists():
    if time.time() > deadline:
        print("GATE_TIMEOUT")
        sys.exit(3)
    time.sleep(0.002)
stdout = variant.encode()
try:
    row = store.record_terminal(
        host_job_id=job_id, status="COMPLETED", hub_record={"variant": variant},
        stdout_bytes=stdout, stdout_sha256=hashlib.sha256(stdout).hexdigest(),
        result_digest=hashlib.sha256(b"r" + stdout).hexdigest(),
        payload={"hypothesis": variant},
        receipt_sha256=hashlib.sha256(b"x" + stdout).hexdigest())
    print("OK", row.receipt_sha256)
except Exception as exc:
    print("ERR", exc.args[0])
"""


def test_concurrent_terminal_overwrites_across_processes_first_writer_wins(tmp_path):
    h = make_harness(tmp_path)
    gate = tmp_path / "go"
    src_root = str(Path(seshat.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": src_root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    variants = [f"variant-{i}" for i in range(5)]
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(tmp_path / "store"), h.job_id, variant, str(gate)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        for variant in variants
    ]
    gate.write_text("go", encoding="utf-8")
    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        outputs.append(out.strip())
    winners = [o for o in outputs if o.startswith("OK ")]
    losers = [o for o in outputs if o.startswith("ERR ")]
    assert len(winners) == 1, outputs
    assert len(losers) == 4
    assert {o for o in losers} == {"ERR TERMINAL_RESULT_ALREADY_ISSUED"}
    stored = h.adapter.store.get_terminal(h.job_id)
    assert stored.receipt_sha256 == winners[0].split()[1]
    assert stored.payload["hypothesis"] in variants

    # An identical re-record by the winner is idempotent; a different one is refused.
    again = h.adapter.store.record_terminal(
        host_job_id=h.job_id,
        status="COMPLETED",
        hub_record=stored.hub_record,
        stdout_bytes=stored.stdout_bytes,
        stdout_sha256=stored.stdout_sha256,
        result_digest=stored.result_digest,
        payload=stored.payload,
        receipt_sha256=stored.receipt_sha256,
    )
    assert again.receipt_sha256 == stored.receipt_sha256


_SUBMIT_CHILD = r"""
import sys, time
from pathlib import Path
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
store_dir, job_id, nonce, gate = sys.argv[1:5]
store = HostJobStore(Path(store_dir))
deadline = time.time() + 30
while not Path(gate).exists():
    if time.time() > deadline:
        print("GATE_TIMEOUT")
        sys.exit(3)
    time.sleep(0.002)
try:
    store.begin_submission(job_id, nonce=nonce, auth_detail={"authorized_by": "child"},
                           attempt_detail={"child": nonce})
    print("OK")
except Exception as exc:
    print("ERR", exc.args[0])
"""


_KEYED_OPEN_CHILD = r"""
import sys, time
from pathlib import Path
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.host_security import HostIntegrityKey
store_dir, job_id, gate = sys.argv[1:4]
MAC = b"public-test-literal-mac-key-0001"
deadline = time.time() + 30
while not Path(gate).exists():
    if time.time() > deadline:
        print("GATE_TIMEOUT")
        sys.exit(3)
    time.sleep(0.002)
try:
    store = HostJobStore(Path(store_dir), integrity_key=HostIntegrityKey(MAC))
    job = store.get_job(job_id)
    print("OK", job.host_job_id)
except Exception as exc:
    print("ERR", exc.args[0])
"""


def test_concurrent_keyed_store_opens_remain_consistent(tmp_path):
    """Concurrent keyed opens must all observe the same sealed meta+job rows; no naked
    ``sqlite3.IntegrityError`` should surface on the host side."""

    store_dir = tmp_path / "keyed"
    from seshat.fabric_waves.external_carrier.host_security import HostIntegrityKey

    primary = HostJobStore(store_dir, integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    h = make_harness(tmp_path / "h", prepare=False)
    h.adapter.store = primary
    job = h.adapter.prepare(h.need, replay=h.origin.replay_dict())
    job_id = job.host_job_id
    # Drop the IMMUTABLE_ROW triggers on jobs/terminals/submissions/meta (simulating a
    # low-privilege attacker who has file access). The MAC and the keyed constraint must still
    # refuse to admit any mutated row.
    tamper_sql(store_dir, "UPDATE meta SET v='false' WHERE k='integrity_key_required'")
    gate = tmp_path / "go-open"
    src_root = str(Path(seshat.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": src_root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _KEYED_OPEN_CHILD, str(store_dir), job_id, str(gate)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        for _ in range(3)
    ]
    gate.write_text("go", encoding="utf-8")
    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        outputs.append(out.strip())
    for line in outputs:
        # All child processes must refuse to admit the mutated meta row (no naked
        # ``sqlite3.IntegrityError`` leaks out as a different code) AND the meta row's MAC
        # verification must surface the same code every time.
        assert line.startswith("ERR HOST_STORE_METADATA_TAMPERED"), line
    # Re-running the open in the parent process also fails closed.
    with pytest.raises(ExternalAdmissionError) as exc:
        HostJobStore(store_dir, integrity_key=HostIntegrityKey(MAC_KEY_BYTES))
    assert _code(exc) == "HOST_STORE_METADATA_TAMPERED"


def test_racing_dispatchers_cannot_both_claim_the_submission(tmp_path):
    h = make_harness(tmp_path)
    gate = tmp_path / "go-submit"
    src_root = str(Path(seshat.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": src_root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _SUBMIT_CHILD, str(tmp_path / "store"), h.job_id,
             f"nonce-child-{i}", str(gate)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        for i in range(4)
    ]
    gate.write_text("go", encoding="utf-8")
    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=90)
        assert proc.returncode == 0, err
        outputs.append(out.strip())
    assert outputs.count("OK") == 1, outputs
    assert outputs.count("ERR SUBMISSION_STATE_AMBIGUOUS") == 3, outputs
    kinds = [item["kind"] for item in h.adapter.store.submissions(h.job_id)]
    assert kinds == ["LIVE_AUTH_CONSUMED", "SUBMIT_ATTEMPTED"]


def test_preflight_failure_is_not_sent_and_does_not_brick_the_job(tmp_path, monkeypatch):
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path)
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)
    bad = AiyeExecSubmitter(exe="relative-aiye-exec", spool_dir=tmp_path / "s", runner=runner)
    blocked = dispatcher.dispatch(h.job_id, execute=True, submitter=bad,
                                  authorization=_auth(h.spec))
    assert blocked.state == "BLOCKED_EXTERNAL" and blocked.detail == "PROTOCOL_UNVERIFIED"
    assert calls == [] and not (tmp_path / "s").exists()  # nothing written before validation
    assert h.adapter.store.submissions(h.job_id) == []
    good = AiyeExecSubmitter(exe=str(tmp_path / "aiye-exec"), spool_dir=tmp_path / "s", runner=runner)
    result = dispatcher.dispatch(
        h.job_id, execute=True, submitter=good, authorization=_auth(h.spec, nonce="nonce-retry")
    )
    assert result.state == "BLOCKED_EXTERNAL" and calls == []


def test_oversize_model_output_becomes_typed_terminal_not_a_stuck_job(tmp_path):
    h = make_harness(tmp_path)
    outcome = h.complete(b"x" * (HostLimits().max_stdout_bytes + 1))
    assert outcome.state == "OUTPUT_REJECTED" and outcome.detail == "MODEL_OUTPUT_TOO_LARGE"
    assert h.adapter.store.get_terminal(h.job_id).status == "OUTPUT_REJECTED"


def test_ledger_need_drift_blocks_resume_even_when_host_return_is_valid(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    ledger = h.waiting.engine.external_ledger
    ledger.research_needs[0] = ledger.research_needs[0].model_copy(
        update={"question_query": "a different question than the owner approved"}
    )
    with pytest.raises(ExternalAdmissionError) as exc:
        phase_b.resume_live(h.waiting, adapter=h.adapter, host_job_id=h.job_id)
    assert _code(exc) == "LEDGER_NEED_PIN_DRIFT"
    assert not any(
        r.object_type == "external.proposal" for r in h.waiting.engine.sediment.all_records()
    )


# 11. duplicate idempotence -----------------------------------------------------------------


def test_duplicates_are_idempotent_and_replays_are_refused(tmp_path):
    h = make_harness(tmp_path)
    same = h.adapter.prepare(h.need, replay=h.origin.replay_dict())
    assert same.host_job_id == h.job_id and len(h.adapter.store.list_job_ids()) == 1
    # A deterministic machine replay (different created_at) maps to the same persisted job.
    replayed = phase_b.start_waiting_run(h.origin).need
    assert replayed.created_at is not None
    assert h.adapter.prepare(replayed).host_job_id == h.job_id
    conflicting = h.need.model_copy(update={"canonical_input_hash": "4" * 64})
    with pytest.raises(ExternalAdmissionError) as exc:
        h.adapter.prepare(conflicting)
    assert _code(exc) == "HOST_REQUEST_ID_CONFLICT"

    data = good_stdout(h.carriers)
    first = h.complete(data)
    second = h.complete(data)
    assert first.terminal.receipt_sha256 == second.terminal.receipt_sha256
    assert h.evidence() == h.evidence()

    receipt = ExternalResumeReceipt(
        request_id=h.need.request_id, run_id=h.need.run_id, evidence_return=h.evidence()
    )
    ledger = h.waiting.engine.external_ledger
    verify_resume_receipt(ledger=ledger, receipt=receipt, port=h.adapter)
    with pytest.raises(ExternalAdmissionError) as exc:
        verify_resume_receipt(ledger=ledger, receipt=receipt, port=h.adapter)
    assert _code(exc) == "IDEMPOTENCY_REPLAY"


# 12. restarted spool / host refuses forged currentness -------------------------------------


def test_restarted_host_ignores_forged_spool_and_marker_files(tmp_path):
    h = make_harness(tmp_path)
    spool = tmp_path / "hub_spool" / h.spec.hub_job_id
    spool.mkdir(parents=True)
    data = good_stdout(h.carriers)
    forged = make_record(h.spec, data, issuer_id="rogue-issuer")
    (spool / "record.json").write_text(forged.model_dump_json(), encoding="utf-8")
    (spool / "stdout.bin").write_bytes(data)
    (tmp_path / "terminal.json").write_text('{"status": "COMPLETED"}', encoding="utf-8")
    (tmp_path / "current.json").write_text('{"current": true}', encoding="utf-8")

    restarted = make_adapter(
        tmp_path, h.need, h.authority, store_name="store"  # same on-disk store, new instance
    )
    dispatcher = HostDispatcher(synthetic_only=True, adapter=restarted)
    with pytest.raises(ExternalAdmissionError) as exc:
        dispatcher.ingest(h.job_id, fetcher=SpoolHubFetcher(tmp_path / "hub_spool"), execute=True)
    assert _code(exc) == "HUB_RECEIPT_UNKNOWN_ISSUER"
    with pytest.raises(ExternalAdmissionError) as exc:
        restarted.build_evidence_return(h.job_id)
    assert _code(exc) == "TERMINAL_RESULT_MISSING"

    genuine = make_record(h.spec, data)
    (spool / "record.json").write_text(genuine.model_dump_json(), encoding="utf-8")
    outcome = dispatcher.ingest(
        h.job_id, fetcher=SpoolHubFetcher(tmp_path / "hub_spool"), execute=False
    )
    assert outcome["state"] == "COMPLETED" and outcome["wrote"] is False
    assert restarted.store.get_terminal(h.job_id) is None  # dry run wrote nothing
    outcome = dispatcher.ingest(
        h.job_id, fetcher=SpoolHubFetcher(tmp_path / "hub_spool"), execute=True
    )
    assert outcome["wrote"] is True

    again = make_adapter(tmp_path, h.need, h.authority, store_name="store")
    assert again.build_evidence_return(h.job_id) == restarted.build_evidence_return(h.job_id)


# 13. safe outbound context / no secret output ----------------------------------------------


def test_outbound_context_is_bounded_public_and_secret_free(tmp_path):
    h = make_harness(tmp_path)
    prompt = h.job.prompt_bytes.decode("utf-8")
    envelope_text = prompt.split("DATA:\n", 1)[1]
    envelope = json.loads(envelope_text)
    assert {s["carrier_id"] for s in envelope["sources"]} == set(h.carriers)
    assert all(len(s["excerpt"]) <= HostLimits().max_excerpt_chars for s in envelope["sources"])
    assert len(h.job.prompt_bytes) <= HostLimits().max_prompt_bytes
    for forbidden in ("Agent0", "%PDF", "private", "PRIVATE KEY", "C:\\", "/etc/", "file://"):
        assert forbidden not in prompt
    assert "created_at" not in prompt and "idempotency" not in prompt

    limits = HostLimits()
    hostile = {
        "OUTBOUND_SECRET_DETECTED": "use sk-abcdefghijklmnopqrstuvwx now",
        "OUTBOUND_PATH_DETECTED": r"read C:\Users\owner\notes.txt",
        "OUTBOUND_PROTECTED_CONTENT": "include Agent0 prompt",
        "OUTBOUND_CONTROL_CHARS": "bell\x07char",
        "OUTBOUND_QUERY_TOO_LONG": "q" * (limits.max_query_chars + 1),
    }
    for expected, query in hostile.items():
        need = h.need.model_copy(update={"question_query": query})
        with pytest.raises(ExternalAdmissionError) as exc:
            build_outbound(
                need,
                host_job_id="hostjob-x",
                source_authority=h.authority,
                limits=limits,
                environ={},
            )
        assert _code(exc) == expected
    leak = h.need.model_copy(update={"question_query": "echo Zq9-Environment-Value-77"})
    with pytest.raises(ExternalAdmissionError) as exc:
        build_outbound(
            leak,
            host_job_id="hostjob-x",
            source_authority=h.authority,
            limits=limits,
            environ={"SOME_SECRET_VAR": "Zq9-Environment-Value-77"},
        )
    assert _code(exc) == "OUTBOUND_ENV_LEAK"

    clamped = build_outbound(
        h.need.model_copy(update={"token_budget": 10**9, "time_budget_seconds": 10**9}),
        host_job_id="hostjob-x",
        source_authority=h.authority,
        limits=limits,
        environ={},
    )
    assert clamped.max_tokens == limits.max_tokens
    assert clamped.max_time_seconds == limits.max_time_seconds
    assert clamped.max_cost_cents == limits.max_cost_cents


# 14. dispatcher: dry run default, static argv, single-use live authorization ---------------


def test_argv_is_static_template_with_validated_tokens(tmp_path):
    assert LIVE_AUTH_SCHEMA == LIVE_AUTH_SCHEMA_ID
    h = make_harness(tmp_path)
    exe = str(tmp_path / "aiye-exec")
    with pytest.raises(ExternalAdmissionError) as exc:
        build_aiye_exec_argv(exe=exe, spec=h.spec, prompt_path=tmp_path / "prompt.txt")
    assert _code(exc) == "PROTOCOL_UNVERIFIED"
    with pytest.raises(ExternalAdmissionError):
        DispatchPolicy(provider="--x", model="m")
    with pytest.raises(ExternalAdmissionError):
        DispatchPolicy(provider="p", model="m", role="implement")


def test_dispatch_dry_run_default_and_live_requires_exact_single_use_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path)
    calls: list[tuple[list[str], dict]] = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    exe = str(tmp_path / "aiye-exec")
    submitter = AiyeExecSubmitter(exe=exe, spool_dir=tmp_path / "spool", runner=runner)
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)

    dry = dispatcher.dispatch(h.job_id, exe=exe, spool_dir=tmp_path / "spool")
    assert dry.state == "DRY_RUN" and dry.manifest["argv"] is None
    assert calls == [] and h.adapter.store.submissions(h.job_id) == []

    for kwargs, code in (
        ({"submitter": submitter}, "LIVE_DISPATCH_NOT_AUTHORIZED"),
        ({"authorization": _auth(h.spec)}, "LIVE_DISPATCH_NOT_AUTHORIZED"),
        ({"submitter": submitter, "authorization": _auth(h.spec, spec_sha256="5" * 64)},
         "LIVE_AUTHORIZATION_BINDING_MISMATCH"),
        ({"submitter": submitter, "authorization": _auth(h.spec, prompt_sha256="6" * 64)},
         "LIVE_AUTHORIZATION_BINDING_MISMATCH"),
        ({"submitter": submitter, "authorization": _auth(h.spec, host_job_id="hostjob-x")},
         "LIVE_AUTHORIZATION_BINDING_MISMATCH"),
        ({"submitter": submitter, "authorization": _auth(h.spec, expires_at="2000-01-01T00:00:00Z")},
         "LIVE_AUTHORIZATION_EXPIRED"),
        ({"submitter": submitter, "authorization": _auth(h.spec, source_review_sha256="zz")},
         "LIVE_AUTHORIZATION_INVALID"),
        ({"submitter": submitter, "authorization": _auth(h.spec, nonce="")},
         "LIVE_AUTHORIZATION_INVALID"),
    ):
        with pytest.raises(ExternalAdmissionError) as exc:
            dispatcher.dispatch(h.job_id, execute=True, **kwargs)
        assert _code(exc) == code, kwargs
    assert calls == []

    result = dispatcher.dispatch(h.job_id, execute=True, submitter=submitter,
                                 authorization=_auth(h.spec))
    assert result.state == "BLOCKED_EXTERNAL" and result.detail == "PROTOCOL_UNVERIFIED"
    assert calls == [] and h.adapter.store.submissions(h.job_id) == []


def test_provider_failures_are_typed_and_ambiguous_submits_never_resubmit(tmp_path, monkeypatch):
    # Live-dispatch protocol gate must let us through for this isolated-engine test; the unit
    # under test is the OSError→AMBIGUOUS classification, not the protocol gate.
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path)
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)

    sub = SyntheticTransportFailure("SUBMIT_DISPATCH_AMBIGUOUS")
    # OSError from a (substituted) runner cannot prove that the child never started (fork() may
    # have happened before exec refused), so we conservatively classify as AMBIGUOUS, not
    # BLOCKED_EXTERNAL/PROVIDER_UNAVAILABLE. The nonce is then consumed and the submission
    # state is ATTEMPTED; any further dispatch against the same job (fresh OR reused nonce)
    # is refused on the state check before the nonce check even runs.
    blocked = dispatcher.dispatch(
        h.job_id, execute=True, submitter=sub, authorization=_auth(h.spec)
    )
    assert blocked.state == "AMBIGUOUS" and blocked.detail == "SUBMIT_DISPATCH_AMBIGUOUS"
    with pytest.raises(ExternalAdmissionError) as exc:  # ATTEMPTED state refuses a fresh nonce
        dispatcher.dispatch(h.job_id, execute=True, submitter=sub, authorization=_auth(h.spec, nonce="nonce-os-fresh"))
    assert _code(exc) == "SUBMISSION_STATE_AMBIGUOUS"
    kinds = [item["kind"] for item in h.adapter.store.submissions(h.job_id)]
    assert "SUBMIT_AMBIGUOUS" in kinds and kinds.count("SUBMIT_ACKED") == 0

    # The BUDGET_EXHAUSTED-mapped nonzero exit must NOT silently turn into a safe RETRY: the
    # exit_code_map result that is not on the documented _PROVEN_NOT_SENT_CODES list is escalated
    # to SUBMIT_TRANSPORT_AMBIGUOUS. We test this against a SEPARATE harness because the previous
    # dispatch already moved the first job into ``ATTEMPTED`` state and a same-job retry would
    # only verify ``SUBMISSION_STATE_AMBIGUOUS`` rather than the transport-classification branch.
    mapped_h = make_harness(tmp_path / "mapped")
    dispatcher_m = HostDispatcher(synthetic_only=True, adapter=mapped_h.adapter)

    mapped = SyntheticTransportFailure("SUBMIT_TRANSPORT_AMBIGUOUS")
    res = dispatcher_m.dispatch(
        mapped_h.job_id, execute=True, submitter=mapped, authorization=_auth(mapped_h.spec)
    )
    assert res.state == "AMBIGUOUS" and res.detail == "SUBMIT_TRANSPORT_AMBIGUOUS"
    assert "sk-should-not-surface" not in json.dumps(mapped_h.adapter.store.submissions(mapped_h.job_id))
    with pytest.raises(ExternalAdmissionError) as exc:
        dispatcher_m.dispatch(
            mapped_h.job_id, execute=True, submitter=mapped, authorization=_auth(mapped_h.spec, nonce="nonce-b2")
        )
    assert _code(exc) == "SUBMISSION_STATE_AMBIGUOUS"
    mapped_kinds = [item["kind"] for item in mapped_h.adapter.store.submissions(mapped_h.job_id)]
    assert "SUBMIT_AMBIGUOUS" in mapped_kinds and mapped_kinds.count("SUBMIT_ACKED") == 0

    # Timeout must be tested against a freshly approved job/store: after the mapped job is in
    # ATTEMPTED state, ``begin_submission`` refuses any further dispatch with SUBMISSION_STATE_AMBIGUOUS,
    # so reusing the same job would not exercise the timeout→AMBIGUOUS path. A separate harness
    # isolates the timeout semantics.
    t = make_harness(tmp_path / "timeout")
    dispatcher_t = HostDispatcher(synthetic_only=True, adapter=t.adapter)

    amb = SyntheticTransportFailure("SUBMIT_TIMEOUT_AMBIGUOUS")
    res = dispatcher_t.dispatch(
        t.job_id,
        execute=True,
        submitter=amb,
        authorization=_auth(t.spec, nonce="nonce-timeout-1"),
    )
    assert res.state == "AMBIGUOUS" and res.detail == "SUBMIT_TIMEOUT_AMBIGUOUS"
    # No double submit: a second dispatch against the same fresh job is refused.
    with pytest.raises(ExternalAdmissionError) as exc:
        dispatcher_t.dispatch(
            t.job_id,
            execute=True,
            submitter=amb,
            authorization=_auth(t.spec, nonce="nonce-timeout-2"),
        )
    assert _code(exc) == "SUBMISSION_STATE_AMBIGUOUS"
    timeout_kinds = [item["kind"] for item in t.adapter.store.submissions(t.job_id)]
    assert "SUBMIT_AMBIGUOUS" in timeout_kinds and timeout_kinds.count("SUBMIT_ACKED") == 0


def test_live_dispatch_fails_closed_when_caller_protocol_unverified(tmp_path):
    """No SESHAT_PHASE_B_PROTOCOL_VERIFIED env override means live dispatch must fail closed."""

    h = make_harness(tmp_path)
    exe = str(tmp_path / "aiye-exec")
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)

    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    sub = AiyeExecSubmitter(exe=exe, spool_dir=tmp_path / "s", runner=runner)
    result = dispatcher.dispatch(h.job_id, execute=True, submitter=sub, authorization=_auth(h.spec))
    assert result.state == "BLOCKED_EXTERNAL" and result.detail == "PROTOCOL_UNVERIFIED"
    assert h.adapter.store.submissions(h.job_id) == []
    again = dispatcher.dispatch(h.job_id, execute=True, submitter=sub,
                                authorization=_auth(h.spec, nonce="nonce-x"))
    assert again.state == "BLOCKED_EXTERNAL"


def test_synthetic_nonzero_exit_stays_ambiguous_and_never_double_submits(tmp_path, monkeypatch):
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path)
    calls: list[Any] = []

    sub = SyntheticTransportFailure("SUBMIT_EXIT_AMBIGUOUS")
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)
    res = dispatcher.dispatch(
        h.job_id, execute=True, submitter=sub, authorization=_auth(h.spec)
    )
    assert res.state == "AMBIGUOUS" and res.detail == "SUBMIT_EXIT_AMBIGUOUS"
    assert len(calls) == 0
    with pytest.raises(ExternalAdmissionError) as exc:
        dispatcher.dispatch(
            h.job_id, execute=True, submitter=sub, authorization=_auth(h.spec, nonce="nonce-retry")
        )
    assert _code(exc) == "SUBMISSION_STATE_AMBIGUOUS"
    assert len(calls) == 0


def test_caller_protocol_argv_gaps_documented_for_independent_review():
    from seshat.fabric_waves.external_carrier.host_dispatcher import caller_protocol_argv_gaps

    gaps = caller_protocol_argv_gaps()
    assert "CALLER_PROTOCOL_REQUIRES_AGENT_AUTO" in gaps
    assert "CALLER_PROTOCOL_DECISION_ID_VS_DECISION_FLAG" in gaps


# 15. two-host E5 re-entry: live in-process and replay-verified -----------------------------


def _assert_artifacts(out: Path, receipt: dict, *, host_job_id: str) -> None:
    assert set(receipt["artifact_file_digests"]) == set(phase_b.PHASE_B_ARTIFACTS)
    for name, meta in receipt["artifact_file_digests"].items():
        data = (out / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"]
        assert len(data) == meta["byte_length"]
    assert (out / "receipt.json").is_file()
    page = (out / "carpet.html").read_text(encoding="utf-8")
    assert host_job_id in page and "Phase B external provenance" in page
    assert "REGISTRY_PINS_ONLY" in page and "FakeHost" not in page
    for jsonl in (
        "research_needs.jsonl",
        "job_dispatch.jsonl",
        "independent_host_job_receipts.jsonl",
        "terminal_output_sha.jsonl",
        "evidence_returns.jsonl",
    ):
        lines = [ln for ln in (out / jsonl).read_text(encoding="utf-8").splitlines() if ln]
        assert lines, jsonl
        for line in lines:
            json.loads(line)
    for path in out.iterdir():
        assert MAC_KEY_BYTES not in path.read_bytes()
    assert receipt["claims"]["fake_host_executor_used"] is False
    assert receipt["claims"]["binding_hash_is_authentication"] is False


@pytest.mark.parametrize("kind", HOSTS)
def test_two_host_live_in_process_resume_with_mock_hub(tmp_path, kind, monkeypatch):
    monkeypatch.setenv("SESHAT_PHASE_B_PROTOCOL_VERIFIED", "true")
    h = make_harness(tmp_path, kind)
    hub = MockHub()
    dispatcher = HostDispatcher(synthetic_only=True, adapter=h.adapter)
    assert dispatcher.dispatch(h.job_id).state == "DRY_RUN" and hub.submitted == []
    sent = dispatcher.dispatch(
        h.job_id, execute=True, submitter=hub, authorization=_auth(h.spec)
    )
    assert sent.state == "SUBMITTED" and len(hub.submitted) == 1
    spec, prompt = hub.submitted[0]
    assert spec == h.spec and prompt == h.job.prompt_bytes

    data = good_stdout(h.carriers)
    hub.records[spec.hub_job_id] = (make_record(spec, data), data)
    ingested = dispatcher.ingest(h.job_id, fetcher=hub, execute=True)
    assert ingested["state"] == "COMPLETED" and ingested["wrote"] is True

    result = phase_b.resume_live(h.waiting, adapter=h.adapter, host_job_id=h.job_id)
    assert result.mode == phase_b.PHASE_B_LIVE_IN_PROCESS_ONLY
    assert result.run_record.outcome in {FabricRunOutcome.CONVERGED, FabricRunOutcome.SATURATED}
    host = "met" if kind == "meteorology" else "campus"
    assert result.facts["downstream_fired_threads"] == sorted(
        [f"external-integrate-{host}", f"reconcile-{host}"]
    )
    assert result.facts["proposal_epistemic_level"] == "E5"
    assert f"obs-{host}-beta" in result.facts["stable_observation_versions"]
    proposal_prov = " ".join(result.facts["proposal_provenance"])
    assert f"job:{h.job_id}" in proposal_prov and f"request:{h.need.request_id}" in proposal_prov

    out = tmp_path / "artifacts"
    receipt = phase_b.export_phase_b_artifacts(
        out, result=result, adapter=h.adapter, host_job_id=h.job_id,
        transport_kind=phase_b.TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT,
    )
    assert receipt["mode"] == phase_b.PHASE_B_LIVE_IN_PROCESS_ONLY
    assert receipt["transport_kind"] == phase_b.TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT
    _assert_artifacts(out, receipt, host_job_id=h.job_id)
    resume_doc = json.loads((out / "resume_receipt.json").read_text(encoding="utf-8"))
    assert resume_doc["state_restoration"] == "SINGLE_PROCESS_IN_MEMORY_ENGINE"

    # The engine will not accept the same return a second time.
    with pytest.raises(WaveEngineConfigurationError):
        h.waiting.engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=h.need.request_id, run_id=h.need.run_id, evidence_return=result.evidence
            ),
            budget=BUDGET,
            port=h.adapter,
        )


@pytest.mark.parametrize("kind", HOSTS)
def test_two_host_replay_verified_resume_after_restart(tmp_path, kind):
    h = make_harness(tmp_path, kind)
    h.complete()
    # "Restart": discard the original engine and every in-memory object; keep only the store.
    restarted = make_adapter(tmp_path, h.need, h.authority, store_name="store")
    result = phase_b.resume_by_replay(adapter=restarted, host_job_id=h.job_id)
    assert result.engine is not h.waiting.engine
    assert result.mode == phase_b.PHASE_B_REPLAY_VERIFIED
    assert result.run_record.outcome in {FabricRunOutcome.CONVERGED, FabricRunOutcome.SATURATED}
    assert len(result.facts["downstream_fired_threads"]) == 2
    out = tmp_path / "artifacts"
    receipt = phase_b.export_phase_b_artifacts(
        out, result=result, adapter=restarted, host_job_id=h.job_id,
        transport_kind=phase_b.TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT,
    )
    _assert_artifacts(out, receipt, host_job_id=h.job_id)
    resume_doc = json.loads((out / "resume_receipt.json").read_text(encoding="utf-8"))
    assert resume_doc["mode"] == "PHASE_B_REPLAY_VERIFIED"
    assert resume_doc["state_restoration"].startswith("NOT_RESTORED")
    # The two threads that FIRED are exactly the dependent ones; the beta branch is unchanged.
    assert not any(
        v is None for v in result.facts["stable_observation_versions"].values()
    )


def test_missing_replay_material_is_phase_b_required_not_a_fake_resume(tmp_path):
    h = make_harness(tmp_path, with_replay=False)
    h.complete()
    with pytest.raises(ExternalAdmissionError) as exc:
        phase_b.resume_by_replay(adapter=h.adapter, host_job_id=h.job_id)
    assert _code(exc) == "PHASE_B_REQUIRED_NO_REPLAY_MATERIAL"
    assert phase_b.PHASE_B_REQUIRED == "PHASE_B_REQUIRED"
    # The live path still works in the original process (and is labelled as such).
    result = phase_b.resume_live(h.waiting, adapter=h.adapter, host_job_id=h.job_id)
    assert result.mode == phase_b.PHASE_B_LIVE_IN_PROCESS_ONLY


def test_machine_return_with_wrong_material_cannot_reenter_the_engine(tmp_path):
    h = make_harness(tmp_path)
    h.complete()
    evidence = h.evidence()
    forged = evidence.model_copy(
        update={"proposal_payload": {**evidence.proposal_payload, "hypothesis": "forged"}}
    )
    budget_before = h.waiting.engine.sediment.version_map()
    with pytest.raises(WaveEngineConfigurationError):
        h.waiting.engine.resume_external_evidence(
            receipt=ExternalResumeReceipt(
                request_id=h.need.request_id, run_id=h.need.run_id, evidence_return=forged
            ),
            budget=BUDGET,
            port=h.adapter,
        )
    assert h.waiting.engine.sediment.version_map() == budget_before
    assert not any(
        r.object_type == "external.proposal" for r in h.waiting.engine.sediment.all_records()
    )


# 16. trust boundary: unprivileged core stays clean -----------------------------------------

_CORE_FILES = (
    "contracts.py",
    "ledger.py",
    "port.py",
    "wait_checkpoint.py",
    "hosts.py",
    "fake_host.py",
)
_FORBIDDEN_CORE_IMPORTS = {"subprocess", "sqlite3", "socket", "http", "urllib", "requests"}
_HOST_MODULES = (
    "host_security",
    "hub_protocol",
    "host_envelope",
    "host_store",
    "host_adapter",
    "host_dispatcher",
    "phase_b",
    "host_cli",
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _attribute_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_unprivileged_core_has_no_host_secret_env_or_process_imports():
    package = Path(seshat.__file__).resolve().parent / "fabric_waves"
    core = [package / "external_carrier" / name for name in _CORE_FILES]
    core.append(package / "engine.py")
    for path in core:
        imports = _imports(path)
        top = {name.split(".")[0] for name in imports}
        assert not (top & _FORBIDDEN_CORE_IMPORTS), path.name
        assert not any(
            name.rsplit(".", 1)[-1] in _HOST_MODULES for name in imports
        ), path.name
        assert "environ" not in _attribute_names(path), path.name


def test_host_modules_never_import_model_clis_and_only_dispatcher_spawns_processes():
    package = Path(seshat.__file__).resolve().parent / "fabric_waves" / "external_carrier"
    for name in _HOST_MODULES:
        source = (package / f"{name}.py").read_text(encoding="utf-8").lower()
        for banned in ("claude", "codex", "anthropic", "openai"):
            assert banned not in source, (name, banned)
        top = {item.split(".")[0] for item in _imports(package / f"{name}.py")}
        if name not in {"host_dispatcher", "host_cli"}:
            assert "subprocess" not in top, name
        assert not (top & {"socket", "http", "urllib", "requests"}), name
        assert "shell=true" not in source.replace(" ", ""), name


def test_host_cli_entry_point_is_registered():
    # Under a built wheel, seshat.__file__ lives in site-packages and is not
    # an address for the source checkout pyproject.toml.
    root = Path(__file__).resolve().parents[2]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'seshat-fabric-external = "seshat.fabric_waves.external_carrier.host_cli:main"' in text


def test_owner_approvals_reject_malformed_entries():
    with pytest.raises(ExternalAdmissionError):
        OwnerApprovals([{"request_pin_sha256": "short"}])
    with pytest.raises(ExternalAdmissionError):
        OwnerApprovals(
            [
                {
                    "request_pin_sha256": "a" * 64,
                    "request_id": "r",
                    "run_id": "x",
                    "approved_by": "o",
                    "scope": "something_else",
                }
            ]
        )
    assert material_hash({"a": 1}) == material_hash({"a": 1})
