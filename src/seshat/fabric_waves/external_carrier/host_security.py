"""HOST-ONLY safety primitives for the trusted AORUS Hub adapter (Phase B).

Boundary: the unprivileged fabric core (engine, contracts, port, ledger, hosts) never imports
this module. It holds no credentials; callers inject optional integrity keys and environment
mappings explicitly. Nothing here prints or serializes a key.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError

# Only these invented public carriers may ever be placed in an outbound Hub envelope.
PUBLIC_SYNTHETIC_CARRIERS: frozenset[str] = frozenset(
    {
        "campus-branch-alpha",
        "campus-branch-beta",
        "met-sensor-north",
        "met-sensor-south",
    }
)

SUPPORTED_OUTPUT_SCHEMA = "external.hypothesis.v1"
E5_ONLY_CLASSES: frozenset[str] = frozenset({"E5", "structured_hypothesis"})
ALLOWED_HUB_ROLES: frozenset[str] = frozenset({"analyze", "classify"})


class HostBoundaryError(ExternalAdmissionError):
    """Host-side refusal. The stable machine code is args[0]."""

    @property
    def code(self) -> str:
        return str(self.args[0])


@dataclass(frozen=True)
class HostLimits:
    """Absolute host ceilings. Requests may ask for less, never more (values are clamped)."""

    max_tokens: int = 8192
    max_time_seconds: int = 1800
    max_cost_cents: int = 200
    max_excerpt_chars: int = 2000
    max_topic_chars: int = 300
    max_query_chars: int = 600
    max_prompt_bytes: int = 24_000
    max_stdout_bytes: int = 64_000
    max_hypothesis_chars: int = 2000
    max_rationale_chars: int = 4000
    max_uncertainty_chars: int = 500
    max_carriers: int = 2
    allowed_carrier_ids: frozenset[str] = PUBLIC_SYNTHETIC_CARRIERS


class HostIntegrityKey:
    """Optional host-private HMAC key. Redacted repr; the key is never exported."""

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
            raise HostBoundaryError("HOST_INTEGRITY_KEY_TOO_SHORT")
        self._key = bytes(key)

    def mac(self, text: str) -> str:
        return hmac.new(self._key, text.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, text: str, mac: str) -> bool:
        if not isinstance(mac, str):
            return False
        return hmac.compare_digest(self.mac(text).encode("utf-8"), mac.encode("utf-8", "replace"))

    def __repr__(self) -> str:
        return "HostIntegrityKey(<redacted>)"

    __str__ = __repr__


_SECRET_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"sk-[A-Za-z0-9_\-]{16,}",
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)\b(api[_-]?key|secret|password|passwd|bearer)\s*[:=]\s*\S+",
        r"ghp_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    )
)
_PATH_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"(?i)(?<![A-Za-z0-9])[a-z]:[\\/]",
        r"\\\\[A-Za-z0-9_.$-]+\\",
        r"(?<![A-Za-z0-9_.])/(etc|home|root|usr|var|proc|mnt|Users|tmp)/",
        r"\.\.[\\/]",
        r"(?i)file://",
    )
)
_PROTECTED_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"%PDF-",
        r"(?i)\bagent[-_ ]?0\b",
        r"(?i)private[-_ ]?v4",
        r"(?i)\bMETHODBODY[-_ ]PRIVATE\b",
    )
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MIN_ENV_LEAK_LEN = 8


def scan_text(
    text: str,
    *,
    direction: str,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Refuse secrets, paths, protected markers, control chars and env value echoes.

    ``direction`` is OUTBOUND or INBOUND and prefixes the stable error code.
    """

    prefix = direction.upper()
    if _CONTROL_CHARS.search(text):
        raise HostBoundaryError(f"{prefix}_CONTROL_CHARS")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise HostBoundaryError(f"{prefix}_SECRET_DETECTED")
    for pattern in _PATH_PATTERNS:
        if pattern.search(text):
            raise HostBoundaryError(f"{prefix}_PATH_DETECTED")
    for pattern in _PROTECTED_PATTERNS:
        if pattern.search(text):
            raise HostBoundaryError(f"{prefix}_PROTECTED_CONTENT")
    if environ:
        for value in environ.values():
            if isinstance(value, str) and len(value) >= _MIN_ENV_LEAK_LEN and value in text:
                raise HostBoundaryError(f"{prefix}_ENV_LEAK")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_safe_token(value: str, *, code: str, extra: str = "") -> str:
    """Static-argument guard: no leading dash, no whitespace, no shell metacharacters.

    Base alphabet is ``[A-Za-z0-9._-]``; callers may add specific extra characters (for
    provider/model names). Identifiers used as path components get no extras.
    """

    if not isinstance(value, str):
        raise HostBoundaryError(code)
    pattern = r"[A-Za-z0-9][A-Za-z0-9._" + re.escape(extra) + r"-]{0,79}"
    if re.fullmatch(pattern, value) is None or ".." in value:
        raise HostBoundaryError(code)
    return value


