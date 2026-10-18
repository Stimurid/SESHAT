"""Offline F09A1 batch demo: python -m seshat.batch_demo --fixture HOST --output NEW_DIR [--resume]."""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from seshat.batch import (
    BatchItemSpec,
    BatchManifest,
    cancel_batch,
    resume_batch,
    run_batch,
    source_pins_from_runtime,
    status_batch,
)
from seshat.corpus import _digest
from seshat.report_demo import (demo_request, install_fixture, synthetic_scientific_asset,
                                synthetic_source_contents, synthetic_method_bodies)


def demo_manifest(host: str, runtime, batch_id: str | None = None,
                  scientific_asset=None) -> BatchManifest:
    pins = source_pins_from_runtime(runtime)
    bid = batch_id or f"demo-{host}-{uuid.uuid4().hex[:12]}"
    items = (
        BatchItemSpec(item_id="r03-corpus", request=demo_request("R03")),
        BatchItemSpec(item_id="r02-method-graph", request=demo_request("R02")),
        BatchItemSpec(item_id="r05-external-blocked", request=demo_request("R05")),
        BatchItemSpec(item_id="r01-individual", request=demo_request("R01")),
    )
    if scientific_asset is not None:
        request = demo_request("R01").model_copy(update={
            "expected_method_body_version": scientific_asset.method_body_version})
        items = (BatchItemSpec(item_id="r01-readable", request=request),
                 BatchItemSpec(item_id="r03-corpus", request=demo_request("R03")),
                 BatchItemSpec(item_id="r05-external-blocked", request=demo_request("R05")))
    return BatchManifest(
        batch_id=bid,
        host_id=host,
        caller_id="demo",
        rights_scope="synthetic-public",
        source_pins=pins,
        scientific_asset_digests=(_digest(scientific_asset),) if scientific_asset else (),
        items=items,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic offline durable batch demonstration")
    parser.add_argument("--fixture", choices=("sechenovka-like", "meteorology"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--scientific", action="store_true")
    parser.add_argument("--cancel", action="store_true", help="Cancel queued work on existing batch")
    parser.add_argument("--status", action="store_true", help="Print status and exit")
    args = parser.parse_args(argv)

    if args.status or args.cancel:
        if not args.output.is_dir():
            print("BATCH_NOT_FOUND", file=sys.stderr)
            return 2
        if args.cancel:
            cancel_batch(args.output)
        st = status_batch(args.output)
        print(st.model_dump_json(indent=2))
        return 0

    manifest_path = args.output / "manifest.json"
    with TemporaryDirectory(prefix="seshat-batch-fixture-") as scratch:
        runtime = install_fixture(Path(scratch), args.fixture)
        asset = synthetic_scientific_asset(runtime, args.fixture) if args.scientific else None
        assets = (asset,) if asset else ()
        source_contents = synthetic_source_contents(runtime, asset) if asset else {}
        if args.resume:
            if not manifest_path.is_file():
                print("BATCH_RESUME_MISSING_MANIFEST", file=sys.stderr)
                return 2
            manifest = BatchManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            if manifest.host_id != args.fixture:
                print("BATCH_HOST_MISMATCH", file=sys.stderr)
                return 2
            resume_batch(args.output, manifest, runtime, caller_id="demo",
                         rights_scope="synthetic-public", scientific_assets=assets,
                         scientific_sources=source_contents,
                         method_bodies=synthetic_method_bodies()
                         if asset else {})
        else:
            manifest = demo_manifest(args.fixture, runtime, scientific_asset=asset)
            run_batch(args.output, manifest, runtime, resume=False, caller_id="demo",
                      rights_scope="synthetic-public", scientific_assets=assets,
                      scientific_sources=source_contents,
                      method_bodies=synthetic_method_bodies()
                      if asset else {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
