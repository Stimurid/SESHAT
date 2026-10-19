"""Trusted G1 Carpet sediment -> F07-admitted F08 readable R01/R02 bridge.

Only the authenticated owner host calls this function. A source pin, textual
method description, ledger hash or user-supplied asset is NOT a capability.
The bridge validates an ACTUAL MethodBody activation and its current sediment
against the F07-selected member and the G1 FULL_REQUIRED carrier receipts.
The generated output remains UNREVIEWED and is never a scientific decision.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal

from pydantic import Field

from seshat.contracts import AcceptanceState, RawAccessPolicy, SourceAccessStatus
from seshat.corpus import FrozenModel
from seshat.corpus_host import HostRuntime
from seshat.fabric_waves.contracts import ActivationOutcome, EpistemicLevel
from seshat.fabric_waves.engine import WaveEngine
from seshat.fabric_waves.sediment import payload_hash
from seshat.reports import ReportProjection, ReportRequest, report_session
from seshat.scientific_report import AnchoredClaim, ScientificReportAsset, Subassembly


class FabricClaim(FrozenModel):
    page: int = Field(ge=1)
    text: str = Field(min_length=1)
    evidence_excerpt: str = Field(min_length=1)


class FabricSubassembly(FrozenModel):
    subassembly_id: str = Field(min_length=1)
    functional_object: str = Field(min_length=1)
    method: str = Field(min_length=1)
    material: str = Field(min_length=1)
    result: str = Field(min_length=1)
    counterexample_or_unknown: str = Field(min_length=1)
    claims: tuple[FabricClaim, ...] = Field(min_length=1)


class FabricReportPayload(FrozenModel):
    protocol: Literal["seshat.fabric.r01.source_reconstruction.v1"]
    research_problem: str = Field(min_length=1)
    author_scope: str = Field(min_length=1)
    subassemblies: tuple[FabricSubassembly, ...] = Field(min_length=1)


class FabricReportBridgeReceipt(FrozenModel):
    """Private host-side evidence. Never part of a customer export bundle."""

    run_id: str
    activation_id: str
    ledger_head_sha256: str
    sediment_id: str
    sediment_version: str
    registered_method_id: str
    registered_method_version: str
    registered_method_signature: str
    source_carrier_id: str
    source_version: str
    source_sha256: str
    report_projection_digest: str
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


_LEVEL_TO_STAGE = {
    EpistemicLevel.E1: "E1_OBSERVATION",
    EpistemicLevel.E2: "E2_RECONSTRUCTION",
    EpistemicLevel.E3: "E3_CONTRAST",
    EpistemicLevel.E4: "E4_CRITERIA",
    EpistemicLevel.E5: "E5_PROPOSAL",
}


def project_fabric_r01_r02(
    *,
    runtime: HostRuntime,
    authenticated_caller: str,
    authorized_view: str,
    request: ReportRequest,
    engine: WaveEngine,
    run_id: str,
    sediment_id: str,
    source_contents: Mapping[str, bytes],
    method_definition: bytes,
    rights_basis: str,
) -> tuple[ReportProjection, FabricReportBridgeReceipt]:
    """Compose a report from a MethodBody-produced source-anchored sediment.

    The caller supplies a trusted in-process F07 runtime and a trusted G1
    engine, never arbitrary serialized ledger data. The method_definition
    denotes the separately pinned readable method description, NOT a hash
    of the executable callable. The registry signature is recorded separately.
    """

    if (
        request.report_id not in {"R01", "R02"}
        or len(request.selections) != 1
        or request.rights_scope != authorized_view
        or request.selections[0].caller_id != authenticated_caller
        or not method_definition
        or not rights_basis
    ):
        raise ValueError("FABRIC_REPORT_REQUEST_DENIED")

    # F07 decides what is visible. A Fabric proof never grants corpus access.
    selection = runtime.session(
        authenticated_caller=authenticated_caller, authorized_view=authorized_view
    )(request.selections[0])
    if len(selection.members) != 1:
        raise ValueError("FABRIC_REPORT_SELECTION_NOT_SINGLE")
    member = selection.members[0]

    try:
        ledger, sediment, _ = engine.snapshot(run_id)
        ledger.verify()
    except (KeyError, ValueError, RuntimeError):
        raise ValueError("FABRIC_LEDGER_UNVERIFIED") from None
    runs = [run for run in ledger.runs if run.run_id == run_id]
    if len(runs) != 1:
        raise ValueError("FABRIC_RUN_NOT_PROVEN")
    run = runs[0]
    records = [s for s in sediment.all_records() if s.sediment_id == sediment_id]
    if len(records) != 1:
        raise ValueError("FABRIC_SEDIMENT_NOT_PROVEN")
    record = records[0]
    if (
        record.object_type != "science.reconstruction.v1"
        or record.research_object_id != member.object_id
        or record.version != run.sediment_final_versions.get(sediment_id)
        or record.payload_hash != payload_hash(record.payload)
        or record.acceptance_state not in (AcceptanceState.WORKING, AcceptanceState.PROPOSED)
    ):
        raise ValueError("FABRIC_SEDIMENT_STALE_OR_INCOMPATIBLE")

    activations = [
        act for act in ledger.activations
        if act.run_id == run_id and act.outcome is ActivationOutcome.FIRED
        and sediment_id in act.produced_sediment_ids
        and act.thread_id == record.produced_by_thread
        and act.method_body_refs == record.method_body_refs
    ]
    if len(activations) != 1 or len(record.method_body_refs) != 1:
        raise ValueError("FABRIC_METHOD_INVOCATION_UNPROVEN")
    act = activations[0]
    waves = [wave for wave in ledger.waves
             if wave.wave_id == act.wave_id and wave.run_id == run_id]
    if len(waves) != 1 or act.thread_id not in waves[0].fired_thread_ids:
        raise ValueError("FABRIC_WAVE_UNPROVEN")
    ref = record.method_body_refs[0]
    spec = engine.thread_specs.get(act.thread_id)
    if (
        spec is None
        or spec.raw_access_policy is not RawAccessPolicy.FULL_REQUIRED
        or ref not in spec.method_body_refs
        or not engine.bodies.has(ref)
        or engine.bodies.signature_for(ref) is None
    ):
        raise ValueError("FABRIC_METHOD_POLICY_DENIED")

    # MVP: exactly one versioned source per individual reconstruction.
    if len(record.source_carrier_refs) != 1:
        raise ValueError("FABRIC_SOURCE_SET_UNSUPPORTED")
    carrier_id = record.source_carrier_refs[0]
    source_carriers = [c for c in member.carriers if c.carrier_id == carrier_id]
    if (
        len(source_carriers) != 1 or carrier_id not in act.source_carrier_ids
        or carrier_id not in spec.admissible_source_carriers
    ):
        raise ValueError("FABRIC_SOURCE_NOT_F07_ADMITTED")
    carrier = source_carriers[0]
    manifest = record.source_access_manifest
    if (
        manifest is None
        or manifest.policy is not RawAccessPolicy.FULL_REQUIRED
        or not manifest.all_declared_sources_verified
        or not manifest.receipts
        or any(item.status is not SourceAccessStatus.VERIFIED for item in manifest.receipts)
        or not any(item.carrier_id == carrier_id and item.read_kind == "FULL"
                   and item.source_version == carrier.version
                   and item.content_sha256 == carrier.sha256
                   for item in manifest.receipts)
    ):
        raise ValueError("FABRIC_SOURCE_RECEIPT_UNVERIFIED")

    content = source_contents.get(carrier_id)
    if content is None or hashlib.sha256(content).hexdigest() != carrier.sha256:
        raise ValueError("FABRIC_SOURCE_BYTES_STALE")
    if engine.carrier_store is None:
        raise ValueError("FABRIC_SOURCE_STORE_MISSING")
    try:
        stored_digest = engine.carrier_store.pin_content_digest(
            carrier_id, pinned_version=carrier.version
        )
    except (ValueError, KeyError):
        raise ValueError("FABRIC_SOURCE_STORE_STALE") from None
    if stored_digest != carrier.sha256:
        raise ValueError("FABRIC_SOURCE_STORE_STALE")

    try:
        payload = FabricReportPayload.model_validate(record.payload)
    except ValueError:
        raise ValueError("FABRIC_REPORT_PAYLOAD_INVALID") from None

    source_text = content.decode("utf-8")
    synthetic_pages = source_text.startswith("SYNTHETIC PAGE 1:")
    subs = []
    for item in payload.subassemblies:
        claims = []
        for claim in item.claims:
            if claim.evidence_excerpt not in source_text:
                raise ValueError("FABRIC_CLAIM_NOT_IN_SOURCE")
            locator_state = "OWNER_ASSERTED"
            if synthetic_pages:
                marker = f"SYNTHETIC PAGE {claim.page}:"
                if marker not in source_text:
                    raise ValueError("FABRIC_CLAIM_PAGE_INVALID")
                current_page = source_text.split(marker, 1)[1].split(
                    f"SYNTHETIC PAGE {claim.page + 1}:", 1
                )[0]
                if claim.evidence_excerpt not in current_page:
                    raise ValueError("FABRIC_CLAIM_PAGE_INVALID")
                locator_state = "VERIFIED_IN_SYNTHETIC_SOURCE"
            claims.append(AnchoredClaim(
                stage=_LEVEL_TO_STAGE[record.epistemic_level],
                subassembly_id=item.subassembly_id,
                text=claim.text,
                carrier_id=carrier_id,
                source_version=carrier.version,
                source_sha256=carrier.sha256,
                page=claim.page,
                page_locator_state=locator_state,
            ))
        subs.append(Subassembly(
            subassembly_id=item.subassembly_id,
            functional_object=item.functional_object,
            method=item.method,
            material=item.material,
            result=item.result,
            counterexample_or_unknown=item.counterexample_or_unknown,
            claims=tuple(claims),
        ))

    # The proof is about real G1 execution. Scientific validity remains
    # unreviewed; no E-level is raised and no human acceptance is forged.
    method_label = f"{ref.method_body_id}@{ref.version}"
    asset = ScientificReportAsset(
        object_id=member.object_id,
        caller_id=authenticated_caller,
        rights_scope=authorized_view,
        producer_id=f"fabric:{run_id}:{act.activation_id}",
        rights_basis=rights_basis,
        currentness_as_of=request.as_of,
        source_member=member,
        method_body_version=method_label,
        method_body_sha256=hashlib.sha256(method_definition).hexdigest(),
        analytic_state_version=record.version,
        review_status="FABRIC_GENERATED_UNREVIEWED",
        research_problem=payload.research_problem,
        author_scope=payload.author_scope,
        evidence_subassembly_ids=tuple(item.subassembly_id for item in subs),
        subassemblies=tuple(subs),
    )
    pinned_request = request.model_copy(
        update={"expected_method_body_version":method_label}
    )
    report = report_session(
        runtime, authenticated_caller=authenticated_caller,
        authorized_view=authorized_view,
        scientific_assets=(asset,),
        scientific_sources=dict(source_contents),
        method_bodies={method_label: method_definition},
    )(pinned_request)
    if report.status != "SOURCE_GROUNDED_UNREVIEWED":
        raise ValueError("FABRIC_REPORT_NOT_RENDERED")
    return report, FabricReportBridgeReceipt(
        run_id=run_id,
        activation_id=act.activation_id,
        ledger_head_sha256=ledger.head_hash,
        sediment_id=record.sediment_id,
        sediment_version=record.version,
        registered_method_id=ref.method_body_id,
        registered_method_version=ref.version,
        registered_method_signature=engine.bodies.signature_for(ref),
        source_carrier_id=carrier_id,
        source_version=carrier.version,
        source_sha256=carrier.sha256,
        report_projection_digest=report.digest,
    )
