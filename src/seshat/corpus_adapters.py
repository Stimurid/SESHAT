"""Explicit, metadata-only host adapters for F07.

Adapters run only after the host has authorized row access. They never fetch
source bytes, guess affiliations, or treat row metadata as a rights grant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import Field, model_validator

from seshat.contracts import ResearchObject, SourceCarrier
from seshat.corpus import EvidenceField, FrozenModel, StudyRecord, TemporalProvenance


class HostTemporalMetadata(FrozenModel):
    """Private host join result; constructing this model grants no access rights."""

    object_id: str = Field(min_length=1)
    evidence: tuple[TemporalProvenance, ...]

    @model_validator(mode="after")
    def unique_fields(self):
        names = [item.source_field for item in self.evidence]
        if len(names) != len(set(names)):
            raise ValueError("duplicate temporal source field")
        return self


def pinned_temporal_metadata(
    raw: bytes, *, expected_sha256: str, expected_object_id: str, source_version: str,
) -> HostTemporalMetadata:
    """Decode one independently authorized, pinned per-study JSON envelope.

    Host-only: the host must authorize the master/intake join AND these fields,
    verify study identity against the master, and pin the resulting bytes outside
    reader control. source_version is per-study, not a private population epoch.
    Shape: {study_id, defended_on?, defense_date?, abstract_published?}.
    Null/absent means unknown; only ISO dates or integer years are accepted.
    Never pass a whole master-file digest into public per-study provenance.
    This verifies envelope integrity, not original scientific facts or authority.
    """
    try:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise ValueError
        row = json.loads(raw)
        names = {"defended_on", "defense_date", "abstract_published"}
        if (not isinstance(row, dict) or set(row) - (names | {"study_id"})
                or row.get("study_id") != expected_object_id):
            raise ValueError
        evidence = tuple(TemporalProvenance(
            source_field=name, source_value=row[name], source_sha256=digest,
            source_version=source_version,
            precision="YEAR" if type(row[name]) is int else "DATE",
        ) for name in sorted(names) if row.get(name) is not None)
        return HostTemporalMetadata(object_id=expected_object_id, evidence=evidence)
    except Exception:
        raise ValueError("invalid host temporal metadata") from None


def evidenced_study(
    *, object_id: str, version: str, object_type: str,
    carriers: Sequence[SourceCarrier],
    fields: Sequence[EvidenceField],
    roles: Sequence[EvidenceField] = (),
) -> StudyRecord:
    """Host-neutral adapter; arbitrary evidenced field names are permitted."""
    copied = tuple(carrier.model_copy(deep=True) for carrier in carriers)
    return StudyRecord(
        research_object=ResearchObject(object_id=object_id, version=version,
                                       object_type=object_type,
                                       carrier_ids=[carrier.carrier_id for carrier in copied]),
        carriers=copied,
        fields=tuple(field.model_copy(deep=True) for field in fields),
        roles=tuple(role.model_copy(deep=True) for role in roles),
    )


def sechenovka_v4_metadata_row(
    row: Mapping[str, object], *, row_evidence_ref: str, record_version: str,
    temporal_metadata: HostTemporalMetadata | None = None,
) -> StudyRecord:
    """Map an already authorized v4 intake row; no Drive fetch or raw PDF read.

    The host must supply this row under its own access controls. Its study_id
    and carrier IDs remain in the rights-controlled runtime, never fixtures.
    Intake year is a cohort label ONLY. Explicit temporal fields require the
    separate host-authorized pinned channel; similarly named intake keys are
    ignored. Missing fields stay missing (UNKNOWN_METADATA for declared fields,
    NOT_EVALUABLE if not declared). No degree-award assertion is produced.
    """
    study_id = row.get("study_id")
    year = row.get("year")
    abstract = row.get("abstract")
    dissertation = row.get("dissertation")
    if (not isinstance(study_id, str) or not study_id
            or isinstance(year, bool) or not isinstance(year, int)):
        raise ValueError("authorized v4 row lacks required study metadata")
    if not isinstance(abstract, Mapping):
        raise ValueError("authorized v4 row lacks abstract carrier metadata")
    entries = [("abstract", abstract)]
    if dissertation is not None:
        if not isinstance(dissertation, Mapping):
            raise ValueError("invalid dissertation carrier metadata")
        entries.append(("dissertation", dissertation))
    carriers = []
    for role, source in entries:
        carrier_id = source.get("drive_file_id")
        digest = source.get("sha256")
        if (not isinstance(carrier_id, str) or not carrier_id.strip()
                or not isinstance(digest, str)):
            raise ValueError("carrier identity pin is missing")
        carriers.append(SourceCarrier(
            carrier_id=carrier_id, source_identity=f"v4:{role}", version=record_version,
            content_sha256=digest,
        ))
    fields = [EvidenceField(name="cohort_year", value=year,
                            evidence_ref=f"{row_evidence_ref}:year")]
    if temporal_metadata is not None:
        temporal_metadata = HostTemporalMetadata.model_validate(temporal_metadata.model_dump())
        if temporal_metadata.object_id != study_id:
            raise ValueError("temporal metadata study mismatch")
        for evidence in temporal_metadata.evidence:
            ref = f"temporal-sha256:{evidence.source_sha256}:{evidence.source_field}"
            fields.extend((
                EvidenceField(name=evidence.source_field, value=evidence.source_value,
                              evidence_ref=ref, temporal_provenance=evidence),
                EvidenceField(name=f"{evidence.source_field}_year", value=evidence.year,
                              evidence_ref=ref, temporal_provenance=evidence),
            ))
    roles = [EvidenceField(name="source_role", value=role,
                           evidence_ref=f"{row_evidence_ref}:{role}") for role, _ in entries]
    specialty = row.get("specialty_raw")
    if specialty is not None and not isinstance(specialty, str):
        raise ValueError("invalid specialty metadata")
    if isinstance(specialty, str) and specialty.strip():
        fields.append(EvidenceField(name="specialty", value=specialty,
                                    evidence_ref=f"{row_evidence_ref}:specialty_raw"))
    # Explicit structural classifications permit known/unknown and pair
    # selectors without turning absent specialty into a fabricated value.
    fields.extend((
        EvidenceField(name="specialty_status",
                      value="known" if isinstance(specialty, str) and specialty.strip()
                      else "UNKNOWN", evidence_ref=f"{row_evidence_ref}:specialty_raw"),
        EvidenceField(name="pair_status", value="paired" if dissertation is not None
                      else "abstract-only", evidence_ref=f"{row_evidence_ref}:dissertation"),
    ))
    return evidenced_study(object_id=study_id, version=record_version,
                           object_type="study", carriers=carriers, fields=fields, roles=roles)


def load_private_v4_metadata_fixture(
    intake_path: Path, *, expected_file_sha256: str,
    expected_row_sha256_by_id_hash: Mapping[str, str], record_version: str,
) -> tuple[StudyRecord, ...]:
    """Read a private JSONL metadata fixture in an isolated, authorized runner.

    The caller owns the private path, expected digests and entitlements. This
    function never reads carrier/PDF bytes, never logs rows, and returns private
    records only to that caller. Do not call it from public CI or AORUS.
    """
    try:
        raw = intake_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_file_sha256:
            raise ValueError
        output = []
        seen = set()
        for line in raw.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("study_id"), str):
                raise ValueError
            identity_hash = hashlib.sha256(row["study_id"].encode("utf-8")).hexdigest()
            if (identity_hash in seen or
                    expected_row_sha256_by_id_hash.get(identity_hash)
                    != hashlib.sha256(line).hexdigest()):
                raise ValueError
            seen.add(identity_hash)
            output.append(sechenovka_v4_metadata_row(
                row, row_evidence_ref=f"intake-sha256:{hashlib.sha256(line).hexdigest()}",
                record_version=record_version,
            ))
        if seen != set(expected_row_sha256_by_id_hash):
            raise ValueError
        return tuple(output)
    except Exception:
        # Exception text must never contain private path, ID, or row content.
        raise ValueError("private v4 metadata fixture verification failed") from None
