"""F07: deterministic, metadata-only corpus selections.

The host supplies evidenced metadata and an independent entitlement authority.
Nothing in ResearchObject.metadata or SourceCarrier.metadata grants visibility.
Selections are source-addressed views, never semantic admissions or raw reads.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Literal, NoReturn, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

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


class TemporalProvenance(FrozenModel):
    """Explicit host-authorized metadata, not proof of defense or degree award.

    The SHA pins a per-study evidence envelope, never a whole private population.
    ISO calendar dates and integer years retain different precision. No cohort,
    publication or alternate date can stand in for the defended_on source field.
    """

    source_field: Literal["defended_on", "defense_date", "abstract_published"]
    source_value: StrictStr | StrictInt
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_version: str = Field(min_length=1)
    precision: Literal["DATE", "YEAR"]

    @model_validator(mode="after")
    def explicit_value(self):
        value = self.source_value
        if self.precision == "YEAR":
            if type(value) is not int or not 1 <= value <= 9999:
                raise ValueError("invalid explicit temporal year")
        else:
            if not isinstance(value, str):
                raise ValueError("invalid explicit temporal date")
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise ValueError("invalid explicit temporal date") from None
            if parsed.isoformat() != value:
                raise ValueError("temporal dates require YYYY-MM-DD")
        return self

    @property
    def year(self) -> int:
        return (self.source_value if self.precision == "YEAR"
                else date.fromisoformat(self.source_value).year)


class EvidenceField(FrozenModel):
    """A host-declared field with a source-specific provenance token."""

    name: str = Field(min_length=1)
    value: StrictStr | StrictInt
    evidence_ref: str = Field(min_length=1)
    temporal_provenance: TemporalProvenance | None = None

    @model_validator(mode="after")
    def temporal_binding(self):
        temporal_names = {name for base in ("defended_on", "defense_date", "abstract_published")
                          for name in (base, f"{base}_year")}
        provenance = self.temporal_provenance
        if self.name in temporal_names:
            if provenance is None:
                raise ValueError("temporal field requires explicit source provenance")
            expected = (provenance.year if self.name.endswith("_year")
                        else provenance.source_value)
            if (self.name not in {provenance.source_field, f"{provenance.source_field}_year"}
                    or type(self.value) is not type(expected) or self.value != expected):
                raise ValueError("temporal field does not match its source")
        elif provenance is not None:
            raise ValueError("temporal provenance cannot relabel another field")
        return self


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
        temporal_sources = {}
        for field in self.fields:
            provenance = field.temporal_provenance
            if provenance is not None:
                prior = temporal_sources.setdefault(provenance.source_field, provenance)
                if prior != provenance:
                    raise ValueError("conflicting temporal source provenance")
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
    semantics_version: Literal["F07-2"] = "F07-2"

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


def public_selection_digest(spec: CorpusSelectionSpec) -> str:
    """Canonical public request identity, independent of callbacks/private epochs."""
    public_spec = spec.model_dump(mode="json", exclude={"manifest", "predicate"})
    public_spec["predicate"] = spec.predicate.canonical()
    return _digest({"domain": "seshat.f07.public-selection.v3", "selection": public_spec})


class Visibility(StrEnum):
    VISIBLE = "VISIBLE"
    DENIED = "DENIED"


class EntitlementAuthority(Protocol):
    """Projection policy supplied by the embedding host, NOT authenticated here.

    A server must bind this outside its request boundary before exposing private
    records. Decisions must be consistent for one immutable policy snapshot.
    Legacy seal_selection is ignored: the public digest is computed internally.
    revision is private host bookkeeping;
    public projection does not read it or claim authoritative currentness.
    """

    def revision(self, caller_id: str, view_id: str) -> str: ...

    def visibility(self, caller_id: str, view_id: str, object_id: str) -> Visibility: ...

    def carrier_visibility(
        self, caller_id: str, view_id: str, object_id: str, carrier_id: str
    ) -> Visibility: ...

    def may_count_denied(self, caller_id: str, view_id: str) -> bool: ...

    def seal_selection(self, caller_id: str, view_id: str, canonical_json: str) -> str: ...


class TrustedManifestAuthority(Protocol):
    """Legacy reader shape, retained for migration only; NEVER called by selectors.

    A Python object implementing this protocol establishes no source authority.
    This public API has no authenticated host integration. Owner-side bootstrap
    is separate in corpus_host; it never accepts this reader protocol.
    """

    def current_pin(self, manifest_id: str) -> ManifestPin: ...

    def resolve(self, pin: ManifestPin) -> tuple[PopulationManifest, tuple[StudyRecord, ...]]: ...


def canonical_population_digest(
    manifest_id: str, version: str, declared_fields: frozenset[str],
    records: tuple[StudyRecord, ...] | list[StudyRecord],
) -> str:
    """Private content checksum, never proof of source authenticity.

    Do not expose this full-population checksum through public projections.
    """
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
    identity_state: Literal["PIN_ASSERTED_NOT_VERIFIED"] = "PIN_ASSERTED_NOT_VERIFIED"


class MemberPin(FrozenModel):
    object_id: str
    version: str
    carriers: tuple[CarrierPin, ...]


class CorpusSpaceSnapshot(FrozenModel):
    selection_digest: str
    manifest_digest: str
    semantics_version: Literal["F07-2"] = "F07-2"
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
    source_state: Literal["METADATA_ONLY"] = "METADATA_ONLY"
    selection_state: Literal["PROVISIONAL"] = "PROVISIONAL"
    evidence_state: Literal["PENDING_HOST_ATTESTATION"] = "PENDING_HOST_ATTESTATION"
    currentness_state: Literal["UNVERIFIED_CURRENTNESS"] = "UNVERIFIED_CURRENTNESS"
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


def _safe_member(record: StudyRecord) -> MemberPin:
    obj = record.research_object
    return MemberPin(
        object_id=obj.object_id,
        version=obj.version,
        carriers=tuple(sorted((CarrierPin(
            carrier_id=c.carrier_id, version=c.version, sha256=c.content_sha256,
        ) for c in record.carriers),
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
    """Build a fresh PROVISIONAL projection, never evidence or cache authority.

    Legacy verification arguments are deliberately inert. In particular no
    caller-supplied reader is invoked, even to check its pin. Full-population
    pins are private assertions; comparing them here would reveal hidden-only
    updates through errors. Host source admission belongs outside this API.

    Noninterference assumes identical visible records, public schema, selector
    and entitlement decisions. Denied content is neither validated
    nor fingerprinted. This function is not an in-process security sandbox.
    """
    try:
        may_count = authority.may_count_denied(spec.caller_id, spec.view_id)
        # No full-population identifier/version/hash or policy epoch is a
        # public selector input. Even count permission grants only a count.
        sealed_selection = public_selection_digest(spec)
    except Exception:
        raise ValueError("entitlement check failed") from None
    if not isinstance(may_count, bool):
        raise ValueError("invalid denied-count entitlement")

    visible: dict[str, StudyRecord] = {}
    seen: dict[str, str] = {}
    denied_ids: set[str] = set()
    for supplied in records:
        # Only routing identities are inspected before policy. In particular,
        # do not deep-copy/serialize/hash/validate the denied payload first.
        try:
            object_id = supplied.research_object.object_id
            decision = authority.visibility(spec.caller_id, spec.view_id, object_id)
            if decision is Visibility.VISIBLE:
                for carrier in supplied.carriers:
                    carrier_decision = authority.carrier_visibility(
                        spec.caller_id, spec.view_id, object_id, carrier.carrier_id
                    )
                    if carrier_decision is Visibility.DENIED:
                        decision = Visibility.DENIED
                        break
                    if carrier_decision is not Visibility.VISIBLE:
                        raise ValueError
            if decision is not Visibility.VISIBLE and decision is not Visibility.DENIED:
                raise ValueError
        except Exception:
            raise ValueError("entitlement check failed") from None
        if decision is Visibility.DENIED:
            if may_count:
                denied_ids.add(object_id)
            continue
        try:
            # Revalidation catches model_copy/model_construct drift, but only
            # after ALL carrier and study visibility checks have succeeded.
            record = StudyRecord.model_validate(supplied.model_dump(mode="python"))
            fingerprint = _digest(_record_payload(record))
        except Exception:
            raise ValueError("invalid study pin") from None
        prior_fingerprint = seen.setdefault(object_id, fingerprint)
        if prior_fingerprint != fingerprint:
            raise ValueError("conflicting duplicate study")
        visible.setdefault(object_id, record)

    # A denied candidate colliding with a visible study must not turn into an
    # exception oracle. Only admitted records participate in deduplication.
    ordered = [visible[key] for key in sorted(visible)]
    carrier_pins: dict[str, tuple[str, str]] = {}
    for record in ordered:
        for carrier in record.carriers:
            pin = (carrier.version, carrier.content_sha256)
            if carrier_pins.setdefault(carrier.carrier_id, pin) != pin:
                raise ValueError("conflicting visible carrier pin")
    public_schema = {"domain": "seshat.f07.public-schema.v2",
                     "declared_fields": sorted(manifest.declared_fields)}
    input_digest = _digest({"schema": public_schema,
                            "records": [_record_payload(item) for item in ordered]})
    members: list[MemberPin] = []
    outcomes = {match: 0 for match in Match}
    for record in ordered:
        outcome = _match(spec.predicate, record, manifest.declared_fields)
        outcomes[outcome] += 1
        if outcome is Match.TRUE:
            members.append(_safe_member(record))
    payload = dict(
        selection_digest=sealed_selection,
        manifest_digest=_digest(public_schema),
        semantics_version="F07-2",
        authorization_revision="UNVERIFIED_CURRENTNESS",
        members=tuple(members),
        eligible_studies=len(ordered),
        eligible_carriers=len({c.carrier_id for record in ordered for c in record.carriers}),
        selected_studies=len(members),
        selected_carriers=len({c.carrier_id for member in members for c in member.carriers}),
        predicate_false=outcomes[Match.FALSE], unknown_metadata=outcomes[Match.UNKNOWN],
        not_evaluable=outcomes[Match.NOT_EVALUABLE],
        # An ID that also has an admitted record is already in visible studies.
        denied_studies=len(denied_ids - visible.keys()) if may_count else None,
        suppressed_remainder=False,
        input_digest=input_digest,
    )
    snapshot = CorpusSpaceSnapshot(snapshot_digest="", **payload)
    return snapshot.model_copy(update={
        "snapshot_digest": _digest(snapshot.model_dump(mode="json", exclude={"snapshot_digest"}))
    })


def _record_payload(record: StudyRecord) -> dict:
    """Canonical record identity; call only for admitted or private records."""
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
            "fields": sorted((field.model_dump(mode="json", exclude_none=True)
                              for field in record.fields),
                             key=lambda value: value["name"]),
            "roles": sorted((role.model_dump(mode="json", exclude_none=True)
                             for role in record.roles),
                            key=lambda value: (str(value["value"]), value["evidence_ref"]))}


def require_current(
    prior: CorpusSpaceSnapshot,
    spec: CorpusSelectionSpec,
    manifest: PopulationManifest,
    records: tuple[StudyRecord, ...] | list[StudyRecord],
    authority: EntitlementAuthority,
    *, trusted_manifest: TrustedManifestAuthority | None = None,
    require_verified: bool = False,
) -> NoReturn:
    """Reject authoritative reuse until a separately authenticated host exists.

    Equality of public projections cannot prove current private policy/source
    epochs. Do not even inspect those inputs here: the same typed refusal must
    apply to unchanged, rotated, stale and forged snapshots. For useful fresh
    metadata selection call build_corpus_space and retain its UNVERIFIED status.
    """
    raise UnverifiedCurrentnessError("UNVERIFIED_CURRENTNESS")


class StaleCorpusSpaceError(ValueError):
    """Compatibility base for callers that previously caught stale views."""


class UnverifiedCurrentnessError(StaleCorpusSpaceError):
    """No authenticated private epoch check is available; reuse is blocked."""


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
