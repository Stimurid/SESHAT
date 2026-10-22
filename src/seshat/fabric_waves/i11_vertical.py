"""One operator command: admitted source + MethodAsset -> R01/R02/R03 + replay.

Reuses the existing operator ledger, F07 selection types, and private R01/R02
composer. Does not rewrite Carpet, restore an issuer, or submit a paid model
job. A genuine authorial ModelRun is bound only from an already-terminal
ordinary Hub receipt whose bytes the operator still holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from seshat.contracts import SourceCarrier
from seshat.corpus import (
    CorpusSelectionSpec,
    EvidenceField,
    ManifestPin,
    PopulationManifest,
    Predicate,
    Visibility,
    build_corpus_space,
)
from seshat.corpus_adapters import evidenced_study
from seshat.fabric_waves.contracts import EpistemicLevel
from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    AUTHORIAL_I11_SHA256,
    AUTHORIAL_I11_VERSION,
    CCBY_PAGES_SHA256,
    CCBY_PDF_SHA256,
    FICTIONAL_METHOD_ID,
    FICTIONAL_METHOD_VERSION,
    OBSERVED_I11_JOB_ID,
    OBSERVED_I11_STDOUT_SHA256,
    ActivityNetworkState,
    _claim_from_event,
    activity_state_from_model_payload,
    execute_fictional_i11,
    fictional_method_bytes,
    parse_page_map,
    validate_activity_network,
    world_bytes,
)
from seshat.fabric_waves.operator_methodbody import (
    OperatorBodyResult,
    OperatorInvocation,
    OperatorMethodBodyPin,
    OperatorRunLedger,
    OperatorSourcePin,
    invoke_operator_method_body,
    replay_and_verify_operator_run,
)
from seshat.fabric_waves.operator_private_reports import (
    compose_private_operator_r01r02,
    verify_private_operator_r01r02,
)
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger

INDAGO_STATUS = "NOT_LIVE"
OWNER_EXCLUSION_SCHEMA = "seshat.owner_source_exclusion.v1"
F07_PERMISSION_SCHEMA = "seshat.f07_per_operation_permission.v1"
DEFAULT_EXCLUSION_SCHEMA = "seshat.owner_source_exclusion.default_empty"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class _InventedRights:
    def __init__(self, denied: frozenset[str] = frozenset()) -> None:
        self.denied = set(denied)
        self.version = "invented-rights-1"

    def revision(self, caller_id: str, view_id: str) -> str:
        return self.version

    def visibility(self, caller_id: str, view_id: str, object_id: str) -> Visibility:
        return Visibility.DENIED if object_id in self.denied else Visibility.VISIBLE

    def carrier_visibility(
        self, caller_id: str, view_id: str, object_id: str, carrier_id: str
    ) -> Visibility:
        return self.visibility(caller_id, view_id, object_id)

    def may_count_denied(self, caller_id: str, view_id: str) -> bool:
        return False

    def seal_selection(self, caller_id: str, view_id: str, canonical_json: str) -> str:
        return _sha(canonical_json.encode("utf-8"))


def load_exclusion_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "schema": DEFAULT_EXCLUSION_SCHEMA,
            "operator_supplied": False,
            "authority": None,
            "status": "DEFAULT_EMPTY",
            "excluded": {
                "source_drive_ids": [],
                "source_names": [],
                "aliases": [],
                "source_sha256": [],
            },
        }
    policy = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(policy, dict) or "excluded" not in policy:
        raise ValueError("I11_EXCLUSION_POLICY_INVALID")
    if policy.get("schema") != OWNER_EXCLUSION_SCHEMA:
        raise ValueError("I11_EXCLUSION_POLICY_INVALID")
    excluded = policy["excluded"]
    if not isinstance(excluded, dict):
        raise ValueError("I11_EXCLUSION_POLICY_INVALID")
    for key in ("source_drive_ids", "source_names", "aliases"):
        if key not in excluded or not isinstance(excluded[key], list):
            raise ValueError("I11_EXCLUSION_POLICY_INVALID")
    excluded.setdefault("source_sha256", [])
    if not isinstance(excluded["source_sha256"], list):
        raise ValueError("I11_EXCLUSION_POLICY_INVALID")
    return {**policy, "operator_supplied": True}


def is_real_authorizing_policy(policy: dict[str, Any]) -> bool:
    return (
        policy.get("operator_supplied") is True
        and policy.get("schema") == OWNER_EXCLUSION_SCHEMA
        and policy.get("authority") == "OWNER_EXPLICIT"
        and policy.get("status") == "PERMANENT_ACTIVE_EXCLUSION"
    )


def load_f07_permission(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    permission = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(permission, dict):
        raise ValueError("I11_F07_PERMISSION_INVALID")
    required = {
        "schema": F07_PERMISSION_SCHEMA,
        "rights_class": "FULL_REQUIRED",
        "grant": "OPERATOR_DECLARED_UNATTESTED",
        "independent_attestation": "NONE",
    }
    for key, expected in required.items():
        if permission.get(key) != expected:
            raise ValueError("I11_F07_PERMISSION_INVALID")
    for key in ("permission_id", "operation_id", "source_id", "source_sha256"):
        if not isinstance(permission.get(key), str) or not permission[key]:
            raise ValueError("I11_F07_PERMISSION_INVALID")
    digest = str(permission["source_sha256"]).casefold()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("I11_F07_PERMISSION_INVALID")
    pages = permission.get("pages_sha256")
    if pages is not None:
        pages = str(pages).casefold()
        if len(pages) != 64 or any(ch not in "0123456789abcdef" for ch in pages):
            raise ValueError("I11_F07_PERMISSION_INVALID")
        permission = {**permission, "pages_sha256": pages}
    return permission


def _identity_excluded(source_id: str, source_name: str, exclusion_policy: dict[str, Any]) -> bool:
    excluded = exclusion_policy.get("excluded", {})
    denied = {
        str(item).casefold()
        for key in ("source_drive_ids", "source_names", "aliases")
        for item in excluded.get(key, ())
    }
    return source_id.casefold() in denied or (bool(source_name) and source_name.casefold() in denied)


def admit_source(
    *,
    source_id: str,
    source_name: str = "",
    source_bytes: bytes | None,
    exclusion_policy: dict[str, Any],
    f07_full_read_granted: bool,
    invented_public: bool = False,
    f07_permission: dict[str, Any] | None = None,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    if _identity_excluded(source_id, source_name, exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    if source_bytes:
        digest = _sha(source_bytes)
        denied_hashes = {
            str(item).casefold()
            for item in exclusion_policy.get("excluded", {}).get("source_sha256", ())
        }
        if digest in denied_hashes:
            raise ValueError("I11_SOURCE_EXCLUDED")
        if expected_source_sha256 and digest != expected_source_sha256.casefold():
            raise ValueError("I11_VERSION_DRIFT")
    if invented_public:
        if not source_bytes:
            return {
                "status": "BLOCKED_SOURCE_RIGHTS",
                "source_id": source_id,
                "reason": "TEST_ONLY invented fixture supplied no bytes.",
                "f07_full_read": False,
                "path": "TEST_ONLY",
            }
        return {
            "status": "ADMITTED_INVENTED_PUBLIC",
            "source_id": source_id,
            "source_sha256": _sha(source_bytes),
            "rights": "operator-created-public-test-fixture",
            "f07_full_read": False,
            "path": "TEST_ONLY",
            "provenance": "SELF_OBSERVED_UNATTESTED",
        }
    if not is_real_authorizing_policy(exclusion_policy):
        return {
            "status": "BLOCKED_SOURCE_RIGHTS",
            "source_id": source_id,
            "reason": "POLICY_MISSING",
            "f07_full_read": False,
            "cli_flag_is_not_grant": True,
        }
    if f07_permission is None:
        return {
            "status": "BLOCKED_SOURCE_RIGHTS",
            "source_id": source_id,
            "reason": "F07_PERMISSION_MISSING" if not f07_full_read_granted else "F07_FLAG_IS_NOT_GRANT",
            "f07_full_read": False,
            "cli_flag_is_not_grant": True,
        }
    if _identity_excluded(str(f07_permission.get("source_id") or ""), "", exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    if f07_permission.get("operation_id") != AUTHORIAL_I11_ID:
        return {
            "status": "BLOCKED_SOURCE_RIGHTS",
            "source_id": source_id,
            "reason": "F07_OPERATION_MISMATCH",
            "f07_full_read": False,
        }
    if not source_bytes:
        return {
            "status": "BLOCKED_SOURCE_RIGHTS",
            "source_id": source_id,
            "reason": "SOURCE_BYTES_REQUIRED",
            "f07_full_read": False,
        }
    digest = _sha(source_bytes)
    allowed = {
        str(f07_permission["source_sha256"]).casefold(),
        str(f07_permission.get("pages_sha256") or "").casefold(),
    }
    if digest not in allowed:
        raise ValueError("I11_VERSION_DRIFT")
    return {
        "status": "ADMITTED_OPERATOR_DECLARED_UNATTESTED",
        "source_id": source_id,
        "source_sha256": digest,
        "rights": "operator-declared-unattested",
        "f07_full_read": False,
        "cli_flag_is_not_grant": True,
        "f07_permission_id": f07_permission["permission_id"],
        "policy_digest": _sha(_canonical({
            "schema": exclusion_policy.get("schema"),
            "excluded": exclusion_policy.get("excluded"),
        })),
        "provenance": "SELF_OBSERVED_UNATTESTED",
    }


def admit_model_run(
    *,
    job_id: str | None,
    stdout_bytes: bytes | None,
    method_bytes: bytes | None,
    expected_method_sha256: str = AUTHORIAL_I11_SHA256,
    expected_stdout_sha256: str | None = None,
    expected_job_id: str = OBSERVED_I11_JOB_ID,
    submit_new_paid_job: bool = False,
) -> dict[str, Any]:
    if submit_new_paid_job:
        raise ValueError("I11_DUPLICATE_LAUNCH")
    if not job_id or not stdout_bytes or not method_bytes:
        return {
            "status": "BLOCKED_MODEL_ADMISSION",
            "reason": (
                "No terminal ordinary Hub/local job bytes were supplied in this "
                "scene, and this command will not create credentials or a new paid job."
            ),
            "indago": INDAGO_STATUS,
        }
    if _sha(method_bytes) != expected_method_sha256:
        raise ValueError("I11_METHOD_PIN_MISMATCH")
    if expected_stdout_sha256 and _sha(stdout_bytes) != expected_stdout_sha256:
        raise ValueError("I11_VERSION_DRIFT")
    if job_id != expected_job_id:
        raise ValueError("I11_DUPLICATE_LAUNCH")
    return {
        "status": "OBSERVED_TERMINAL_UNATTESTED",
        "job_id": job_id,
        "provider": "claude",
        "model": "opus",
        "method_sha256": _sha(method_bytes),
        "stdout_sha256": _sha(stdout_bytes),
        "cost": "UNKNOWN",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_ASSERTED",
        "customer_release": "BLOCKED",
        "indago": INDAGO_STATUS,
    }


def _require_hub_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("I11_FORGED_JOB")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("I11_FORGED_JOB")
    job_id = receipt.get("job_id")
    if job_id != OBSERVED_I11_JOB_ID:
        raise ValueError("I11_FORGED_JOB")
    if receipt.get("state") != "SUCCEEDED" or receipt.get("exit_code") != 0:
        raise ValueError("I11_FORGED_JOB")
    model = str(receipt.get("model") or "").casefold()
    if "opus" not in model:
        raise ValueError("I11_FORGED_JOB")
    return receipt


def observe_existing_i11_package(
    package_dir: Path,
    *,
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    source_id: str = "",
    source_name: str = "",
    f07_full_read_granted: bool = False,
) -> dict[str, Any]:
    """Bind an already-terminal private package. Never re-submits a model job."""
    if not is_real_authorizing_policy(exclusion_policy) or f07_permission is None:
        return {
            "status": "BLOCKED_REAL_MODEL_BINDING",
            "reason": "POLICY_OR_F07_PERMISSION_MISSING",
            "cli_flag_is_not_grant": True,
        }
    if not package_dir.is_dir():
        return {
            "status": "BLOCKED_REAL_MODEL_BINDING",
            "reason": "PACKAGE_MISSING",
        }
    pointer_path = package_dir / "model_run_pointer.json"
    if not pointer_path.is_file():
        return {"status": "BLOCKED_REAL_MODEL_BINDING", "reason": "POINTER_MISSING"}
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if not isinstance(pointer, dict) or not pointer.get("run_id"):
        raise ValueError("I11_FORGED_JOB")
    candidate_id = source_id or str(f07_permission.get("source_id") or "")
    candidate_name = source_name
    if _identity_excluded(candidate_id, candidate_name, exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    if _identity_excluded(str(pointer.get("run_id") or ""), "", exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    hub = _require_hub_receipt(package_dir / "hub_receipt_original.json")
    method_path = package_dir.parent / "I11_ACTIVITY_NETWORK_v1.0_FROZEN.txt"
    stdout_path = package_dir / "model_stdout_original.txt"
    pdf_path = package_dir.parent / "open_source.pdf"
    pages_path = package_dir.parent / "source_repo" / "m7_source" / "open_source_pages.txt"
    state_path = package_dir / "activity_network_state.json"
    if not method_path.is_file() or not stdout_path.is_file() or not state_path.is_file():
        return {"status": "BLOCKED_REAL_MODEL_BINDING", "reason": "MODEL_BYTES_MISSING"}
    method_bytes = method_path.read_bytes()
    stdout_bytes = stdout_path.read_bytes()
    if not pdf_path.is_file() or not pages_path.is_file():
        return {
            "status": "BLOCKED_SOURCE_RIGHTS",
            "reason": "CC-BY PDF or page extract missing or hash-drifted on this host.",
        }
    pdf_bytes = pdf_path.read_bytes()
    pages_bytes = pages_path.read_bytes()
    if _sha(pdf_bytes) != CCBY_PDF_SHA256 or _sha(pages_bytes) != CCBY_PAGES_SHA256:
        raise ValueError("I11_VERSION_DRIFT")
    if str(pointer.get("stdout_sha") or "").casefold() != OBSERVED_I11_STDOUT_SHA256:
        raise ValueError("I11_VERSION_DRIFT")
    if str(pointer.get("source_sha") or "").casefold() != CCBY_PDF_SHA256:
        raise ValueError("I11_VERSION_DRIFT")
    admission = admit_source(
        source_id=candidate_id or "observed-ccby-pdf",
        source_name=candidate_name,
        source_bytes=pdf_bytes,
        exclusion_policy=exclusion_policy,
        f07_full_read_granted=f07_full_read_granted,
        f07_permission=f07_permission,
        expected_source_sha256=CCBY_PDF_SHA256,
    )
    if admission["status"] != "ADMITTED_OPERATOR_DECLARED_UNATTESTED":
        return {**admission, "status": admission.get("status", "BLOCKED_SOURCE_RIGHTS")}
    pages_admission = admit_source(
        source_id=f"{candidate_id or 'observed-ccby-pdf'}-pages",
        source_name=candidate_name,
        source_bytes=pages_bytes,
        exclusion_policy=exclusion_policy,
        f07_full_read_granted=f07_full_read_granted,
        f07_permission=f07_permission,
        expected_source_sha256=CCBY_PAGES_SHA256,
    )
    if pages_admission["status"] != "ADMITTED_OPERATOR_DECLARED_UNATTESTED":
        return pages_admission
    observed = admit_model_run(
        job_id=str(pointer.get("run_id")),
        stdout_bytes=stdout_bytes,
        method_bytes=method_bytes,
        expected_stdout_sha256=OBSERVED_I11_STDOUT_SHA256,
    )
    if observed.get("status") != "OBSERVED_TERMINAL_UNATTESTED":
        return observed
    if hub["job_id"] != observed["job_id"]:
        raise ValueError("I11_FORGED_JOB")
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("I11_TRUNCATED_MODEL_OUTPUT")
    derivative = None
    derivative_path = package_dir / "activity_network_state_reviewed_evidence_only.json"
    if derivative_path.is_file():
        raw_derivative = json.loads(derivative_path.read_text(encoding="utf-8"))
        if isinstance(raw_derivative, dict):
            derivative = raw_derivative
    page_map = parse_page_map(pages_bytes)
    state = activity_state_from_model_payload(
        payload,
        source_bytes=pages_bytes,
        expected_source_sha256=CCBY_PAGES_SHA256,
        job_id=observed["job_id"],
        page_map=page_map,
        typographic_derivative=derivative,
    )
    observed.update({
        "source_pdf_sha256": CCBY_PDF_SHA256,
        "source_pages_sha256": CCBY_PAGES_SHA256,
        "source_kind": "CC_BY_PUBLISHED_PAPER",
        "method_id": AUTHORIAL_I11_ID,
        "method_version": AUTHORIAL_I11_VERSION,
        "hub_receipt_sha256": _sha((package_dir / "hub_receipt_original.json").read_bytes()),
        "typed_state": state,
        "typed_actor_count": len(state.actors),
        "typed_event_count": len(state.action_events),
        "typed_relation_count": len(state.relations),
        "pages_bytes": pages_bytes,
        "method_bytes": method_bytes,
        "admission": admission,
    })
    return observed


def _world_pins(world: Literal["world_a", "world_b"]) -> tuple[
    OperatorSourcePin, bytes, OperatorMethodBodyPin, bytes
]:
    source_bytes = world_bytes(world)
    method_bytes = fictional_method_bytes()
    source = OperatorSourcePin(
        source_id=f"public-invented-{world}",
        source_version="invented-v1",
        sha256=_sha(source_bytes),
        rights_basis="operator-created-public-test-fixture",
        authorized_view="private-operator",
    )
    method = OperatorMethodBodyPin(
        method_body_id=FICTIONAL_METHOD_ID,
        version=FICTIONAL_METHOD_VERSION,
        invocation_body_sha256=_sha(method_bytes),
    )
    return source, source_bytes, method, method_bytes


def run_fictional_world(
    world: Literal["world_a", "world_b"],
    ledger: OperatorRunLedger | SQLiteOperatorRunLedger,
    *,
    owner_excluded_source_ids: frozenset[str],
    owner_excluded_source_sha256: frozenset[str],
) -> tuple[Any, bytes, bytes]:
    source, source_bytes, method, method_bytes = _world_pins(world)
    admit_source(
        source_id=source.source_id,
        source_bytes=source_bytes,
        exclusion_policy={"excluded": {
            "source_drive_ids": list(owner_excluded_source_ids),
            "source_names": [],
            "aliases": [],
            "source_sha256": list(owner_excluded_source_sha256),
        }},
        f07_full_read_granted=True,
        invented_public=True,
    )
    receipt = invoke_operator_method_body(
        ledger=ledger,
        run_id=f"i11-fictional-{world}",
        job_id=f"local-i11-{world}",
        source=source,
        source_bytes=source_bytes,
        method=method,
        method_body_invocation_bytes=method_bytes,
        method_callable=execute_fictional_i11,
        requested_view="private-operator",
        declared_model_identity="deterministic-local-i11-interpreter-no-LLM",
        owner_excluded_source_ids=owner_excluded_source_ids,
        owner_excluded_source_sha256=owner_excluded_source_sha256,
    )
    return receipt, source_bytes, method_bytes


def compose_private_i11_r03(
    state_a: ActivityNetworkState,
    state_b: ActivityNetworkState,
    selection: dict[str, Any],
) -> dict[str, Any]:
    if state_a.work_id == state_b.work_id:
        raise ValueError("I11_R03_SAME_WORK")
    shared_team = any(
        "SAME_RESEARCH_TEAM" in item for item in (
            state_a.explicit_non_equivalences + state_b.explicit_non_equivalences
        )
    )
    if shared_team:
        raise ValueError("I11_FALSE_SHARED_TEAM")
    layers_a = {event.layer for event in state_a.action_events}
    layers_b = {event.layer for event in state_b.action_events}
    content = {
        "schema": "seshat.operator_private_r03.v1",
        "report_id": "R03",
        "status": "SOURCE_GROUNDED_UNREVIEWED",
        "visibility": "OWNER_PRIVATE_ONLY",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "corpus_selection": selection,
        "coverage": {
            "selected_works": 2,
            "not_a_186_corpus": True,
            "membership_kinds": selection.get("membership_kinds", {
                state_a.work_id: "TEST_ONLY_FICTIONAL",
                state_b.work_id: "TEST_ONLY_FICTIONAL",
            }),
            "unknown": (
                "No shared research team is evidenced.",
                "Implementation efficacy remains UNKNOWN.",
                "Cross-world personal identity is UNKNOWN beyond listed formal names.",
            ),
        },
        "comparisons": [
            {
                "axis": "RP_vs_FT",
                "world_a_event_count": sum(1 for event in state_a.action_events if event.layer in {"RP", "FT"}),
                "world_b_event_count": sum(1 for event in state_b.action_events if event.layer in {"RP", "FT"}),
                "inference_forbidden": "shared formal role is not a shared team",
            },
            {
                "axis": "SS_vs_PO",
                "world_a_event_count": sum(1 for event in state_a.action_events if event.layer in {"SS", "PO"}),
                "world_b_event_count": sum(1 for event in state_b.action_events if event.layer in {"SS", "PO"}),
                "inference_forbidden": "clinical staff are not publication authors",
            },
            {
                "axis": "IM_vs_PR",
                "world_a_event_count": sum(1 for event in state_a.action_events if event.layer in {"IM", "PR"}),
                "world_b_event_count": sum(1 for event in state_b.action_events if event.layer in {"IM", "PR"}),
                "inference_forbidden": "reported implementation is not efficacy",
            },
            {
                "axis": "layer_presence",
                "world_a": sorted(layers_a),
                "world_b": sorted(layers_b),
                "unknown": "layers absent from a work stay UNKNOWN, not negative proof",
            },
        ],
        "indago": INDAGO_STATUS,
    }
    return {**content, "projection_sha256": _sha(_canonical(content))}


def fictional_corpus_selection(
    source_a: bytes,
    source_b: bytes,
    *,
    denied: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    pin = ManifestPin(manifest_id="invented-i11-mini", version="1", sha256="b" * 64)
    manifest = PopulationManifest(
        pin=pin,
        declared_fields=frozenset({"specialty"}),
    )
    records = (
        evidenced_study(
            object_id="invented-world_a",
            version="1",
            object_type="invented.public.study",
            carriers=(
                SourceCarrier(
                    carrier_id="public-invented-world_a",
                    source_identity="invented-utf8",
                    version="invented-v1",
                    content_sha256=_sha(source_a),
                ),
            ),
            fields=(
                EvidenceField(
                    name="specialty",
                    value="invented-organization",
                    evidence_ref="fixture:world-a:specialty",
                ),
            ),
        ),
        evidenced_study(
            object_id="invented-world_b",
            version="1",
            object_type="invented.public.study",
            carriers=(
                SourceCarrier(
                    carrier_id="public-invented-world_b",
                    source_identity="invented-utf8",
                    version="invented-v1",
                    content_sha256=_sha(source_b),
                ),
            ),
            fields=(
                EvidenceField(
                    name="specialty",
                    value="invented-measurement",
                    evidence_ref="fixture:world-b:specialty",
                ),
            ),
        ),
    )
    spec = CorpusSelectionSpec(
        selector_id="i11-two-world-mini",
        version="1",
        manifest=pin,
        predicate=Predicate(op="ids", ids=("invented-world_a", "invented-world_b")),
        caller_id="private-operator",
        view_id="research",
    )
    snapshot = build_corpus_space(spec, manifest, records, _InventedRights(denied))
    if snapshot.selected_studies != 2:
        raise ValueError("I11_DENIED_SOURCE")
    membership = [member.object_id for member in snapshot.members]
    return {
        "selector_id": spec.selector_id,
        "version": spec.version,
        "membership": membership,
        "membership_kinds": {item: "TEST_ONLY_FICTIONAL" for item in membership},
        "selected_studies": snapshot.selected_studies,
        "selection_digest": snapshot.selection_digest,
        "snapshot_digest": snapshot.snapshot_digest,
        "source_state": snapshot.source_state,
        "semantic_acceptance_state": snapshot.semantic_acceptance_state,
    }


def _state_from_receipt_notes(receipt: Any) -> ActivityNetworkState:
    for note in receipt.output_sediment.payload.get("notes", ()):
        if isinstance(note, str) and note.startswith("{") and "work_id" in note:
            return ActivityNetworkState.model_validate(json.loads(note))
    raise ValueError("I11_TRUNCATED_MODEL_OUTPUT")


def run_fictional_vertical(
    out: Path,
    *,
    verify_only: bool = False,
    owner_excluded_source_ids: frozenset[str] = frozenset(),
    owner_excluded_source_sha256: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOperatorRunLedger(out / "runs.sqlite")
    reports: dict[str, Any] = {}
    states: dict[str, ActivityNetworkState] = {}
    bytes_by_world: dict[str, tuple[bytes, bytes]] = {}
    for world in ("world_a", "world_b"):
        run_id = f"i11-fictional-{world}"
        source_bytes = world_bytes(world)  # type: ignore[arg-type]
        method_bytes = fictional_method_bytes()
        if verify_only:
            receipt = replay_and_verify_operator_run(
                ledger=ledger,
                run_id=run_id,
                source_bytes=source_bytes,
                method_body_invocation_bytes=method_bytes,
            )
        else:
            receipt, source_bytes, method_bytes = run_fictional_world(
                world,  # type: ignore[arg-type]
                ledger,
                owner_excluded_source_ids=owner_excluded_source_ids,
                owner_excluded_source_sha256=owner_excluded_source_sha256,
            )
        bytes_by_world[world] = (source_bytes, method_bytes)
        preview = compose_private_operator_r01r02(
            receipt, ledger=ledger, source_bytes=source_bytes,
            method_invocation_bytes=method_bytes,
        )
        verify_private_operator_r01r02(
            preview, receipt, ledger=ledger, source_bytes=source_bytes,
            method_invocation_bytes=method_bytes,
        )
        preview_path = out / f"private_r01r02_{world}.json"
        if preview_path.exists():
            stored = json.loads(preview_path.read_text(encoding="utf-8"))
            if _canonical(stored) != _canonical(preview):
                raise ValueError("I11_STALE_REPORT")
            reports[world] = stored
        elif verify_only:
            raise ValueError("OPERATOR_R01R02_PRIVATE_RECEIPT_MISSING")
        else:
            _write_exclusive(preview_path, preview)
            reports[world] = preview
        states[world] = _state_from_receipt_notes(receipt)
        validate_activity_network(states[world], source_bytes, expected_source_sha256=_sha(source_bytes))
    selection = fictional_corpus_selection(bytes_by_world["world_a"][0], bytes_by_world["world_b"][0])
    r03 = compose_private_i11_r03(states["world_a"], states["world_b"], selection)
    r03_path = out / "private_r03.json"
    if r03_path.exists():
        stored_r03 = json.loads(r03_path.read_text(encoding="utf-8"))
        if _canonical(stored_r03) != _canonical(r03):
            raise ValueError("I11_STALE_REPORT")
    elif verify_only:
        raise ValueError("OPERATOR_R01R02_PRIVATE_RECEIPT_MISSING")
    else:
        _write_exclusive(r03_path, r03)
    manifest = {
        "schema": "seshat.i11_vertical_manifest.v1",
        "mode": "TEST_ONLY_FICTIONAL_TWO_WORLD",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_PERFORMED",
        "customer_release": "BLOCKED",
        "model_run_attested": False,
        "authorial_i11_executed": False,
        "indago": INDAGO_STATUS,
        "worlds": {
            world: {
                "run_id": f"i11-fictional-{world}",
                "source_sha256": _sha(bytes_by_world[world][0]),
                "method_sha256": _sha(bytes_by_world[world][1]),
                "r01r02_sha256": reports[world]["projection_sha256"],
            }
            for world in ("world_a", "world_b")
        },
        "r03_sha256": r03["projection_sha256"],
        "corpus_selection": selection,
    }
    manifest["manifest_sha256"] = _sha(_canonical(manifest))
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if _canonical(stored_manifest) != _canonical(manifest):
            raise ValueError("I11_STALE_REPORT")
    elif not verify_only:
        _write_exclusive(manifest_path, manifest)
    return {
        "status": "READBACK_VERIFIED_SELF_OBSERVED" if verify_only else "EXECUTED_OR_RESUMED_SELF_OBSERVED",
        "manifest_sha256": manifest["manifest_sha256"],
        "r03_sha256": r03["projection_sha256"],
        "worlds": list(manifest["worlds"]),
        "customer_release": "BLOCKED",
        "indago": INDAGO_STATUS,
    }


def _bind_observed_callable(state: ActivityNetworkState):
    def _bind(invocation: OperatorInvocation) -> OperatorBodyResult:
        if _sha(invocation.method_body_invocation_bytes) != AUTHORIAL_I11_SHA256:
            raise ValueError("I11_METHOD_PIN_MISMATCH")
        validate_activity_network(
            state, invocation.source_bytes, expected_source_sha256=_sha(invocation.source_bytes)
        )
        claims = tuple(_claim_from_event(event) for event in state.action_events)
        return OperatorBodyResult(
            research_object_id=state.work_id,
            claims=claims,
            epistemic_level=EpistemicLevel.E2,
            notes=(
                "observed_i11_bind_no_new_paid_job",
                json.dumps(state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False),
            ),
        )

    return _bind


def run_observed_vertical(
    out: Path,
    package_dir: Path,
    *,
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    verify_only: bool = False,
    source_id: str = "",
    source_name: str = "",
    f07_full_read_granted: bool = False,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    observed = observe_existing_i11_package(
        package_dir,
        exclusion_policy=exclusion_policy,
        f07_permission=f07_permission,
        source_id=source_id,
        source_name=source_name,
        f07_full_read_granted=f07_full_read_granted,
    )
    if observed.get("status") != "OBSERVED_TERMINAL_UNATTESTED":
        public = {k: v for k, v in observed.items() if k not in {
            "typed_state", "pages_bytes", "method_bytes"
        }}
        target = out / "observed_model_run.json"
        if not target.exists():
            _write_exclusive(target, public)
        return public
    state: ActivityNetworkState = observed["typed_state"]
    pages_bytes: bytes = observed["pages_bytes"]
    method_bytes: bytes = observed["method_bytes"]
    excluded = exclusion_policy.get("excluded", {})
    ledger = SQLiteOperatorRunLedger(out / "runs.sqlite")
    source = OperatorSourcePin(
        source_id="observed-ccby-pages",
        source_version="ccby-pages-v1",
        sha256=_sha(pages_bytes),
        rights_basis="operator-declared-unattested-ccby-pages",
        authorized_view="private-operator",
    )
    method = OperatorMethodBodyPin(
        method_body_id=AUTHORIAL_I11_ID,
        version=AUTHORIAL_I11_VERSION,
        invocation_body_sha256=_sha(method_bytes),
    )
    if verify_only:
        receipt = replay_and_verify_operator_run(
            ledger=ledger,
            run_id="i11-observed-ccby",
            source_bytes=pages_bytes,
            method_body_invocation_bytes=method_bytes,
        )
    else:
        receipt = invoke_operator_method_body(
            ledger=ledger,
            run_id="i11-observed-ccby",
            job_id=observed["job_id"],
            source=source,
            source_bytes=pages_bytes,
            method=method,
            method_body_invocation_bytes=method_bytes,
            method_callable=_bind_observed_callable(state),
            requested_view="private-operator",
            declared_model_identity="claude/opus-observed-terminal-no-new-job",
            owner_excluded_source_ids=frozenset(
                str(item) for item in excluded.get("source_drive_ids", ())
            ),
            owner_excluded_source_sha256=frozenset(
                str(item) for item in excluded.get("source_sha256", ())
                if isinstance(item, str) and len(item) == 64
            ),
        )
    preview = compose_private_operator_r01r02(
        receipt, ledger=ledger, source_bytes=pages_bytes, method_invocation_bytes=method_bytes
    )
    verify_private_operator_r01r02(
        preview, receipt, ledger=ledger, source_bytes=pages_bytes,
        method_invocation_bytes=method_bytes,
    )
    preview_path = out / "private_r01r02_observed.json"
    if preview_path.exists():
        stored = json.loads(preview_path.read_text(encoding="utf-8"))
        if _canonical(stored) != _canonical(preview):
            raise ValueError("I11_STALE_REPORT")
    elif verify_only:
        raise ValueError("OPERATOR_R01R02_PRIVATE_RECEIPT_MISSING")
    else:
        _write_exclusive(preview_path, preview)
    control_bytes = world_bytes("world_b")
    control_method = fictional_method_bytes()
    control_receipt, _, _ = run_fictional_world(
        "world_b",
        ledger,
        owner_excluded_source_ids=frozenset(
            str(item) for item in excluded.get("source_drive_ids", ())
        ),
        owner_excluded_source_sha256=frozenset(
            str(item) for item in excluded.get("source_sha256", ())
            if isinstance(item, str) and len(item) == 64
        ),
    )
    control_state = _state_from_receipt_notes(control_receipt)
    validate_activity_network(control_state, control_bytes, expected_source_sha256=_sha(control_bytes))
    selection = {
        "selector_id": "i11-observed-plus-test-only",
        "version": "1",
        "membership": [state.work_id, control_state.work_id],
        "membership_kinds": {
            state.work_id: "ADMITTED_REAL_OBSERVED",
            control_state.work_id: "TEST_ONLY_FICTIONAL",
        },
        "selected_studies": 2,
        "not_a_186_corpus": True,
    }
    r03 = compose_private_i11_r03(state, control_state, selection)
    r03_path = out / "private_r03.json"
    if r03_path.exists():
        stored_r03 = json.loads(r03_path.read_text(encoding="utf-8"))
        if _canonical(stored_r03) != _canonical(r03):
            raise ValueError("I11_STALE_REPORT")
    elif not verify_only:
        _write_exclusive(r03_path, r03)
    public = {
        "status": "OBSERVED_BOUND_SELF_OBSERVED",
        "job_id": observed["job_id"],
        "stdout_sha256": observed["stdout_sha256"],
        "method_sha256": observed["method_sha256"],
        "source_pdf_sha256": CCBY_PDF_SHA256,
        "source_pages_sha256": CCBY_PAGES_SHA256,
        "hub_receipt_sha256": observed["hub_receipt_sha256"],
        "typed_actor_count": observed["typed_actor_count"],
        "typed_event_count": observed["typed_event_count"],
        "typed_relation_count": observed["typed_relation_count"],
        "r01r02_sha256": preview["projection_sha256"],
        "r03_sha256": r03["projection_sha256"],
        "control": "TEST_ONLY_FICTIONAL",
        "provenance": "SELF_OBSERVED_UNATTESTED",
        "scientific_acceptance": "NOT_ASSERTED",
        "customer_release": "BLOCKED",
        "indago": INDAGO_STATUS,
    }
    target = out / "observed_model_run.json"
    if not target.exists():
        _write_exclusive(target, public)
    return public


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as sink:
        sink.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        sink.flush()
        os.fsync(sink.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SESHAT I11 vertical: source+method to private reports")
    parser.add_argument(
        "--mode",
        choices=("fictional", "admit-candidate", "observe-existing"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--exclusion-policy", type=Path)
    parser.add_argument("--f07-permission", type=Path)
    parser.add_argument("--source-id", default="")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--f07-full-read", action="store_true")
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--submit-new-paid-job", action="store_true")
    opts = parser.parse_args(argv)
    opts.out.mkdir(parents=True, exist_ok=True)
    policy = load_exclusion_policy(opts.exclusion_policy)
    permission = load_f07_permission(opts.f07_permission)
    if opts.mode == "fictional":
        result = run_fictional_vertical(
            opts.out,
            verify_only=opts.verify_only,
            owner_excluded_source_ids=frozenset(
                str(item) for item in policy.get("excluded", {}).get("source_drive_ids", ())
            ),
            owner_excluded_source_sha256=frozenset(
                str(item) for item in policy.get("excluded", {}).get("source_sha256", ())
                if isinstance(item, str) and len(item) == 64
            ),
        )
    elif opts.mode == "admit-candidate":
        candidate = opts.source_id or (permission or {}).get("source_id") or ""
        if _identity_excluded(str(candidate), opts.source_name, policy):
            raise ValueError("I11_SOURCE_EXCLUDED")
        may_open = is_real_authorizing_policy(policy) and permission is not None
        source_bytes = opts.source_file.read_bytes() if opts.source_file and may_open else None
        result = admit_source(
            source_id=opts.source_id,
            source_name=opts.source_name,
            source_bytes=source_bytes,
            exclusion_policy=policy,
            f07_full_read_granted=opts.f07_full_read,
            f07_permission=permission,
        )
        if not (opts.out / "admission.json").exists():
            _write_exclusive(opts.out / "admission.json", result)
    else:
        if opts.submit_new_paid_job:
            raise ValueError("I11_DUPLICATE_LAUNCH")
        if opts.package_dir is None:
            result = {
                "status": "BLOCKED_REAL_MODEL_BINDING",
                "reason": "PACKAGE_MISSING",
            }
        else:
            result = run_observed_vertical(
                opts.out,
                opts.package_dir,
                exclusion_policy=policy,
                f07_permission=permission,
                verify_only=opts.verify_only,
                source_id=opts.source_id,
                source_name=opts.source_name,
                f07_full_read_granted=opts.f07_full_read,
            )
        if result.get("status") != "OBSERVED_BOUND_SELF_OBSERVED":
            fictional = run_fictional_vertical(
                opts.out / "test_only_fictional",
                verify_only=opts.verify_only,
            )
            result = {
                **result,
                "independent_test_only": fictional,
            }
    printable = {
        key: value for key, value in result.items()
        if key not in {"typed_state", "pages_bytes", "method_bytes"}
    }
    print(json.dumps(printable, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
