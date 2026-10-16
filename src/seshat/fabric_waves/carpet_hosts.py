"""Declarative two-host carpet fixtures (campus operations + meteorology).

Same engine mechanics and thread registry pattern; only carriers, thread ids and
synthetic bodies differ. No medicine or host-specific hardcoding in the core.
"""

from __future__ import annotations

from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult
from seshat.fabric_waves.scenarios import bundle, engine_for, output, source_store


def _read_carrier(inv: BodyInvocation, *, branch: str) -> BodyResult:
    text = inv.carried_payload["text"]
    return output(
        inv,
        {
            "branch": branch,
            "excerpt": text[:48],
            "byte_length": len(text),
        },
    )


def _question(inv: BodyInvocation, *, default_topic: str) -> BodyResult:
    payload = inv.carried_payload
    return output(
        inv,
        {
            "topic": payload.get("topic", default_topic),
            "query": payload.get("query", "synthesize divergent operational readings"),
        },
    )


def _concepts(inv: BodyInvocation) -> BodyResult:
    question = inv.carried_payload["candidate_sediments"][0]
    return output(
        inv,
        {
            "terms": ("utilization", "sensor-divergence", "reconciliation"),
            "question_version": question.version,
        },
    )


def _evidence(inv: BodyInvocation, *, branch: str, signal_key: str) -> BodyResult:
    obs = next(
        record
        for record in inv.carried_payload["candidate_sediments"]
        if record.sediment_id.startswith("obs-")
    )
    concepts = next(
        record
        for record in inv.carried_payload["candidate_sediments"]
        if record.sediment_id.startswith("concepts")
    )
    return output(
        inv,
        {
            "branch": branch,
            "signal": signal_key,
            "obs_version": obs.version,
            "concept_version": concepts.version,
            "reading": obs.payload["excerpt"],
        },
    )


def _reconcile(inv: BodyInvocation) -> BodyResult:
    states = inv.carried_payload["candidate_sediments"]
    by_branch = {record.payload["branch"]: record for record in states}
    alpha = by_branch.get("alpha")
    beta = by_branch.get("beta")
    if alpha is None or beta is None:
        return BodyResult(aporia="MISSING_EVIDENCE_BRANCH")
    divergent = alpha.payload["signal"] != beta.payload["signal"]
    return output(
        inv,
        {
            "alpha_signal": alpha.payload["signal"],
            "beta_signal": beta.payload["signal"],
            "divergent": divergent,
            "alpha_version": alpha.version,
            "beta_version": beta.version,
        },
    )


def _answer(inv: BodyInvocation) -> BodyResult:
    reconciliation = inv.carried_payload["candidate_sediments"][0]
    return output(
        inv,
        {
            "grounded": True,
            "alpha_signal": reconciliation.payload["alpha_signal"],
            "beta_signal": reconciliation.payload["beta_signal"],
            "divergent": reconciliation.payload["divergent"],
            "reconcile_version": reconciliation.version,
        },
    )


def _human_governance_gate(inv: BodyInvocation) -> BodyResult:
    reconciliation = inv.carried_payload["candidate_sediments"][0]
    if inv.carried_payload.get("governance_hold") and reconciliation.payload.get("divergent"):
        return BodyResult(aporia="OPERATOR_GOVERNANCE_REQUIRED")
    return output(
        inv,
        {
            "alpha_signal": reconciliation.payload["alpha_signal"],
            "beta_signal": reconciliation.payload["beta_signal"],
            "divergent": reconciliation.payload["divergent"],
            "reconcile_version": reconciliation.version,
        },
    )


