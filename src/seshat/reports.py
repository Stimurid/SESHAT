"""F08-A metadata reports. Owner-bound composition, no method execution or raw reads.

The host session is the authority boundary. Models/digests are not credentials.
Only the returned compose callable belongs on an authenticated transport.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from html import escape
from typing import Literal

from pydantic import Field, model_validator

from seshat.blackboard import Blackboard
from seshat.corpus import (
    CorpusSelectionSpec, FrozenModel, MemberPin, _digest, public_selection_digest,
)
from seshat.corpus_host import HostRuntime
from seshat.scientific_report import ScientificReportAsset, validate_asset
from seshat.scientific_report import render_markdown as scientific_markdown
from seshat.scientific_report import render_html as scientific_html

ReportId = Literal["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"]
BlockCode = Literal[
    "BLOCKED_METHOD", "BLOCKED_EXTERNAL_EVIDENCE", "BLOCKED_ADAPTER",
    "BLOCKED_DECISION_RIGHTS",
]


def canonical_bytes(value) -> bytes:
    if isinstance(value, FrozenModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


class ReportRequest(FrozenModel):
    report_id: ReportId = "R03"
    selections: tuple[CorpusSelectionSpec, ...] = Field(min_length=1)
    rights_scope: str
    as_of: date
    template_version: Literal["F08-A-1"] = "F08-A-1"
    # Optional optimistic pin. Selected visible members only, never population SHA.
    expected_members: tuple[MemberPin, ...] | None = None
    expected_snapshot_digests: tuple[str, ...] | None = None
    expected_method_body_version: str | None = None

    @model_validator(mode="after")
    def unique_selections(self):
        names = [s.selector_id for s in self.selections]
        if len(set(names)) != len(names):
            raise ValueError("DUPLICATE_SELECTION")
        if any(s.view_id != self.rights_scope for s in self.selections):
            raise ValueError("REPORT_SCOPE_MISMATCH")
        return self


class EvidenceRef(FrozenModel):
    ref: str
    kind: Literal["SOURCE_PIN", "HOST_FIELD", "SELECTION", "METHOD_STATE"]
    object_id: str | None = None
    field: str | None = None
    member: MemberPin | None = None
    detail: str = "Metadata provenance; original source fact not verified"


class Claim(FrozenModel):
    label: str
    value: str | int
    state: Literal["KNOWN_METADATA", "UNKNOWN", "NOT_EVALUABLE", "BLOCKED"]
    evidence: tuple[str, ...]


class ReportSection(FrozenModel):
    title: str
    claims: tuple[Claim, ...]


class ReportBlock(FrozenModel):
    code: BlockCode
    unmet_input: str


class SelectionProvenance(FrozenModel):
    selector_id: str
    version: str
    predicate_json: str
    selection_digest: str
    snapshot_digest: str
    members: tuple[MemberPin, ...]


class ReportProjection(FrozenModel):
    report_id: ReportId
    host_id: str
    template_version: str
    as_of: date
    rights_scope: str
    status: Literal["SUBSTANTIVE_METADATA", "PARTIAL_METADATA", "BLOCKED",
                    "SOURCE_GROUNDED_UNREVIEWED"]
    selections: tuple[SelectionProvenance, ...]
    sections: tuple[ReportSection, ...]
    evidence: tuple[EvidenceRef, ...]
    blocks: tuple[ReportBlock, ...]
    source_state: Literal["METADATA_ONLY", "OWNER_SUPPLIED_SOURCE_ANCHORED"] = "METADATA_ONLY"
    currentness: Literal["HOST_RECHECKED_AT_COMPOSITION_NOT_HISTORICAL_AS_OF"] = (
        "HOST_RECHECKED_AT_COMPOSITION_NOT_HISTORICAL_AS_OF")
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    source_mode: Literal["HOST_METADATA", "OWNER_ADMITTED_CLAIMS"] = "HOST_METADATA"
    utterance_mode: Literal["SOURCE_FIXATION_AND_DESCRIPTIVE_COMPARISON"] = (
        "SOURCE_FIXATION_AND_DESCRIPTIVE_COMPARISON")
    method_states: tuple[MethodState, ...] = ()
    source_composition_groups: tuple[SourceCompositionGroup, ...] = ()
    method_evidence_graph: TypedGraph | None = None
    scientific_asset: ScientificReportAsset | None = None
    digest: str


class ReportReceipt(FrozenModel):
    report_id: ReportId
    receipt_version: Literal["F08-A-receipt-1"] = "F08-A-receipt-1"
    host_id: str
    rights_scope: str
    as_of: date
    selections: tuple[SelectionProvenance, ...]
    template_version: str
    projection_digest: str
    report_json_sha256: str
    report_html_sha256: str
    report_markdown_sha256: str | None = None
    method_body_version: str | None = None
    method_body_sha256: str | None = None
    scientific_source_sha256s: tuple[str, ...] = ()
    status: str
    substantive_completed: bool
    blocks: tuple[ReportBlock, ...]


class MethodAsset(FrozenModel):
    """Owner-only binding to a rights-cleared state; never a request parameter.

    No MethodBody is loaded by F08. A verified body pin can identify a previously
    admitted result but cannot authorize new science. Scope must match session.
    """
    object_id: str
    derived_id: str
    version: str
    rights_scope: str
    caller_id: str
    source_member: MemberPin
    body_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class MethodState(FrozenModel):
    object_id: str
    state: Literal["BLOCKED_METHOD"] = "BLOCKED_METHOD"
    result_currentness: Literal["UNAVAILABLE", "ACCEPTED_CURRENT", "STALE_OR_CANDIDATE"]
    diagnostic: str
    evidence: tuple[str, ...]


class SourceCompositionGroup(FrozenModel):
    """A disjoint subset of the selected union classified by source-role structure.

    Group membership is determined by each admitted record's role values, not
    selection membership. Recognized role sets: ``{A}`` -> A-only, ``{D}`` ->
    D-only, ``{A, D}`` -> A+D, anything else (missing or unexpected roles) ->
    UNKNOWN. The four categories are typed and disjoint: a single OBJECT
    appears in at most one group. The denominator is the authorized selected
    union; denied or private corpus rows are never counted.
    """
    group_id: Literal["A-only", "D-only", "A+D", "UNKNOWN"]
    scope: Literal["selected_union"]
    provenance: tuple[str, ...]
    selected_studies: int = Field(ge=0)
    selected_carriers: int = Field(ge=0)
    object_ids: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


class GraphNode(FrozenModel):
    """Typed node in the Object-Method-Evidence graph.

    Each node carries exactly one ``kind`` and the relevant fields for that
    kind; the other kind-specific fields remain None. EVIDENCE nodes only
    reference evidence tokens already admitted to the projection's evidence
    dictionary; no actor-invented source facts.
    """
    node_id: str = Field(min_length=1)
    kind: Literal["OBJECT", "METHOD_CANDIDATE", "METHOD_STATE", "EVIDENCE"]
    object_id: str | None = None
    candidate_label: str | None = None
    candidate_field: str | None = None
    state: Literal["BLOCKED_METHOD"] | None = None
    result_currentness: Literal["UNAVAILABLE", "ACCEPTED_CURRENT", "STALE_OR_CANDIDATE"] | None = None
    diagnostic: str | None = None
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def kind_shape(self):
        if self.kind == "OBJECT":
            if not self.object_id:
                raise ValueError("OBJECT node requires object_id")
        elif self.kind == "METHOD_CANDIDATE":
            if not self.candidate_label or not self.candidate_field or not self.evidence_ref:
                raise ValueError("METHOD_CANDIDATE requires label, field and evidence_ref")
        elif self.kind == "METHOD_STATE":
            if not self.object_id or not self.state or not self.result_currentness or not self.evidence_ref:
                raise ValueError("METHOD_STATE requires object_id, state, currentness and evidence_ref")
        elif self.kind == "EVIDENCE":
            if not self.evidence_ref:
                raise ValueError("EVIDENCE node requires evidence_ref")
        return self


class GraphEdge(FrozenModel):
    """Directed typed edge between two GraphNodes in the same graph."""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class TypedGraph(FrozenModel):
    """Object-Method-Evidence typed graph.

    All edge endpoints exist as nodes in the same graph. MethodBody is never
    verified by F08, so METHOD_STATE state is always ``BLOCKED_METHOD``;
    ``result_currentness`` reflects the asset/board relationship only, never
    scientific acceptance.
    """
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


ReportProjection.model_rebuild()


_FIELDS = ("title", "specialty", "lab", "cohort_year", "defended_on_year",
           "method_candidate", "infrastructure")
_BLOCKS = {
    "R05": ("BLOCKED_EXTERNAL_EVIDENCE", "owner-reviewed external field evidence"),
    "R06": ("BLOCKED_EXTERNAL_EVIDENCE", "owner-reviewed comparative evidence and baseline"),
    "R07": ("BLOCKED_EXTERNAL_EVIDENCE", "owner-reviewed opportunity evidence and constraints"),
    "R08": ("BLOCKED_ADAPTER", "authorized education adapter and learning context"),
    "R09": ("BLOCKED_DECISION_RIGHTS", "institutional decision mandate and authorized inputs"),
}


def report_session(runtime: HostRuntime, *, authenticated_caller: str, authorized_view: str,
                   blackboard: Blackboard | None = None,
                   method_assets: tuple[MethodAsset, ...] = (),
                   scientific_assets: tuple[ScientificReportAsset, ...] = (),
                   scientific_sources: dict[str, bytes] | None = None,
                   method_bodies: dict[str, bytes] | None = None):
    """Owner factory. Do not accept runtime, board or assets from client JSON.

    All fields in the explicit report allowlist must be publishable in the host
    grant. This version has record/carrier rights, not per-field redaction.
    """
    def compose(request: ReportRequest) -> ReportProjection:
        request = ReportRequest.model_validate(request.model_dump())
        if request.rights_scope != authorized_view:
            raise ValueError("REPORT_SCOPE_MISMATCH")
        with runtime._lock:
            inputs = [(s, *runtime._report_inputs(
                s, authenticated_caller=authenticated_caller, authorized_view=authorized_view))
                for s in sorted(request.selections, key=lambda s: s.selector_id)]
            return _compose(request, inputs, blackboard, method_assets, authenticated_caller,
                            runtime._configuration.host_id, scientific_assets,
                            scientific_sources or {}, method_bodies or {})
    return compose


def _classify_member(roles: tuple) -> str:
    """Map an admitted record's role values to a composition category.

    The four typed categories are disjoint; nothing is silently bucketed into
    A-only. Records with no roles or with unexpected role values fall in
    UNKNOWN so the report never silently classifies a private carrier role.
    """
    role_values = frozenset(str(r.value) for r in roles)
    if role_values == frozenset({"A"}):
        return "A-only"
    if role_values == frozenset({"D"}):
        return "D-only"
    if role_values == frozenset({"A", "D"}):
        return "A+D"
    return "UNKNOWN"


def _build_source_composition_groups(ordered_members, rows, selection_refs, refs):
    """Compute disjoint composition groups from selected union records.

    Each record's role set determines its single category; the four groups
    are emitted in deterministic order with their own per-group study /
    carrier counts, sorted object_ids and SOURCE_PIN plus HOST_FIELD role evidence.
    """
    categories = ("A-only", "D-only", "A+D", "UNKNOWN")
    buckets = {cat: [] for cat in categories}
    for member in ordered_members:
        record = rows[member.object_id]
        buckets[_classify_member(record.roles)].append(member)
    groups = []
    for cat in categories:
        members_in_cat = buckets[cat]
        object_ids = tuple(sorted(m.object_id for m in members_in_cat))
        carrier_ids = sorted({c.carrier_id for m in members_in_cat for c in m.carriers})
        member_evidence = []
        for m in members_in_cat:
            token = f"source:{_digest(m)}"
            if token not in refs:
                refs[token] = EvidenceRef(ref=token, kind="SOURCE_PIN",
                                          object_id=m.object_id, member=m)
            member_evidence.append(refs[token])
            record = rows[m.object_id]
            for role in sorted(record.roles, key=lambda r: (str(r.value), r.evidence_ref)):
                role_ref = role.evidence_ref
                member_evidence.append(refs[role_ref])
        member_evidence.sort(key=lambda r: r.ref)
        groups.append(SourceCompositionGroup(
            group_id=cat, scope="selected_union",
            provenance=tuple(selection_refs),
            selected_studies=len(members_in_cat),
            selected_carriers=len(carrier_ids),
            object_ids=object_ids,
            evidence=tuple(member_evidence),
        ))
    return tuple(groups)


def _build_method_evidence_graph(ordered_members, rows, method_state_by_member, refs):
    """Build a directed typed Object-Method-Evidence graph for R02.

    OBJECT nodes cover the selected union.     METHOD_CANDIDATE nodes are
    anchored to their HOST_FIELD evidence ref. METHOD_STATE nodes cover
    every admitted MethodState, including UNAVAILABLE bindings that cite
    only the source pin. EVIDENCE nodes mirror the
    projection's evidence dictionary without inventing private facts.
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[tuple[str, str, str, tuple[str, ...]]] = []

    def add_node(nid, **kwargs):
        if nid in nodes:
            raise ValueError(f"duplicate graph node {nid!r}")
        nodes[nid] = GraphNode(node_id=nid, **kwargs)

    def add_edge(source, target, kind, evidence=()):
        if source not in nodes:
            raise ValueError(f"edge references missing source node {source!r}")
        if target not in nodes:
            raise ValueError(f"edge references missing target node {target!r}")
        edges.append((source, target, kind, tuple(sorted(set(evidence)))))

    def add_evidence_node(ref):
        nid = f"evidence:{ref}"
        if nid not in nodes:
            add_node(nid, kind="EVIDENCE", evidence_ref=ref)
        return nid

    for member in ordered_members:
        nid = f"object:{member.object_id}"
        add_node(nid, kind="OBJECT", object_id=member.object_id)
        source_token = f"source:{_digest(member)}"
        if source_token not in refs:
            refs[source_token] = EvidenceRef(ref=source_token, kind="SOURCE_PIN",
                                             object_id=member.object_id, member=member)
        evidence_nid = add_evidence_node(source_token)
        add_edge(nid, evidence_nid, "EVIDENCED_BY", (source_token,))

    for member in ordered_members:
        record = rows[member.object_id]
        field = next((f for f in record.fields if f.name == "method_candidate"), None)
        if field is None:
            continue
        nid = f"method-candidate:{member.object_id}:{field.name}"
        evidence_ref = field.evidence_ref
        add_node(nid, kind="METHOD_CANDIDATE",
                 candidate_label=str(field.value),
                 candidate_field=field.name,
                 evidence_ref=evidence_ref)
        object_nid = f"object:{member.object_id}"
        add_edge(object_nid, nid, "DECLARES_CANDIDATE")
        evidence_nid = add_evidence_node(evidence_ref)
        add_edge(nid, evidence_nid, "EVIDENCED_BY", (evidence_ref,))

    for member in ordered_members:
        ms = method_state_by_member.get(member.object_id)
        if ms is None:
            continue
        nid = f"method-state:{member.object_id}"
        source_token = f"source:{_digest(member)}"
        if source_token not in refs:
            refs[source_token] = EvidenceRef(ref=source_token, kind="SOURCE_PIN",
                                             object_id=member.object_id, member=member)
        bind_token = ms.evidence[1] if len(ms.evidence) >= 2 else source_token
        add_node(nid, kind="METHOD_STATE",
                 object_id=member.object_id,
                 state=ms.state,
                 result_currentness=ms.result_currentness,
                 diagnostic=ms.diagnostic,
                 evidence_ref=bind_token)
        object_nid = f"object:{member.object_id}"
        add_edge(object_nid, nid, "HAS_STATE")
        evidence_nid = add_evidence_node(bind_token)
        add_edge(nid, evidence_nid, "SUPPORTED_BY", (bind_token,))
        source_evidence_nid = add_evidence_node(source_token)
        add_edge(nid, source_evidence_nid, "BINDS_SOURCE_PIN", (source_token,))

    sorted_nodes = tuple(nodes[nid] for nid in sorted(nodes))
    sorted_edges = tuple(GraphEdge(source=s, target=t, kind=k, evidence=e)
                         for s, t, k, e in sorted(edges))
    return TypedGraph(nodes=sorted_nodes, edges=sorted_edges)


