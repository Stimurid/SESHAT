"""F07: deterministic, metadata-only corpus selections.

The host supplies evidenced metadata and an independent entitlement authority.
Nothing in ResearchObject.metadata or SourceCarrier.metadata grants visibility.
Selections are source-addressed views, never semantic admissions or raw reads.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seshat.blackboard import AmbiguousStateError, Blackboard
from seshat.contracts import ResearchObject, SourceCarrier


def _digest(value: BaseModel | dict) -> str:
    data = (
        value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, BaseModel) else value
    )
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ManifestPin(FrozenModel):
    manifest_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceField(FrozenModel):
    """A host-declared field with a source-specific provenance token."""

    name: str = Field(min_length=1)
    value: str | int
    evidence_ref: str = Field(min_length=1)


class StudyRecord(FrozenModel):
    research_object: ResearchObject
    carriers: tuple[SourceCarrier, ...]
    fields: tuple[EvidenceField, ...] = ()
    roles: tuple[EvidenceField, ...] = ()

    @model_validator(mode="after")
    def pinned(self) -> StudyRecord:
        obj = self.research_object
        if not obj.object_id or not obj.version or not obj.carrier_ids:
            raise ValueError("study identity and carrier references are required")
        by_id = {carrier.carrier_id: carrier for carrier in self.carriers}
        if len(by_id) != len(self.carriers) or set(by_id) != set(obj.carrier_ids):
            raise ValueError("carrier references must be unique and complete")
        if any(not c.version or not c.content_sha256 or
               len(c.content_sha256) != 64 or
               any(x not in "0123456789abcdef" for x in c.content_sha256)
               for c in self.carriers):
            raise ValueError("carrier version and lowercase SHA-256 are required")
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("duplicate evidenced field")
        if any(role.name != "source_role" for role in self.roles):
            raise ValueError("source roles require explicit source_role evidence")
        return self


class PopulationManifest(FrozenModel):
    pin: ManifestPin
    declared_fields: frozenset[str]


class Predicate(FrozenModel):
    op: Literal["ids", "range", "equals", "and", "or"]
    field: str | None = None
    ids: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    lower: int | None = None
    upper: int | None = None
    children: tuple[Predicate, ...] = ()

    @model_validator(mode="after")
    def valid_shape(self) -> Predicate:
        if self.op == "ids":
            valid = bool(self.ids) and not (
                self.field or self.values or self.children or self.lower is not None
                or self.upper is not None
            )
        elif self.op == "range":
            valid = (bool(self.field) and self.lower is not None and self.upper is not None
                     and self.lower <= self.upper
                     and not (self.ids or self.values or self.children))
        elif self.op == "equals":
            valid = bool(self.field and self.values) and not (
                self.ids or self.children or self.lower is not None or self.upper is not None
            )
        else:
            valid = len(self.children) >= 2 and not (
                self.field or self.ids or self.values or self.lower is not None
                or self.upper is not None
            )
        if not valid:
            raise ValueError("invalid predicate shape")
        return self

    def canonical(self) -> dict:
        if self.op == "ids":
            return {"op": self.op, "ids": sorted(set(self.ids))}
        if self.op == "range":
            return {"op": self.op, "field": self.field, "lower": self.lower,
                    "upper": self.upper}
        if self.op == "equals":
            return {"op": self.op, "field": self.field, "values": sorted(set(self.values))}
        children = [child.canonical() for child in self.children]
        by_json = {
            json.dumps(child, ensure_ascii=False, sort_keys=True, separators=(",", ":")): child
            for child in children
        }
        return {"op": self.op, "children": [by_json[key] for key in sorted(by_json)]}


Predicate.model_rebuild()


class CorpusSelectionSpec(FrozenModel):
    selector_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    manifest: ManifestPin
    predicate: Predicate
    caller_id: str = Field(min_length=1)
    view_id: str = Field(min_length=1)
    semantics_version: Literal["F07-1"] = "F07-1"

    @property
    def canonical_json(self) -> str:
        data = {**self.model_dump(mode="json", exclude={"predicate"}),
                "predicate": self.predicate.canonical()}
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


class Match(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN_METADATA"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class Visibility(StrEnum):
    VISIBLE = "VISIBLE"
    DENIED = "DENIED"


class EntitlementAuthority(Protocol):
    """Implemented by the trusted host, outside untrusted record metadata."""

    def revision(self, caller_id: str, view_id: str) -> str: ...

    def visibility(self, caller_id: str, view_id: str, object_id: str) -> Visibility: ...

    def carrier_visibility(
        self, caller_id: str, view_id: str, object_id: str, carrier_id: str
    ) -> Visibility: ...

    def may_count_denied(self, caller_id: str, view_id: str) -> bool: ...

    def seal_selection(self, caller_id: str, view_id: str, canonical_json: str) -> str: ...


class TrustedManifestAuthority(Protocol):
    """Host-owned reader, injected by the trusted runtime, never by a request body.

    The implementation must read its own authoritative manifest and return its
    canonical records, including primary-source field references and carrier
    pins. It must check issuer rights before returning them. This interface is
    a trust boundary, not a signature or a claim that source bytes were read.
    """

    def current_pin(self, manifest_id: str) -> ManifestPin: ...

    def resolve(self, pin: ManifestPin) -> tuple[PopulationManifest, tuple[StudyRecord, ...]]: ...


def canonical_population_digest(
    manifest_id: str, version: str, declared_fields: frozenset[str],
    records: tuple[StudyRecord, ...] | list[StudyRecord],
) -> str:
    """Domain-separated content pin over the complete authoritative population."""
    payloads = [_record_payload(record) for record in records]
    payloads.sort(key=lambda value: json.dumps(value, ensure_ascii=False,
                                               sort_keys=True, separators=(",", ":")))
    return _digest({"domain": "seshat.f07.population.v1", "manifest_id": manifest_id,
                    "version": version, "declared_fields": sorted(declared_fields),
                    "records": payloads})


class CarrierPin(FrozenModel):
    carrier_id: str
    version: str
    sha256: str
    identity_state: Literal["PIN_ASSERTED_NOT_VERIFIED", "METADATA_PIN_VERIFIED_BY_HOST"] = (
        "PIN_ASSERTED_NOT_VERIFIED")


class MemberPin(FrozenModel):
    object_id: str
    version: str
    carriers: tuple[CarrierPin, ...]


class CorpusSpaceSnapshot(FrozenModel):
    selection_digest: str
    manifest_digest: str
    semantics_version: Literal["F07-1"] = "F07-1"
    authorization_revision: str
    members: tuple[MemberPin, ...]
    eligible_studies: int
    eligible_carriers: int
    selected_studies: int
    selected_carriers: int
    predicate_false: int
    unknown_metadata: int
    not_evaluable: int
    denied_studies: int | None
    suppressed_remainder: bool
    input_digest: str
    snapshot_digest: str
    source_state: Literal["METADATA_ONLY", "EVIDENCE_VERIFIED"] = "METADATA_ONLY"
    runtime_ingestion_state: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    semantic_acceptance_state: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


def _match(predicate: Predicate, record: StudyRecord, declared: frozenset[str]) -> Match:
    if predicate.op == "ids":
        return Match.TRUE if record.research_object.object_id in predicate.ids else Match.FALSE
    if predicate.op in {"and", "or"}:
        outcomes = [_match(child, record, declared) for child in predicate.children]
        if predicate.op == "and":
            if Match.FALSE in outcomes:
                return Match.FALSE
            if all(item is Match.TRUE for item in outcomes):
                return Match.TRUE
        else:
            if Match.TRUE in outcomes:
                return Match.TRUE
            if all(item is Match.FALSE for item in outcomes):
                return Match.FALSE
        return Match.NOT_EVALUABLE if Match.NOT_EVALUABLE in outcomes else Match.UNKNOWN
    if predicate.field not in declared:
        return Match.NOT_EVALUABLE
    if predicate.field == "source_role":
        if predicate.op != "equals":
            return Match.NOT_EVALUABLE
        if not record.roles:
            return Match.UNKNOWN
        return (Match.TRUE if any(str(role.value) in predicate.values for role in record.roles)
                else Match.FALSE)
    fields = {field.name: field.value for field in record.fields}
    value = fields.get(predicate.field)
    if value is None:
        return Match.UNKNOWN
    if predicate.op == "equals":
        return Match.TRUE if str(value) in predicate.values else Match.FALSE
    if isinstance(value, bool) or not isinstance(value, int):
        return Match.NOT_EVALUABLE
    return Match.TRUE if predicate.lower <= value <= predicate.upper else Match.FALSE


def _safe_member(record: StudyRecord, *, verified: bool = False) -> MemberPin:
    obj = record.research_object
    return MemberPin(
        object_id=obj.object_id,
        version=obj.version,
        carriers=tuple(sorted((CarrierPin(
            carrier_id=c.carrier_id, version=c.version, sha256=c.content_sha256,
            identity_state=("METADATA_PIN_VERIFIED_BY_HOST" if verified
                            else "PIN_ASSERTED_NOT_VERIFIED")) for c in record.carriers),
                              key=lambda c: c.carrier_id)),
    )


def build_corpus_space(
    spec: CorpusSelectionSpec,
    manifest: PopulationManifest,
    records: tuple[StudyRecord, ...] | list[StudyRecord],
    authority: EntitlementAuthority,
    *, trusted_manifest: TrustedManifestAuthority | None = None,
    require_verified: bool = False,
) -> CorpusSpaceSnapshot:
    """Re-evaluate rights before touching metadata; no denied IDs enter a receipt.

    A denied study contributes to no visible denominator. Its count is emitted
    only if the host authority explicitly grants that aggregate right.
    """
    if spec.manifest != manifest.pin:
        raise ValueError("population manifest mismatch")
    if require_verified:
        if trusted_manifest is None:
            raise ValueError("trusted manifest authority required")
        try:
            if trusted_manifest.current_pin(spec.manifest.manifest_id) != spec.manifest:
                raise ValueError("unrecognized authority pin")
            authoritative_manifest, authoritative_records = trusted_manifest.resolve(spec.manifest)
            if authoritative_manifest.pin != spec.manifest:
                raise ValueError("authority pin mismatch")
            actual = canonical_population_digest(
                authoritative_manifest.pin.manifest_id,
                authoritative_manifest.pin.version,
                authoritative_manifest.declared_fields, authoritative_records,
            )
            if actual != spec.manifest.sha256:
                raise ValueError("authority content mismatch")
        except Exception:
            raise ValueError("trusted manifest verification failed") from None
        # The request's records and declared fields have no authority in this mode.
        manifest = authoritative_manifest
        records = authoritative_records
    try:
        revision = authority.revision(spec.caller_id, spec.view_id)
        may_count = authority.may_count_denied(spec.caller_id, spec.view_id)
        # Host-keyed digest prevents a public snapshot from becoming an oracle
        # for low-entropy hidden IDs in an exact-ID predicate.
        # The full population SHA and rights revision may change solely because
        # of hidden rows. Neither may influence a public view without count rights.
        public_spec = json.loads(spec.canonical_json)
        if not may_count:
            public_spec["manifest"].pop("sha256", None)
        sealed_selection = authority.seal_selection(
            spec.caller_id, spec.view_id,
            json.dumps(public_spec, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
        )
    except Exception:
        raise ValueError("entitlement check failed") from None
    if not isinstance(revision, str) or not revision:
        raise ValueError("authorization revision is required")
    if not isinstance(may_count, bool):
        raise ValueError("invalid denied-count entitlement")
    # The unkeyed spec.digest is for rights-controlled internal storage only.
    if (not isinstance(sealed_selection, str) or len(sealed_selection) != 64
            or any(ch not in "0123456789abcdef" for ch in sealed_selection)):
        raise ValueError("selection seal is required")
    visible: dict[str, StudyRecord] = {}
    seen: dict[str, str] = {}
    denied_ids: set[str] = set()
    for supplied in records:
        # Copy before the host callback can mutate the caller's input.
        record = supplied.model_copy(deep=True)
        object_id = record.research_object.object_id
        try:
            decision = authority.visibility(spec.caller_id, spec.view_id, object_id)
            if decision is Visibility.VISIBLE:
                carrier_decisions = [authority.carrier_visibility(
                    spec.caller_id, spec.view_id, object_id, carrier.carrier_id
                ) for carrier in record.carriers]
                if any(item is Visibility.DENIED for item in carrier_decisions):
                    decision = Visibility.DENIED
                elif any(item is not Visibility.VISIBLE for item in carrier_decisions):
                    raise ValueError("invalid entitlement decision")
        except Exception:
            raise ValueError("entitlement check failed") from None
        if decision is Visibility.DENIED:
            denied_ids.add(object_id)
            continue
        if decision is not Visibility.VISIBLE:
            raise ValueError("invalid entitlement decision")
        try:
            fingerprint = _digest(_record_payload(record))
        except Exception:
            raise ValueError("invalid study pin") from None
        prior_fingerprint = seen.setdefault(object_id, fingerprint)
        if prior_fingerprint != fingerprint:
            raise ValueError("conflicting duplicate study")
        previous = visible.get(object_id)
        if previous is not None:
            continue
        visible[object_id] = record
    # A changing decision for the same object is an entitlement failure. Do not
    # reveal whether that object was denied in an error sent to the caller.
    if denied_ids.intersection(visible):
        raise ValueError("entitlement check failed")
    denied = len(denied_ids)
    # The manifest SHA is a host-pinned source identity. This additional digest
    # binds the exact visible study/carrier/field contents used for this view.
    ordered = [visible[key] for key in sorted(visible)]
    public_pin = manifest.pin.model_dump(mode="json")
    if not may_count:
        public_pin.pop("sha256", None)
    input_digest = _digest({"manifest": {"pin": public_pin,
                                         "declared_fields": sorted(manifest.declared_fields)},
                            "records": [_record_payload(item) for item in ordered]})
    members: list[MemberPin] = []
    outcomes = {match: 0 for match in Match}
    for record in ordered:
        outcome = _match(spec.predicate, record, manifest.declared_fields)
        outcomes[outcome] += 1
        if outcome is Match.TRUE:
            members.append(_safe_member(record, verified=require_verified))
    payload = {
        "selection_digest": sealed_selection,
        "authorization_revision": revision if may_count else "VISIBLE_PROJECTION",
        "input_digest": input_digest,
        "members": [member.model_dump(mode="json") for member in members],
        "outcomes": {key.value: value for key, value in outcomes.items()},
        "denied": denied if may_count else None,
        "suppressed_remainder": False,
    }
    return CorpusSpaceSnapshot(
        selection_digest=sealed_selection,
        manifest_digest=_digest(public_pin),
        authorization_revision=revision if may_count else "VISIBLE_PROJECTION",
        members=tuple(members),
        eligible_studies=len(ordered),
        eligible_carriers=sum(len(record.carriers) for record in ordered),
        selected_studies=len(members),
        selected_carriers=sum(len(member.carriers) for member in members),
        predicate_false=outcomes[Match.FALSE], unknown_metadata=outcomes[Match.UNKNOWN],
        not_evaluable=outcomes[Match.NOT_EVALUABLE],
        denied_studies=denied if may_count else None,
        suppressed_remainder=False,
        input_digest=input_digest, snapshot_digest=_digest(payload),
        source_state="EVIDENCE_VERIFIED" if require_verified else "METADATA_ONLY",
    )


def _record_payload(record: StudyRecord) -> dict:
    """Canonical input identity; raw locators only affect a private digest."""
    member = _safe_member(record)
    return {"member": member.model_dump(mode="json"),
            "object_type": record.research_object.object_type,
            "parents": sorted(record.research_object.parent_object_ids),
            "carrier_evidence": sorted(({
                "carrier_id": carrier.carrier_id,
                "source_identity": carrier.source_identity,
                "media_type": carrier.media_type,
                "uri": carrier.uri,
                "byte_length": carrier.byte_length,
            } for carrier in record.carriers), key=lambda value: value["carrier_id"]),
            "fields": sorted((field.model_dump(mode="json") for field in record.fields),
                             key=lambda value: value["name"]),
            "roles": sorted((role.model_dump(mode="json") for role in record.roles),
                            key=lambda value: (str(value["value"]), value["evidence_ref"]))}


def require_current(
    prior: CorpusSpaceSnapshot,
    spec: CorpusSelectionSpec,
    manifest: PopulationManifest,
    records: tuple[StudyRecord, ...] | list[StudyRecord],
    authority: EntitlementAuthority,
    *, trusted_manifest: TrustedManifestAuthority | None = None,
    require_verified: bool = False,
) -> CorpusSpaceSnapshot:
    """Fail closed when manifest, visible inputs, or entitlement has changed."""
    try:
        current = build_corpus_space(spec, manifest, records, authority,
                                     trusted_manifest=trusted_manifest,
                                     require_verified=require_verified)
    except ValueError:
        raise StaleCorpusSpaceError("corpus view is stale") from None
    if current.snapshot_digest != prior.snapshot_digest or current.source_state != prior.source_state:
        raise StaleCorpusSpaceError("corpus view is stale")
    return current


class StaleCorpusSpaceError(ValueError):
    pass


def current_accepted(
    blackboard: Blackboard, research_object_id: str, object_type: str | None = None
):
    """Historical accepted revisions are filtered through current status."""
    return tuple(obj for obj in blackboard.history(research_object_id, object_type)
                 if obj.acceptance_state.value == "ACCEPTED")


def accepted_current_one(
    blackboard: Blackboard, research_object_id: str, object_type: str
):
    """Require an unambiguous present acceptance, never an append-order winner."""
    candidates = current_accepted(blackboard, research_object_id, object_type)
    if len(candidates) > 1:
        raise AmbiguousStateError("multiple current accepted objects")
    return candidates[0] if candidates else None
