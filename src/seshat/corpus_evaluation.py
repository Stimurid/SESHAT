"""Private, metadata-only F07 oracle comparison; no authority or PDF access.

Run ONLY in an independently authorized isolated runner. All arguments,
including the contract, contain private identities and stay out of public Git.
An oracle match establishes mechanical agreement, not source authenticity.
The owner supplies exact predicate objects and primary-record JSON pointers;
this module does not guess the unpublished MASTER schema or oracle DSL.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from seshat.corpus import (
    CorpusSelectionSpec, EntitlementAuthority, FrozenModel, ManifestPin,
    PopulationManifest, Predicate, build_corpus_space,
)
from seshat.corpus_adapters import sechenovka_v4_metadata_row


# Public aggregate/digest receipts read from the owner's 2026-10-15 return.
# They are comparison targets, not credentials or independent source authority.
REAL_V4_MASTER_SHA256 = "b3c2c3f2f98e71928c4a1597a87779ad9624886a38d1f29ddf87fa152bc047a9"
REAL_V4_INTAKE_SHA256 = "9fd236978aee4781b66978847e41a7220e34969cc66d8c70ef957359ea5a15ed"
REAL_V4_POPULATION_PIN = "88acf12c11d6a9c019222bc82c1094a811f1e860320a657b9313c2b75a626806"
REAL_V4_ORACLES = {
    "ALL": (186, 280, 94, "69823f8deffa744844e24d2016fcdcca0bb393b10021f714d5404a3b81f01bd5"),
    "2021-2023": (54, 85, 31, "682867f2133ab05a97f3c42d8f243c04ad365ae05a4ae6f51e53c6062e4d3d45"),
    "2024-2026": (132, 195, 63, "0b7b227751d55cb38fceb9b02091b541eda92f84d4ba9f2f27ecdf34583a9d9b"),
    "2025": (93, 131, 38, "fe7b3443053f5f49fb3c2769df100b6384677e1adfdbc9b0ca2c1448907f81ea"),
    "2026": (12, 24, 12, "63b4bf36a1b453787a5e61ed4ecf48ce962b70e84da0156cbb2f2fd1cb3b4feb"),
    "paired": (94, 188, 94, "3cab2fe433cde2ee5b8e580ad89ba82545d309313eebfd04d1886dd22f47ffaf"),
    "abstract-only": (92, 92, 0, "36816dbc9811b52f256c61ac299273d25680404147d681a66edda48143b0795d"),
    "specialty known": (82, 126, 44, "6b6f890dc9370fc0fce90ee515e6607fa18f1e061f16ddea08c8dca26613b230"),
    "specialty UNKNOWN": (104, 154, 50, "71dfa810d201541c2aa059940f325f69609d521ace1cb8169ab5f12e561fda2c"),
    "2021-2023 paired": (31, 62, 31, "f1c4bf57b1246a6997b6c0f418f9afb03e6f5d9a7ee789e5969fb3d2b03ddca6"),
    "2024-2026 paired": (63, 126, 63, "881ba7fdd0c74f5180a9bc1ff0557120dd5a0765544db2cf0e2066c06ae68b61"),
    "2025 paired": (38, 76, 38, "286d44239fbe69ead6eac410bdea0ba4b90107e056790e757ade9c970cc7cf48"),
    "2025 specialty known": (4, 7, 3, "877444e8ab0e68e6c60cf5e2d9ea0280cc43330230108898343fcd1131b6b828"),
    "2026 specialty known": (0, 0, 0, "43404890c80e5130dcf1cb898e4c3f83f5da33b40f36a661c71a37666e9b0e6a"),
}


class PrivateOracleMember(FrozenModel):
    study_key: str = Field(min_length=1)
    source_shas: tuple[str, ...]


class PrivateSelectorOracle(FrozenModel):
    name: str = Field(min_length=1)
    query: Predicate
    # Exact original oracle object, not a newly guessed serialization of query.
    oracle_predicate: dict[str, Any]
    members: tuple[PrivateOracleMember, ...]
    membership_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    studies: int = Field(ge=0)
    carriers: int = Field(ge=0)
    pairs: int = Field(ge=0)


class PrivateCarrierBinding(FrozenModel):
    """Absolute JSON pointers into the pinned master; values are not authority."""

    carrier_id: str = Field(min_length=1)
    drive_id_pointer: str
    sha256_pointer: str
    year_pointer: str
    specialty_pointer: str
    source_card_pointer: str


class PrivateV4Contract(FrozenModel):
    master_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    intake_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    population_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Relative to each intake study row; supplied from reviewed schema mapping.
    intake_source_card_pointer: str
    bindings: tuple[PrivateCarrierBinding, ...]
    selectors: tuple[PrivateSelectorOracle, ...]
    expected_studies: int = Field(gt=0)
    expected_carriers: int = Field(gt=0)
    expected_pairs: int = Field(ge=0)
    expected_unknown_specialties: int = Field(ge=0)


class PrivateV4Comparison(FrozenModel):
    comparison_state: Literal["MATCHED_DECLARED_ORACLES"] = "MATCHED_DECLARED_ORACLES"
    evidence_state: Literal["PENDING_HOST_ATTESTATION"] = "PENDING_HOST_ATTESTATION"
    currentness_state: Literal["UNVERIFIED_CURRENTNESS"] = "UNVERIFIED_CURRENTNESS"
    identity_qa_state: Literal["NOT_CLEARED_BY_METADATA"] = "NOT_CLEARED_BY_METADATA"
    semantic_acceptance_state: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
    selectors_compared: int


class PrivateV4EvaluationError(ValueError):
    """Constant, non-identifying failure; private details must not escape."""


def _pointer(value: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _membership(members: tuple[PrivateOracleMember, ...]) -> list[dict]:
    if len({m.study_key for m in members}) != len(members):
        raise ValueError
    for member in members:
        if (not member.source_shas or len(set(member.source_shas)) != len(member.source_shas)
                or any(len(s) != 64 or any(c not in "0123456789abcdef" for c in s)
                       for s in member.source_shas)):
            raise ValueError
    return [{"study_key": m.study_key, "source_shas": sorted(m.source_shas)}
            for m in sorted(members, key=lambda m: m.study_key)]


def oracle_membership_digest(population_pin: str, predicate: dict,
                             members: tuple[PrivateOracleMember, ...]) -> str:
    """The owner's canonical receipt algorithm; result is private by default."""
    payload = {"population_manifest_sha256": population_pin,
               "predicate": predicate, "members": _membership(members)}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def compare_private_v4_metadata(
    master_path: Path, intake_path: Path, contract: PrivateV4Contract,
    authority: EntitlementAuthority, *, caller_id: str, view_id: str,
) -> PrivateV4Comparison:
    """Read pinned metadata, join carrier identity and fields, compare F07 sets.

    No network, logging, file writes, code evaluation or original source reads.
    Missing files/fields, ambiguous binding, forged hash/ID/year/specialty/card,
    changed entitlement or any wrong member set fail with the same error.
    Caller-chosen pins are assertions: a match NEVER emits verified evidence.
    """
    try:
        return _compare(master_path, intake_path, contract, authority, caller_id, view_id)
    except Exception:
        raise PrivateV4EvaluationError("PRIVATE_V4_COMPARISON_BLOCKED_OR_MISMATCH") from None


