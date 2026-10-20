"""Public SYNTHETIC G1 -> F07 -> F08 -> F09A owner-private CLI demonstration.

No medical source, real author MethodBody, network agent or customer release.
Run with a NEW output directory below a trusted owner-controlled parent:
python -m seshat.fabric_waves.report_bridge_demo --output /tmp/owner-demo
"""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from seshat.batch import assert_safe_path, resume_batch, run_batch
from seshat.batch_demo import demo_manifest
from seshat.contracts import AcceptanceState
from seshat.fabric_waves.contracts import (
    EpistemicLevel, StoneEvent, StoneEventKind, WaveBudget,
)
from seshat.fabric_waves.method_body import BodyResult
from seshat.fabric_waves.report_bridge import project_fabric_r01_r02
from seshat.fabric_waves.scenarios import bundle, engine_for, source_store
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash
from seshat.report_demo import (
    demo_request, install_fixture, write_artifacts,
)
from seshat.reports import artifacts


SYNTHETIC_METHOD_DEFINITION = (
    b"SYNTHETIC ONLY: separate the two PAGE-tagged source observations; "
    b"retain exact evidence excerpts; report unsupported claims as unknown."
)


def _synthetic_source_method(object_id: str, carrier_id: str):
    """Return a deterministic in-process MethodBody with no prewritten findings."""

    def method(inv):
        source_text = inv.carried_payload["text"]
        if not source_text.startswith("SYNTHETIC PAGE 1:"):
            return BodyResult(aporia="SYNTHETIC_SOURCE_FORMAT_REQUIRED")
        first = source_text.splitlines()[1]
        second = source_text.split("SYNTHETIC PAGE 2:", 1)[1].splitlines()[0].strip()
        assemblies = []
        for n, excerpt in ((1, first), (2, second)):
            fields = [item.strip().rstrip(".") for item in excerpt.split(";")]
            if len(fields) != 3:
                return BodyResult(aporia="SYNTHETIC_SOURCE_FIELDS_INVALID")
            assemblies.append({
                "subassembly_id": f"observation-{n}",
                "functional_object": fields[0],
                "method": fields[1],
                "material": "синтетическая исследовательская запись",
                "result": fields[2],
                "counterexample_or_unknown": (
                    "Область применимости к другим измерениям не установлена."
                ),
                "claims": [{
                    "page": n,
                    "text": f"Страница источника отдельно описывает {fields[0]}.",
                    "evidence_excerpt": excerpt,
                }],
            })
        payload = {
            "protocol": "seshat.fabric.r01.source_reconstruction.v1",
            "research_problem": (
                "Какие различные наблюдения и измерительные операции "
                "описаны в двух страницах синтетического источника?"
            ),
            "author_scope": "Авторство отдельных измерений не подтверждается источником.",
            "subassemblies": assemblies,
        }
        digest = payload_hash(payload)
        return BodyResult(produced_sediments=(SedimentRecord(
            sediment_id="synthetic-r01-proven",
            object_type="science.reconstruction.v1",
            version=digest,
            research_object_id=object_id,
            payload=payload,
            payload_hash=digest,
            provenance=("PUBLIC_SYNTHETIC_TWO_PAGE_OPERATION",),
            method_body_refs=(inv.method_body_ref,),
            source_carrier_refs=(carrier_id,),
            read_dependencies=inv.consumed_sediment_ids,
            produced_by_thread=inv.thread_id,
            produced_at_tick=inv.tick,
            produced_in_wave=inv.wave_index,
            produced_by_stone_kind=inv.stone_kind,
            epistemic_level=EpistemicLevel.E1,
            acceptance_state=AcceptanceState.WORKING,
        ),))

    return method


