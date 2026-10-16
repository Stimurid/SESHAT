"""Pinned, public synthetic mechanics fixtures. No private method bodies."""
from dataclasses import asdict, dataclass
from typing import Callable

from seshat.contracts import RawAccessPolicy
from seshat.fabric_waves.contracts import (
    EpistemicLevel, MethodBodyRef, PropagationLaw, StoneEventKind,
    ThreadNodeSpec, WorkflowThreadSpec,
)
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.fixtures import carrier
from seshat.fabric_waves.method_body import BodyInvocation, BodyResult, MethodBodyRegistry
from seshat.fabric_waves.sediment import SedimentRecord, SedimentState, payload_hash
from seshat.fabric_waves.source_access import FabricCarrierStore


@dataclass(frozen=True)
class SyntheticBody:
    method_body_id: str
    version: str
    fn: Callable[[BodyInvocation], BodyResult]

    def __call__(self, invocation: BodyInvocation) -> BodyResult:
        return self.fn(invocation)


@dataclass(frozen=True)
class SyntheticCorpusSelection:
    """Fixture-only exact membership; does not implement or accept production F07."""
    selection_id: str
    version: str
    members: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if len({sid for sid, _ in self.members}) != len(self.members):
            raise ValueError("DUPLICATE_SELECTION_MEMBER")


def output(inv: BodyInvocation, payload: dict, kind: str = "synthetic.state") -> BodyResult:
    digest = payload_hash(payload)
    return BodyResult(produced_sediments=(SedimentRecord(
        sediment_id=inv.carried_payload["output_sediment_id"], object_type=kind,
        version=digest, research_object_id="synthetic", payload=payload, payload_hash=digest,
        provenance=("PUBLIC_SYNTHETIC_FIXTURE",), method_body_refs=(inv.method_body_ref,),
        source_carrier_refs=tuple(inv.carried_payload["carriers"]),
        epistemic_level=EpistemicLevel.E1 if inv.carried_payload["source_access_manifest"] else EpistemicLevel.E3,
        read_dependencies=inv.consumed_sediment_ids, produced_by_thread=inv.thread_id,
        produced_at_tick=inv.tick, produced_in_wave=inv.wave_index,
        produced_by_stone_kind=inv.stone_kind,
    ),))


def bundle(tid: str, fn: Callable, *, reads: tuple[str, ...] = (),
           source: str | None = None, kinds: tuple[StoneEventKind, ...] | None = None,
           accepts_operator_query: bool = False):
    ref = MethodBodyRef(method_body_id="synthetic." + tid, version="1")
    spec = WorkflowThreadSpec(thread_id=tid, name=tid, purpose="synthetic mechanical oracle",
        method_body_refs=(ref,), admissible_source_carriers=(source,) if source else (),
        raw_access_policy=RawAccessPolicy.FULL_REQUIRED if source else RawAccessPolicy.NEVER,
        accepts_operator_query=accepts_operator_query,
        nodes=(ThreadNodeSpec(node_id="compute", operation_id=ref.method_body_id,
            method_body_ref=ref, consumes_sediment_ids=reads,
            produces_sediment_id=tid, output_sediment_type="synthetic.state"),),
        input_state=reads, output_state=(tid,), exit_criterion="typed state or explicit APORIA",
        bounded_budget_hint=8)
    law = PropagationLaw(thread_id=tid, initial_state=reads,
        wakes_on_carrier_ids=(source,) if source else (),
        wakes_on_stone_kinds=kinds or ((StoneEventKind.SEDIMENT_AVAILABLE,) if reads
                                     else (StoneEventKind.QUERY, StoneEventKind.SOURCE_DELTA)))
    return spec, law, SyntheticBody(ref.method_body_id, ref.version, fn)


