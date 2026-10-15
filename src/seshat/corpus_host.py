"""Owner-side F07 runtime. Never install this control plane in a caller process.

The OS/service boundary is the trust boundary, not a Python class name. An
owner launches reviewed code with pinned, read-only metadata and rights files.
Only a session's select(request) is exposed through authenticated transport;
paths, pins, install(), cache diagnostics and policy never come from requests.
Arbitrary code execution in this process is explicitly outside this model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import Field

from seshat.corpus import (
    CorpusSelectionSpec, CorpusSpaceSnapshot, FrozenModel, ManifestPin,
    PopulationManifest, StudyRecord, Visibility, _digest, build_corpus_space,
)


class FilePin(FrozenModel):
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def read_pinned(pin: FilePin) -> bytes:
    """Hash and parse the same bytes; never reopen between check and use."""
    raw = pin.path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise ValueError("HOST_INPUT_UNAVAILABLE")
    return raw


class HostConfiguration(FrozenModel):
    host_id: str = Field(min_length=1)
    primary: FilePin
    rights: FilePin


class SourcePackage(FrozenModel):
    host_id: str = Field(min_length=1)
    manifest_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    declared_fields: frozenset[str]
    # Decode denied rows without semantic validation: invalid hidden metadata
    # must not become a public exception oracle. Admission validates visible rows.
    records: tuple[object, ...]


class Grant(FrozenModel):
    caller_id: str
    view_id: str
    object_ids: frozenset[str]
    carrier_ids: frozenset[str]


class RightsPackage(FrozenModel):
    host_id: str = Field(min_length=1)
    epoch: str = Field(min_length=1)
    grants: tuple[Grant, ...]


class PackageAttestation(FrozenModel):
    """Private owner diagnostic. NEVER merged into a public corpus projection."""

    package_state: Literal["SOURCE_PACKAGE_INTEGRITY_VERIFIED"] = (
        "SOURCE_PACKAGE_INTEGRITY_VERIFIED")
    original_source_fact_state: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    raw_access_state: Literal["NOT_READ"] = "NOT_READ"
    semantic_acceptance_state: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


class _Rights:
    def __init__(self, grant: Grant | None):
        self.grant = grant

    def visibility(self, caller_id, view_id, object_id):
        return (Visibility.VISIBLE if self.grant and object_id in self.grant.object_ids
                else Visibility.DENIED)

    def carrier_visibility(self, caller_id, view_id, object_id, carrier_id):
        return (Visibility.VISIBLE if self.grant and carrier_id in self.grant.carrier_ids
                else Visibility.DENIED)

    def may_count_denied(self, caller_id, view_id):
        return False


class HostRuntime:
    """Privileged bootstrap/control plane; never a public dependency injection API.

    install is an owner-only atomic epoch transition. Every request rechecks
    the exact installed bytes, including the complete private rights package.
    A changed file without an independently installed pin fails closed. Old
    public receipts cannot certify currentness: select always checks private
    epochs first. Diagnostics and rebuild_count are owner-only.
    """

    def __init__(self, configuration: HostConfiguration):
        self._lock = RLock()
        self._cache = {}
        self._epoch = None
        self.rebuild_count = 0
        self.install(configuration)

    def install(self, configuration: HostConfiguration) -> None:
        configuration = HostConfiguration.model_validate(configuration.model_dump())
        with self._lock:
            # Validate before changing a working owner configuration.
            self._load(configuration)
            self._configuration = configuration

    @staticmethod
    def _load(configuration):
        try:
            source = SourcePackage.model_validate_json(read_pinned(configuration.primary))
            rights = RightsPackage.model_validate_json(read_pinned(configuration.rights))
            if source.host_id != configuration.host_id or rights.host_id != configuration.host_id:
                raise ValueError
            if len({(g.caller_id, g.view_id) for g in rights.grants}) != len(rights.grants):
                raise ValueError
            return source, rights
        except Exception:
            raise ValueError("HOST_INPUT_UNAVAILABLE") from None

    def session(self, *, authenticated_caller: str, authorized_view: str):
        """Called by host authentication middleware, never from request claims.

        Return only this callable to the transport adapter. Do not export the
        runtime/control plane or accept caller-selected paths/policy objects.
        """
        def select(request: CorpusSelectionSpec) -> CorpusSpaceSnapshot:
            request = CorpusSelectionSpec.model_validate(request.model_dump())
            if (request.caller_id, request.view_id) != (authenticated_caller, authorized_view):
                raise ValueError("SESSION_SCOPE_MISMATCH")
            with self._lock:
                source, rights = self._load(self._configuration)
                epoch = (self._configuration.host_id, self._configuration.primary.sha256,
                         self._configuration.rights.sha256, rights.epoch)
                if epoch != self._epoch:
                    self._cache.clear()
                    self._epoch = epoch
                # The request manifest is not a trust root or an epoch oracle.
                key = request.canonical_json
                if key not in self._cache:
                    grant = next((g for g in rights.grants
                                  if (g.caller_id, g.view_id) ==
                                  (authenticated_caller, authorized_view)), None)
                    records = []
                    policy = _Rights(grant)
                    for row in source.records:
                        if not isinstance(row, dict):
                            # No routing identity: visibility cannot be decided.
                            raise ValueError("invalid study pin")
                        identity = row.get("research_object")
                        object_id = identity.get("object_id") if isinstance(identity, dict) else None
                        if not isinstance(object_id, str):
                            raise ValueError("invalid study pin")
                        if policy.visibility(None, None, object_id) is Visibility.DENIED:
                            continue
                        # Phase 1 inspects ONLY recognizable routing IDs. Scan
                        # all entries without parsing malformed neighbours; a
                        # known denial wins regardless of order or duplicates.
                        carriers = row.get("carriers")
                        routing_ids = []
                        if isinstance(carriers, list):
                            routing_ids.extend(c.get("carrier_id") for c in carriers
                                               if isinstance(c, dict)
                                               and isinstance(c.get("carrier_id"), str)
                                               and c["carrier_id"].strip())
                        references = identity.get("carrier_ids")
                        if isinstance(references, list):
                            routing_ids.extend(c for c in references
                                               if isinstance(c, str) and c.strip())
                        if any(policy.carrier_visibility(None, None, object_id, carrier_id)
                               is Visibility.DENIED for carrier_id in routing_ids):
                            continue
                        try:
                            # Phase 2 validates only rows without known denial.
                            # Malformed visible rows remain errors, not absences.
                            record = StudyRecord.model_validate(row)
                        except Exception:
                            raise ValueError("invalid study pin") from None
                        # Bind every field to its actual pinned source record.
                        # Full file SHA/row ordinal stay PRIVATE: hidden row
                        # insertion or rotation cannot alter public evidence refs.
                        def bound(field):
                            token = _digest({"host": source.host_id,
                                             "object": record.research_object.object_id,
                                             "name": field.name, "value": field.value})
                            return field.model_copy(update={
                                "evidence_ref": f"host-field:{token}"})
                        records.append(record.model_copy(update={
                            "fields": tuple(bound(f) for f in record.fields),
                            "roles": tuple(bound(f) for f in record.roles)}))
                    manifest = PopulationManifest(pin=ManifestPin(
                        manifest_id=source.manifest_id, version=source.version,
                        sha256=self._configuration.primary.sha256),
                        declared_fields=source.declared_fields)
                    self._cache[key] = build_corpus_space(request, manifest, records, _Rights(grant))
                    self.rebuild_count += 1
                return self._cache[key].model_copy(deep=True)
        return select

    def attest_package(self) -> PackageAttestation:
        with self._lock:
            self._load(self._configuration)
            return PackageAttestation()


def main(argv=None) -> int:
    """Owner-started process boundary; stdin is the untrusted request channel.

    The owner supplies argv/read-only mounts. A client controls only stdin JSON
    lines; it cannot replace configuration, session, policy or callbacks. Use a
    separate noncredentialed identity and authenticate the pipe before starting
    this process. The launcher must not forward client-chosen argv/environment.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Owner-side F07 JSON-line worker")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--caller-id", required=True)
    parser.add_argument("--view-id", required=True)
    args = parser.parse_args(argv)
    try:
        configuration = HostConfiguration.model_validate_json(read_pinned(
            FilePin(path=args.config, sha256=args.config_sha256)))
        if configuration.host_id != args.host_id:
            raise ValueError
        runtime = HostRuntime(configuration)
        select = runtime.session(authenticated_caller=args.caller_id, authorized_view=args.view_id)
    except Exception:
        print('{"error":"HOST_INPUT_UNAVAILABLE"}', flush=True)
        return 2
    for line in sys.stdin:
        try:
            request = CorpusSelectionSpec.model_validate_json(line)
            response = select(request).model_dump(mode="json")
        except Exception:
            response = {"error": "SELECTION_UNAVAILABLE"}
        print(json.dumps(response, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
