"""Bounded, domain-neutral reconciliation over SESHAT candidate views.

The controller schedules an explicitly supplied reciprocal operation pair.  It
compares provider-proposed constraints, records version-pinned attempts, and
stops with a typed outcome.  It does not interpret domain methods, choose a
semantic winner, or grant acceptance.

Receipts are in-memory only.  They contain references and hashes, never source
content or candidate payloads.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from seshat.adapters.base import SourceAccess
from seshat.contracts import (
    AcceptanceState,
    Aporia,
    DependencyEdge,
    DerivedObject,
    Observation,
    OperationSpec,
    RawAccessPolicy,
    ResearchObject,
    SourceAccessManifest,
    SourceAccessStatus,
)
from seshat.runtime import (
    EvidenceAccessError,
    ProviderResultError,
    Runtime,
    UnsupportedOperationError,
)


class RunOutcome(StrEnum):
    CONVERGED = "CONVERGED"
    APORIA = "APORIA"
    EXHAUSTED = "EXHAUSTED"
    BLOCKED = "BLOCKED"


class StopReason(StrEnum):
    CONSTRAINTS_COMPATIBLE = "CONSTRAINTS_COMPATIBLE"
    PERSISTENT_CONTRADICTION = "PERSISTENT_CONTRADICTION"
    MAX_ROUNDS = "MAX_ROUNDS"
    MAX_OPERATION_CALLS = "MAX_OPERATION_CALLS"
    UNCHANGED_CANDIDATE = "UNCHANGED_CANDIDATE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    SOURCE_ACCESS_BLOCKED = "SOURCE_ACCESS_BLOCKED"
    SOURCE_DRIFT = "SOURCE_DRIFT"
    CANDIDATE_DRIFT = "CANDIDATE_DRIFT"
    INVALID_PROPOSAL = "INVALID_PROPOSAL"
    ACCEPTANCE_LAUNDERING = "ACCEPTANCE_LAUNDERING"
    STRATEGY_STOPPED = "STRATEGY_STOPPED"


class ReconciliationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_rounds: int = Field(ge=1)
    max_operation_calls: int = Field(ge=1)
    aporia_after_rounds: int = Field(default=2, ge=1)


class CandidateRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    derived_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    acceptance_state: AcceptanceState | None = None


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    carrier_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ProposedConstraint(BaseModel):
    """A provider-declared constraint; the controller does not invent metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    value: Any
    incompatible_with: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class DeclaredMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mismatch_id: str = Field(min_length=1)
    against_operation_id: str = Field(min_length=1)
    constraint_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class ReconciliationProposal(BaseModel):
    """Typed, non-authoritative provider proposal for one operation attempt."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    input_source_refs: list[SourceRef]
    input_candidate_refs: list[CandidateRef]
    candidate: DerivedObject
    constraints: list[ProposedConstraint] = Field(default_factory=list)
    mismatches: list[DeclaredMismatch] = Field(default_factory=list)
    provenance: list[str] = Field(min_length=1)
    causal_links: list[str] = Field(default_factory=list)
    claims_convergence: bool = False


class ReconciliationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int = Field(ge=1)
    round_number: int = Field(ge=1)
    operation_id: str
    input_source_refs: list[SourceRef] = Field(default_factory=list)
    input_candidate_refs: list[CandidateRef] = Field(default_factory=list)
    output_proposal_ref: ProposalRef | None = None
    output_candidate_ref: CandidateRef | None = None
    constraints: list[ProposedConstraint] = Field(default_factory=list)
    mismatches: list[DeclaredMismatch] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    causal_links: list[str] = Field(default_factory=list)
    source_access_manifest: SourceAccessManifest | None = None
    provider_claims_convergence: bool = False
    duplicate_candidate: bool = False
    unchanged_candidate: bool = False
    error_code: str | None = None
    error_detail: str | None = None


class ReconciliationLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    research_object_id: str
    operation_ids: list[str]
    budget: ReconciliationBudget
    attempts: list[ReconciliationAttempt]
    operation_calls: int = Field(ge=0)
    rounds_completed: int = Field(ge=0)
    outcome: RunOutcome
    stop_reason: StopReason
    aporia: Aporia | None = None
    quarantined_candidate_refs: list[CandidateRef] = Field(default_factory=list)
    durable: bool = False
    persistence: str = "in-memory"


class ReconciliationProvider(Protocol):
    def supports(self, spec: OperationSpec) -> bool: ...

    def propose(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        observations: Iterable[Observation],
        prior_state: Iterable[DerivedObject],
        source_access: SourceAccess,
    ) -> ReconciliationProposal: ...


class NextOperationStrategy(Protocol):
    def choose_next(
        self,
        operation_ids: tuple[str, ...],
        attempts: tuple[ReconciliationAttempt, ...],
        operation_calls: int,
    ) -> str | None: ...


class AlternatingPairStrategy:
    """Deterministic host-neutral alternation; no method semantics are embedded."""

    def choose_next(
        self,
        operation_ids: tuple[str, ...],
        attempts: tuple[ReconciliationAttempt, ...],
        operation_calls: int,
    ) -> str:
        del attempts
        return operation_ids[operation_calls % len(operation_ids)]


class ReconciliationConfigurationError(ValueError):
    pass


class _ProposalViolation(ValueError):
    def __init__(
        self,
        reason: StopReason,
        detail: str,
        *,
        manifest: SourceAccessManifest | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.manifest = manifest


def _candidate_ref(obj: DerivedObject) -> CandidateRef:
    return CandidateRef(
        derived_id=obj.derived_id,
        version=obj.version,
        acceptance_state=obj.acceptance_state,
    )


def _candidate_snapshot(objects: Iterable[DerivedObject]) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (obj.derived_id, obj.version, obj.acceptance_state.value)
            for obj in objects
        )
    )


def _source_refs(manifest: SourceAccessManifest) -> tuple[SourceRef, ...]:
    refs: dict[str, SourceRef] = {}
    for receipt in manifest.receipts:
        if (
            receipt.status is SourceAccessStatus.VERIFIED
            and receipt.source_version is not None
            and receipt.content_sha256 is not None
        ):
            refs[receipt.carrier_id] = SourceRef(
                carrier_id=receipt.carrier_id,
                source_version=receipt.source_version,
                content_sha256=receipt.content_sha256,
            )
    return tuple(sorted(refs.values(), key=lambda ref: ref.carrier_id))


def _semantic_fingerprint(proposal: ReconciliationProposal) -> str:
    material = {
        "payload": proposal.candidate.payload,
        "constraints": [item.model_dump(mode="json") for item in proposal.constraints],
        "mismatches": [item.model_dump(mode="json") for item in proposal.mismatches],
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: {"type": type(value).__qualname__},
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _OperationAdapter:
    """Validate a typed proposal before Runtime is allowed to persist it."""

    def __init__(
        self,
        controller: ReconciliationController,
        spec: OperationSpec,
        provider: ReconciliationProvider,
    ) -> None:
        self.controller = controller
        self.spec = spec
        self.provider = provider
        self.proposal: ReconciliationProposal | None = None
        self.manifest: SourceAccessManifest | None = None

    def supports(self, spec: OperationSpec) -> bool:
        return spec.operation_id == self.spec.operation_id and self.provider.supports(spec)

    def execute(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        observations: Iterable[Observation],
        prior_state: Iterable[DerivedObject],
        source_access: SourceAccess,
    ) -> DerivedObject:
        prior = tuple(prior_state)
        before = _candidate_snapshot(prior)
        self.manifest = source_access.manifest()
        proposal = self.provider.propose(
            spec,
            research_object,
            tuple(observations),
            prior,
            source_access,
        )
        self.manifest = source_access.manifest()
        if not isinstance(proposal, ReconciliationProposal):
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "provider did not return a ReconciliationProposal",
                manifest=self.manifest,
            )

        current = self.controller.runtime.blackboard.candidate_state(research_object.object_id)
        if _candidate_snapshot(current) != before:
            raise _ProposalViolation(
                StopReason.CANDIDATE_DRIFT,
                "candidate state changed during an operation attempt",
                manifest=self.manifest,
            )

        actual_sources = _source_refs(self.manifest)
        proposed_sources = tuple(
            sorted(proposal.input_source_refs, key=lambda ref: ref.carrier_id)
        )
        if spec.raw_access_policy is RawAccessPolicy.FULL_REQUIRED and not actual_sources:
            raise _ProposalViolation(
                StopReason.SOURCE_ACCESS_BLOCKED,
                "FULL_REQUIRED proposal has no verified source references",
                manifest=self.manifest,
            )
        if proposed_sources != actual_sources:
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "proposal source references do not match verified access receipts",
                manifest=self.manifest,
            )
        self.controller._pin_sources(research_object.version, actual_sources, self.manifest)

        if proposal.operation_id != spec.operation_id:
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "proposal operation does not match the scheduled operation",
                manifest=self.manifest,
            )
        candidate = proposal.candidate
        if candidate.acceptance_state not in {
            AcceptanceState.WORKING,
            AcceptanceState.PROPOSED,
        }:
            raise _ProposalViolation(
                StopReason.ACCEPTANCE_LAUNDERING,
                "executor proposals may only be WORKING or PROPOSED",
                manifest=self.manifest,
            )
        if (
            candidate.operation_id != spec.operation_id
            or candidate.research_object_id != research_object.object_id
            or candidate.object_type != spec.output_type
        ):
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "candidate identity does not match the scheduled operation",
                manifest=self.manifest,
            )
        if candidate.derived_id.startswith("seshat:"):
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "candidate uses the controller-reserved seshat: ID namespace",
                manifest=self.manifest,
            )
        if not proposal.provenance or not candidate.provenance:
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "proposal and candidate provenance are required",
                manifest=self.manifest,
            )

        available = {(obj.derived_id, obj.version): obj for obj in prior}
        requested = {(ref.derived_id, ref.version) for ref in proposal.input_candidate_refs}
        if len(requested) != len(proposal.input_candidate_refs):
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "duplicate candidate references are not permitted",
                manifest=self.manifest,
            )
        if not requested.issubset(available):
            raise _ProposalViolation(
                StopReason.CANDIDATE_DRIFT,
                "proposal references a stale, rejected, missing, or version-drifted candidate",
                manifest=self.manifest,
            )
        if any(
            ref.acceptance_state is not None
            and ref.acceptance_state
            is not available[(ref.derived_id, ref.version)].acceptance_state
            for ref in proposal.input_candidate_refs
        ):
            raise _ProposalViolation(
                StopReason.CANDIDATE_DRIFT,
                "proposal candidate status pin no longer matches active state",
                manifest=self.manifest,
            )
        if not {ref.derived_id for ref in proposal.input_candidate_refs}.issubset(
            candidate.parent_derived_ids
        ):
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "candidate lineage omits a declared input candidate",
                manifest=self.manifest,
            )
        if proposal.input_candidate_refs and not proposal.causal_links:
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "candidate-based revision requires explicit causal links",
                manifest=self.manifest,
            )

        proposal_ref = (proposal.proposal_id, proposal.version)
        if proposal_ref in self.controller._seen_proposal_refs:
            raise _ProposalViolation(
                StopReason.INVALID_PROPOSAL,
                "proposal ID/version was already used in this run",
                manifest=self.manifest,
            )

        normalized_inputs = [
            _candidate_ref(available[(ref.derived_id, ref.version)])
            for ref in proposal.input_candidate_refs
        ]
        self.proposal = proposal.model_copy(
            update={
                "input_source_refs": list(actual_sources),
                "input_candidate_refs": normalized_inputs,
            },
            deep=True,
        )
        self.controller._seen_proposal_refs.add(proposal_ref)
        return candidate.model_copy(deep=True)


class ReconciliationController:
    """Run one explicit reciprocal relation under finite, inspectable gates."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        operations: tuple[OperationSpec, OperationSpec],
        providers: Mapping[str, ReconciliationProvider],
        budget: ReconciliationBudget,
        strategy: NextOperationStrategy | None = None,
    ) -> None:
        if len(operations) != 2 or operations[0].operation_id == operations[1].operation_id:
            raise ReconciliationConfigurationError(
                "reconciliation requires exactly two distinct operations"
            )
        left, right = operations
        if (
            right.operation_id not in left.dependency_ids
            or left.operation_id not in right.dependency_ids
        ):
            raise ReconciliationConfigurationError(
                "the bounded pair must declare reciprocal operation dependencies"
            )
        self.runtime = runtime
        self.operations = operations
        self.providers = dict(providers)
        self.budget = budget
        self.strategy = strategy or AlternatingPairStrategy()
        self._pinned_research_version: str | None = None
        self._pinned_sources: tuple[SourceRef, ...] | None = None
        self._seen_proposal_refs: set[tuple[str, str]] = set()
        self._run_output_ids: list[str] = []
        self._quarantined_candidate_refs: list[CandidateRef] = []

    def _pin_sources(
        self,
        research_version: str,
        refs: tuple[SourceRef, ...],
        manifest: SourceAccessManifest,
    ) -> None:
        if self._pinned_sources is None:
            self._pinned_research_version = research_version
            self._pinned_sources = refs
            return
        if self._pinned_research_version != research_version or self._pinned_sources != refs:
            raise _ProposalViolation(
                StopReason.SOURCE_DRIFT,
                "source or research-object version changed during reconciliation",
                manifest=manifest,
            )

    @staticmethod
    def _has_contradiction(proposals: Mapping[str, ReconciliationProposal]) -> bool:
        constraints = {
            item.constraint_id: item
            for proposal in proposals.values()
            for item in proposal.constraints
        }
        incompatible = any(
            other_id in constraints
            for constraint in constraints.values()
            for other_id in constraint.incompatible_with
        )
        mismatch_operations = {
            proposal.operation_id
            for proposal in proposals.values()
            if proposal.mismatches
        }
        return incompatible or len(mismatch_operations) == len(proposals)

    @staticmethod
    def _has_converged(proposals: Mapping[str, ReconciliationProposal]) -> bool:
        return bool(proposals) and all(
            proposal.constraints and not proposal.mismatches
            for proposal in proposals.values()
        ) and not ReconciliationController._has_contradiction(proposals)

    @staticmethod
    def _aporia(
        run_id: str,
        research_object_id: str,
        proposals: Mapping[str, ReconciliationProposal],
        attempts: Iterable[ReconciliationAttempt],
    ) -> Aporia:
        evidence_ids = [
            attempt.output_proposal_ref.proposal_id
            for attempt in attempts
            if attempt.output_proposal_ref is not None
        ]
        for proposal in proposals.values():
            evidence_ids.extend(item.constraint_id for item in proposal.constraints)
            evidence_ids.extend(item.mismatch_id for item in proposal.mismatches)
        return Aporia(
            aporia_id=f"{run_id}:aporia",
            subject_id=research_object_id,
            kind="PERSISTENT_RECONCILIATION_CONTRADICTION",
            evidence_ids=evidence_ids,
            description="Provider-declared constraints remain incompatible after bounded revision.",
            blocks_operation_ids=list(proposals),
            resolved=False,
        )

    def _ledger(
        self,
        *,
        run_id: str,
        research_object_id: str,
        attempts: list[ReconciliationAttempt],
        operation_calls: int,
        rounds_completed: int,
        outcome: RunOutcome,
        stop_reason: StopReason,
        aporia: Aporia | None = None,
    ) -> ReconciliationLedger:
        return ReconciliationLedger(
            run_id=run_id,
            research_object_id=research_object_id,
            operation_ids=[item.operation_id for item in self.operations],
            budget=self.budget,
            attempts=attempts,
            operation_calls=operation_calls,
            rounds_completed=rounds_completed,
            outcome=outcome,
            stop_reason=stop_reason,
            aporia=aporia,
            quarantined_candidate_refs=self._quarantined_candidate_refs,
        )

    def _quarantine_run_outputs(
        self,
        *,
        run_id: str,
        research_object_id: str,
        reason: StopReason,
    ) -> None:
        active = {
            item.derived_id: item
            for item in self.runtime.blackboard.candidate_state(research_object_id)
            if item.derived_id in self._run_output_ids
        }
        if not active:
            return
        material = "|".join(sorted(active)) + f"|{reason.value}"
        suffix = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        marker = DerivedObject(
            derived_id=f"seshat:reconciliation:{run_id}:quarantine:{suffix}",
            object_type="seshat.reconciliation_quarantine",
            version="1",
            operation_id="seshat.reconciliation.guard",
            research_object_id=research_object_id,
            payload={"reason": reason.value, "candidate_ids": sorted(active)},
            provenance=["seshat:reconciliation-controller"],
            acceptance_state=AcceptanceState.STALE,
        )
        self.runtime.blackboard.put(marker)
        for derived_id in active:
            self.runtime.blackboard.add_dependency(
                DependencyEdge(
                    upstream_id=marker.derived_id,
                    downstream_id=derived_id,
                    dependency_type="reconciliation_blocked_source_or_state_drift",
                )
            )
        self.runtime.blackboard.invalidate_descendants(marker.derived_id)
        self._quarantined_candidate_refs = [
            _candidate_ref(self.runtime.blackboard.get(derived_id))
            for derived_id in sorted(active)
        ]

    def _blocked_attempt(
        self,
        attempts: list[ReconciliationAttempt],
        *,
        round_number: int,
        operation_id: str,
        reason: StopReason,
        detail: str,
        manifest: SourceAccessManifest | None = None,
    ) -> None:
        attempts.append(
            ReconciliationAttempt(
                attempt_number=len(attempts) + 1,
                round_number=round_number,
                operation_id=operation_id,
                input_source_refs=(
                    list(_source_refs(manifest)) if manifest is not None else []
                ),
                input_candidate_refs=[
                    _candidate_ref(item)
                    for item in self.runtime.blackboard.candidate_state(
                        self._active_research_object_id
                    )
                ],
                source_access_manifest=manifest,
                error_code=reason.value,
                error_detail=detail,
            )
        )

    def run(self, *, run_id: str, research_object_id: str) -> ReconciliationLedger:
        self._pinned_research_version = None
        self._pinned_sources = None
        self._seen_proposal_refs = set()
        self._run_output_ids = []
        self._quarantined_candidate_refs = []
        self._active_research_object_id = research_object_id
        operation_ids = tuple(item.operation_id for item in self.operations)
        specs = {item.operation_id: item for item in self.operations}
        attempts: list[ReconciliationAttempt] = []
        latest: dict[str, ReconciliationProposal] = {}
        seen_fingerprints: dict[str, set[str]] = {item: set() for item in operation_ids}
        last_fingerprint: dict[str, str] = {}
        pending_duplicate: StopReason | None = None
        operation_calls = 0
        rounds_completed = 0
        expected_candidates = _candidate_snapshot(
            self.runtime.blackboard.candidate_state(research_object_id)
        )

        missing = [item for item in operation_ids if item not in self.providers]
        if missing:
            self._blocked_attempt(
                attempts,
                round_number=1,
                operation_id=missing[0],
                reason=StopReason.MISSING_CAPABILITY,
                detail="required reconciliation provider is unavailable",
            )
            return self._ledger(
                run_id=run_id,
                research_object_id=research_object_id,
                attempts=attempts,
                operation_calls=0,
                rounds_completed=0,
                outcome=RunOutcome.BLOCKED,
                stop_reason=StopReason.MISSING_CAPABILITY,
            )

        while True:
            if operation_calls >= self.budget.max_operation_calls:
                reason = (
                    StopReason.MAX_ROUNDS
                    if rounds_completed >= self.budget.max_rounds
                    else StopReason.MAX_OPERATION_CALLS
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.EXHAUSTED,
                    stop_reason=reason,
                )
            round_number = operation_calls // len(operation_ids) + 1
            if round_number > self.budget.max_rounds:
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.EXHAUSTED,
                    stop_reason=StopReason.MAX_ROUNDS,
                )

            operation_id = self.strategy.choose_next(
                operation_ids, tuple(attempts), operation_calls
            )
            if operation_id not in specs:
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id or "<none>",
                    reason=StopReason.STRATEGY_STOPPED,
                    detail="strategy did not select an operation in the bounded pair",
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=StopReason.STRATEGY_STOPPED,
                )

            current_candidates = _candidate_snapshot(
                self.runtime.blackboard.candidate_state(research_object_id)
            )
            if current_candidates != expected_candidates:
                reason = StopReason.CANDIDATE_DRIFT
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=reason,
                    detail="candidate state changed between reconciliation attempts",
                )
                self._quarantine_run_outputs(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    reason=reason,
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=reason,
                )

            spec = specs[operation_id]
            adapter = _OperationAdapter(self, spec, self.providers[operation_id])
            operation_calls += 1
            try:
                result = self.runtime.run(
                    spec,
                    adapter,
                    research_object_id=research_object_id,
                )
                proposal = adapter.proposal
                if proposal is None:
                    raise _ProposalViolation(
                        StopReason.INVALID_PROPOSAL,
                        "provider returned no validated proposal",
                        manifest=adapter.manifest,
                    )
            except _ProposalViolation as exc:
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=exc.reason,
                    detail=exc.detail,
                    manifest=exc.manifest,
                )
                if exc.reason in {
                    StopReason.SOURCE_DRIFT,
                    StopReason.CANDIDATE_DRIFT,
                    StopReason.SOURCE_ACCESS_BLOCKED,
                }:
                    self._quarantine_run_outputs(
                        run_id=run_id,
                        research_object_id=research_object_id,
                        reason=exc.reason,
                    )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=exc.reason,
                )
            except EvidenceAccessError as exc:
                reason = (
                    StopReason.SOURCE_DRIFT
                    if exc.code.value == "SOURCE_DRIFT"
                    else StopReason.SOURCE_ACCESS_BLOCKED
                )
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=reason,
                    detail=f"source access failed: {exc.code.value}",
                    manifest=exc.manifest,
                )
                self._quarantine_run_outputs(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    reason=reason,
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=reason,
                )
            except ProviderResultError:
                reason = StopReason.ACCEPTANCE_LAUNDERING
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=reason,
                    detail="runtime rejected a provider-origin state transition",
                    manifest=adapter.manifest,
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=reason,
                )
            except UnsupportedOperationError:
                reason = StopReason.MISSING_CAPABILITY
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=reason,
                    detail="provider does not support the scheduled operation",
                    manifest=adapter.manifest,
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=reason,
                )
            except Exception as exc:  # provider failures become typed, sanitized receipts
                reason = StopReason.PROVIDER_ERROR
                self._blocked_attempt(
                    attempts,
                    round_number=round_number,
                    operation_id=operation_id,
                    reason=reason,
                    detail=f"provider failed with {type(exc).__name__}",
                    manifest=adapter.manifest,
                )
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.BLOCKED,
                    stop_reason=reason,
                )

            fingerprint = _semantic_fingerprint(proposal)
            unchanged = last_fingerprint.get(operation_id) == fingerprint
            duplicate = fingerprint in seen_fingerprints[operation_id]
            if unchanged:
                pending_duplicate = StopReason.UNCHANGED_CANDIDATE
            elif duplicate and pending_duplicate is None:
                pending_duplicate = StopReason.DUPLICATE_CANDIDATE
            seen_fingerprints[operation_id].add(fingerprint)
            last_fingerprint[operation_id] = fingerprint
            latest[operation_id] = proposal
            manifest = result.source_access_manifest
            attempts.append(
                ReconciliationAttempt(
                    attempt_number=len(attempts) + 1,
                    round_number=round_number,
                    operation_id=operation_id,
                    input_source_refs=proposal.input_source_refs,
                    input_candidate_refs=proposal.input_candidate_refs,
                    output_proposal_ref=ProposalRef(
                        proposal_id=proposal.proposal_id,
                        version=proposal.version,
                    ),
                    output_candidate_ref=_candidate_ref(result),
                    constraints=proposal.constraints,
                    mismatches=proposal.mismatches,
                    provenance=proposal.provenance,
                    causal_links=proposal.causal_links,
                    source_access_manifest=manifest,
                    provider_claims_convergence=proposal.claims_convergence,
                    duplicate_candidate=duplicate,
                    unchanged_candidate=unchanged,
                )
            )
            self._run_output_ids.append(result.derived_id)
            expected_candidates = _candidate_snapshot(
                self.runtime.blackboard.candidate_state(research_object_id)
            )

            if operation_calls % len(operation_ids) != 0:
                continue
            rounds_completed = round_number
            if set(latest) == set(operation_ids) and self._has_converged(latest):
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.CONVERGED,
                    stop_reason=StopReason.CONSTRAINTS_COMPATIBLE,
                )
            if (
                rounds_completed >= self.budget.aporia_after_rounds
                and set(latest) == set(operation_ids)
                and self._has_contradiction(latest)
            ):
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.APORIA,
                    stop_reason=StopReason.PERSISTENT_CONTRADICTION,
                    aporia=self._aporia(run_id, research_object_id, latest, attempts),
                )
            if pending_duplicate is not None:
                return self._ledger(
                    run_id=run_id,
                    research_object_id=research_object_id,
                    attempts=attempts,
                    operation_calls=operation_calls,
                    rounds_completed=rounds_completed,
                    outcome=RunOutcome.EXHAUSTED,
                    stop_reason=pending_duplicate,
                )