def _compose(request, inputs, board, assets, caller, host_id, scientific_assets=(),
             scientific_sources=None, method_bodies=None):
    refs = {}
    sections = []
    provenance = []
    members = {}
    rows = {}
    membership = {}
    method_states = []

    def claim(label, value, evidence, state="KNOWN_METADATA"):
        return Claim(label=label, value=value, state=state, evidence=tuple(sorted(set(evidence))))

    for selection, snapshot, records in inputs:
        token = f"selection:{snapshot.snapshot_digest}"
        refs[token] = EvidenceRef(ref=token, kind="SELECTION",
                                  detail="Authorized population and predicate evaluation")
        provenance.append(SelectionProvenance(
            selector_id=selection.selector_id, version=selection.version,
            predicate_json=canonical_bytes(selection.predicate.canonical()).decode(),
            selection_digest=public_selection_digest(selection),
            snapshot_digest=snapshot.snapshot_digest, members=snapshot.members))
        membership[selection.selector_id] = {m.object_id for m in snapshot.members}
        for member in snapshot.members:
            if member.object_id in members and members[member.object_id] != member:
                raise ValueError("REPORT_SOURCE_CHANGED")
            members[member.object_id] = member
        for record in records:
            rows[record.research_object.object_id] = record
        metrics = ("eligible_studies", "eligible_carriers", "selected_studies",
                   "selected_carriers", "predicate_false", "unknown_metadata", "not_evaluable")
        sections.append(ReportSection(title=f"Subset {selection.selector_id}@{selection.version}",
            claims=tuple(claim(name, getattr(snapshot, name), (token,)) for name in metrics)))

    ordered_members = tuple(members[key] for key in sorted(members))
    if request.expected_snapshot_digests is not None:
        if sorted(request.expected_snapshot_digests) != sorted(p.snapshot_digest for p in provenance):
            raise ValueError("REPORT_SNAPSHOT_CHANGED")
    if request.expected_members is not None:
        expected = tuple(sorted(request.expected_members, key=lambda m: m.object_id))
        if expected != ordered_members:
            raise ValueError("REPORT_SOURCE_CHANGED")
    if request.report_id == "R01" and len(members) != 1:
        raise ValueError("R01_REQUIRES_ONE_RESEARCH_OBJECT")
    admitted_science = None
    if request.report_id in {"R01", "R02"} and len(members) == 1:
        visible_assets = [a for a in scientific_assets
                          if a.object_id in members and a.caller_id == caller
                          and a.rights_scope == request.rights_scope]
        if (len(visible_assets) == 1 and request.expected_method_body_version is not None
                and visible_assets[0].method_body_version == request.expected_method_body_version
                and visible_assets[0].currentness_as_of == request.as_of):
            admitted_science = ScientificReportAsset.model_validate(
                visible_assets[0].model_dump())
            validate_asset(admitted_science, members[admitted_science.object_id],
                           scientific_sources or {}, method_bodies or {})
    selection_refs = tuple(refs)
    summary = [claim("unique research objects (selected union)", len(members), selection_refs),
               claim("unique source carriers (selected union)",
                     len({c.carrier_id for m in members.values() for c in m.carriers}),
                     selection_refs)]
    names = sorted(membership)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            summary.append(claim(f"overlap {left} / {right}",
                                 len(membership[left] & membership[right]), selection_refs))
    sections.append(ReportSection(title="Local field / authorized denominators", claims=tuple(summary)))

    for member in ordered_members:
        token = f"source:{_digest(member)}"
        refs[token] = EvidenceRef(ref=token, kind="SOURCE_PIN", object_id=member.object_id,
                                  member=member)
        record = rows[member.object_id]
        fields = {f.name: f for f in record.fields if f.name in _FIELDS}
        claims = [claim("research object", member.object_id, (token,)),
                  claim("record version", member.version, (token,)),
                  claim("source status", "METADATA_ONLY / raw source NOT_READ", (token,))]
        for name in _FIELDS:
            field = fields.get(name)
            if field is None:
                claims.append(claim(name, "UNKNOWN", (token,), "UNKNOWN"))
            else:
                # HostRuntime has replaced arbitrary input refs by safe field digests.
                ref = field.evidence_ref
                refs[ref] = EvidenceRef(ref=ref, kind="HOST_FIELD", object_id=member.object_id,
                                        field=name, member=member,
                                        detail="Pinned host metadata field; not scientific acceptance")
                claims.append(claim(name, field.value, (ref,)))
        roles = sorted({str(r.value) for r in record.roles})
        role_refs = []
        for role in record.roles:
            ref = role.evidence_ref
            refs[ref] = EvidenceRef(ref=ref, kind="HOST_FIELD", object_id=member.object_id,
                                    field="source_role", member=member,
                                    detail=f"Pinned source_role {role.value}; not scientific acceptance")
            role_refs.append(ref)
        role_evidence = tuple(sorted({token, *role_refs}))
        claims.append(claim("source roles", "+".join(roles) or "UNKNOWN", role_evidence,
                            "KNOWN_METADATA" if roles else "UNKNOWN"))
        claims.append(claim("degree award", "NOT_EVALUABLE: no degree-award evidence",
                            (token,), "NOT_EVALUABLE"))
        if request.report_id in {"R01", "R02", "R04"}:
            state = "BLOCKED_METHOD: authorized MethodBody/result binding unavailable"
            result_currentness = "UNAVAILABLE"
            method_refs = (token,)
            matching = [a for a in assets if a.object_id == member.object_id
                        and a.caller_id == caller and a.rights_scope == request.rights_scope]
            # Denied assets do not affect diagnostics, counts or digests.
            if len(matching) == 1 and board is not None:
                asset = matching[0]
                try:
                    obj = board.get(asset.derived_id, version=asset.version)
                    if asset.source_member != member:
                        state = "BLOCKED_METHOD: source binding stale"
                    elif obj.research_object_id != member.object_id or obj.object_type != "Method":
                        state = "BLOCKED_METHOD: incompatible state binding"
                    elif obj.acceptance_state.value != "ACCEPTED":
                        state = "BLOCKED_METHOD: stale, historical or candidate state"
                        result_currentness = "STALE_OR_CANDIDATE"
                    elif asset.body_sha256 is None:
                        state = "BLOCKED_METHOD: MethodBody unavailable"
                    elif len([o for o in board.history(member.object_id, "Method")
                              if o.acceptance_state.value == "ACCEPTED"]) != 1:
                        state = "BLOCKED_METHOD: ambiguous accepted state"
                    else:
                        result_currentness = "ACCEPTED_CURRENT"
                        state = ("BLOCKED_METHOD: accepted-current result binding only; "
                                 "MethodBody bytes not read or verified; interpretation NOT_EXECUTED")
                    method_token = "method:" + _digest({
                        "asset": asset.model_dump(mode="json"), "state": state})
                    refs[method_token] = EvidenceRef(
                        ref=method_token, kind="METHOD_STATE", object_id=member.object_id,
                        detail=f"{asset.derived_id}@{asset.version}: {state}")
                    method_refs = (token, method_token)
                except (KeyError, ValueError):
                    state = "BLOCKED_METHOD: result version unavailable"
            claims.append(claim("Method state", state, method_refs,
                                "BLOCKED" if state.startswith("BLOCKED") else "KNOWN_METADATA"))
            method_states.append(MethodState(object_id=member.object_id,
                result_currentness=result_currentness,
                diagnostic=state, evidence=method_refs))
        sections.append(ReportSection(title=f"Evidence matrix / {member.object_id}", claims=tuple(claims)))

    composition_groups: tuple[SourceCompositionGroup, ...] = ()
    if request.report_id == "R03":
        composition_groups = _build_source_composition_groups(ordered_members, rows,
                                                              selection_refs, refs)
        group_claims = [claim(f"{g.group_id} studies", g.selected_studies,
                              tuple(ref_.ref for ref_ in g.evidence) or selection_refs)
                        for g in composition_groups]
        group_claims.extend(claim(f"{g.group_id} carriers", g.selected_carriers,
                                  tuple(ref_.ref for ref_ in g.evidence) or selection_refs)
                            for g in composition_groups)
        group_claims.append(claim(
            "composition provenance", "selected_union / disjoint by OBJECT role set",
            selection_refs))
        sections.append(ReportSection(
            title="Source composition groups / selected union",
            claims=tuple(group_claims)))
        for axis in ("specialty", "lab", "cohort_year", "defended_on_year"):
            buckets = {}
            for member in ordered_members:
                record = rows[member.object_id]
                field = next((f for f in record.fields if f.name == axis), None)
                label = str(field.value) if field is not None else "UNKNOWN"
                evidence = field.evidence_ref if field is not None else f"source:{_digest(member)}"
                buckets.setdefault(label, []).append(evidence)
            sections.append(ReportSection(title=f"Distribution / {axis} / selected union",
                claims=tuple(claim(label, len(evidence), evidence)
                             for label, evidence in sorted(buckets.items()))))

    method_evidence_graph: TypedGraph | None = None
    if request.report_id == "R02":
        method_state_by_member = {ms.object_id: ms for ms in method_states}
        method_evidence_graph = _build_method_evidence_graph(ordered_members, rows,
                                                             method_state_by_member, refs)

    blocks = []
    if request.report_id in _BLOCKS:
        code, unmet = _BLOCKS[request.report_id]
        blocks.append(ReportBlock(code=code, unmet_input=unmet))
    elif request.report_id in {"R01", "R02", "R04"} and admitted_science is None:
        blocks.append(ReportBlock(code="BLOCKED_METHOD",
                                  unmet_input="authorized method execution and scientific review"))
    status = ("SOURCE_GROUNDED_UNREVIEWED" if admitted_science is not None else
              "BLOCKED" if request.report_id in _BLOCKS else
              "SUBSTANTIVE_METADATA" if request.report_id == "R03" else "PARTIAL_METADATA")
    projection = ReportProjection(
        report_id=request.report_id, host_id=host_id, template_version=request.template_version,
        as_of=request.as_of, rights_scope=request.rights_scope, status=status,
        selections=tuple(provenance), sections=tuple(sections),
        evidence=tuple(refs[key] for key in sorted(refs)), blocks=tuple(blocks),
        method_states=tuple(method_states),
        source_composition_groups=composition_groups,
        method_evidence_graph=method_evidence_graph,
        scientific_asset=admitted_science,
        source_state=("OWNER_SUPPLIED_SOURCE_ANCHORED" if admitted_science
                      else "METADATA_ONLY"),
        source_mode=("OWNER_ADMITTED_CLAIMS" if admitted_science else "HOST_METADATA"),
        digest="")
    return projection.model_copy(update={"digest": _digest(
        projection.model_dump(mode="json", exclude={"digest"}))})


