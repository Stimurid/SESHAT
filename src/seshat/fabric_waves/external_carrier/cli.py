"""Phase B host bridge CLI (dispatch / ingest stubs — trusted adapter not executed here)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASE_B_REQUEST = {
    "status": "PHASE_B_REQUIRED",
    "action": "trusted_host_adapter",
    "description": (
        "Implement credentialed Windows hub adapter that exports HostJobReceipt "
        "with compute_host_binding_hash verification; engine ingests only normalized "
        "AgentEvidenceReturn via resume_external_evidence."
    ),
    "cli_contract": {
        "dispatch": "seshat-fabric-external dispatch --request-json PATH",
        "ingest": "seshat-fabric-external ingest --receipt-json PATH --run-id ID",
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("phase-b-request", help="Emit machine-consumable Phase B dispatch request")
    dispatch = sub.add_parser("dispatch", help="PHASE_B_REQUIRED — not implemented")
    dispatch.add_argument("--request-json", type=Path, required=True)
    ingest = sub.add_parser("ingest", help="PHASE_B_REQUIRED — not implemented")
    ingest.add_argument("--receipt-json", type=Path, required=True)
    ingest.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "phase-b-request":
        print(json.dumps(PHASE_B_REQUEST, indent=2, sort_keys=True))
        return 0
    print(json.dumps(PHASE_B_REQUEST, indent=2, sort_keys=True), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