def _compare(master_path, intake_path, contract, authority, caller_id, view_id):
    master_bytes, intake_bytes = master_path.read_bytes(), intake_path.read_bytes()
    if (hashlib.sha256(master_bytes).hexdigest() != contract.master_sha256
            or hashlib.sha256(intake_bytes).hexdigest() != contract.intake_sha256):
        raise ValueError
    master = json.loads(master_bytes)
    bindings = {b.carrier_id: b for b in contract.bindings}
    if len(bindings) != len(contract.bindings) or len(bindings) != contract.expected_carriers:
        raise ValueError
    records, study_ids, carrier_ids, primary_pointers = [], set(), set(), set()
    pairs = unknown = 0
    for line in intake_bytes.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        record = sechenovka_v4_metadata_row(
            row, row_evidence_ref=f"intake-sha256:{hashlib.sha256(line).hexdigest()}",
            record_version="v4")
        study_id = record.research_object.object_id
        if study_id in study_ids:
            raise ValueError
        study_ids.add(study_id)
        pairs += len(record.carriers) == 2
        unknown += not any(f.name == "specialty" for f in record.fields)
        for carrier in record.carriers:
            if carrier.carrier_id in carrier_ids:
                raise ValueError
            carrier_ids.add(carrier.carrier_id)
            binding = bindings[carrier.carrier_id]
            if binding.drive_id_pointer in primary_pointers:
                raise ValueError
            primary_pointers.add(binding.drive_id_pointer)
            if (_pointer(master, binding.drive_id_pointer) != carrier.carrier_id
                    or _pointer(master, binding.sha256_pointer) != carrier.content_sha256
                    or _pointer(master, binding.year_pointer) != row["year"]
                    or _pointer(master, binding.specialty_pointer) != row.get("specialty_raw")
                    or _pointer(master, binding.source_card_pointer)
                    != _pointer(row, contract.intake_source_card_pointer)):
                raise ValueError
        records.append(record)
    if (len(records), len(carrier_ids), pairs, unknown) != (
        contract.expected_studies, contract.expected_carriers, contract.expected_pairs,
        contract.expected_unknown_specialties,
    ) or carrier_ids != bindings.keys():
        raise ValueError
    if not contract.selectors or len({s.name for s in contract.selectors}) != len(contract.selectors):
        raise ValueError
    manifest = PopulationManifest(
        pin=ManifestPin(manifest_id="private-v4-oracle", version="v4",
                        sha256=contract.population_manifest_sha256),
        declared_fields=frozenset({"cohort_year", "specialty", "source_role",
                                   "specialty_status", "pair_status"}),
    )
    for case in contract.selectors:
        if oracle_membership_digest(contract.population_manifest_sha256,
                                     case.oracle_predicate, case.members) != case.membership_sha256:
            raise ValueError
        query = CorpusSelectionSpec(selector_id=case.name, version="1", manifest=manifest.pin,
                                    predicate=case.query, caller_id=caller_id, view_id=view_id)
        result = build_corpus_space(query, manifest, records, authority)
        actual = tuple(PrivateOracleMember(study_key=m.object_id,
                                           source_shas=tuple(c.sha256 for c in m.carriers))
                       for m in result.members)
        if (_membership(actual) != _membership(case.members)
                or oracle_membership_digest(contract.population_manifest_sha256,
                                             case.oracle_predicate, actual) != case.membership_sha256
                or (result.selected_studies, result.selected_carriers,
                    sum(len(m.carriers) == 2 for m in result.members))
                != (case.studies, case.carriers, case.pairs)):
            raise ValueError
    return PrivateV4Comparison(selectors_compared=len(contract.selectors))