def read_file_under(base: Path, user_path: str | Path, *, max_bytes: int) -> tuple[Path, bytes]:
    """Read a regular file strictly inside ``base``.

    Rejects ``..``, symlink components, non-regular files, oversize files and paths that
    resolve outside the base directory.
    """

    try:
        raw = Path(user_path)
    except (TypeError, ValueError):
        raise HostBoundaryError("PATH_INVALID") from None
    if "\x00" in str(raw):
        raise HostBoundaryError("PATH_INVALID")
    if ".." in raw.parts:
        raise HostBoundaryError("PATH_TRAVERSAL")
    base_abs = Path(os.path.abspath(base))
    candidate = raw if raw.is_absolute() else base_abs / raw
    candidate_abs = Path(os.path.abspath(candidate))
    try:
        relative = candidate_abs.relative_to(base_abs)
    except ValueError:
        raise HostBoundaryError("PATH_OUTSIDE_BASE") from None
    if not relative.parts:
        raise HostBoundaryError("PATH_NOT_REGULAR_FILE")
    cursor = base_abs
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise HostBoundaryError("PATH_SYMLINK_DENIED")
    resolved = Path(os.path.realpath(candidate_abs))
    try:
        resolved.relative_to(Path(os.path.realpath(base_abs)))
    except ValueError:
        raise HostBoundaryError("PATH_OUTSIDE_BASE") from None
    try:
        info = os.lstat(resolved)
    except FileNotFoundError:
        raise HostBoundaryError("PATH_NOT_FOUND") from None
    if not stat.S_ISREG(info.st_mode):
        raise HostBoundaryError("PATH_NOT_REGULAR_FILE")
    if info.st_size > max_bytes:
        raise HostBoundaryError("PATH_TOO_LARGE")
    # Re-validate on the opened descriptor so a swap after lstat (symlink/FIFO) is refused.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(resolved, flags)
    except FileNotFoundError:
        raise HostBoundaryError("PATH_NOT_FOUND") from None
    except OSError:
        raise HostBoundaryError("PATH_OPEN_REFUSED") from None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise HostBoundaryError("PATH_NOT_REGULAR_FILE")
        if opened.st_size > max_bytes:
            raise HostBoundaryError("PATH_TOO_LARGE")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise HostBoundaryError("PATH_TOO_LARGE")
    return resolved, data


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via temp file + fsync + atomic replace, then verify the readback."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    if path.read_bytes() != data:
        raise HostBoundaryError("ATOMIC_WRITE_READBACK_MISMATCH")


__all__ = [
    "ALLOWED_HUB_ROLES",
    "E5_ONLY_CLASSES",
    "PUBLIC_SYNTHETIC_CARRIERS",
    "SUPPORTED_OUTPUT_SCHEMA",
    "HostBoundaryError",
    "HostIntegrityKey",
    "HostLimits",
    "atomic_write_bytes",
    "read_file_under",
    "require_safe_token",
    "scan_text",
    "sha256_hex",
]