def render_html(report: ReportProjection) -> bytes:
    """No URLs, scripts, remote resources or raw carrier metadata are rendered."""
    if report.scientific_asset is not None:
        return scientific_html(report.scientific_asset).encode("utf-8")
    def e(value):
        return escape(str(value), quote=True)
    anchors = {ref.ref: f"e{i}" for i, ref in enumerate(report.evidence)}
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
             'style-src \'unsafe-inline\'">',
             '<title>SESHAT evidence report</title><style>body{font:16px system-ui;'
             'max-width:1100px;margin:2em auto;padding:1em}table{border-collapse:collapse;'
             'width:100%}td,th{border:1px solid #aaa;padding:.5em;text-align:left}'
             'code{overflow-wrap:anywhere}details{margin:1em 0}</style><body>',
             f'<h1>{e(report.report_id)} — {e(report.status)}</h1>',
             '<p>Metadata evidence only. No scientific acceptance, defense or degree award '
             'is inferred. Counts use authorized populations only. Cohort is not defense year.</p>',
             f'<p>As-of label: {e(report.as_of)}. Sources rechecked at composition; '
             'historical as-of reconstruction is unavailable.</p>',
             f'<p>Template {e(report.template_version)} · digest <code>{e(report.digest)}</code></p>']
    for block in report.blocks:
        parts.append(f'<p><strong>{e(block.code)}</strong>: {e(block.unmet_input)}</p>')
    parts.append('<h2>Exact selection provenance</h2>')
    for selection in report.selections:
        parts.append(f'<details><summary>{e(selection.selector_id)}@{e(selection.version)}</summary>'
                     f'<pre>{e(json.dumps(selection.model_dump(mode="json"), indent=2))}</pre></details>')
    if report.report_id == "R04":
        axes = ("research object", "method_candidate", "infrastructure", "lab", "Method state")
        parts.append('<h2>Object × Method × Infrastructure atlas</h2><table><tr>'
                     + ''.join(f'<th>{e(axis)}</th>' for axis in axes) + '</tr>')
        for section in report.sections:
            if not section.title.startswith("Evidence matrix / "):
                continue
            fields = {c.label: c for c in section.claims}
            parts.append('<tr>')
            for axis in axes:
                cell = fields[axis]
                links = ' '.join(f'<a href="#{anchors[r]}">evidence</a>' for r in cell.evidence)
                parts.append(f'<td>{e(cell.value)} {links}</td>')
            parts.append('</tr>')
        parts.append('</table>')
    if report.source_composition_groups:
        parts.append('<h2>Source composition groups</h2>')
        parts.append('<p>Disjoint composition of the authorized selected union by '
                     'OBJECT role set. Group denominator: selected union, never the '
                     'private corpus. UNKNOWN covers missing/non-{A,D,A+D} role sets.</p>')
        parts.append('<table><tr><th>Group</th><th>Selected studies</th>'
                     '<th>Selected carriers</th><th>Object IDs</th>'
                     '<th>Provenance</th><th>Evidence</th></tr>')
        for group in report.source_composition_groups:
            label = group.group_id
            ids = ", ".join(group.object_ids) if group.object_ids else "(none)"
            ev_links = ' '.join(f'<a href="#{anchors[r.ref]}">evidence</a>'
                                for r in group.evidence)
            parts.append(f'<tr><td>{e(label)}</td>'
                         f'<td>{e(group.selected_studies)}</td>'
                         f'<td>{e(group.selected_carriers)}</td>'
                         f'<td>{e(ids)}</td>'
                         f'<td>{e(group.scope)}</td>'
                         f'<td>{ev_links}</td></tr>')
        parts.append('</table>')
        for label in ("A-only", "D-only", "A+D"):
            parts.append(f'<p><strong>{e(label)}</strong></p>')
    if report.method_evidence_graph is not None:
        graph = report.method_evidence_graph
        parts.append('<h2>Object\u2013Method\u2013Evidence graph</h2>')
        parts.append('<p>Typed directed graph over OBJECT, METHOD_CANDIDATE, '
                     'METHOD_STATE and EVIDENCE nodes. Every edge endpoint exists; '
                     'no actor-invented source facts. State remains '
                     'BLOCKED_METHOD because no actual MethodBody is verified by F08.</p>')
        parts.append('<h3>Nodes</h3><table><tr><th>Node ID</th><th>Kind</th>'
                     '<th>Detail</th><th>Evidence</th></tr>')
        for node in graph.nodes:
            if node.kind == "OBJECT":
                detail = f"object_id={node.object_id}"
            elif node.kind == "METHOD_CANDIDATE":
                detail = (f"label={node.candidate_label}; "
                          f"field={node.candidate_field}")
            elif node.kind == "METHOD_STATE":
                detail = (f"state={node.state}; "
                          f"result_currentness={node.result_currentness}; "
                          f"diagnostic={node.diagnostic}")
            else:
                detail = f"evidence_ref={node.evidence_ref}"
            ev_link = ""
            if node.evidence_ref and node.evidence_ref in anchors:
                ev_link = f'<a href="#{anchors[node.evidence_ref]}">evidence</a>'
            parts.append(f'<tr><td>{e(node.node_id)}</td>'
                         f'<td>{e(node.kind)}</td>'
                         f'<td>{e(detail)}</td>'
                         f'<td>{ev_link}</td></tr>')
        parts.append('</table>')
        parts.append('<h3>Edges</h3><table><tr><th>Source</th><th>Kind</th>'
                     '<th>Target</th><th>Evidence</th></tr>')
        for edge in graph.edges:
            ev_links = ' '.join(f'<a href="#{anchors[r]}">{e(r)}</a>'
                                for r in edge.evidence if r in anchors)
            parts.append(f'<tr><td>{e(edge.source)}</td>'
                         f'<td>{e(edge.kind)}</td>'
                         f'<td>{e(edge.target)}</td>'
                         f'<td>{ev_links}</td></tr>')
        parts.append('</table>')
    for section in report.sections:
        parts.append(f'<h2>{e(section.title)}</h2><table><tr><th>Claim</th><th>Value</th>'
                     '<th>State</th><th>Evidence</th></tr>')
        for claim in section.claims:
            links = ' '.join(f'<a href="#{anchors[r]}">{e(r)}</a>' for r in claim.evidence)
            parts.append(f'<tr><td>{e(claim.label)}</td><td>{e(claim.value)}</td>'
                         f'<td>{e(claim.state)}</td><td>{links}</td></tr>')
        parts.append('</table>')
    parts.append('<h2>Authorized evidence drillback</h2>')
    for ref in report.evidence:
        parts.append(f'<details id="{anchors[ref.ref]}"><summary>{e(ref.ref)}</summary>'
                     f'<pre>{e(json.dumps(ref.model_dump(mode="json"), indent=2))}</pre></details>')
    parts.append('</body></html>')
    return '\n'.join(parts).encode('utf-8')


