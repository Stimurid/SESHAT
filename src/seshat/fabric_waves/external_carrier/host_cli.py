"""HOST-ONLY Phase B CLI: write-origin | prepare | dispatch | ingest | resume | status.

DRY RUN IS THE DEFAULT for prepare/dispatch/ingest/resume. Durable or chargeable effects need
an explicit ``--execute``; a live Hub submission additionally needs ``--authorization`` (a
single-use coordinator document bound to the exact job, spec and prompt digests) and a
configured absolute ``aiye-exec`` path. All file arguments are confined to ``--host-dir``.

Exit codes: 0 ok, 2 refused (stable error code on stderr), 10 WAITING, 11 BLOCKED_EXTERNAL.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from seshat.fabric_waves.contracts import StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.engine import WaveEngine, WaveEngineConfigurationError
from seshat.fabric_waves.external_carrier.host_adapter import (
    APPROVAL_SCHEMA,
    DispatchPolicy,
    OwnerApprovals,
    TrustedHubHostAdapter,
)
from seshat.fabric_waves.external_carrier.host_dispatcher import (
    AiyeExecSubmitter,
    HostDispatcher,
    SpoolHubFetcher,
)
from seshat.fabric_waves.external_carrier.host_envelope import (
    FabricStoreSourceAuthority,
    SourceAuthority,
)
from seshat.fabric_waves.external_carrier.host_security import (
    HostBoundaryError,
    HostIntegrityKey,
    HostLimits,
    atomic_write_bytes,
    read_file_under,
    require_safe_token,
)
from seshat.fabric_waves.external_carrier.host_store import HostJobStore
from seshat.fabric_waves.external_carrier.hub_protocol import HubIssuer, HubIssuerRegistry
from seshat.fabric_waves.external_carrier.phase_b import (
    ENGINE_FACTORIES,
    TRANSPORT_KIND_HUB_SPOOL_RECORD,
    TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT,
    OriginManifest,
    export_phase_b_artifacts,
    resume_by_replay,
    start_waiting_run,
)
from seshat.fabric_waves.external_carrier.port import ExternalAdmissionError

CONFIG_SCHEMA = "seshat.host_config.v1"
CONFIG_NAME = "host_config.json"
_MAX_DOC_BYTES = 256_000
EXIT_OK, EXIT_REFUSED, EXIT_WAITING, EXIT_BLOCKED = 0, 2, 10, 11
# Re-export the canonical Phase-B transport labels so the CLI does not diverge from the
# library API. The library owns the gating decision.
TRANSPORT_UNATTESTED_MANUAL_IMPORT = TRANSPORT_KIND_UNATTESTED_MANUAL_IMPORT
TRANSPORT_HUB_SPOOL_RECORD = TRANSPORT_KIND_HUB_SPOOL_RECORD


class _UnionAuthority:
    """Route source authority calls to whichever engine store owns the carrier."""

    def __init__(self, authorities: list[SourceAuthority]) -> None:
        self._authorities = authorities

    def current_source_versions(self, carrier_ids: tuple[str, ...]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for item in self._authorities:
            merged.update(item.current_source_versions(carrier_ids))
        return merged

    def _owner(self, carrier_id: str) -> SourceAuthority:
        for item in self._authorities:
            if carrier_id in item.current_source_versions((carrier_id,)):
                return item
        raise HostBoundaryError("SOURCE_CARRIER_UNKNOWN")

    def pin_content_digest(self, carrier_id: str, *, pinned_version: str) -> str:
        return self._owner(carrier_id).pin_content_digest(carrier_id, pinned_version=pinned_version)

    def read_public_text(self, carrier_id: str, *, pinned_version: str) -> str:
        return self._owner(carrier_id).read_public_text(carrier_id, pinned_version=pinned_version)


def _read_json(host_dir: Path, name: str | Path) -> dict[str, Any]:
    _, raw = read_file_under(host_dir, name, max_bytes=_MAX_DOC_BYTES)
    try:
        data = json.loads(raw)
    except ValueError:
        raise HostBoundaryError("JSON_DOCUMENT_INVALID") from None
    if not isinstance(data, dict):
        raise HostBoundaryError("JSON_DOCUMENT_INVALID")
    return data


def _key_from_env(name: Any, environ: Mapping[str, str]) -> HostIntegrityKey | None:
    if name in (None, ""):
        return None
    value = environ.get(str(name))
    if not value:
        raise HostBoundaryError("HOST_KEY_ENV_MISSING")
    return HostIntegrityKey(value.encode("utf-8"))


def load_config(host_dir: Path, environ: Mapping[str, str]) -> dict[str, Any]:
    config = _read_json(host_dir, CONFIG_NAME)
    if config.get("schema") != CONFIG_SCHEMA:
        raise HostBoundaryError("HOST_CONFIG_INVALID")
    return config


def build_adapter(
    host_dir: Path,
    *,
    environ: Mapping[str, str],
    factories: Mapping[str, Callable[[], WaveEngine]] | None = None,
) -> tuple[TrustedHubHostAdapter, dict[str, Any]]:
    config = load_config(host_dir, environ)
    try:
        issuers = [
            HubIssuer(
                issuer_id=str(item["issuer_id"]),
                hub_instance_id=str(item["hub_instance_id"]),
                allowed_providers=frozenset(item["allowed_providers"]),
                allowed_models=frozenset(item["allowed_models"]),
                mac_key=_key_from_env(item.get("mac_key_env"), environ),
            )
            for item in config["issuers"]
        ]
        policy = DispatchPolicy(
            provider=str(config["policy"]["provider"]),
            model=str(config["policy"]["model"]),
            role=str(config["policy"].get("role", "analyze")),
        )
        scopes = frozenset(str(s) for s in config["allowed_host_scopes"])
        approvals_name = str(config["approvals_file"])
    except HostBoundaryError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HostBoundaryError("HOST_CONFIG_INVALID") from None
    approvals_doc = _read_json(host_dir, approvals_name)
    table = factories if factories is not None else ENGINE_FACTORIES
    authority = _UnionAuthority(
        [FabricStoreSourceAuthority(factory().carrier_store) for factory in table.values()]
    )
    store = HostJobStore(
        host_dir / "store", integrity_key=_key_from_env(config.get("integrity_key_env"), environ)
    )
    adapter = TrustedHubHostAdapter(
        store=store,
        registry=HubIssuerRegistry(issuers),
        source_authority=authority,
        approvals=OwnerApprovals.from_document(approvals_doc),
        policy=policy,
        allowed_host_scopes=scopes,
        limits=HostLimits(),
        environ=environ,
    )
    return adapter, config


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str))


def resolve_export_transport_kind(
    adapter: TrustedHubHostAdapter, host_job_id: str, explicit: str | None
) -> str:
    if explicit is None:
        return TRANSPORT_UNATTESTED_MANUAL_IMPORT
    kind = require_safe_token(explicit, code="TRANSPORT_KIND_INVALID")
    if kind == TRANSPORT_HUB_SPOOL_RECORD:
        adapter.assert_hub_attested_for_export(host_job_id)
        return kind
    if kind == TRANSPORT_UNATTESTED_MANUAL_IMPORT:
        return kind
    raise HostBoundaryError("TRANSPORT_KIND_UNKNOWN")


def _origin_from_args(args: argparse.Namespace) -> OriginManifest:
    return OriginManifest(
        engine_kind=args.engine,
        run_id=require_safe_token(args.run_id, code="RUN_ID_INVALID"),
        stone=StoneEvent(
            event_id=require_safe_token(args.event_id, code="EVENT_ID_INVALID"),
            kind=StoneEventKind.QUERY,
            issued_at_tick=0,
            payload={"topic": args.topic, "query": args.query},
        ),
        budget=WaveBudget(
            max_waves=args.max_waves,
            max_activations=args.max_activations,
            max_stone_events=args.max_stone_events,
            aporia_after_waves=args.aporia_after_waves,
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-dir", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    origin = sub.add_parser("write-origin", help="Write an origin manifest (data only)")
    origin.add_argument("--engine", required=True, choices=sorted(ENGINE_FACTORIES))
    origin.add_argument("--run-id", required=True)
    origin.add_argument("--event-id", required=True)
    origin.add_argument("--topic", required=True)
    origin.add_argument("--query", required=True)
    origin.add_argument("--max-waves", type=int, default=40)
    origin.add_argument("--max-activations", type=int, default=80)
    origin.add_argument("--max-stone-events", type=int, default=80)
    origin.add_argument("--aporia-after-waves", type=int, default=2)
    origin.add_argument("--out-name", required=True)

    prep = sub.add_parser("prepare", help="Gate + persist a job (dry run unless --execute)")
    prep.add_argument("--origin", required=True)
    prep.add_argument("--execute", action="store_true")

    disp = sub.add_parser("dispatch", help="Submit via aiye-exec (dry run unless --execute)")
    disp.add_argument("--host-job-id", required=True)
    disp.add_argument("--execute", action="store_true")
    disp.add_argument("--authorization")

    ing = sub.add_parser("ingest", help="Verify a Hub record (dry run unless --execute)")
    ing.add_argument("--host-job-id", required=True)
    ing.add_argument("--execute", action="store_true")

    res = sub.add_parser("resume", help="Replay-verified resume (artifacts only with --execute)")
    res.add_argument("--host-job-id", required=True)
    res.add_argument("--execute", action="store_true")
    res.add_argument("--output-name", default=None)
    res.add_argument(
        "--transport-kind",
        default=None,
        help=(
            "Verbatim export label; default UNATTESTED_MANUAL_IMPORT. "
            "HUB_SPOOL_RECORD requires a verified Hub submission chain."
        ),
    )

    stat = sub.add_parser("status", help="Show persisted job state")
    stat.add_argument("--host-job-id", required=True)
    return parser


def run(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    factories: Mapping[str, Callable[[], WaveEngine]] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = environ if environ is not None else os.environ
    host_dir = Path(args.host_dir)

    if args.command == "write-origin":
        origin = _origin_from_args(args)
        name = require_safe_token(args.out_name, code="OUT_NAME_INVALID")
        target = host_dir / "origins" / f"{name}.json"
        data = json.dumps(origin.replay_dict(), sort_keys=True, indent=2).encode("utf-8")
        atomic_write_bytes(target, data)
        _emit({"state": "WRITTEN", "path": str(target), "bytes": len(data)})
        return EXIT_OK

    adapter, config = build_adapter(host_dir, environ=env, factories=factories)
    dispatcher = HostDispatcher(adapter=adapter)
    spool = host_dir / "hub_spool"

    if args.command == "prepare":
        origin = OriginManifest.from_replay(_read_json(host_dir, args.origin))
        waiting = start_waiting_run(origin, factories=factories)
        if args.execute:
            job = adapter.prepare(waiting.need, replay=origin.replay_dict())
            _emit({"state": "PREPARED", "host_job_id": job.host_job_id, "dry_run": False})
        else:
            summary = adapter.preview(waiting.need)
            _emit({"state": "DRY_RUN", "dry_run": True, **summary})
        return EXIT_OK

    if args.command == "dispatch":
        authorization = None
        submitter = None
        exe = config.get("aiye_exec_path")
        if args.execute:
            if not args.authorization or not exe:
                raise HostBoundaryError("LIVE_DISPATCH_NOT_AUTHORIZED")
            authorization = _read_json(host_dir, args.authorization)
            submitter = AiyeExecSubmitter(exe=str(exe), spool_dir=spool, runner=runner)
        result = dispatcher.dispatch(
            args.host_job_id,
            execute=bool(args.execute),
            submitter=submitter,
            authorization=authorization,
            exe=str(exe) if exe else None,
            spool_dir=spool,
        )
        _emit(
            {
                "state": result.state,
                "detail": result.detail,
                "host_job_id": result.host_job_id,
                "hub_job_id": result.hub_job_id,
                "manifest": result.manifest,
                "dry_run": not args.execute,
            }
        )
        return EXIT_BLOCKED if result.state in {"BLOCKED_EXTERNAL", "AMBIGUOUS"} else EXIT_OK

    if args.command == "ingest":
        outcome = dispatcher.ingest(
            args.host_job_id, fetcher=SpoolHubFetcher(spool), execute=bool(args.execute)
        )
        _emit(outcome)
        return EXIT_WAITING if outcome["state"] == "WAITING" else EXIT_OK

    if args.command == "resume":
        result = resume_by_replay(
            adapter=adapter, host_job_id=args.host_job_id, factories=factories
        )
        payload: dict[str, Any] = {
            "state": "RESUMED",
            "mode": result.mode,
            "dry_run": not args.execute,
            "run_outcome": result.run_record.outcome.value,
            "causal_facts": result.facts,
        }
        if args.execute:
            name = require_safe_token(args.output_name or args.host_job_id, code="OUT_NAME_INVALID")
            transport_kind = resolve_export_transport_kind(
                adapter, args.host_job_id, args.transport_kind
            )
            receipt = export_phase_b_artifacts(
                host_dir / "artifacts" / name,
                result=result,
                adapter=adapter,
                host_job_id=args.host_job_id,
                transport_kind=transport_kind,
            )
            payload["artifacts"] = sorted(receipt["artifact_file_digests"])
        _emit(payload)
        return EXIT_OK

    if args.command == "status":
        job = adapter.load_job(args.host_job_id)
        terminal = adapter.store.get_terminal(args.host_job_id)
        _emit(
            {
                "host_job_id": job.host_job_id,
                "request_id": job.request_id,
                "submissions": adapter.store.submissions(args.host_job_id),
                "terminal_status": terminal.status if terminal else None,
                "approval_schema": APPROVAL_SCHEMA,
            }
        )
        return EXIT_OK
    return EXIT_REFUSED


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (ExternalAdmissionError, WaveEngineConfigurationError) as exc:
        print(json.dumps({"error": str(exc.args[0]) if exc.args else "REFUSED"}), file=sys.stderr)
        return EXIT_REFUSED
    except (ValidationError, sqlite3.Error, OSError, UnicodeError) as exc:
        # Closed refusal without a traceback; the message is withheld (it may echo inputs).
        print(json.dumps({"error": f"HOST_ERROR:{type(exc).__name__}"}), file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
