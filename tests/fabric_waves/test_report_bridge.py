"""Real G1 synthetic MethodBody -> F07 admitted source -> F08 readable report."""

import json

import pytest

from seshat.contracts import AcceptanceState, RawAccessPolicy
from seshat.corpus_host import HostConfiguration
from seshat.fabric_waves.contracts import EpistemicLevel, StoneEvent, StoneEventKind, WaveBudget
from seshat.fabric_waves.method_body import BodyResult
from seshat.fabric_waves.report_bridge import project_fabric_r01_r02
from seshat.fabric_waves.scenarios import bundle, engine_for, source_store
from seshat.fabric_waves.sediment import SedimentRecord, payload_hash
from seshat.report_demo import demo_request, install_fixture, pin_package
from seshat.reports import artifacts


def setup_run(tmp_path, *, false_claim=False, false_page=False, epistemic=EpistemicLevel.E1):
    fixture = tmp_path / "host"
    fixture.mkdir()
    runtime = install_fixture(fixture, "meteorology")
    request = demo_request("R01")
    member = runtime.session(authenticated_caller="demo", authorized_view="synthetic-public")(
        request.selections[0]
    ).members[0]
    carrier = member.carriers[0]
    source_bytes = (fixture / f"{carrier.carrier_id}.txt").read_bytes()

    def actual_synthetic_method(invocation):
        text = invocation.carried_payload["text"]
        assert text.startswith("SYNTHETIC PAGE 1:")
        first_excerpt = text.splitlines()[1]
        second_excerpt = text.split("SYNTHETIC PAGE 2:", 1)[1].splitlines()[0].strip()
        entries = ((1, first_excerpt), (2, second_excerpt))
        assemblies = []
        for page, excerpt in entries:
            columns = [c.strip().rstrip(".") for c in excerpt.split(";")]
            assert len(columns) == 3
            assemblies.append({
                "subassembly_id": f"component-{page}",
                "functional_object": columns[0],
                "material": "синтетическое наблюдение",
                "method": columns[1],
                "result": columns[2],
                "counterexample_or_unknown": "Результат других наблюдений не установлен.",
                "claims": [{
                    "page": 99 if false_page else page,
                    "text": f"По отдельной исходной записи исследуется {columns[0]}.",
                    "evidence_excerpt": "NOT-IN-SOURCE" if false_claim else excerpt,
                }],
            })
        payload = {
            "protocol": "seshat.fabric.r01.source_reconstruction.v1",
            "research_problem": "Чем различаются осадки и температура на двух синтетических страницах?",
            "author_scope": "Авторство измерений по синтетическому тексту не установлено.",
            "subassemblies": assemblies,
        }
        digest = payload_hash(payload)
        return BodyResult(produced_sediments=(SedimentRecord(
            sediment_id="synthetic-r01", object_type="science.reconstruction.v1",
            version=digest, research_object_id=member.object_id,
            payload=payload, payload_hash=digest, provenance=("PUBLIC_SYNTHETIC_METHOD",),
            method_body_refs=(invocation.method_body_ref,),
            source_carrier_refs=(carrier.carrier_id,),
            read_dependencies=invocation.consumed_sediment_ids,
            produced_by_thread=invocation.thread_id,
            produced_at_tick=invocation.tick,
            produced_in_wave=invocation.wave_index,
            produced_by_stone_kind=invocation.stone_kind,
            epistemic_level=epistemic,
            acceptance_state=AcceptanceState.WORKING,
        ),))

    engine = engine_for([
        bundle(
            "synthetic-r01", actual_synthetic_method,
            source=carrier.carrier_id, output_sediment_type="science.reconstruction.v1"
        )
    ], source_store({carrier.carrier_id: source_bytes.decode("utf-8")}))
    run = engine.run(
        run_id="synthetic-fabric-r01", budget=WaveBudget(
            max_waves=12, max_activations=12, max_stone_events=12,
        ),
        initial_stone=StoneEvent(
            event_id="synthetic-research-stone", kind=StoneEventKind.QUERY,
            issued_at_tick=0, target_research_object_id=member.object_id,
            payload={"topic": "two-source-positions"},
        ),
    )
    assert run.activations_total == 1
    source_contents = {carrier.carrier_id: source_bytes}
    kwargs = dict(
        runtime=runtime, authenticated_caller="demo", authorized_view="synthetic-public",
        request=request, engine=engine, run_id=run.run_id, sediment_id="synthetic-r01",
        source_contents=source_contents,
        method_definition=b"PUBLIC_SYNTHETIC_METHOD_R01_V1",
        rights_basis="public-synthetic-text-fixture",
    )
    return runtime, engine, carrier, kwargs


