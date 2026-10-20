"""Invented private-runner fixtures only; no real v4 acceptance claim."""

import hashlib
import json

import pytest

from seshat.corpus_adapters import sechenovka_v4_metadata_row
from seshat.corpus_evaluation import (
    PrivateCarrierBinding, PrivateOracleMember, PrivateSelectorOracle,
    PrivateV4Contract, PrivateV4EvaluationError, compare_private_v4_metadata,
    compare_real_v4_metadata, oracle_membership_digest,
)
from test_corpus_selection import Rights, field, year


def encode(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def fixture(tmp_path):
    rows = [
        {"study_id": "invented-a", "year": 2025, "specialty_raw": "A", "card": "card-a",
         "abstract": {"drive_file_id": "carrier-a", "sha256": "a" * 64},
         "dissertation": {"drive_file_id": "carrier-b", "sha256": "b" * 64}},
        {"study_id": "invented-b", "year": 2026, "specialty_raw": None, "card": "card-b",
         "abstract": {"drive_file_id": "carrier-c", "sha256": "c" * 64}},
    ]
    master_rows, bindings = [], []
    for row in rows:
        for role in ("abstract", "dissertation"):
            if role not in row:
                continue
            prefix = f"/files/{len(master_rows)}"
            master_rows.append({**row[role], "year": row["year"],
                                "specialty": row["specialty_raw"], "card": row["card"]})
            bindings.append(PrivateCarrierBinding(
                carrier_id=row[role]["drive_file_id"], drive_id_pointer=prefix + "/drive_file_id",
                sha256_pointer=prefix + "/sha256", year_pointer=prefix + "/year",
                specialty_pointer=prefix + "/specialty", source_card_pointer=prefix + "/card"))
    master, intake = tmp_path / "invented-master.json", tmp_path / "invented-intake.jsonl"
    master.write_bytes(encode({"files": master_rows}))
    intake.write_bytes(b"\n".join(encode(row) for row in rows) + b"\n")
    members = (PrivateOracleMember(study_key="invented-a", source_shas=("a" * 64, "b" * 64)),
               PrivateOracleMember(study_key="invented-b", source_shas=("c" * 64,)))
    selectors = []
    for name, predicate, oracle_predicate, selected, carriers, pairs in (
        ("all", year(2025, 2026), {"years": [2025, 2026]}, members, 3, 1),
        ("known", field("specialty_status", "known"), {"known": True}, members[:1], 2, 1),
        ("unknown", field("specialty_status", "UNKNOWN"), {"known": False}, members[1:], 1, 0),
        ("paired", field("pair_status", "paired"), {"paired": True}, members[:1], 2, 1),
    ):
        selectors.append(PrivateSelectorOracle(
            name=name, query=predicate, oracle_predicate=oracle_predicate, members=selected,
            membership_sha256=oracle_membership_digest("e" * 64, oracle_predicate, selected),
            studies=len(selected), carriers=carriers, pairs=pairs))
    contract = PrivateV4Contract(
        master_sha256=hashlib.sha256(master.read_bytes()).hexdigest(),
        intake_sha256=hashlib.sha256(intake.read_bytes()).hexdigest(),
        population_manifest_sha256="e" * 64, intake_source_card_pointer="/card",
        bindings=tuple(bindings), selectors=tuple(selectors), expected_studies=2,
        expected_carriers=3, expected_pairs=1, expected_unknown_specialties=1)
    return master, intake, contract


def compare(master, intake, contract, rights=None):
    return compare_private_v4_metadata(master, intake, contract, rights or Rights(),
                                       caller_id="private-evaluator", view_id="private-all")


def test_synthetic_exact_sets_and_permutation_not_real_v4(tmp_path):
    master, intake, contract = fixture(tmp_path)
    result = compare(master, intake, contract)
    assert result.selectors_compared == 4
    assert result.comparison_state == "MATCHED_DECLARED_ORACLES"
    assert result.evidence_state == "PENDING_HOST_ATTESTATION"
    assert result.identity_qa_state == "NOT_CLEARED_BY_METADATA"
    assert "invented" not in result.model_dump_json()
    intake.write_bytes(b"\n".join(reversed(intake.read_bytes().splitlines())) + b"\n")
    changed = contract.model_copy(update={
        "intake_sha256": hashlib.sha256(intake.read_bytes()).hexdigest()})
    assert compare(master, intake, changed) == result
    with pytest.raises(PrivateV4EvaluationError):
        compare_real_v4_metadata(master, intake, changed, Rights(),
                                 caller_id="private", view_id="private")


@pytest.mark.parametrize("mutation", ["sha", "id", "year", "specialty", "card",
                                     "duplicate", "missing", "oracle", "query", "rights"])
def test_recomputed_file_hash_does_not_hide_join_or_member_mismatch(tmp_path, mutation):
    master, intake, contract = fixture(tmp_path)
    rows = [json.loads(line) for line in intake.read_bytes().splitlines()]
    if mutation == "sha":
        rows[0]["abstract"]["sha256"] = "f" * 64
    elif mutation == "id":
        rows[0]["study_id"] = "forged-private-id"
    elif mutation in {"year", "specialty", "card"}:
        key, value = {"year": ("year", 2099), "specialty": ("specialty_raw", "forged"),
                      "card": ("card", "forged-card")}[mutation]
        rows[0][key] = value
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "missing":
        rows.pop()
    elif mutation in {"oracle", "query"}:
        case = contract.selectors[0].model_copy(update=(
            {"membership_sha256": "f" * 64} if mutation == "oracle"
            else {"query": year(2026, 2026)}))
        contract = contract.model_copy(update={"selectors": (case, *contract.selectors[1:])})
    intake.write_bytes(b"\n".join(encode(row) for row in rows))
    contract = contract.model_copy(update={
        "intake_sha256": hashlib.sha256(intake.read_bytes()).hexdigest()})
    rights = Rights(denied={"invented-a"}) if mutation == "rights" else Rights()
    with pytest.raises(PrivateV4EvaluationError) as error:
        compare(master, intake, contract, rights)
    assert str(error.value) == "PRIVATE_V4_COMPARISON_BLOCKED_OR_MISMATCH"
    assert "invented" not in str(error.value) and str(tmp_path) not in str(error.value)


def test_missing_source_file_and_wrong_master_pin_fail_without_path(tmp_path):
    master, intake, contract = fixture(tmp_path)
    with pytest.raises(PrivateV4EvaluationError):
        compare(master, intake, contract.model_copy(update={"master_sha256": "f" * 64}))
    master.unlink()
    with pytest.raises(PrivateV4EvaluationError) as error:
        compare(master, intake, contract)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize("specialty", [None, "", "  "])
def test_unknown_specialty_is_not_a_fabricated_specialty_value(specialty):
    record = sechenovka_v4_metadata_row(
        {"study_id": "invented", "year": 2025, "specialty_raw": specialty,
         "abstract": {"drive_file_id": "invented-carrier", "sha256": "a" * 64}},
        row_evidence_ref="synthetic:row", record_version="v4")
    values = {f.name: f.value for f in record.fields}
    assert "specialty" not in values
    assert values["specialty_status"] == "UNKNOWN"
