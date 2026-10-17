"""S-RUG-CORE-003 Phase A portfolio: WAITING_EXTERNAL → verified resume → re-entry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from seshat.fabric_waves.carpet_export import (
    all_run_events,
    operator_stone_events,
    run_ledger_head_hash,
    sediment_records_for_run,
)
from seshat.fabric_waves.carpet_portfolio import (
    PORTFOLIO_HASHED_ARTIFACTS,
    _budget,
    _git_meta,
    artifact_file_digests,
)
from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.external_carrier.contracts import ExternalResumeReceipt
from seshat.fabric_waves.external_carrier.fake_host import FakeHostExecutor
from seshat.fabric_waves.external_carrier.hosts import (
    campus_external_host_engine,
    meteorology_external_host_engine,
)
from seshat.fabric_waves.source_module_manifest import build_source_module_manifest
from seshat.fabric_waves.trace import render_html


def _query(event_id: str, topic: str) -> StoneEvent:
    return StoneEvent(
        event_id=event_id,
        kind=StoneEventKind.QUERY,
        issued_at_tick=0,
        payload={
            "topic": topic,
            "query": "reconcile divergent branches with external research carrier",
        },
    )


def execute_external_portfolio() -> dict[str, Any]:
    """Run T1–T5 campus/met external carrier demos; returns engines and receipt material."""
    campus = campus_external_host_engine()
    budget = _budget()
    t1 = campus.run(
        run_id="ext-t1-campus",
        budget=budget,
        initial_stone=_query("ext-t1-q", "campus-facility-utilization"),
    )
    assert t1.outcome.value == "WAITING_EXTERNAL"
    need = campus.external_ledger.research_needs[-1]
    fake = FakeHostExecutor(host_scope=need.worker_ref.host_scope)
    job_id = fake.dispatch(need)
    campus.external_ledger.agent_jobs.append(
        {"job_id": job_id, "request_id": need.request_id, "synthetic": True}
    )
    proposal = {
        "hypothesis": "utilization gap explained by sensor calibration drift",
        "branch_focus": "alpha",
        "confidence": "E5-proposal",
    }
    evidence = fake.synthesize_return(need=need, job_id=job_id, proposal=proposal)
    beta_version_before = campus.sediment.version_map().get("obs-campus-beta")
    receipt = ExternalResumeReceipt(
        request_id=need.request_id,
        run_id="ext-t1-campus",
        evidence_return=evidence,
    )
    t2 = campus.resume_external_evidence(receipt=receipt, budget=budget, port=fake)
    assert t2.outcome.value in {"CONVERGED", "SATURATED"}
    beta_version_after = campus.sediment.version_map().get("obs-campus-beta")
    assert beta_version_before == beta_version_after
    activations = {a.thread_id for a in campus.ledger.activations_for_run("ext-t1-campus")}
    assert "external-integrate-campus" in activations
    assert "reconcile-campus" in activations

    campus.run(
        run_id="ext-t3-waiting-delta",
        budget=budget,
        initial_stone=_query("ext-t3-q", "campus-facility-utilization"),
    )
    stale_need = campus.external_ledger.research_needs[-1]
    stale_job = fake.dispatch(stale_need)
    stale_evidence = fake.synthesize_return(
        need=stale_need,
        job_id=stale_job,
        proposal={"hypothesis": "stale path"},
    )
    campus.run(
        run_id="ext-t3-delta-only",
        budget=budget,
        initial_stone=StoneEvent(
            event_id="ext-t3-delta",
            kind=StoneEventKind.SOURCE_DELTA,
            issued_at_tick=3,
            target_carrier_id="campus-branch-alpha",
            payload={
                "old_version": "1",
                "new_version": "2",
                "text": "revised lab telemetry: utilization index 79%",
            },
        ),
    )
    campus.external_ledger.mark_stale(stale_need.request_id)
    from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError, verify_resume_receipt

    try:
        verify_resume_receipt(
            ledger=campus.external_ledger,
            receipt=ExternalResumeReceipt(
                request_id=stale_need.request_id,
                run_id="ext-t3-waiting-delta",
                evidence_return=stale_evidence,
            ),
            port=fake,
        )
        raise AssertionError("stale return must not verify")
    except ExternalAdmissionError:
        pass

    met = meteorology_external_host_engine()
    met.run(
        run_id="ext-t4-met",
        budget=budget,
        initial_stone=_query("ext-t4-q", "winter-operations-wind-icing"),
    )
    met_need = met.external_ledger.research_needs[-1]
    met_fake = FakeHostExecutor(host_scope=met_need.worker_ref.host_scope)
    met_job = met_fake.dispatch(met_need)
    met_evidence = met_fake.synthesize_return(
        need=met_need,
        job_id=met_job,
        proposal={"hypothesis": "wind sensor icing asymmetry", "domain": "meteorology"},
    )
    met.resume_external_evidence(
        receipt=ExternalResumeReceipt(
            request_id=met_need.request_id,
            run_id="ext-t4-met",
            evidence_return=met_evidence,
        ),
        budget=budget,
        port=met_fake,
    )

    return {
        "campus": campus,
        "met": met,
        "primary_run_id": "ext-t1-campus",
        "primary_resume": {
            "run_id": "ext-t1-campus",
            "request_id": need.request_id,
            "job_id": job_id,
        },
    }


def export_external_artifacts(output_dir: Path, engines: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    campus: WaveEngine = engines["campus"]
    run_id = engines["primary_run_id"]
    ledger, sediment, _ = campus.snapshot(run_id)
    stones = operator_stone_events(ledger, run_id)
    event_lines = [
        json.dumps(event, ensure_ascii=False, sort_keys=True)
        for event in all_run_events(ledger, run_id)
    ]
    waves_lines = [
        json.dumps(w.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
        for w in ledger.waves
        if w.run_id == run_id
    ]
    activation_lines = [
        json.dumps(a.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
        for a in ledger.activations
        if a.run_id == run_id
    ]
    sediment_records = sediment_records_for_run(ledger, sediment, run_id)
    resonances = [
        r.model_dump(mode="python") for r in ledger.resonances_for_run(run_id)
    ]
    run_record = next(r for r in ledger.runs if r.run_id == run_id)
    html = render_html(
        run_record=run_record,
        ledger=ledger,
        sediment=sediment,
        resonances={r.resonance_id: r for r in ledger.resonances_for_run(run_id)},
        thread_specs=campus.thread_specs,
        title="SESHAT external carrier — campus WAITING→resume",
    )
    (output_dir / "stones.json").write_text(
        json.dumps(stones, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "events.jsonl").write_text("\n".join(event_lines) + "\n", encoding="utf-8")
    (output_dir / "waves.jsonl").write_text("\n".join(waves_lines) + "\n", encoding="utf-8")
    (output_dir / "activations.jsonl").write_text(
        "\n".join(activation_lines) + "\n", encoding="utf-8"
    )
    (output_dir / "sediment.json").write_text(
        json.dumps(sediment_records, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "resonances.json").write_text(
        json.dumps(resonances, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (output_dir / "carpet.html").write_text(html, encoding="utf-8")
    campus.external_ledger.export_jsonl(output_dir)
    primary_resume = engines.get("primary_resume") or {
        "run_id": run_id,
        "request_id": campus.external_ledger.research_needs[0].request_id,
    }
    resume_receipt = {
        "run_id": primary_resume["run_id"],
        "request_id": primary_resume["request_id"],
        "job_id": primary_resume.get("job_id"),
        "phase": "PHASE_A_SYNTHETIC_RESUME",
        "phase_b": "REQUIRED",
    }
    campus.external_ledger.export_resume_receipt(output_dir, resume_receipt)
    file_digests = artifact_file_digests(output_dir)
    receipt = {
        "portfolio_digest_sha256": file_digests.get("activations.jsonl", {}).get("sha256", ""),
        "artifact_file_digests": file_digests,
        "source_modules": build_source_module_manifest(),
        "runs": [
            {
                "run_id": run_id,
                "ledger_head_hash": run_ledger_head_hash(ledger, run_id),
            }
        ],
        "artifact_files": [
            *PORTFOLIO_HASHED_ARTIFACTS,
            "research_needs.jsonl",
            "agent_jobs.jsonl",
            "evidence_returns.jsonl",
            "resume_receipt.json",
            "receipt.json",
        ],
        "git": _git_meta(),
        "known_limits": [
            "PHASE_B_REQUIRED: trusted AORUS Hub WorkerCarrier adapter not executed in this job.",
            "FakeHostExecutor used only inside deterministic portfolio/tests.",
            "Process restart durable resume: WAITING state held in-memory on WaveEngine only.",
        ],
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "external_carrier_portfolio",
    )
    args = parser.parse_args(argv)
    engines = execute_external_portfolio()
    receipt = export_external_artifacts(args.output_dir, engines)
    print(f"Wrote external carrier portfolio to {args.output_dir.resolve()}")
    print(f"phase_b={receipt['known_limits'][0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