def run_demo(root: Path) -> dict[str, str]:
    root = assert_safe_path(root, must_not_exist=True)
    if not root.parent.is_dir():
        raise ValueError("SYNTHETIC_REPORT_PARENT_MISSING")
    root.mkdir()
    with TemporaryDirectory(prefix="seshat-fabric-bridge-synthetic-") as d:
        original_dir = Path(d)
        runtime = install_fixture(original_dir, "meteorology")
        request = demo_request("R01")
        member = runtime.session(
            authenticated_caller="demo", authorized_view="synthetic-public"
        )(request.selections[0]).members[0]
        carrier = member.carriers[0]
        source = (original_dir / f"{carrier.carrier_id}.txt").read_bytes()
        engine = engine_for([
            bundle(
                "synthetic-r01-proven",
                _synthetic_source_method(member.object_id, carrier.carrier_id),
                source=carrier.carrier_id,
                output_sediment_type="science.reconstruction.v1",
            )
        ], source_store({carrier.carrier_id: source.decode("utf-8")}))
        run = engine.run(
            run_id="synthetic-method-run-r01",
            budget=WaveBudget(max_waves=12, max_activations=12, max_stone_events=12),
            initial_stone=StoneEvent(
                event_id="synthetic-operator-question", kind=StoneEventKind.QUERY,
                issued_at_tick=0, target_research_object_id=member.object_id,
                payload={"topic": "two-independent-source-observations"},
            ),
        )
        if not run.sediment_final_versions.get("synthetic-r01-proven"):
            raise ValueError("SYNTHETIC_G1_DID_NOT_PRODUCE_RECORD")
        contents = {carrier.carrier_id: source}
        projection, proof = project_fabric_r01_r02(
            runtime=runtime, authenticated_caller="demo",
            authorized_view="synthetic-public", request=request,
            engine=engine, run_id=run.run_id, sediment_id="synthetic-r01-proven",
            source_contents=contents,
            method_definition=SYNTHETIC_METHOD_DEFINITION,
            rights_basis="public-synthetic-method-fixture",
            locator_verifier="SYNTHETIC_PAGE_TAG_V1",
        )
        write_artifacts(root / "report", artifacts(projection))
        asset = projection.scientific_asset
        if asset is None:
            raise ValueError("SYNTHETIC_G1_REPORT_MISSING_ASSET")
        manifest = demo_manifest("meteorology", runtime,
                                 batch_id="fabric-synthetic-r01", scientific_asset=asset)
        receipt = run_batch(
            root / "owner-private-batch", manifest, runtime,
            caller_id="demo", rights_scope="synthetic-public",
            scientific_assets=(asset,), scientific_sources=contents,
            method_bodies={asset.method_body_version: SYNTHETIC_METHOD_DEFINITION},
        )
        if not receipt.code_pass or receipt.scientific_accepted != "NEVER_AUTO_SET":
            raise ValueError("SYNTHETIC_G1_F09A_NOT_CODE_COMPLETE")
        # The DEMO itself must exercise a durable no-op restart, not merely
        # rely on a separate test that calls resume_batch.
        original_bytes = (root / "owner-private-batch" / "batch_receipt.json").read_bytes()
        resumed = resume_batch(
            root / "owner-private-batch", manifest, runtime,
            caller_id="demo", rights_scope="synthetic-public",
            scientific_assets=(asset,), scientific_sources=contents,
            method_bodies={asset.method_body_version: SYNTHETIC_METHOD_DEFINITION},
        )
        if (
            resumed != receipt
            or (root / "owner-private-batch" / "batch_receipt.json").read_bytes()
               != original_bytes
        ):
            raise ValueError("SYNTHETIC_G1_F09A_RESUME_CHANGED")
        return {
            "mode": "PUBLIC_SYNTHETIC_ONLY",
            "bridge": "G1_METHOD_ACTIVATED_TO_F07_F08_F09A",
            "run_id": proof.run_id,
            "fabric_sediment_version": proof.sediment_version,
            "report_digest": proof.report_projection_digest,
            "r01": "report/report.md",
            "private_batch": "owner-private-batch",
            "batch_resume": "VERIFIED_NOOP",
            "science_owner_review": "NOT_PERFORMED",
            "customer_release": "NOT_AUTHORIZED",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    import json

    result = run_demo(args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
