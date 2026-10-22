"""Pre-read admission for the one predeclared CC BY I11 package.

Caller-written OWNER_EXPLICIT JSON is not a rights grant. Identity, alias and
path are checked before any real source file is opened. Digest uses bytes
only after that guard; semantic/model transfer waits until the digest matches
the code-pinned published paper. Publication CC BY is not F07 attestation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from seshat.fabric_waves.i11_activity_network import (
    AUTHORIAL_I11_ID,
    CCBY_PAGES_SHA256,
    CCBY_PDF_SHA256,
)

PREDECLARED_SOURCE_IDS = frozenset({
    "plos-one-e0293107-ccby",
    "plos-one-e0293107-ccby-pages",
    "observed-ccby-pdf",
    "observed-ccby-pages",
})
PREDECLARED_PATH_NAMES = frozenset({"open_source.pdf", "open_source_pages.txt"})
PREDECLARED_DIGESTS = frozenset({CCBY_PDF_SHA256, CCBY_PAGES_SHA256})


def _fold(value: str) -> str:
    return str(value or "").strip().casefold()


def identity_is_predeclared(source_id: str, source_name: str = "") -> bool:
    sid = _fold(source_id)
    name = Path(_fold(source_name)).name
    allowed = {_fold(item) for item in PREDECLARED_SOURCE_IDS}
    if sid in allowed:
        return True
    if sid.endswith("-pages") and sid[: -len("-pages")] in allowed:
        return True
    return name in PREDECLARED_PATH_NAMES


def source_path_is_predeclared(path: Path | None) -> bool:
    if path is None:
        return False
    if path.name.casefold() in PREDECLARED_PATH_NAMES:
        return True
    posix = path.as_posix().replace("\\", "/").casefold()
    return posix.endswith("m7_source/open_source_pages.txt")


def permission_pins_predeclared_package(permission: dict[str, Any] | None) -> bool:
    if not isinstance(permission, dict):
        return False
    if permission.get("operation_id") != AUTHORIAL_I11_ID:
        return False
    if not identity_is_predeclared(str(permission.get("source_id") or "")):
        return False
    digest = _fold(str(permission.get("source_sha256") or ""))
    pages = _fold(str(permission.get("pages_sha256") or ""))
    if digest != CCBY_PDF_SHA256:
        return False
    if pages and pages != CCBY_PAGES_SHA256:
        return False
    return True


def guard_real_source_pre_read(
    *,
    source_id: str,
    source_name: str = "",
    source_path: Path | None,
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    identity_excluded,
) -> None:
    """Fail closed before opening real source bytes."""
    if identity_excluded(source_id, source_name, exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    if source_path is not None and identity_excluded(source_path.name, source_path.name, exclusion_policy):
        raise ValueError("I11_SOURCE_EXCLUDED")
    if f07_permission is not None:
        if identity_excluded(str(f07_permission.get("source_id") or ""), "", exclusion_policy):
            raise ValueError("I11_SOURCE_EXCLUDED")
        perm_sha = _fold(str(f07_permission.get("source_sha256") or ""))
        excluded_hashes = {
            _fold(str(item))
            for item in exclusion_policy.get("excluded", {}).get("source_sha256", ())
        }
        if perm_sha and perm_sha in excluded_hashes:
            raise ValueError("I11_SOURCE_EXCLUDED")
    if not identity_is_predeclared(source_id, source_name):
        raise ValueError("I11_SOURCE_NOT_PREDECLARED")
    if source_path is not None and not source_path_is_predeclared(source_path):
        raise ValueError("I11_SOURCE_NOT_PREDECLARED")
    if not permission_pins_predeclared_package(f07_permission):
        raise ValueError("I11_SOURCE_NOT_PREDECLARED")


def read_real_source_after_pre_read_guard(
    *,
    path: Path,
    source_id: str,
    source_name: str = "",
    exclusion_policy: dict[str, Any],
    f07_permission: dict[str, Any] | None,
    identity_excluded,
) -> bytes:
    guard_real_source_pre_read(
        source_id=source_id,
        source_name=source_name or path.name,
        source_path=path,
        exclusion_policy=exclusion_policy,
        f07_permission=f07_permission,
        identity_excluded=identity_excluded,
    )
    return path.read_bytes()
