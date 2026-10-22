"""Runnable *non-model* owner-local, no-service SESHAT MethodBody smoke test.

Two completely invented fixtures, private SQLite receipt, fresh-process
readback. Never submits a paid agent job or processes protected sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from seshat.fabric_waves.operator_builtin_method import execute_literal_method
from seshat.fabric_waves.operator_methodbody import (
    OperatorMethodBodyPin,
    OperatorSourcePin,
    invoke_operator_method_body,
    replay_and_verify_operator_run,
)
from seshat.fabric_waves.operator_sqlite_ledger import SQLiteOperatorRunLedger
from seshat.fabric_waves.operator_private_reports import (
    compose_private_operator_r01r02, verify_private_operator_r01r02,
)

FIXTURES = {
    "materials": (
        "INVENTED MATERIAL STUDY\nCompound: alloy\nCheck: heat and fracture.\n",
        "alloy",
    ),
    "organization": (
        "INVENTED WORKFLOW CSV\nstage,operator,result\ntriage,team,reviewed\n",
        "triage",
    ),
}


def inputs(fixture: str):
    if fixture not in FIXTURES:
        raise ValueError("OPERATOR_FIXTURE_UNKNOWN")
    content, needle = FIXTURES[fixture]
    source_bytes = content.encode("utf-8")
    method_bytes = json.dumps({
        "schema": "SESHAT_OPERATOR_METHOD_V1",
        "operation": "literal_span_find",
        "needle": needle,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    source = OperatorSourcePin(
        source_id=f"public-invented-{fixture}",
        source_version="invented-v1",
        sha256=hashlib.sha256(source_bytes).hexdigest(),
        rights_basis="operator-created-public-test-fixture",
        authorized_view="private-operator",
    )
    method = OperatorMethodBodyPin(
        method_body_id="seshat.generic.literal_span_find",
        version="1",
        invocation_body_sha256=hashlib.sha256(method_bytes).hexdigest(),
    )
    return source, source_bytes, method, method_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description="No-service SESHAT operator local smoke test")
    parser.add_argument("--fixture", choices=tuple(FIXTURES), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--private-report", action="store_true", help="produce/readback owner-private R01/R02 preview")
    opts = parser.parse_args(argv)
    opts.out.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteOperatorRunLedger(opts.out / "runs.sqlite")
    source, src_bytes, method, method_bytes = inputs(opts.fixture)
    run_id = f"local-demo-{opts.fixture}"
    if opts.verify_only:
        receipt = replay_and_verify_operator_run(
            ledger=ledger, run_id=run_id, source_bytes=src_bytes,
            method_body_invocation_bytes=method_bytes,
        )
        result = {"status": "READBACK_VERIFIED_SELF_OBSERVED",
                  "run_id": run_id, "digest": receipt.output_digest}
    else:
        receipt = invoke_operator_method_body(
            ledger=ledger, run_id=run_id, job_id=f"local-{opts.fixture}",
            source=source, source_bytes=src_bytes, method=method,
            method_body_invocation_bytes=method_bytes,
            method_callable=execute_literal_method,
            requested_view="private-operator",
            declared_model_identity="deterministic-local-method-no-LLM",
            owner_excluded_source_ids=frozenset(),
            owner_excluded_source_sha256=frozenset(),
        )
        result = {"status": "EXECUTED_OR_RESUMED_SELF_OBSERVED",
                  "run_id": run_id, "digest": receipt.output_digest,
                  "method_hash": receipt.method_body_invocation_sha256,
                  "source_hash": receipt.source_sha256,
                  "output_state": str(receipt.output_sediment.acceptance_state),
                  "provenance": receipt.provenance,
                  "claim_count": len(receipt.output_sediment.payload["claims"])}
    if opts.private_report:
        preview = compose_private_operator_r01r02(
            receipt, ledger=ledger, source_bytes=src_bytes,
            method_invocation_bytes=method_bytes,
        )
        preview_path = opts.out / "private_r01r02.json"
        if preview_path.exists():
            stored = json.loads(preview_path.read_text(encoding="utf-8"))
            verify_private_operator_r01r02(
                stored, receipt, ledger=ledger, source_bytes=src_bytes,
                method_invocation_bytes=method_bytes,
            )
            result["preview_status"] = "VERIFIED_EXISTING_PRIVATE"
        elif opts.verify_only:
            raise ValueError("OPERATOR_R01R02_PRIVATE_RECEIPT_MISSING")
        else:
            # Exclusive creation prevents silently overwriting forged receipt
            # bytes on a repeated local run. This is not a public artifact.
            with preview_path.open("x", encoding="utf-8") as sink:
                sink.write(json.dumps(preview, ensure_ascii=False, sort_keys=True, indent=2))
                sink.flush()
                import os
                os.fsync(sink.fileno())
            result["preview_status"] = "CREATED_PRIVATE"
        result["preview_sha256"] = preview["projection_sha256"]
        result["preview_path"] = str(preview_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