def test_actual_fabric_method_invocation_makes_readable_report(tmp_path):
    _, engine, carrier, kwargs = setup_run(tmp_path)
    report, receipt = project_fabric_r01_r02(**kwargs)
    assert report.status == "SOURCE_GROUNDED_UNREVIEWED"
    assert report.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.registered_method_id == "synthetic.synthetic-r01"
    assert receipt.source_carrier_id == carrier.carrier_id
    assert receipt.ledger_head_sha256 == engine.snapshot(receipt.run_id)[0].head_hash
    assert len(report.scientific_asset.subassemblies) == 2
    files = artifacts(report)
    readable = files["report.md"].decode("utf-8")
    assert "FABRIC_GENERATED_UNREVIEWED" in readable
    assert "Осадки в горном водосборе" in readable
    assert "Температура прибрежного слоя" in readable
    assert "VERIFIED_IN_SYNTHETIC_SOURCE" in readable
    assert "с. 1" in readable and "с. 2" in readable
    assert receipt.report_projection_digest == report.digest


def test_report_bridge_reproduces_exact_same_output(tmp_path):
    _, _, _, kwargs = setup_run(tmp_path)
    a = project_fabric_r01_r02(**kwargs)
    b = project_fabric_r01_r02(**kwargs)
    assert artifacts(a[0]) == artifacts(b[0])
    assert a[1] == b[1]


@pytest.mark.parametrize("bad", [
    "fake-run", "fake-sediment", "wrong-research-selection", "missing-method",
    "wrong-policy", "tampered-source", "source-revoked", "missing-receipt",
])
def test_fabric_bridge_fails_closed(tmp_path, bad):
    runtime, engine, carrier, kwargs = setup_run(tmp_path)
    if bad == "fake-run":
        kwargs["run_id"] = "nonexistent-run"
        failure = "FABRIC_LEDGER_UNVERIFIED"
    elif bad == "fake-sediment":
        kwargs["sediment_id"] = "imaginary-sediment"
        failure = "FABRIC_SEDIMENT_NOT_PROVEN"
    elif bad == "wrong-research-selection":
        req = kwargs["request"]
        sel = req.selections[0]
        sel = sel.model_copy(update={"predicate":sel.predicate.model_copy(
            update={"ids": ("synthetic-3",)})})
        kwargs["request"] = req.model_copy(update={"selections":(sel,)})
        failure = "FABRIC_SEDIMENT_STALE_OR_INCOMPATIBLE"
    elif bad == "missing-method":
        engine.bodies._bodies.clear()
        failure = "FABRIC_METHOD_POLICY_DENIED"
    elif bad == "wrong-policy":
        spec = engine.thread_specs["synthetic-r01"]
        engine.thread_specs["synthetic-r01"] = spec.model_copy(
            update={"raw_access_policy": RawAccessPolicy.NEVER})
        failure = "FABRIC_METHOD_POLICY_DENIED"
    elif bad == "tampered-source":
        kwargs["source_contents"] = {carrier.carrier_id: b"incorrect bytes"}
        failure = "FABRIC_SOURCE_BYTES_STALE"
    elif bad == "source-revoked":
        engine.carrier_store.revoke_content_same_version(carrier.carrier_id)
        failure = "FABRIC_SOURCE_STORE_STALE"
    elif bad == "missing-receipt":
        # A missing G1 MethodBody activation is not equivalent to a printed hash.
        snap = engine._snapshots[kwargs["run_id"]]
        snap[0]._activations.clear()
        failure = "FABRIC_LEDGER_UNVERIFIED"
    with pytest.raises(ValueError, match=failure):
        project_fabric_r01_r02(**kwargs)


@pytest.mark.parametrize("false_claim,false_page", [
    (True, False), (False, True),
])
def test_fabric_claim_needs_source_excerpt_and_page(tmp_path, false_claim, false_page):
    _, _, _, kwargs = setup_run(
        tmp_path, false_claim=false_claim, false_page=false_page)
    failure = "FABRIC_CLAIM_NOT_IN_SOURCE" if false_claim else "FABRIC_CLAIM_PAGE_INVALID"
    with pytest.raises(ValueError, match=failure):
        project_fabric_r01_r02(**kwargs)


