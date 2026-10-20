"""Source-agnostic, operator-local MethodBody execution route.

This is a SEPARATE pathway from :mod:`seshat.fabric_waves.report_bridge`,
whose ``project_fabric_r01_r02`` stays synthetic-only and is not modified by
this module. That guard exists because no trusted deployment attestation
exists for arbitrary executable code against a real research corpus. This
route is for an *ordinary user-operated* local run: the operator supplies
their own already-loaded, already-trusted Python callable (never a string
this module evaluates) and accepts that the resulting provenance is
``SELF_OBSERVED_UNATTESTED`` -- observed on the operator's own host, never
independently attested by a privileged issuer. No dedicated privileged
issuer server exists or is created by this module (owner decision,
see GitHub issue #65: the historic dedicated issuer server was destroyed and
reinstatement is rejected).

Guarantees this module enforces, fail-closed:

* ``FULL_REQUIRED`` source admission only after the exact supplied bytes hash
  to the operator's pinned sha256 -- never a metadata record alone.
* The author-pinned MethodBody identity+version+exact-invocation-body-bytes
  digest must match the bytes actually supplied for this run, and the
  operator-supplied callable is ACTUALLY INVOKED. There is no code path that
  marks a run verified without a real Python call happening.
* Every claim's evidence excerpt is checked against a byte-exact span of the
  real source bytes that were read, not a textual search for a synthetic
  marker -- this works for any UTF-8 source, not only the synthetic fixture
  convention used by the guarded bridge.
* The receipt never carries ``ACCEPTED`` acceptance or an asserted scientific
  acceptance; promotion to accepted canon stays exclusively a human,
  off-fabric act. Epistemic level is capped below the proposal ceiling.
* Raw source bytes, raw method-body bytes and raw stdout never appear in the
  receipt; only hashes/lengths/ids do. Export requires separately supplied,
  human-authored, rights-reviewed prose.
* Resuming the same ``run_id`` with the same pinned inputs replays the cached
  receipt instead of re-invoking; resuming with different inputs is an
  ambiguous duplicate and is denied, never a silent overwrite.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import Literal

from pydantic import Field

from seshat.contracts import (
    AcceptanceState,
    RawAccessPolicy,
    SourceAccessManifest,
    SourceAccessReceipt,
    SourceAccessStatus,
)
from seshat.corpus import FrozenModel
from seshat.fabric_waves.contracts import EpistemicLevel, MethodBodyRef, StoneEventKind
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash

# Populated only from a private host-side policy fed by the owner's current
# exclusion set (GitHub issue #65). Left empty here: issue #65 was not
# fetchable in this bounded, network-less session (no `gh`/WebFetch
# approval available; see the task receipt's OPEN QUESTIONS). Real excluded
# identifiers must never be hardcoded into this public module or into test
# fixtures -- callers pass them in via ``owner_excluded_source_ids`` from a
# private configuration surface.
_OWNER_EXCLUDED_SOURCE_IDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OperatorInvocation:
    """Inputs handed to the operator-supplied callable for one real call."""

    run_id: str
    job_id: str
    source_id: str
    source_bytes: bytes
    source_text: str
    method_body_id: str
    method_body_version: str
    method_body_invocation_bytes: bytes


class OperatorSourcePin(FrozenModel):
    source_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_basis: str = Field(min_length=1)
    authorized_view: str = Field(min_length=1)


class OperatorMethodBodyPin(FrozenModel):
    method_body_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    invocation_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OperatorClaim(FrozenModel):
    text: str = Field(min_length=1)
    evidence_excerpt: str = Field(min_length=1)
    byte_offset: int = Field(ge=0)
    byte_length: int = Field(ge=1)
    # Human-visible label only. Verification uses byte_offset/byte_length
    # against the real source bytes, never this label.
    page: int | None = Field(default=None, ge=1)


class OperatorBodyResult(FrozenModel):
    claims: tuple[OperatorClaim, ...] = Field(min_length=1)
    research_object_id: str = Field(min_length=1)
    epistemic_level: EpistemicLevel = EpistemicLevel.E2
    notes: tuple[str, ...] = Field(default_factory=tuple)


class OperatorInvocationReceipt(FrozenModel):
    """Host-private evidence of the real call. Never place in an export bundle."""

    stdout_sha256: str | None
    stdout_byte_length: int | None
    exit_status: Literal["OK", "EXCEPTION"]
    exception_class: str | None = None


class OperatorRunReceipt(FrozenModel):
    """Host-side receipt. Still owner-private until rights-reviewed export (h)."""

    run_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_access_manifest: SourceAccessManifest
    method_body_id: str = Field(min_length=1)
    method_body_version: str = Field(min_length=1)
    method_body_invocation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_model_identity: str = Field(min_length=1)
    declared_token_cost: int | Literal["UNKNOWN"] = "UNKNOWN"
    invocation: OperatorInvocationReceipt
    output_sediment: SedimentRecord
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: Literal["SELF_OBSERVED_UNATTESTED"] = "SELF_OBSERVED_UNATTESTED"
    scientific_acceptance: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


class OperatorExportBundle(FrozenModel):
    """The only artifact this module allows out of the owner-private boundary."""

    run_id: str
    method_body_id: str
    method_body_version: str
    source_id: str
    source_version: str
    reviewer_rights_statement: str = Field(min_length=1)
    reviewed_prose: str = Field(min_length=1)
    receipt_output_digest: str


def _input_fingerprint(
    *,
    run_id: str,
    job_id: str,
    source: OperatorSourcePin,
    method: OperatorMethodBodyPin,
    declared_model_identity: str,
    requested_view: str,
    declared_token_cost: int | Literal["UNKNOWN"],
) -> str:
    return payload_hash(
        {
            "run_id": run_id,
            "job_id": job_id,
            "source_id": source.source_id,
            "source_version": source.source_version,
            "source_sha256": source.sha256,
            "source_rights_basis": source.rights_basis,
            "source_authorized_view": source.authorized_view,
            "requested_view": requested_view,
            "declared_token_cost": declared_token_cost,
            "method_body_id": method.method_body_id,
            "method_body_version": method.version,
            "method_body_invocation_sha256": method.invocation_body_sha256,
            "declared_model_identity": declared_model_identity,
        }
    )


class OperatorRunLedger:
    """In-memory, host-private causal record of operator-local runs.

    Resuming the same ``run_id`` with an unchanged input fingerprint replays
    the cached receipt deterministically with no re-invocation. Resuming the
    same ``run_id`` with a CHANGED fingerprint is an ambiguous duplicate and
    is denied -- a run_id is not a license to silently overwrite a different
    attempt.
    """

    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}
        self._receipts: dict[str, OperatorRunReceipt] = {}

    def record_or_resume(
        self,
        run_id: str,
        fingerprint: str,
        build: Callable[[], OperatorRunReceipt],
    ) -> OperatorRunReceipt:
        existing = self._fingerprints.get(run_id)
        if existing is not None:
            if existing != fingerprint:
                raise ValueError("OPERATOR_RUN_ID_AMBIGUOUS_DUPLICATE")
            return self._receipts[run_id]
        receipt = build()
        self._fingerprints[run_id] = fingerprint
        self._receipts[run_id] = receipt
        return receipt

    def get(self, run_id: str) -> OperatorRunReceipt:
        receipt = self._receipts.get(run_id)
        if receipt is None:
            raise ValueError("OPERATOR_RUN_NOT_FOUND")
        return receipt


def invoke_operator_method_body(
    *,
    ledger: OperatorRunLedger,
    run_id: str,
    job_id: str,
    source: OperatorSourcePin,
    source_bytes: bytes,
    method: OperatorMethodBodyPin,
    method_body_invocation_bytes: bytes,
    method_callable: Callable[[OperatorInvocation], OperatorBodyResult] | None,
    requested_view: str,
    declared_model_identity: str = "UNKNOWN",
    declared_token_cost: int | Literal["UNKNOWN"] = "UNKNOWN",
    owner_excluded_source_ids: frozenset[str] = frozenset(),
) -> OperatorRunReceipt:
    """Run one real, owner-operated MethodBody invocation against one source.

    Every validation below fails closed with a distinct error code. Nothing
    here can produce a receipt that claims a method ran without this function
    actually calling ``method_callable``.
    """

    if method_callable is None:
        raise ValueError("OPERATOR_INVOCATION_REQUIRED")
    if not source.rights_basis.strip():
        raise ValueError("OPERATOR_SOURCE_RIGHTS_MISSING")
    if requested_view != source.authorized_view:
        raise ValueError("OPERATOR_SOURCE_RIGHTS_VIEW_MISMATCH")
    if (
        source.source_id in _OWNER_EXCLUDED_SOURCE_IDS
        or source.source_id in owner_excluded_source_ids
    ):
        raise ValueError("OPERATOR_SOURCE_EXCLUDED_BY_OWNER_POLICY")

    actual_source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if not source_bytes or actual_source_sha256 != source.sha256:
        raise ValueError("OPERATOR_SOURCE_BYTES_STALE")

    actual_method_sha256 = hashlib.sha256(method_body_invocation_bytes).hexdigest()
    if not method_body_invocation_bytes or actual_method_sha256 != method.invocation_body_sha256:
        raise ValueError("OPERATOR_METHOD_BODY_DRIFT")

    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("OPERATOR_SOURCE_NOT_UTF8") from None

    model_identity = declared_model_identity.strip() or "UNKNOWN"
    fingerprint = _input_fingerprint(
        run_id=run_id,
        job_id=job_id,
        source=source,
        method=method,
        declared_model_identity=model_identity,
        requested_view=requested_view,
        declared_token_cost=declared_token_cost,
    )

    def _execute() -> OperatorRunReceipt:
        invocation = OperatorInvocation(
            run_id=run_id,
            job_id=job_id,
            source_id=source.source_id,
            source_bytes=source_bytes,
            source_text=source_text,
            method_body_id=method.method_body_id,
            method_body_version=method.version,
            method_body_invocation_bytes=method_body_invocation_bytes,
        )
        buffer = StringIO()
        exit_status: Literal["OK", "EXCEPTION"] = "OK"
        exception_class: str | None = None
        result: OperatorBodyResult | None = None
        try:
            with redirect_stdout(buffer):
                result = method_callable(invocation)
        except Exception as exc:  # the operator's own code; must not crash the host
            exit_status = "EXCEPTION"
            exception_class = type(exc).__name__
        stdout_bytes = buffer.getvalue().encode("utf-8")
        invocation_receipt = OperatorInvocationReceipt(
            stdout_sha256=hashlib.sha256(stdout_bytes).hexdigest(),
            stdout_byte_length=len(stdout_bytes),
            exit_status=exit_status,
            exception_class=exception_class,
        )
        if exit_status != "OK" or result is None:
            raise ValueError("OPERATOR_METHOD_INVOCATION_FAILED")
        if not isinstance(result, OperatorBodyResult):
            raise ValueError("OPERATOR_METHOD_RESULT_INVALID")
        if result.epistemic_level is EpistemicLevel.E5:
            raise ValueError("OPERATOR_EPISTEMIC_PROMOTION_DENIED")

        for claim in result.claims:
            # Plain UTF-8 adapter cannot truthfully verify PDF/HTML page labels.
            if claim.page is not None:
                raise ValueError("OPERATOR_PAGE_MAP_REQUIRED")
            span = source_bytes[claim.byte_offset : claim.byte_offset + claim.byte_length]
            try:
                decoded_span = span.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("OPERATOR_CLAIM_SPAN_INVALID") from None
            if decoded_span != claim.evidence_excerpt:
                raise ValueError("OPERATOR_CLAIM_SPAN_INVALID")

        manifest = SourceAccessManifest(
            policy=RawAccessPolicy.FULL_REQUIRED,
            receipts=[
                SourceAccessReceipt(
                    carrier_id=source.source_id,
                    source_version=source.source_version,
                    read_kind="FULL",
                    status=SourceAccessStatus.VERIFIED,
                    content_sha256=actual_source_sha256,
                    byte_length=len(source_bytes),
                    returned_byte_length=len(source_bytes),
                    detail="BYTE_HASH_VERIFIED; RIGHTS_BASIS_OPERATOR_DECLARED_UNATTESTED",
                )
            ],
            all_declared_sources_verified=True,
        )

        payload = {
            "claims": [claim.model_dump(mode="python") for claim in result.claims],
            "notes": list(result.notes),
        }
        p_hash = payload_hash(payload)
        output_sediment = SedimentRecord(
            sediment_id=f"operator:{run_id}:{job_id}",
            object_type="operator.methodbody.reconstruction.v1",
            version=p_hash,
            research_object_id=result.research_object_id,
            payload=payload,
            payload_hash=p_hash,
            provenance=(
                "operator-local-methodbody",
                f"run={run_id}",
                f"job={job_id}",
                "SELF_OBSERVED_UNATTESTED",
            ),
            method_body_refs=(
                MethodBodyRef(method_body_id=method.method_body_id, version=method.version),
            ),
            source_carrier_refs=(source.source_id,),
            acceptance_state=AcceptanceState.PROPOSED,
            produced_by_thread=f"operator:{job_id}",
            produced_at_tick=0,
            produced_in_wave=1,
            produced_by_stone_kind=StoneEventKind.QUERY,
            source_access_manifest=manifest,
            epistemic_level=result.epistemic_level,
        )
        output_digest = hashlib.sha256(
            f"{p_hash}:{invocation_receipt.stdout_sha256}".encode("utf-8")
        ).hexdigest()
        return OperatorRunReceipt(
            run_id=run_id,
            job_id=job_id,
            source_id=source.source_id,
            source_version=source.source_version,
            source_sha256=actual_source_sha256,
            source_access_manifest=manifest,
            method_body_id=method.method_body_id,
            method_body_version=method.version,
            method_body_invocation_sha256=actual_method_sha256,
            declared_model_identity=model_identity,
            declared_token_cost=declared_token_cost,
            invocation=invocation_receipt,
            output_sediment=output_sediment,
            output_digest=output_digest,
        )

    return ledger.record_or_resume(run_id, fingerprint, _execute)


def replay_and_verify_operator_run(
    *,
    ledger: OperatorRunLedger,
    run_id: str,
    source_bytes: bytes,
    method_body_invocation_bytes: bytes,
) -> OperatorRunReceipt:
    """Private readback: prove freshly supplied bytes still match what ran.

    This never re-invokes the method body -- the ledger already proved one
    real invocation happened. It proves the bytes being read back now are,
    byte for byte, the ones that produced the stored receipt.
    """

    cached = ledger.get(run_id)
    if hashlib.sha256(source_bytes).hexdigest() != cached.source_sha256:
        raise ValueError("OPERATOR_REPLAY_SOURCE_MISMATCH")
    if (
        hashlib.sha256(method_body_invocation_bytes).hexdigest()
        != cached.method_body_invocation_sha256
    ):
        raise ValueError("OPERATOR_REPLAY_METHOD_MISMATCH")
    return cached


def export_rights_reviewed_prose(
    *,
    receipt: OperatorRunReceipt,
    reviewed_prose: str,
    reviewer_rights_statement: str,
    raw_method_body_invocation_bytes: bytes | None = None,
    raw_source_bytes: bytes | None = None,
) -> OperatorExportBundle:
    """The only sanctioned exit from the owner-private boundary (h).

    ``raw_method_body_invocation_bytes``/``raw_source_bytes`` are accepted
    only so this function can refuse to export if a caller's prose leaked
    the secret bytes verbatim; they are never themselves written out.
    """

    if raw_method_body_invocation_bytes is None or raw_source_bytes is None:
        raise ValueError("OPERATOR_EXPORT_REVIEW_BYTES_REQUIRED")
    if not reviewer_rights_statement.strip():
        raise ValueError("OPERATOR_EXPORT_RIGHTS_STATEMENT_MISSING")
    if not reviewed_prose.strip():
        raise ValueError("OPERATOR_EXPORT_PROSE_REQUIRED")
    for raw in (raw_method_body_invocation_bytes, raw_source_bytes):
        if not raw:
            continue
        try:
            raw_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if raw_text and raw_text in reviewed_prose:
            raise ValueError("OPERATOR_EXPORT_SECRET_LEAK_DENIED")
    return OperatorExportBundle(
        run_id=receipt.run_id,
        method_body_id=receipt.method_body_id,
        method_body_version=receipt.method_body_version,
        source_id=receipt.source_id,
        source_version=receipt.source_version,
        reviewer_rights_statement=reviewer_rights_statement,
        reviewed_prose=reviewed_prose,
        receipt_output_digest=receipt.output_digest,
    )


__all__ = [
    "OperatorBodyResult",
    "OperatorClaim",
    "OperatorExportBundle",
    "OperatorInvocation",
    "OperatorInvocationReceipt",
    "OperatorMethodBodyPin",
    "OperatorRunLedger",
    "OperatorRunReceipt",
    "OperatorSourcePin",
    "export_rights_reviewed_prose",
    "invoke_operator_method_body",
    "replay_and_verify_operator_run",
]
