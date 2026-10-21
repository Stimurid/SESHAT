"""M5 acceptance hosts built from the invented room fixture (lab Zeta + sensors)."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult
from seshat.fabric_waves.scenarios import bundle, engine_for, output, source_store


def host_slug(host_id: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", host_id.lower()).strip("-")
    return token[:48] or "m5-host"


def carrier_id_from_uri(uri: str) -> str:
    return uri.replace("synthetic://", "m5-").replace("/", "-")


def _signal_from_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _proposal(inv: BodyInvocation) -> BodyResult:
    reconciled = inv.carried_payload["candidate_sediments"][0]
    return output(
        inv,
        {
            "proposal": "SYNTHETIC_CONDITIONAL_HYPOTHESIS",
            "based_on_version": reconciled.version,
            "promotion": "NOT_AUTHORIZED_WITHOUT_DECISION",
        },
        kind="synthetic.proposal",
    )


def _frontier_request(inv: BodyInvocation) -> BodyResult:
    return output(
        inv,
        {
            "status": "WAITING_SOURCE",
            "need": "EXTERNAL_EVIDENCE_RETURN",
            "synthetic_callback": "DETERMINISTIC_NAMED_FIXTURE_ONLY",
        },
        kind="synthetic.research_need",
    )


def build_host_engine(host: Mapping[str, Any]) -> tuple[WaveEngine, dict[str, str]]:
    """Return engine plus map source URI -> carrier_id."""

    slug = host_slug(str(host["host_id"]))
    sources = list(host.get("source_versions") or [])
    if len(sources) < 2:
        raise ValueError("M5 host requires at least two synthetic sources")
    alpha_src, beta_src = sources[0], sources[1]
    alpha_id = carrier_id_from_uri(str(alpha_src["id"]))
    beta_id = carrier_id_from_uri(str(beta_src["id"]))
    alpha_text = str(alpha_src["content"])
    beta_text = str(beta_src["content"])
    uri_map = {str(alpha_src["id"]): alpha_id, str(beta_src["id"]): beta_id}

    revisions: dict[tuple[str, str, str], Any] = {}
    for stone in host.get("stones") or []:
        if stone.get("kind") != "SOURCE_DELTA":
            continue
        mutation = stone.get("mutation") or {}
        cid = carrier_id_from_uri(str(mutation["source_id"]))
        new_version = str(mutation["new_version"])
        new_content = str(mutation.get("new_content") or mutation.get("text") or "")
        revisions[(cid, str(mutation["old_version"]), new_version)] = carrier(
            carrier_id=cid,
            version=new_version,
            text=new_content,
        )

    # Optional proposal + frontier threads (registry N-H / N-F) without second scheduler.
    extra_bundles = [
        bundle(
            f"proposal-{slug}",
            _proposal,
            reads=(f"reconcile-{slug}",),
        ),
        bundle(
            f"frontier-{slug}",
            _frontier_request,
            reads=(),
            kinds=(),
        ),
    ]
    # Rebuild with extras: merge thread specs into existing engine is heavy; append via new engine.
    from seshat.fabric_waves.carpet_hosts import (  # noqa: PLC0415 — host-local extension
        _read_carrier,
        _question,
        _concepts,
        _evidence,
        _reconcile,
        _answer,
    )

    obs_a = f"obs-{slug}-alpha"
    obs_b = f"obs-{slug}-beta"
    bundles = [
        bundle(obs_a, lambda inv: _read_carrier(inv, branch="alpha"), source=alpha_id),
        bundle(obs_b, lambda inv: _read_carrier(inv, branch="beta"), source=beta_id),
        bundle(
            f"question-{slug}",
            lambda inv: _question(inv, default_topic=f"m5-{slug}"),
            accepts_operator_query=True,
        ),
        bundle(f"concepts-{slug}", _concepts, reads=(f"question-{slug}",)),
        bundle(
            f"evidence-alpha-{slug}",
            lambda inv: _evidence(inv, branch="alpha", signal_key=_signal_from_text(alpha_text)),
            reads=(f"concepts-{slug}", obs_a),
        ),
        bundle(
            f"evidence-beta-{slug}",
            lambda inv: _evidence(inv, branch="beta", signal_key=_signal_from_text(beta_text)),
            reads=(f"concepts-{slug}", obs_b),
        ),
        bundle(
            f"reconcile-{slug}",
            _reconcile,
            reads=(f"evidence-alpha-{slug}", f"evidence-beta-{slug}"),
        ),
        bundle(f"answer-{slug}", _answer, reads=(f"reconcile-{slug}",)),
        *extra_bundles,
    ]
    store = source_store(
        {alpha_id: alpha_text, beta_id: beta_text},
        revisions={key: val for key, val in revisions.items()},
    )
    engine = engine_for(bundles, store)
    return engine, uri_map