def test_e5_remains_a_proposal_even_when_text_report_exists(tmp_path):
    _, _, _, kwargs = setup_run(tmp_path, epistemic=EpistemicLevel.E5)
    report, _ = project_fabric_r01_r02(**kwargs)
    assert report.scientific_acceptance == "NOT_ASSERTED"
    assert report.scientific_asset.review_status == "FABRIC_GENERATED_UNREVIEWED"
    assert all(claim.stage == "E5_PROPOSAL"
               for sub in report.scientific_asset.subassemblies for claim in sub.claims)
    assert b"ACCEPTED" not in artifacts(report)["report.md"]


def test_f07_revocation_after_fabric_run_blocks_readable_report(tmp_path):
    runtime, _, _, kwargs = setup_run(tmp_path)
    cfg = runtime._configuration
    rights = json.loads(cfg.rights.path.read_text(encoding="utf-8"))
    rights["epoch"] = "revoked"
    for grant in rights["grants"]:
        grant["object_ids"] = []
        grant["carrier_ids"] = []
    runtime.install(HostConfiguration(
        host_id=cfg.host_id, primary=cfg.primary,
        rights=pin_package(tmp_path / "rights-revoked.json", rights),
        temporal=cfg.temporal,
    ))
    with pytest.raises(ValueError, match="FABRIC_REPORT_SELECTION_NOT_SINGLE"):
        project_fabric_r01_r02(**kwargs)



def test_fabric_r01_passes_through_durable_f09a_batch_without_science_promotion(tmp_path):
    from seshat.batch import resume_batch, run_batch, status_batch
    from seshat.batch_demo import demo_manifest

    runtime, _, _, kwargs = setup_run(tmp_path)
    report, bridge_receipt = project_fabric_r01_r02(**kwargs)
    asset = report.scientific_asset
    assert asset is not None and bridge_receipt.scientific_acceptance == "NOT_ASSERTED"
    manifest = demo_manifest(
        "meteorology", runtime, batch_id="real-fabric-into-f09a-synthetic",
        scientific_asset=asset,
    )
    root = tmp_path / "owner-private-fabric-batch"
    emitted = run_batch(
        root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
        scientific_assets=(asset,), scientific_sources=dict(kwargs["source_contents"]),
        method_bodies={asset.method_body_version: kwargs["method_definition"]},
    )
    assert emitted.code_pass is True
    assert emitted.scientific_accepted == "NEVER_AUTO_SET"
    assert emitted.items[0].state == "DONE_SCIENTIFIC_UNREVIEWED"
    narrative = (root / "items/r01-readable/report.md").read_bytes()
    assert narrative == artifacts(report)["report.md"]
    initial_index = (root / "index.json").read_bytes()
    initial_receipt = (root / "batch_receipt.json").read_bytes()
    before_attempts = status_batch(root).items[0].attempts
    resumed = resume_batch(
        root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
        scientific_assets=(asset,), scientific_sources=dict(kwargs["source_contents"]),
        method_bodies={asset.method_body_version: kwargs["method_definition"]},
    )
    assert resumed.items[0].attempts == before_attempts
    assert (root / "index.json").read_bytes() == initial_index
    assert (root / "batch_receipt.json").read_bytes() == initial_receipt
    assert (root / "manifest.json").is_file()
    assert b"rights_sha256" not in narrative
    assert b"scientific_accepted" not in narrative



def test_same_real_fabric_evidence_projects_into_r02_without_promoting_science(tmp_path):
    _, _, _, kwargs = setup_run(tmp_path)
    original_request = kwargs["request"]
    kwargs["request"] = original_request.model_copy(update={"report_id": "R02"})
    report, receipt = project_fabric_r01_r02(**kwargs)
    assert report.report_id == "R02"
    assert report.status == "SOURCE_GROUNDED_UNREVIEWED"
    assert report.scientific_acceptance == "NOT_ASSERTED"
    assert receipt.report_projection_digest == report.digest
    assert len(report.scientific_asset.subassemblies) == 2
    assert b"FABRIC_GENERATED_UNREVIEWED" in artifacts(report)["report.md"]
