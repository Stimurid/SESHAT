"""Portable SHA256 receipts for loaded fabric_waves Python modules."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

# Load-bearing causal / rights modules for the carpet portfolio runtime.
# This list is a source-module subset, not a full dependency lock or owner signature.
_MANIFEST_MODULE_NAMES: tuple[str, ...] = (
    "seshat.contracts",
    "seshat.runtime",
    "seshat.fabric_waves.carpet_export",
    "seshat.fabric_waves.carpet_hosts",
    "seshat.fabric_waves.carpet_portfolio",
    "seshat.fabric_waves.contracts",
    "seshat.fabric_waves.decision_gate",
    "seshat.fabric_waves.engine",
    "seshat.fabric_waves.errors",
    "seshat.fabric_waves.fixtures",
    "seshat.fabric_waves.frontier",
    "seshat.fabric_waves.m4_transport_boundary",
    "seshat.fabric_waves.m5_checkpoint",
    "seshat.fabric_waves.m5_oracles",
    "seshat.fabric_waves.m5_room_carpet",
    "seshat.fabric_waves.m5_synthetic_hosts",
    "seshat.fabric_waves.m6_oracles",
    "seshat.fabric_waves.m6_report_composer",
    "seshat.fabric_waves.m6_research_engine",
    "seshat.fabric_waves.room_builder",
    "seshat.fabric_waves.ledger",
    "seshat.fabric_waves.method_body",
    "seshat.fabric_waves.operator",
    "seshat.fabric_waves.operator_ingress",
    "seshat.fabric_waves.propagation",
    "seshat.fabric_waves.resonance",
    "seshat.fabric_waves.scenarios",
    "seshat.fabric_waves.sediment",
    "seshat.fabric_waves.source_access",
    "seshat.fabric_waves.source_module_manifest",
    "seshat.fabric_waves.stone",
    "seshat.fabric_waves.trace",
    "seshat.fabric_waves.external_carrier.contracts",
    "seshat.fabric_waves.external_carrier.ledger",
    "seshat.fabric_waves.external_carrier.port",
    "seshat.fabric_waves.external_carrier.fake_host",
    "seshat.fabric_waves.external_carrier.hosts",
    "seshat.fabric_waves.external_carrier.portfolio",
    "seshat.fabric_waves.external_carrier.cli",
)

_COVERAGE_NOTE = (
    "SOURCE_MODULE_SUBSET: listed fabric_waves and root contracts/runtime modules only; "
    "not a full dependency lock, transitive import closure, wheel signature, or owner signing receipt."
)

_MANIFEST_TOP_KEYS = frozenset({"attestation", "coverage_note", "modules", "manifest_sha256"})
_MODULE_ENTRY_KEYS = frozenset({"module", "relative_path", "byte_length", "sha256"})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _module_file_bytes(module_name: str) -> tuple[str, bytes]:
    module = importlib.import_module(module_name)
    path = Path(module.__file__).resolve()
    try:
        rel = path.relative_to(_repo_root())
        rel_name = rel.as_posix()
    except ValueError:
        rel_name = path.name
    return rel_name, path.read_bytes()


def _canonical_manifest_material(entries: list[dict[str, Any]], coverage_note: str) -> str:
    payload = {"coverage_note": coverage_note, "modules": entries}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_digest(entries: list[dict[str, Any]], coverage_note: str) -> str:
    return hashlib.sha256(
        _canonical_manifest_material(entries, coverage_note).encode("utf-8")
    ).hexdigest()


def _entry_is_safe_relative_path(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    return bool(parts) and ".." not in parts and not Path(relative_path).is_absolute()


def _read_entry_bytes(relative_path: str) -> bytes | None:
    if not _entry_is_safe_relative_path(relative_path):
        return None
    path = (_repo_root() / relative_path).resolve()
    try:
        path.relative_to(_repo_root().resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path.read_bytes()


def build_source_module_manifest() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for module_name in _MANIFEST_MODULE_NAMES:
        relative_path, data = _module_file_bytes(module_name)
        entries.append(
            {
                "module": module_name,
                "relative_path": relative_path,
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    entries.sort(key=lambda item: item["relative_path"])
    return {
        "attestation": "SOURCE_MODULE_BYTES_VERIFIED",
        "coverage_note": _COVERAGE_NOTE,
        "modules": entries,
        "manifest_sha256": _manifest_digest(entries, _COVERAGE_NOTE),
    }


def verify_source_module_manifest(manifest: Mapping[str, Any]) -> bool:
    if set(manifest.keys()) != _MANIFEST_TOP_KEYS:
        return False
    if manifest.get("attestation") != "SOURCE_MODULE_BYTES_VERIFIED":
        return False
    if manifest.get("coverage_note") != _COVERAGE_NOTE:
        return False
    supplied_entries = manifest.get("modules")
    if not isinstance(supplied_entries, list) or not supplied_entries:
        return False
    declared_digest = manifest.get("manifest_sha256")
    if not isinstance(declared_digest, str):
        return False
    if _manifest_digest(supplied_entries, _COVERAGE_NOTE) != declared_digest:
        return False

    rebuilt = build_source_module_manifest()
    fresh_entries = rebuilt["modules"]
    if len(supplied_entries) != len(fresh_entries):
        return False

    seen_paths: set[str] = set()
    seen_modules: set[str] = set()
    for supplied, fresh in zip(supplied_entries, fresh_entries, strict=True):
        if not isinstance(supplied, Mapping):
            return False
        if set(supplied.keys()) != _MODULE_ENTRY_KEYS:
            return False
        for key in _MODULE_ENTRY_KEYS:
            if supplied.get(key) != fresh.get(key):
                return False
        relative_path = str(fresh["relative_path"])
        module_name = str(fresh["module"])
        if module_name in seen_modules or relative_path in seen_paths:
            return False
        seen_modules.add(module_name)
        seen_paths.add(relative_path)
        if not _entry_is_safe_relative_path(relative_path):
            return False
        data = _read_entry_bytes(relative_path)
        if data is None:
            return False
        if len(data) != fresh["byte_length"]:
            return False
        if hashlib.sha256(data).hexdigest() != fresh["sha256"]:
            return False

    return declared_digest == rebuilt["manifest_sha256"]
