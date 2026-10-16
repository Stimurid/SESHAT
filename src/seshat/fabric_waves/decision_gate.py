"""External human authority boundary; no embedded signing key or trusted actor string."""
from collections.abc import Callable
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import ACCEPTANCE_DECISION_RIGHT, EpistemicLevel
from seshat.fabric_waves.sediment import SedimentCollisionError, SedimentState

class TrustedDecisionAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_id: str = Field(min_length=1)
    subject_sediment_id: str = Field(min_length=1)
    subject_version: str = Field(min_length=1)
    choice: Literal["ACCEPT", "REJECT"]
    issuer: str = Field(min_length=1)
    decision_right: str = Field(min_length=1)
    nonce: str = Field(min_length=1)
    attestation_token: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)

DecisionVerifier = Callable[[TrustedDecisionAttestation], bool]

def verify_attestation(attestation: TrustedDecisionAttestation,
                       verifier: DecisionVerifier | None = None) -> None:
    """Host verifier authenticates the full envelope, issuer identity and right grant.

    Inject through authenticated host ingress. There is no self-authentication fallback.
    """
    try:
        valid = (attestation.decision_right == ACCEPTANCE_DECISION_RIGHT
                 and verifier is not None and verifier(attestation) is True)
    except Exception:
        valid = False
    if not valid:
        raise SedimentCollisionError("DECISION_UNAUTHENTICATED") from None

def accept_with_attestation(sediment: SedimentState, attestation: TrustedDecisionAttestation,
                            *, decided_at_tick: int,
                            verifier: DecisionVerifier | None = None) -> None:
    verify_attestation(attestation, verifier)
    replay_key = (attestation.issuer, attestation.nonce)
    if replay_key in sediment._decision_nonces:
        raise SedimentCollisionError("DECISION_REPLAY")
    record = next((r for r in sediment.all_records()
                   if r.sediment_id == attestation.subject_sediment_id), None)
    if (record is None or record.version != attestation.subject_version
            or record.acceptance_state not in (AcceptanceState.WORKING, AcceptanceState.PROPOSED)
            or (attestation.choice == "ACCEPT" and record.epistemic_level is EpistemicLevel.E5)):
        raise SedimentCollisionError("DECISION_SUBJECT_INELIGIBLE")
    if attestation.choice == "ACCEPT":
        sediment._accept_verified(record.sediment_id, decision_id=attestation.decision_id,
                        decided_at_tick=decided_at_tick)
    else:
        sediment.deposit(record.model_copy(update={"acceptance_state": AcceptanceState.REJECTED}))
    sediment._decision_nonces.add(replay_key)

def synthetic_test_attestation(decision_id: str, subject_sediment_id: str) -> TrustedDecisionAttestation:
    """Legacy negative-test fixture: never implicitly trusted."""
    return TrustedDecisionAttestation(decision_id=decision_id,
        subject_sediment_id=subject_sediment_id, subject_version="unverified",
        choice="ACCEPT", issuer="synthetic-untrusted", decision_right=ACCEPTANCE_DECISION_RIGHT,
        nonce=decision_id, attestation_token="UNTRUSTED", decided_by="synthetic-untrusted")
