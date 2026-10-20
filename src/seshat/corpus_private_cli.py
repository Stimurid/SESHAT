"""Owner-launched private v4 evaluation, after review, in a safe offline runner.

Invocation: python -m seshat.corpus_private_cli --config /private/run.json
  --config-sha256 <independently approved SHA> --host-id <owner host>
All input files must be outside the source checkout. No output files, network,
PDFs, MethodBodies, per-study logs or caller-supplied Python callbacks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import Field

from seshat.corpus import FrozenModel
from seshat.corpus_evaluation import PrivateV4Contract, compare_real_v4_metadata
from seshat.corpus_host import FilePin, RightsPackage, _Rights, read_pinned


class OwnerEvaluationConfiguration(FrozenModel):
    host_id: str = Field(min_length=1)
    master: FilePin
    intake: FilePin
    contract: FilePin
    rights: FilePin
    caller_id: str = Field(min_length=1)
    view_id: str = Field(min_length=1)


def evaluate_owner_run(config_pin: FilePin, *, expected_host_id: str) -> dict:
    """Private control-plane API, not an HTTP/public caller verification route.

    Bootstrap SHA and host identity must come from owner deployment, never
    from the party submitting a selector. Return only bounded status data.
    """
    try:
        source_root = Path(__file__).resolve().parents[2]

        def private_path(pin):
            path = pin.path.resolve()
            if not pin.path.is_absolute() or path.is_relative_to(source_root):
                raise ValueError

        private_path(config_pin)
        config = OwnerEvaluationConfiguration.model_validate_json(read_pinned(config_pin))
        if config.host_id != expected_host_id:
            raise ValueError
        for pin in (config.master, config.intake, config.contract, config.rights):
            private_path(pin)
        # Read and validate the contract and independent rights before execution.
        contract = PrivateV4Contract.model_validate_json(read_pinned(config.contract))
        rights = RightsPackage.model_validate_json(read_pinned(config.rights))
        if rights.host_id != expected_host_id:
            raise ValueError
        if (config.master.sha256 != contract.master_sha256
                or config.intake.sha256 != contract.intake_sha256):
            raise ValueError
        if len({(g.caller_id, g.view_id) for g in rights.grants}) != len(rights.grants):
            raise ValueError
        grant = next((g for g in rights.grants if (g.caller_id, g.view_id)
                      == (config.caller_id, config.view_id)), None)
        if grant is None:
            raise ValueError
        read_pinned(config.master)
        read_pinned(config.intake)
        comparison = compare_real_v4_metadata(
            config.master.path, config.intake.path, contract, _Rights(grant),
            caller_id=config.caller_id, view_id=config.view_id)
        # Catch policy changes during evaluation before emitting a pass.
        read_pinned(config.rights)
        read_pinned(config_pin)
        return {"REAL_V4_RUN": "REAL_V4_PASS", "selectors_compared": comparison.selectors_compared,
                "package_state": "SOURCE_PACKAGE_INTEGRITY_VERIFIED",
                "original_source_fact_state": "NOT_VERIFIED",
                "identity_qa_pending": 4, "identity_qa_state": "NOT_CLEARED_BY_METADATA",
                "semantic_acceptance_state": "NOT_ASSERTED", "raw_access_state": "NOT_READ"}
    except FileNotFoundError:
        return {"REAL_V4_RUN": "BLOCKED_SOURCE_ACCESS"}
    except Exception:
        return {"REAL_V4_RUN": "BLOCKED_OR_MISMATCH"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--host-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_owner_run(FilePin(path=args.config, sha256=args.config_sha256),
                                    expected_host_id=args.host_id)
    except Exception:
        result = {"REAL_V4_RUN": "BLOCKED_OR_MISMATCH"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["REAL_V4_RUN"] == "REAL_V4_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