def _host_engine(
    *,
    host_id: str,
    carrier_alpha: str,
    carrier_beta: str,
    alpha_text: str,
    beta_text: str,
    alpha_signal: str,
    beta_signal: str,
    default_topic: str,
    revisions: dict | None = None,
    with_human_governance_gate: bool = False,
    decision_verifier=None,
) -> WaveEngine:
    obs_a = f"obs-{host_id}-alpha"
    obs_b = f"obs-{host_id}-beta"
    bundles = [
        bundle(
            obs_a,
            lambda inv: _read_carrier(inv, branch="alpha"),
            source=carrier_alpha,
        ),
        bundle(
            obs_b,
            lambda inv: _read_carrier(inv, branch="beta"),
            source=carrier_beta,
        ),
        bundle(
            f"question-{host_id}",
            lambda inv: _question(inv, default_topic=default_topic),
        ),
        bundle(
            f"concepts-{host_id}",
            _concepts,
            reads=(f"question-{host_id}",),
        ),
        bundle(
            f"evidence-alpha-{host_id}",
            lambda inv: _evidence(inv, branch="alpha", signal_key=alpha_signal),
            reads=(f"concepts-{host_id}", obs_a),
        ),
        bundle(
            f"evidence-beta-{host_id}",
            lambda inv: _evidence(inv, branch="beta", signal_key=beta_signal),
            reads=(f"concepts-{host_id}", obs_b),
        ),
        bundle(
            f"reconcile-{host_id}",
            _reconcile,
            reads=(f"evidence-alpha-{host_id}", f"evidence-beta-{host_id}"),
        ),
    ]
    if with_human_governance_gate:
        bundles.append(
            bundle(
                f"governance-{host_id}",
                _human_governance_gate,
                reads=(f"reconcile-{host_id}",),
            )
        )
        bundles.append(
            bundle(
                f"answer-{host_id}",
                _answer,
                reads=(f"governance-{host_id}",),
            )
        )
    else:
        bundles.append(
            bundle(
                f"answer-{host_id}",
                _answer,
                reads=(f"reconcile-{host_id}",),
            )
        )
    store = source_store(
        {carrier_alpha: alpha_text, carrier_beta: beta_text},
        revisions=revisions,
    )
    engine = engine_for(bundles, store)
    if decision_verifier is not None:
        engine.decision_verifier = decision_verifier
    return engine


def campus_host_engine() -> WaveEngine:
    """Synthetic university campus / operations research host (T1/T2)."""
    revision = carrier(
        carrier_id="campus-branch-alpha",
        version="2",
        text="revised lab telemetry: utilization index 79%",
    )
    return _host_engine(
        host_id="campus",
        carrier_alpha="campus-branch-alpha",
        carrier_beta="campus-branch-beta",
        alpha_text="lab telemetry: utilization index 82%",
        beta_text="facilities audit memo: utilization index 64%",
        alpha_signal="82",
        beta_signal="64",
        default_topic="campus-facility-utilization",
        revisions={
            ("campus-branch-alpha", "1", "2"): revision,
        },
    )


def campus_decision_host_engine() -> WaveEngine:
    """Campus host with governance gate for T3 APORIA + HUMAN_DECISION portfolio path."""
    from seshat.fabric_waves.decision_gate import host_fixture_verifier

    revision = carrier(
        carrier_id="campus-branch-alpha",
        version="2",
        text="revised lab telemetry: utilization index 79%",
    )
    return _host_engine(
        host_id="campus",
        carrier_alpha="campus-branch-alpha",
        carrier_beta="campus-branch-beta",
        alpha_text="lab telemetry: utilization index 82%",
        beta_text="facilities audit memo: utilization index 64%",
        alpha_signal="82",
        beta_signal="64",
        default_topic="campus-governance-aporia",
        revisions={("campus-branch-alpha", "1", "2"): revision},
        with_human_governance_gate=True,
        decision_verifier=host_fixture_verifier,
    )


def meteorology_host_engine() -> WaveEngine:
    """Synthetic meteorology / industrial maintenance host (T4)."""
    return _host_engine(
        host_id="met",
        carrier_alpha="met-sensor-north",
        carrier_beta="met-sensor-south",
        alpha_text="north tower anemometer: gust 41 kt, icing risk moderate",
        beta_text="south maintenance log: gust 28 kt, icing risk low",
        alpha_signal="41",
        beta_signal="28",
        default_topic="winter-operations-wind-icing",
    )
