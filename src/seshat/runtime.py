"""Minimal SESHAT execution runtime.

The runtime is deliberately small.  It enforces operation contracts and leaves
domain reasoning to OperationProvider implementations.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import ClassVar

from seshat.adapters.base import OperationProvider, SourceContentProvider, SourceProvider
from seshat.blackboard import Blackboard
from seshat.contracts import (
    DependencyEdge,
    DerivedObject,
    Observation,
    OperationSpec,
    RawAccessPolicy,
    ResearchObject,
    SourceAccessErrorCode,
    SourceAccessManifest,
    SourceAccessReceipt,
    SourceAccessStatus,
    SourceAddress,
    SourceCarrier,
    SourceContent,
)


class EvidenceAccessError(RuntimeError):
    def __init__(
        self,
        code: SourceAccessErrorCode,
        message: str,
        manifest: SourceAccessManifest,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.manifest = manifest


class UnsupportedOperationError(RuntimeError):
    pass


class RuntimeSourceAccess:
    """Policy-scoped, receipt-producing access to validated source bytes."""

    _TEXT_MEDIA_TYPES: ClassVar[set[str]] = {
        "text/plain",
        "text/markdown",
        "application/json",
    }
    _SUPPORTED_MEDIA_TYPES: ClassVar[set[str]] = _TEXT_MEDIA_TYPES | {
        "application/octet-stream"
    }

    def __init__(
        self,
        policy: RawAccessPolicy,
        carriers: Iterable[SourceCarrier],
        content_provider: SourceContentProvider | None,
    ) -> None:
        self.policy = policy
        self._carriers = {carrier.carrier_id: carrier for carrier in carriers}
        self._content_provider = content_provider
        self._receipts: list[SourceAccessReceipt] = []
        self._validated: dict[str, SourceContent] = {}
        self._all_declared_sources_verified = False

    def manifest(self) -> SourceAccessManifest:
        return SourceAccessManifest(
            policy=self.policy,
            receipts=list(self._receipts),
            all_declared_sources_verified=self._all_declared_sources_verified,
        )

    def _fail(
        self,
        code: SourceAccessErrorCode,
        message: str,
        *,
        carrier_id: str,
        read_kind: str,
        address: SourceAddress | None = None,
    ) -> None:
        carrier = self._carriers.get(carrier_id)
        self._receipts.append(
            SourceAccessReceipt(
                carrier_id=carrier_id,
                source_version=carrier.version if carrier else None,
                read_kind=read_kind,
                status=(
                    SourceAccessStatus.DENIED
                    if code is SourceAccessErrorCode.POLICY_DENIED
                    else SourceAccessStatus.FAILED
                ),
                address=address,
                error_code=code,
                detail=message,
            )
        )
        raise EvidenceAccessError(code, message, self.manifest())

    def _validated_content(self, carrier_id: str, read_kind: str) -> SourceContent:
        if carrier_id in self._validated:
            return self._validated[carrier_id]

        carrier = self._carriers.get(carrier_id)
        if carrier is None:
            self._fail(
                SourceAccessErrorCode.MISSING_CARRIER,
                f"carrier {carrier_id!r} is not declared for this ResearchObject",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if self._content_provider is None:
            self._fail(
                SourceAccessErrorCode.CONTENT_UNAVAILABLE,
                f"content provider is unavailable for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )

        try:
            content = self._content_provider.open_content(carrier_id)
        except KeyError:
            self._fail(
                SourceAccessErrorCode.CONTENT_UNAVAILABLE,
                f"content is unavailable for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        except PermissionError as exc:
            self._fail(
                SourceAccessErrorCode.UNAUTHORIZED,
                f"content is unauthorized for carrier {carrier_id!r}: {exc}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        except NotImplementedError as exc:
            self._fail(
                SourceAccessErrorCode.UNSUPPORTED_MEDIA,
                f"content reader is unsupported for carrier {carrier_id!r}: {exc}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._fail(
                SourceAccessErrorCode.READ_ERROR,
                f"content read failed for carrier {carrier_id!r}: {exc}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )

        if content.carrier_id != carrier.carrier_id or content.source_version != carrier.version:
            self._fail(
                SourceAccessErrorCode.SOURCE_DRIFT,
                f"content identity/version does not match carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if not content.authorized:
            self._fail(
                SourceAccessErrorCode.UNAUTHORIZED,
                f"content is unauthorized for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if not content.complete:
            self._fail(
                SourceAccessErrorCode.PARTIAL_SOURCE,
                f"content is partial for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if content.media_type not in self._SUPPORTED_MEDIA_TYPES:
            self._fail(
                SourceAccessErrorCode.UNSUPPORTED_MEDIA,
                f"unsupported media type {content.media_type!r} for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if carrier.media_type is not None and content.media_type != carrier.media_type:
            self._fail(
                SourceAccessErrorCode.SOURCE_DRIFT,
                f"content media type does not match carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )

        actual_length = len(content.content)
        actual_sha256 = hashlib.sha256(content.content).hexdigest()
        expected_length = carrier.byte_length
        expected_sha256 = carrier.content_sha256
        if expected_length is None or expected_sha256 is None:
            self._fail(
                SourceAccessErrorCode.INTEGRITY_ERROR,
                f"carrier {carrier_id!r} lacks expected length or SHA-256",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )
        if (
            content.byte_length != actual_length
            or content.content_sha256 != actual_sha256
            or expected_length != actual_length
            or expected_sha256 != actual_sha256
        ):
            self._fail(
                SourceAccessErrorCode.INTEGRITY_ERROR,
                f"length or SHA-256 mismatch for carrier {carrier_id!r}",
                carrier_id=carrier_id,
                read_kind=read_kind,
            )

        self._validated[carrier_id] = content
        return content

    def verify_all(self, carrier_ids: Iterable[str]) -> None:
        for carrier_id in carrier_ids:
            self.read_all(carrier_id)
        self._all_declared_sources_verified = True

    def reject_missing_carriers(self, operation_id: str, carrier_ids: Iterable[str]) -> None:
        missing = sorted(carrier_ids)
        for carrier_id in missing:
            self._receipts.append(
                SourceAccessReceipt(
                    carrier_id=carrier_id,
                    read_kind="FULL",
                    status=SourceAccessStatus.FAILED,
                    error_code=SourceAccessErrorCode.MISSING_CARRIER,
                    detail="declared carrier metadata is missing",
                )
            )
        raise EvidenceAccessError(
            SourceAccessErrorCode.MISSING_CARRIER,
            f"{operation_id} requires full source; missing carriers: {missing}",
            self.manifest(),
        )

    def read_all(self, carrier_id: str) -> bytes:
        if self.policy is not RawAccessPolicy.FULL_REQUIRED:
            self._fail(
                SourceAccessErrorCode.POLICY_DENIED,
                f"whole-source read is denied by {self.policy.value}",
                carrier_id=carrier_id,
                read_kind="FULL",
            )
        content = self._validated_content(carrier_id, "FULL")
        self._receipts.append(
            SourceAccessReceipt(
                carrier_id=carrier_id,
                source_version=content.source_version,
                read_kind="FULL",
                status=SourceAccessStatus.VERIFIED,
                content_sha256=content.content_sha256,
                byte_length=content.byte_length,
                returned_byte_length=content.byte_length,
            )
        )
        return content.content

    def read(self, address: SourceAddress) -> bytes:
        if self.policy is RawAccessPolicy.NEVER:
            self._fail(
                SourceAccessErrorCode.POLICY_DENIED,
                "raw source access is denied by NEVER",
                carrier_id=address.carrier_id,
                read_kind="RANGE",
                address=address,
            )
        carrier = self._carriers.get(address.carrier_id)
        if carrier is None:
            self._fail(
                SourceAccessErrorCode.INVALID_ADDRESS,
                f"address references undeclared carrier {address.carrier_id!r}",
                carrier_id=address.carrier_id,
                read_kind="RANGE",
                address=address,
            )
        if address.source_version is None or address.source_version != carrier.version:
            self._fail(
                SourceAccessErrorCode.SOURCE_DRIFT,
                f"address version does not match carrier {address.carrier_id!r}",
                carrier_id=address.carrier_id,
                read_kind="RANGE",
                address=address,
            )
        if not isinstance(address.start, int) or not isinstance(address.end, int):
            self._fail(
                SourceAccessErrorCode.INVALID_ADDRESS,
                "bounded reads require integer start and end",
                carrier_id=address.carrier_id,
                read_kind="RANGE",
                address=address,
            )

        content = self._validated_content(address.carrier_id, "RANGE")
        start, end = address.start, address.end
        if address.address_type == "byte_range":
            source_length = len(content.content)
            if start < 0 or end < start or end > source_length:
                self._fail(
                    SourceAccessErrorCode.INVALID_ADDRESS,
                    f"byte range [{start}, {end}) is outside [0, {source_length})",
                    carrier_id=address.carrier_id,
                    read_kind="RANGE",
                    address=address,
                )
            selected = content.content[start:end]
        elif address.address_type == "char_range":
            if content.media_type not in self._TEXT_MEDIA_TYPES:
                self._fail(
                    SourceAccessErrorCode.UNSUPPORTED_MEDIA,
                    f"char_range is unsupported for {content.media_type!r}",
                    carrier_id=address.carrier_id,
                    read_kind="RANGE",
                    address=address,
                )
            try:
                text = content.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                self._fail(
                    SourceAccessErrorCode.READ_ERROR,
                    f"UTF-8 decode failed for carrier {address.carrier_id!r}: {exc}",
                    carrier_id=address.carrier_id,
                    read_kind="RANGE",
                    address=address,
                )
            if start < 0 or end < start or end > len(text):
                self._fail(
                    SourceAccessErrorCode.INVALID_ADDRESS,
                    f"character range [{start}, {end}) is outside [0, {len(text)})",
                    carrier_id=address.carrier_id,
                    read_kind="RANGE",
                    address=address,
                )
            selected = text[start:end].encode("utf-8")
        else:
            self._fail(
                SourceAccessErrorCode.INVALID_ADDRESS,
                f"unsupported address type {address.address_type!r}",
                carrier_id=address.carrier_id,
                read_kind="RANGE",
                address=address,
            )

        self._receipts.append(
            SourceAccessReceipt(
                carrier_id=address.carrier_id,
                source_version=content.source_version,
                read_kind="RANGE",
                status=SourceAccessStatus.VERIFIED,
                address=address,
                content_sha256=content.content_sha256,
                byte_length=content.byte_length,
                returned_byte_length=len(selected),
            )
        )
        return selected


class Runtime:
    def __init__(
        self,
        source_provider: SourceProvider,
        blackboard: Blackboard | None = None,
        source_content_provider: SourceContentProvider | None = None,
    ):
        self.source_provider = source_provider
        self.source_content_provider = source_content_provider or (
            source_provider if hasattr(source_provider, "open_content") else None
        )
        self.blackboard = blackboard or Blackboard()

    def _carriers_for(self, research_object: ResearchObject) -> tuple[SourceCarrier, ...]:
        return tuple(self.source_provider.get_carriers(research_object.object_id))

    def _observations_for(self, research_object: ResearchObject) -> tuple[Observation, ...]:
        return tuple(self.source_provider.get_observations(research_object.object_id))

    def _enforce_access(
        self,
        spec: OperationSpec,
        research_object: ResearchObject,
        carriers: tuple[SourceCarrier, ...],
        source_access: RuntimeSourceAccess,
    ) -> None:
        if spec.raw_access_policy is RawAccessPolicy.FULL_REQUIRED:
            if not research_object.carrier_ids:
                raise EvidenceAccessError(
                    SourceAccessErrorCode.MISSING_CARRIER,
                    f"{spec.operation_id} requires full source but ResearchObject has no carriers",
                    source_access.manifest(),
                )
            present = {carrier.carrier_id for carrier in carriers}
            missing = set(research_object.carrier_ids) - present
            if missing:
                source_access.reject_missing_carriers(spec.operation_id, missing)
            source_access.verify_all(research_object.carrier_ids)

    def run(
        self,
        spec: OperationSpec,
        provider: OperationProvider,
        *,
        research_object_id: str,
    ) -> DerivedObject:
        research_object = self.source_provider.get_research_object(research_object_id)
        carriers = self._carriers_for(research_object)
        observations = self._observations_for(research_object)
        source_access = RuntimeSourceAccess(
            spec.raw_access_policy,
            carriers,
            self.source_content_provider,
        )
        self._enforce_access(spec, research_object, carriers, source_access)

        if not provider.supports(spec):
            raise UnsupportedOperationError(spec.operation_id)

        prior_state = tuple(self.blackboard.working_state(research_object_id))
        result = provider.execute(spec, research_object, observations, prior_state, source_access)
        if result.operation_id != spec.operation_id:
            raise ValueError(
                f"provider returned operation_id={result.operation_id!r}, "
                f"expected {spec.operation_id!r}"
            )
        if result.research_object_id != research_object_id:
            raise ValueError("provider returned result for a different ResearchObject")
        result = result.model_copy(update={"source_access_manifest": source_access.manifest()})

        previous = self.blackboard.latest(research_object_id, result.object_type)
        self.blackboard.put(result)

        if previous is not None and previous.derived_id != result.derived_id:
            self.blackboard.mark_changed(previous.derived_id)

        return result

    def link(
        self,
        upstream: DerivedObject,
        downstream: DerivedObject,
        *,
        dependency_type: str,
        invalidates_on_change: bool = True,
    ) -> None:
        self.blackboard.add_dependency(
            DependencyEdge(
                upstream_id=upstream.derived_id,
                downstream_id=downstream.derived_id,
                dependency_type=dependency_type,
                invalidates_on_change=invalidates_on_change,
            )
        )
