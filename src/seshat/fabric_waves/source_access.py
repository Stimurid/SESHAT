"""Trusted carrier content boundary for fabric wave invocations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from seshat.contracts import (
    RawAccessPolicy,
    SourceAccessManifest,
    SourceCarrier,
    SourceContent,
)
from seshat.runtime import RuntimeSourceAccess


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

    def __init__(
        self,
        *,
        carriers: Mapping[str, SourceCarrier],
        contents: Mapping[str, SourceContent],
    ) -> None:
        self._carriers = {key: value.model_copy(deep=True) for key, value in carriers.items()}
        self._contents = {key: value.model_copy(deep=True) for key, value in contents.items()}

    def carriers_for(self, carrier_ids: tuple[str, ...]) -> tuple[SourceCarrier, ...]:
        return tuple(self._carriers[cid] for cid in carrier_ids if cid in self._carriers)

    def apply_delta(
        self,
        carrier_id: str,
        *,
        new_version: str,
        new_text: str,
        media_type: str = "text/plain",
    ) -> None:
        from seshat.fabric_waves.fixtures import carrier as build_carrier

        src, content = build_carrier(
            carrier_id=carrier_id, version=new_version, text=new_text, media_type=media_type
        )
        self._carriers[carrier_id] = src
        self._contents[carrier_id] = content

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
                    "values": list(stone_payload.get("values", ())),
                    "stone_meta": {"policy": policy.value},
                },
                None,
            )

        if not carrier_ids:
            if policy is RawAccessPolicy.FULL_REQUIRED:
                raise ValueError(f"{operation_id} FULL_REQUIRED without carriers")
            return (
                {
                    "text": str(stone_payload.get("text", "")),
                    "values": list(stone_payload.get("values", ())),
                },
                None,
            )

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
            text_parts = [
                access.read_all(cid).decode("utf-8", errors="replace") for cid in carrier_ids
            ]
            text = text_parts[0] if len(text_parts) == 1 else "\n".join(text_parts)
        else:
            # DRILLBACK: source-addressed slice when provided, else full trusted body.
            address = stone_payload.get("drillback_address")
            if isinstance(address, dict):
                from seshat.contracts import SourceAddress

                addr = SourceAddress.model_validate(address)
                text = access.read(addr).decode("utf-8", errors="replace")
            else:
                text = access.read_all(carrier_ids[0]).decode("utf-8", errors="replace")

        manifest = access.manifest()
        return (
            {
                "text": text,
                "values": list(stone_payload.get("values", ())),
                "carriers": carrier_ids,
                "source_versions": {
                    cid: self._carriers[cid].version for cid in carrier_ids if cid in self._carriers
                },
            },
            manifest,
        )
