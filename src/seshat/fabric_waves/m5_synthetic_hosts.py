"""M5 acceptance hosts built from the invented room fixture (lab Zeta + sensors).

Everything here is explicitly synthetic: invented worlds, deterministic
callbacks, no model calls and no real-world sources.  The callbacks do
transform their declared inputs (they derive from the *current* observed
source content and version at call time, never from a value frozen when the
host was built), but they are mechanical fixtures and are not, and must not
be presented as, scientific method bodies.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from seshat.contracts import SourceCarrier, SourceContent
from seshat.fabric_waves.contracts import StoneEventKind
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult
from seshat.fabric_waves.scenarios import bundle, engine_for, output
from seshat.fabric_waves.source_access import FabricCarrierStore

#: Right the fixture's registry declares for every synthetic capability.
SYNTHETIC_RIGHT = "SYNTHETIC_SELF_CONTAINED"

#: Base states a host can supply without running any capability.
BASE_SOURCE_STATE = "SyntheticSourceVersion"
BASE_STONE_STATE = "Stone"

#: State produced only when a run has actually recorded a specific missing
#: source need.  It has no writer in the registry, so the frontier capability
#: is blocked until the runtime observes the need (see
#: :func:`observed_missing_source_needs`).
MISSING_SOURCE_NEED_STATE = "MissingSourceNeed"


def host_slug(host_id: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", host_id.lower()).strip("-")
    return token[:48] or "m5-host"


def carrier_id_from_uri(uri: str) -> str:
    return uri.replace("synthetic://", "m5-").replace("/", "-")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- deterministic synthetic callbacks ----------------------------------------


def _observed_text(inv: BodyInvocation) -> tuple[str, str, str]:
    """Current source text, its version and its digest, resolved at call time."""

    payload = inv.carried_payload
    text = str(payload.get("text") or "")
    versions = payload.get("source_versions") or {}
    carriers = tuple(payload.get("carriers") or ())
    version = str(versions.get(carriers[0], "")) if carriers else ""
    return text, version, _digest(text)


def _m5_observation(inv: BodyInvocation, *, branch: str) -> BodyResult:
    text, version, digest = _observed_text(inv)
    return output(
        inv,
        {
            "branch": branch,
            "observed_version": version,
            "content_sha256": digest,
            "byte_length": len(text.encode("utf-8")),
            "excerpt": text[:64],
            # The operator stone that actually woke this observation. It travels
            # downstream so a later capability can see what it is reacting to.
            "triggering_stone_kind": str(inv.stone_kind),
        },
        kind="synthetic.observation",
    )


def _m5_question(inv: BodyInvocation, *, default_topic: str) -> BodyResult:
    payload = inv.carried_payload
    admitted = payload.get("operator_query") or {}
    question = str(admitted.get("query") or payload.get("query") or "")
    topic = str(admitted.get("topic") or payload.get("topic") or default_topic)
    return output(
        inv,
        {
            "topic": topic,
            "question": question,
            "question_sha256": _digest(question),
            "stone_kind": str(inv.stone_kind),
        },
        kind="synthetic.research_question",
    )


def _m5_concepts(inv: BodyInvocation) -> BodyResult:
    question = inv.carried_payload["candidate_sediments"][0]
    words = [w for w in re.split(r"\W+", str(question.payload.get("question") or "")) if len(w) > 5]
    return output(
        inv,
        {
            # Derived from the actual admitted question text, not a constant list.
            "alternatives": tuple(sorted({w.lower() for w in words})[:5]),
            "question_version": question.version,
        },
        kind="synthetic.concept_alternative",
    )


def _m5_evidence(inv: BodyInvocation, *, branch: str) -> BodyResult:
    states = inv.carried_payload["candidate_sediments"]
    obs = next(r for r in states if r.object_type == "synthetic.observation")
    concepts = next(r for r in states if r.object_type == "synthetic.concept_alternative")
    # Signal derives from the observation produced in THIS run from the
    # current source version; a later source delta changes it.
    signal = _digest(f"{obs.payload['content_sha256']}|{obs.payload['observed_version']}")[:12]
    return output(
        inv,
        {
            "branch": branch,
            "signal": signal,
            "observed_version": obs.payload["observed_version"],
            "observation_sediment_version": obs.version,
            "concept_version": concepts.version,
            "warrant": f"{branch} warrant over {obs.payload['byte_length']} observed bytes",
            "triggering_stone_kind": obs.payload.get("triggering_stone_kind", ""),
        },
        kind="synthetic.evidence_warrant",
    )


def _m5_reconcile(inv: BodyInvocation) -> BodyResult:
    states = [
        r for r in inv.carried_payload["candidate_sediments"]
        if r.object_type == "synthetic.evidence_warrant"
    ]
    by_branch = {r.payload["branch"]: r for r in states}
    alpha, beta = by_branch.get("alpha"), by_branch.get("beta")
    if alpha is None or beta is None:
        return BodyResult(aporia="MISSING_EVIDENCE_BRANCH")
    # The aporia stone woke the observations; the kind travelled down the
    # causal chain on the records this capability actually consumed. Reading
    # it here (rather than this activation's own trigger, which is always
    # SEDIMENT_AVAILABLE) is what makes the conflict observable at the join.
    triggered_by_aporia = any(
        r.payload.get("triggering_stone_kind") == StoneEventKind.APORIA.value
        for r in (alpha, beta)
    )
    if triggered_by_aporia:
        return BodyResult(
            aporia=(
                "SYNTHETIC_CONFLICT_UNRESOLVED: competing criteria over "
                f"alpha@{alpha.payload['observed_version']} and "
                f"beta@{beta.payload['observed_version']}; "
                "discriminating evidence not held by this host"
            )
        )
    return output(
        inv,
        {
            "alpha_signal": alpha.payload["signal"],
            "beta_signal": beta.payload["signal"],
            "divergent": alpha.payload["signal"] != beta.payload["signal"],
            "alpha_version": alpha.version,
            "beta_version": beta.version,
            "alpha_observed_version": alpha.payload["observed_version"],
            "beta_observed_version": beta.payload["observed_version"],
            "consumed_evidence_ids": tuple(sorted(r.sediment_id for r in states)),
        },
        kind="synthetic.reconciled_state",
    )


def _m5_projection(inv: BodyInvocation) -> BodyResult:
    states = inv.carried_payload["candidate_sediments"]
    reconciled = next(r for r in states if r.object_type == "synthetic.reconciled_state")
    return output(
        inv,
        {
            "grounded_in": reconciled.sediment_id,
            "reconcile_version": reconciled.version,
            "divergent": reconciled.payload["divergent"],
            "alpha_observed_version": reconciled.payload["alpha_observed_version"],
            "beta_observed_version": reconciled.payload["beta_observed_version"],
            "limitation": "SYNTHETIC_WORLD_ONLY_NO_EXTERNAL_VALIDITY",
        },
        kind="synthetic.resonance_projection",
    )


def _m5_proposal(inv: BodyInvocation) -> BodyResult:
    reconciled = inv.carried_payload["candidate_sediments"][0]
    return output(
        inv,
        {
            "proposal": "SYNTHETIC_CONDITIONAL_HYPOTHESIS",
            "based_on_version": reconciled.version,
            "promotion": "NOT_AUTHORIZED_WITHOUT_DECISION",
        },
        kind="synthetic.hypothesis_proposal",
    )


def _m5_frontier_need(inv: BodyInvocation) -> BodyResult:
    """Late capability: only reachable once a specific missing need exists."""

    payload = inv.carried_payload
    returned = payload.get("frontier_return") or payload.get("stone_meta") or {}
    need_id = str(payload.get("need_id") or returned.get("need_id") or "")
    return output(
        inv,
        {
            "status": "RESEARCH_NEED_RECORDED",
            "need_id": need_id,
            "needed_source": str(payload.get("needed_source") or returned.get("needed_source") or ""),
            "discriminating_action": str(
                payload.get("discriminating_action")
                or "obtain an independently held synthetic control record"
            ),
            "origin": "DETERMINISTIC_SYNTHETIC_FIXTURE_NOT_A_MODEL_CALL",
        },
        kind="synthetic.research_need",
    )


# -- host construction --------------------------------------------------------


def _m5_source_store(
    sources: Sequence[Mapping[str, Any]],
    *,
    revisions: Mapping[tuple[str, str, str], tuple[SourceCarrier, SourceContent]],
) -> FabricCarrierStore:
    """Carrier store seeded with each fixture source's ACTUAL declared version.

    The generic ``scenarios.source_store`` helper pins every carrier to
    version ``"1"``; the M5 fixture declares ``A1`` / ``B1`` / ``S1``, and a
    later delta states ``old_version`` accordingly.  Seeding ``"1"`` makes
    ``FabricCarrierStore.apply_delta`` raise ``SOURCE_REVISION_CONFLICT``.
    """

    carriers: dict[str, SourceCarrier] = {}
    contents: dict[str, SourceContent] = {}
    for item in sources:
        cid = carrier_id_from_uri(str(item["id"]))
        src, content = carrier(
            carrier_id=cid,
            version=str(item["version"]),
            text=str(item["content"]),
        )
        carriers[cid] = src
        contents[cid] = content

    def revision(cid: str, old: str, new: str) -> tuple[SourceCarrier, SourceContent]:
        try:
            return revisions[(cid, old, new)]
        except KeyError:
            raise ValueError("SOURCE_REVISION_NOT_PINNED_BY_HOST") from None

    return FabricCarrierStore(
        carriers=carriers, contents=contents, revision_provider=revision
    )


def declared_source_versions(host: Mapping[str, Any]) -> dict[str, str]:
    """carrier_id -> version exactly as the fixture declares it."""

    return {
        carrier_id_from_uri(str(item["id"])): str(item["version"])
        for item in host.get("source_versions") or ()
    }


def build_host_engine(
    host: Mapping[str, Any],
) -> tuple[WaveEngine, dict[str, str], dict[str, tuple[str, ...]]]:
    """Return engine, map source URI -> carrier_id, and registry -> thread binding."""

    slug = host_slug(str(host["host_id"]))
    sources = list(host.get("source_versions") or [])
    if len(sources) < 2:
        raise ValueError("M5 host requires at least two synthetic sources")
    alpha_src, beta_src = sources[0], sources[1]
    alpha_id = carrier_id_from_uri(str(alpha_src["id"]))
    beta_id = carrier_id_from_uri(str(beta_src["id"]))
    uri_map = {str(item["id"]): carrier_id_from_uri(str(item["id"])) for item in sources}

    revisions: dict[tuple[str, str, str], tuple[SourceCarrier, SourceContent]] = {}
    for stone in host.get("stones") or []:
        if stone.get("kind") != "SOURCE_DELTA":
            continue
        mutation = stone.get("mutation") or {}
        cid = carrier_id_from_uri(str(mutation["source_id"]))
        revisions[(cid, str(mutation["old_version"]), str(mutation["new_version"]))] = carrier(
            carrier_id=cid,
            version=str(mutation["new_version"]),
            text=str(mutation.get("new_content") or mutation.get("text") or ""),
        )

    obs_a, obs_b = f"obs-{slug}-alpha", f"obs-{slug}-beta"
    question = f"question-{slug}"
    concepts = f"concepts-{slug}"
    ev_a, ev_b = f"evidence-alpha-{slug}", f"evidence-beta-{slug}"
    reconcile = f"reconcile-{slug}"
    projection = f"projection-{slug}"
    proposal = f"proposal-{slug}"
    frontier = f"frontier-{slug}"

    # Observations wake on an operator APORIA stone as well as on QUERY and
    # SOURCE_DELTA: re-deriving the conflicting readings is exactly what a
    # declared conflict asks the room to do. Everything downstream cascades
    # on SEDIMENT_AVAILABLE through the existing propagation laws.
    observation_kinds = (
        StoneEventKind.QUERY,
        StoneEventKind.SOURCE_DELTA,
        StoneEventKind.APORIA,
    )
    bundles = [
        bundle(
            obs_a,
            lambda inv: _m5_observation(inv, branch="alpha"),
            source=alpha_id,
            kinds=observation_kinds,
        ),
        bundle(
            obs_b,
            lambda inv: _m5_observation(inv, branch="beta"),
            source=beta_id,
            kinds=observation_kinds,
        ),
        bundle(
            question,
            lambda inv: _m5_question(inv, default_topic=f"m5-{slug}"),
            accepts_operator_query=True,
        ),
        bundle(concepts, _m5_concepts, reads=(question,)),
        bundle(ev_a, lambda inv: _m5_evidence(inv, branch="alpha"), reads=(concepts, obs_a)),
        bundle(ev_b, lambda inv: _m5_evidence(inv, branch="beta"), reads=(concepts, obs_b)),
        bundle(reconcile, _m5_reconcile, reads=(ev_a, ev_b)),
        bundle(projection, _m5_projection, reads=(reconcile,)),
        bundle(proposal, _m5_proposal, reads=(reconcile,)),
        bundle(frontier, _m5_frontier_need, reads=(), kinds=(StoneEventKind.FRONTIER_RETURN,)),
    ]
    engine = engine_for(bundles, _m5_source_store(sources, revisions=revisions))

    # Registry capability -> the runtime threads that actually implement it.
    # The compiler is given this binding; it does not know these names itself.
    binding: dict[str, tuple[str, ...]] = {
        "N-S": (obs_a, obs_b),
        "N-Q": (question,),
        "N-K": (concepts,),
        "N-E": (ev_a, ev_b),
        "N-C": (reconcile,),
        "N-P": (projection,),
        "N-H": (proposal,),
        "N-F": (frontier,),
    }
    return engine, uri_map, binding


def observed_missing_source_needs(engine: WaveEngine, run_ids: Sequence[str]) -> tuple[str, ...]:
    """Specific unmet needs the runtime actually recorded, as state evidence.

    An aporia recorded against a reconciliation is a concrete missing-source
    need: the room could not discriminate the competing claims from the
    sources it holds.  Only when such a need exists does the registry's
    ``MissingSourceNeed`` input become available, so the frontier capability
    is genuinely late-eligible rather than permanently dead.
    """

    needs: list[str] = []
    for act in engine.ledger.activations:
        if act.run_id in run_ids and act.error_code == "BODY_APORIA":
            needs.append(act.activation_id)
    return tuple(needs)


__all__ = [
    "BASE_SOURCE_STATE",
    "BASE_STONE_STATE",
    "MISSING_SOURCE_NEED_STATE",
    "SYNTHETIC_RIGHT",
    "build_host_engine",
    "carrier_id_from_uri",
    "declared_source_versions",
    "host_slug",
    "observed_missing_source_needs",
]