def compare_real_v4_metadata(
    master_path: Path, intake_path: Path, contract: PrivateV4Contract,
    authority: EntitlementAuthority, *, caller_id: str, view_id: str,
) -> PrivateV4Comparison:
    """Require all 14 owner targets, then run the actual private F07 comparison.

    The full private oracle artifact is REQUIRED: its exact predicate objects
    and member lists are intentionally not reconstructed from public counts.
    This gate is still metadata-only and cannot clear the four identity QA
    flags, certify source authenticity, or grant publication/method rights.
    """
    expected = {s.name: (s.studies, s.carriers, s.pairs, s.membership_sha256)
                for s in contract.selectors}
    if (contract.master_sha256 != REAL_V4_MASTER_SHA256
            or contract.intake_sha256 != REAL_V4_INTAKE_SHA256
            or contract.population_manifest_sha256 != REAL_V4_POPULATION_PIN
            or (contract.expected_studies, contract.expected_carriers,
                contract.expected_pairs, contract.expected_unknown_specialties)
            != (186, 280, 94, 104)
            or len(contract.selectors) != 14 or expected != REAL_V4_ORACLES):
        raise PrivateV4EvaluationError("PRIVATE_V4_COMPARISON_BLOCKED_OR_MISMATCH")
    return compare_private_v4_metadata(master_path, intake_path, contract, authority,
                                       caller_id=caller_id, view_id=view_id)
