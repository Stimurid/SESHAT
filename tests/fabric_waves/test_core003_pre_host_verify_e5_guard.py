"""CORE003 pre-host verify order: invalid E2/E3/E4 never invoke host terminal verification."""

from __future__ import annotations

import pytest

from seshat.fabric_waves.contracts import EpistemicLevel, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.external_carrier.contracts import ExternalResumeReceipt
from seshat.fabric_waves.external_carrier.fake_host import FakeHostExecutor
from seshat.fabric_waves.external_carrier.hosts import (
    campus_external_host_engine,
    meteorology_external_host_engine,
)
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError, verify_resume_receipt

BUDGET = WaveBudget(max_waves=40, max_activations=80, max_stone_events=80)


class _CountingPort:
    def __init__(self, inner: FakeHostExecutor) -> None:
        self._inner = inner
        self.verify_calls = 0

    def authoritative_dispatch(self, *, job_id: str):
        return self._inner.authoritative_dispatch(job_id=job_id)

    def verify_return(self, *, need, evidence):
        self.verify_calls += 1
        return self._inner.verify_return(need=need, evidence=evidence)

    def dispatch(self, need):
        return self._inner.dispatch(need)


def _exercise(host: str, level: EpistemicLevel):
    engine = (
        campus_external_host_engine()
        if host == "campus"
        else meteorology_external_host_engine()
    )
    run_id = f"preconsume:{host}:{level.value}"
    engine.run(
        run_id=run_id,
        budget=BUDGET,
        initial_stone=StoneEvent(
            event_id="q:" + run_id,
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={
                "topic": (
                    "campus-facility-utilization"
                    if host == "campus"
                    else "winter-operations-wind-icing"
                ),
                "query": "public synthetic E5 host verification order test",
            },
        ),
    )
    need = engine.external_ledger.research_needs[-1]
    inner = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = inner.dispatch(need)
    valid = inner.synthesize_return(
        need=need, job_id=job_id, proposal={"hypothesis": "synthetic host result"}
    )
    candidate = valid.model_copy(update={"epistemic_level": level}, deep=True)
    port = _CountingPort(inner)
    try:
        verify_resume_receipt(
            ledger=engine.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=need.request_id,
                run_id=need.run_id,
                evidence_return=candidate,
            ),
            port=port,
        )
        observed = "ADMITTED"
    except ExternalAdmissionError as exc:
        observed = f"DENIED:{exc}"
    admitted = len(engine.external_ledger.evidence_returns)
    if level != EpistemicLevel.E5:
        assert observed.startswith("DENIED")
        assert port.verify_calls == 0
        assert admitted == 0
    else:
        assert observed == "ADMITTED"
        assert port.verify_calls == 1
        assert admitted == 1


@pytest.mark.parametrize("host", ("campus", "meteorology"))
@pytest.mark.parametrize(
    "level",
    (
        EpistemicLevel.E2,
        EpistemicLevel.E3,
        EpistemicLevel.E4,
        EpistemicLevel.E5,
    ),
)
def test_pre_host_verify_epistemic_guard(host, level):
    _exercise(host, level)