def artifacts(report: ReportProjection) -> dict[str, bytes]:
    payload = report.model_dump(mode="json", exclude={"digest"})
    if report.digest != _digest(payload):
        raise ValueError("REPORT_DIGEST_MISMATCH")
    raw, html = canonical_bytes(report), render_html(report)
    markdown = (scientific_markdown(report.scientific_asset).encode("utf-8")
                if report.scientific_asset is not None else None)
    receipt = ReportReceipt(
        report_id=report.report_id, host_id=report.host_id, rights_scope=report.rights_scope,
        as_of=report.as_of, selections=report.selections, template_version=report.template_version,
        projection_digest=report.digest, report_json_sha256=hashlib.sha256(raw).hexdigest(),
        report_html_sha256=hashlib.sha256(html).hexdigest(), status=report.status,
        report_markdown_sha256=(hashlib.sha256(markdown).hexdigest() if markdown else None),
        method_body_version=(report.scientific_asset.method_body_version
                             if report.scientific_asset else None),
        method_body_sha256=(report.scientific_asset.method_body_sha256
                            if report.scientific_asset else None),
        scientific_source_sha256s=(tuple(sorted({c.source_sha256
            for sub in report.scientific_asset.subassemblies for c in sub.claims}))
            if report.scientific_asset else ()),
        substantive_completed=report.status in {"SUBSTANTIVE_METADATA",
                                                 "SOURCE_GROUNDED_UNREVIEWED"}, blocks=report.blocks)
    result = {"report.json": raw, "report.html": html, "receipt.json": canonical_bytes(receipt)}
    if markdown is not None:
        result["report.md"] = markdown
    return result
