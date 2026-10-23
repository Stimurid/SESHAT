"""Explicit in-process I11 R03 input for the serial F09A batch runner.

The bridge carries only already-admitted objects.  It neither reads sources nor
creates admissions, and its digests are replay keys rather than credentials or
scientific attestations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from seshat.corpus import _digest
from seshat.fabric_waves.i11_r03_report_adapter import (
    I11R03V2Projection,
    IndependentScienceReview,
    project_i11_r03_into_f08,
)
from seshat.fabric_waves.i11_two_real_r03 import VerifiedTwoRunAdmission, _GATE_ISSUER
from seshat.reports import ReportProjection

BRIDGE_VERSION = "seshat.f09a.i11-r03.v1"


class F09AI11R03BridgeError(ValueError):
    """An opt-in bridge binding is ambiguous or does not match its batch item."""


class F09AI11R03StaleBundle(F09AI11R03BridgeError):
    """A durable item was previously evaluated with a different bridge bundle."""


@dataclass(frozen=True)
class I11R03BatchBundle:
    """Owner-scoped, non-serializable binding for one R03 batch item.

    ``owner_authorized`` is an explicit local decision bit, not a credential.
    ``admission`` is useful only when it is the genuine in-process gate object.
    """

    item_id: str
    projection: I11R03V2Projection | dict
    admission: VerifiedTwoRunAdmission | None
    independent_review: IndependentScienceReview | dict | None
    owner_authorized: bool

    def __post_init__(self) -> None:
        if not self.item_id:
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_ITEM_ID_REQUIRED")
        try:
            projection = I11R03V2Projection.model_validate(self.projection)
            review = (
                IndependentScienceReview.model_validate(self.independent_review)
                if self.independent_review is not None else None
            )
        except ValueError as exc:
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_INVALID_BUNDLE") from exc
        if review is not None and review.projection_sha256 != projection.projection_sha256:
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_REVIEW_PROJECTION_MISMATCH")
        object.__setattr__(self, "projection", projection)
        object.__setattr__(self, "independent_review", review)

    @property
    def fingerprint(self) -> str:
        admission_digest = None
        gate_issued = False
        if isinstance(self.admission, VerifiedTwoRunAdmission):
            admission_digest = self.admission.admission_digest
            gate_issued = self.admission._issuer is _GATE_ISSUER
        review = self.independent_review
        return _digest({
            "domain": BRIDGE_VERSION,
            "item_id": self.item_id,
            "report_id": "R03",
            "projection_sha256": self.projection.projection_sha256,
            "admission_digest": admission_digest,
            "gate_issued": gate_issued,
            "review": review.model_dump(mode="json") if review is not None else None,
            "owner_authorized": self.owner_authorized,
        })

    def project(self, base_report: ReportProjection) -> ReportProjection:
        # An authorization denial can never be bypassed by a still-live gate object.
        admission = self.admission if self.owner_authorized else None
        return project_i11_r03_into_f08(
            base_report,
            self.projection,
            admission=admission,
            independent_review=self.independent_review,
        )


class F09AI11R03Provider(Protocol):
    """Read-only provider of a pre-bound optional bundle for one batch item."""

    def validate_bindings(self, items: tuple[tuple[str, str], ...]) -> None: ...

    def resolve(self, *, item_id: str, report_id: str) -> I11R03BatchBundle | None: ...


class InProcessI11R03Provider:
    """Bounded provider assembled by the trusted caller before ``run_batch``."""

    def __init__(self, bundles: tuple[I11R03BatchBundle, ...]) -> None:
        by_item: dict[str, I11R03BatchBundle] = {}
        projection_pins: set[str] = set()
        for bundle in bundles:
            if bundle.item_id in by_item:
                raise F09AI11R03BridgeError("I11_R03_BRIDGE_MULTIPLE_ITEM_COLLISION")
            pin = bundle.projection.projection_sha256
            if pin in projection_pins:
                raise F09AI11R03BridgeError("I11_R03_BRIDGE_CROSS_ITEM_COLLISION")
            by_item[bundle.item_id] = bundle
            projection_pins.add(pin)
        self._by_item = by_item

    def validate_bindings(self, items: tuple[tuple[str, str], ...]) -> None:
        report_by_item = dict(items)
        unknown = set(self._by_item) - set(report_by_item)
        if unknown:
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_CROSS_ITEM_BINDING")
        if any(report_by_item[item_id] != "R03" for item_id in self._by_item):
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_REPORT_MISMATCH")

    def resolve(self, *, item_id: str, report_id: str) -> I11R03BatchBundle | None:
        bundle = self._by_item.get(item_id)
        if bundle is None:
            return None
        if report_id != "R03":
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_REPORT_MISMATCH")
        if bundle.item_id != item_id:
            raise F09AI11R03BridgeError("I11_R03_BRIDGE_ITEM_MISMATCH")
        return bundle
