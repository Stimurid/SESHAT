"""Portable SHA256 receipts for loaded fabric_waves Python modules."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

_MANIFEST_MODULE_NAMES: tuple[str, ...] = (
    "seshat.fabric_waves.carpet_portfolio",
    "seshat.fabric_waves.carpet_hosts",
    "seshat.fabric_waves.carpet_export",
    "seshat.fabric_waves.engine",
    "seshat.fabric_waves.source_access",
    "seshat.fabric_waves.method_body",
    "seshat.fabric_waves.contracts",
    "seshat.fabric_waves.trace",
    "seshat.fabric_waves.operator_ingress",
)


def _module_file_bytes(module_name: str) -> tuple[str, bytes]:
    module = importlib.import_module(module_name)
    path = Path(module.__file__).resolve()
    try:
        rel = path.relative_to(Path(__file__).resolve().parents[1])
        rel_name = rel.as_posix()
    except ValueError:
        rel_name = path.name
    return rel_name, path.read_bytes()


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
    manifest_material = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "attestation": "SOURCE_MODULE_BYTES_VERIFIED",
        "modules": entries,
        "manifest_sha256": hashlib.sha256(manifest_material.encode("utf-8")).hexdigest(),
    }


def verify_source_module_manifest(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("attestation") != "SOURCE_MODULE_BYTES_VERIFIED":
        return False
    rebuilt = build_source_module_manifest()
    return manifest.get("manifest_sha256") == rebuilt["manifest_sha256"]
