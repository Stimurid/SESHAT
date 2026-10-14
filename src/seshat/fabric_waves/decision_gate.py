"""Human decision-right attestation for fabric acceptance."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import ACCEPTANCE_DECISION_RIGHT
from seshat.fabric_waves.sediment import SedimentCollisionError, SedimentState

# Explicit test-only attestation secret; production hosts must inject a real trust root.
SYNTHETIC_TEST_ATTESTATION_SECRET: str = "seshat-fabric-test-attestation-v1"


class TrustedDecisionAttestation(BaseModel):
    """Proves an external authority issued the acceptance decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)
    subject_sediment_id: str = Field(min_length=1)
    attestation_token: str = Field(min_length=1)
    decided_by: str = Field(default=ACCEPTANCE_DECISION_RIGHT, min_length=1)


def _expected_token(decision_id: str, subject_sediment_id: str) -> str:
    material = f"{SYNTHETIC_TEST_ATTESTATION_SECRET}|{decision_id}|{subject_sediment_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def synthetic_test_attestation(
    decision_id: str, subject_sediment_id: str
) -> TrustedDecisionAttestation:
    return TrustedDecisionAttestation(
        decision_id=decision_id,
        subject_sediment_id=subject_sediment_id,
        attestation_token=_expected_token(decision_id, subject_sediment_id),
    )


def verify_attestation(attestation: TrustedDecisionAttestation) -> None:
    expected = _expected_token(attestation.decision_id, attestation.subject_sediment_id)
    if attestation.attestation_token != expected:
        raise SedimentCollisionError(
            "decision attestation token is invalid or untrusted"
        )


def accept_with_attestation(
    sediment: SedimentState,
    attestation: TrustedDecisionAttestation,
    *,
    decided_at_tick: int,
) -> None:
    verify_attestation(attestation)
    record = sediment.views["working"].get(attestation.subject_sediment_id)
    if record is None:
        record = sediment.views["candidate"].get(attestation.subject_sediment_id)
    if record is None:
        record = sediment.views["stale"].get(attestation.subject_sediment_id)
    if record is not None and record.acceptance_state is AcceptanceState.STALE:
        raise SedimentCollisionError(
            "cannot accept a STALE sediment without fresh reconciliation"
        )
    sediment.accept(
        attestation.subject_sediment_id,
        decision_id=attestation.decision_id,
        decided_at_tick=decided_at_tick,
    )