def engine_for(bundles, store=None) -> WaveEngine:
    registry = MethodBodyRegistry()
    for spec, _, body in bundles:
        registry.register(body, operations=tuple(n.operation_id for n in spec.nodes))
    return WaveEngine(thread_specs={s.thread_id: s for s, _, _ in bundles},
        propagation_laws={s.thread_id: law for s, law, _ in bundles},
        bodies=registry, sediment=SedimentState(), carrier_store=store)


def source_store(texts: dict[str, str], *, revisions: dict | None = None) -> FabricCarrierStore:
    pairs = {cid: carrier(carrier_id=cid, version="1", text=text) for cid, text in texts.items()}
    def revision(cid, old, new):
        # Host-owned fixture pins. Nothing from the event is used to mint rights.
        return revisions[(cid, old, new)]
    return FabricCarrierStore(carriers={cid: pair[0] for cid, pair in pairs.items()},
        contents={cid: pair[1] for cid, pair in pairs.items()},
        revision_provider=revision if revisions is not None else None)


def repair_engine() -> WaveEngine:
    def reconstruct(inv):
        return output(inv, {"object_scope": "all", "observed": inv.carried_payload["text"]})
    def critique(inv):
        obj = inv.carried_payload["candidate_sediments"][0]
        return output(inv, {"object_version": obj.version,
                            "contradiction": obj.payload["object_scope"] == "all",
                            "required_scope": "observed-only"})
    def refuse(inv):
        critique_state = inv.carried_payload["candidate_sediments"][0]
        if critique_state.payload["contradiction"]:
            return BodyResult(aporia="Synthetic object scope needs human methodological resolution")
        return output(inv, {"repaired": True})
    return engine_for([
        bundle("object", reconstruct, source="source"),
        bundle("method-critic", critique, reads=("object",)),
        bundle("object-repair", refuse, reads=("method-critic",)),
    ], source_store({"source": "synthetic bounded observation"}))


def corpus_engine(*, reverse: bool = False) -> WaveEngine:
    # Explicit source+version membership. Similar subjects confer no membership.
    selection = SyntheticCorpusSelection("synthetic-selection", "1",
                                          (("study-a", "1"), ("study-b", "1")))
    def study(inv):
        return output(inv, {"count": len(inv.carried_payload["text"])})
    def aggregate(inv):
        states = inv.carried_payload["candidate_sediments"]
        if {r.sediment_id for r in states} != {sid for sid, _ in selection.members}:
            return BodyResult(aporia="SELECTION_MEMBERSHIP_MISMATCH")
        for record in states:
            pinned = dict(selection.members)[record.sediment_id]
            if (record.source_access_manifest is None or not record.source_access_manifest.receipts
                    or any(r.source_version != pinned for r in record.source_access_manifest.receipts)):
                return BodyResult(aporia="SELECTION_SOURCE_VERSION_MISMATCH")
        return output(inv, {"selection": asdict(selection), "count": sum(r.payload["count"] for r in states),
                            "cached_refs": {r.sediment_id: r.version for r in states}})
    bundles = [bundle("study-a", study, source="study-a"),
               bundle("study-b", study, source="study-b"),
               bundle("aggregate", aggregate, reads=("study-a", "study-b"))]
    return engine_for(list(reversed(bundles)) if reverse else bundles,
                      source_store({"study-a": "abc", "study-b": "defgh"}))


def revision_engine() -> WaveEngine:
    def source(inv):
        return output(inv, {"count": len(inv.carried_payload["text"])})
    def derived(inv):
        state = inv.carried_payload["candidate_sediments"][0]
        return output(inv, {"count": state.payload["count"], "upstream_version": state.version})
    revision = carrier(carrier_id="source-a", version="2", text="revised synthetic source")
    return engine_for([
        bundle("A", source, source="source-a"), bundle("B", derived, reads=("A",)),
        bundle("C", derived, reads=("B",)), bundle("U", source, source="source-u"),
    ], source_store({"source-a": "old", "source-u": "unrelated"},
                    revisions={("source-a", "1", "2"): revision}))
