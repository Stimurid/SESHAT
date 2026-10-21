"""Trusted carrier content boundary for fabric wave invocations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any

from seshat.contracts import (
    RawAccessPolicy,
    SourceAccessManifest,
    SourceCarrier,
    SourceContent,
)
from seshat.runtime import EvidenceAccessError, RuntimeSourceAccess


class _DictContentProvider:
    def __init__(self, contents: Mapping[str, SourceContent]) -> None:
        self._contents = dict(contents)

    def open_content(self, carrier_id: str) -> SourceContent:
        item = self._contents.get(carrier_id)
        if item is None:
            raise KeyError(f"unknown carrier {carrier_id!r}")
        return item.model_copy(deep=True)


class FabricCarrierStore:
    """Version-pinned carrier bodies trusted by the engine host."""

    _TEXT_PROJECTION_MEDIA_TYPES: frozenset[str] = frozenset(
        {"text/plain", "text/markdown", "application/json"}
    )

    def __init__(
        self,
        *,
        carriers: Mapping[str, SourceCarrier],
        contents: Mapping[str, SourceContent],
        revision_provider: Callable[[str, str, str], tuple[SourceCarrier, SourceContent]] | None = None,
    ) -> None:
        self._carriers = {key: value.model_copy(deep=True) for key, value in carriers.items()}
        self._contents = {key: value.model_copy(deep=True) for key, value in contents.items()}
        self._revision_provider = revision_provider

    def carriers_for(self, carrier_ids: tuple[str, ...]) -> tuple[SourceCarrier, ...]:
        return tuple(self._carriers[cid].model_copy(deep=True)
                     for cid in carrier_ids if cid in self._carriers)

    def current_source_versions(self, carrier_ids: tuple[str, ...]) -> dict[str, str]:
        return {
            cid: self._carriers[cid].version
            for cid in carrier_ids
            if cid in self._carriers
        }

    def pin_content_digest(self, carrier_id: str, *, pinned_version: str) -> str:
        """Authorized content digest for a version-pinned carrier (host authority)."""

        if carrier_id not in self._carriers:
            raise ValueError("SOURCE_CARRIER_UNKNOWN")
        carrier = self._carriers[carrier_id]
        if carrier.version != pinned_version:
            raise ValueError("SOURCE_VERSION_STALE")
        content = self._contents.get(carrier_id)
        if content is None:
            raise ValueError("SOURCE_CONTENT_UNAVAILABLE")
        if (
            content.source_version != pinned_version
            or not content.complete
            or not content.authorized
        ):
            raise ValueError("SOURCE_CONTENT_UNAVAILABLE")
        access = RuntimeSourceAccess(
            policy=RawAccessPolicy.FULL_REQUIRED,
            carriers=(carrier.model_copy(deep=True),),
            content_provider=_DictContentProvider({carrier_id: content}),
            carrier_ids=(carrier_id,),
        )
        try:
            access.verify_all((carrier_id,))
            body = access.read_all(carrier_id)
        except EvidenceAccessError:
            raise ValueError("SOURCE_CONTENT_UNAVAILABLE") from None
        return hashlib.sha256(body).hexdigest()

    def revoke_content_same_version(self, carrier_id: str) -> None:
        """Host/test hook: invalidate readable body while the version id stays unchanged."""

        if carrier_id not in self._contents:
            raise ValueError("SOURCE_CARRIER_UNKNOWN")
        content = self._contents[carrier_id]
        self._contents[carrier_id] = content.model_copy(
            update={"complete": False, "authorized": False, "content": b""}
        )

    def apply_delta(
        self, carrier_id: str, *, new_version: str, new_text: str,
        old_version: str = "", media_type: str = "text/plain",
    ) -> None:
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self._apply_delta(carrier_id, new_version=new_version, new_text=new_text,
                                  old_version=old_version, media_type=media_type)
        except Exception:
            raise ValueError("SOURCE_REVISION_DENIED") from None

    def _apply_delta(
        self,
        carrier_id: str,
        *,
        new_version: str,
        new_text: str,
        old_version: str = "",
        media_type: str = "text/plain",
    ) -> None:
        if self._revision_provider is None or carrier_id not in self._carriers:
            raise ValueError("SOURCE_REVISION_UNVERIFIED")
        if self._carriers[carrier_id].version != old_version or new_version == old_version:
            raise ValueError("SOURCE_REVISION_CONFLICT")
        # Verify old rights as well as the new provider-pinned bytes. Event fields
        # are comparisons, never authority to manufacture SourceContent.
        self.resolve_payload(policy=RawAccessPolicy.FULL_REQUIRED,
                             carrier_ids=(carrier_id,), stone_payload={}, operation_id="revision")
        src, content = self._revision_provider(carrier_id, old_version, new_version)
        if (src.carrier_id != carrier_id or src.version != new_version
                or src.source_identity != self._carriers[carrier_id].source_identity
                or content.content != new_text.encode("utf-8")):
            raise ValueError("SOURCE_REVISION_MISMATCH")
        access = RuntimeSourceAccess(policy=RawAccessPolicy.FULL_REQUIRED,
            carriers=(src,), content_provider=_DictContentProvider({carrier_id: content}),
            carrier_ids=(carrier_id,))
        access.verify_all((carrier_id,))
        access.read_all(carrier_id)
        self._carriers[carrier_id] = src.model_copy(deep=True)
        self._contents[carrier_id] = content.model_copy(deep=True)

    def resolve_payload(
        self,
        *,
        policy: RawAccessPolicy,
        carrier_ids: tuple[str, ...],
        stone_payload: Mapping[str, Any],
        operation_id: str,
    ) -> tuple[dict[str, Any], SourceAccessManifest | None]:
        """Build invocation payload; never pass untrusted stone text for FULL_REQUIRED."""

        if policy is RawAccessPolicy.NEVER:
            return (
                {
                    "text": "",
                    "values": [],
                    "stone_meta": {"policy": policy.value},
                },
                None,
            )

        if not carrier_ids:
            raise ValueError("SOURCE_CARRIERS_REQUIRED")

        carriers = self.carriers_for(carrier_ids)
        provider = _DictContentProvider(
            {cid: self._contents[cid] for cid in carrier_ids if cid in self._contents}
        )
        access = RuntimeSourceAccess(
            policy=policy,
            carriers=carriers,
            content_provider=provider,
            carrier_ids=carrier_ids,
        )
        if policy is RawAccessPolicy.FULL_REQUIRED:
            access.verify_all(carrier_ids)
            # Verified above: every carrier_id is present in self._contents.
            # Non-text media (e.g. application/pdf) must never reach a UTF-8
            # text decode here -- some binary bodies happen to decode without
            # raising, which would silently fabricate garbled "text" instead
            # of failing closed.
            non_text = [
                cid for cid in carrier_ids
                if self._contents[cid].media_type not in self._TEXT_PROJECTION_MEDIA_TYPES
            ]
            if non_text:
                raise ValueError("SOURCE_MEDIA_TEXT_PROJECTION_UNSUPPORTED")
            text_parts = [
                access.read_all(cid).decode("utf-8") for cid in carrier_ids
            ]
            text = text_parts[0] if len(text_parts) == 1 else "\n".join(text_parts)
        else:
            # DRILLBACK: source-addressed slice when provided, else full trusted body.
            address = stone_payload.get("drillback_address")
            if isinstance(address, dict):
                from seshat.contracts import SourceAddress

                addr = SourceAddress.model_validate(address)
                text = access.read(addr).decode("utf-8")
            else:
                raise ValueError("SOURCE_ADDRESS_REQUIRED")

        manifest = access.manifest()
        return (
            {
                "text": text,
                "values": [],
                "carriers": carrier_ids,
                "source_versions": {
                    cid: self._carriers[cid].version for cid in carrier_ids if cid in self._carriers
                },
            },
            manifest,
        )
