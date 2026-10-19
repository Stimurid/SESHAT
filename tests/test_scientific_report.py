"""Synthetic source pages and separately authored, owner-admitted claim states."""
import hashlib

import pytest

from seshat.report_demo import (demo_request, install_fixture, synthetic_scientific_asset,
                                synthetic_source_contents, synthetic_method_bodies)
from seshat.batch import resume_batch, run_batch
from seshat.batch_demo import demo_manifest
from seshat.reports import artifacts, report_session
from seshat.scientific_report import AnchoredClaim, Subassembly
from seshat.scientific_report import render_markdown


def _compose(tmp_path):
    runtime = install_fixture(tmp_path, "meteorology")
    asset = synthetic_scientific_asset(runtime, "meteorology")
    request = demo_request("R01").model_copy(update={
        "expected_method_body_version": asset.method_body_version})
    compose = report_session(runtime, authenticated_caller="demo",
                             authorized_view="synthetic-public", scientific_assets=(asset,),
                             scientific_sources=synthetic_source_contents(runtime, asset),
                             method_bodies=synthetic_method_bodies())
    return runtime, asset, request, compose


def test_readable_report_has_two_separate_source_anchored_objects(tmp_path):
    runtime, asset, request, compose = _compose(tmp_path)
    report = compose(request)
    assert report.status == "SOURCE_GROUNDED_UNREVIEWED"
    files = artifacts(report)
    markdown = files["report.md"].decode()
    assert "Осадки в горном водосборе" in markdown
    assert "Температура прибрежного слоя" in markdown
    assert markdown.index("## 1.") < markdown.index("## 2.")
    assert "OWNER_AUTHORED_UNREVIEWED" in markdown
    assert "с. 1" in markdown
    assert files["report.html"].startswith(b"<!doctype html>")
    assert b"<h2>1." in files["report.html"]
    assert artifacts(report) == files
    assert b"SYNTHETIC PAGE" not in files["report.json"]
    assert hashlib.sha256(files["report.md"]).hexdigest() in files["receipt.json"].decode()
    changed = asset.model_copy(update={"research_problem": "Изменённый исходный вопрос"})
    other = report_session(runtime, authenticated_caller="demo",
                           authorized_view="synthetic-public", scientific_assets=(changed,),
                           scientific_sources=synthetic_source_contents(runtime, asset),
                           method_bodies=synthetic_method_bodies())(request)
    assert other.digest != report.digest


def test_missing_or_wrong_method_version_is_blocked(tmp_path):
    runtime, asset, request, _ = _compose(tmp_path)
    wrong = request.model_copy(update={"expected_method_body_version": "other"})
    report = report_session(runtime, authenticated_caller="demo",
                            authorized_view="synthetic-public", scientific_assets=(asset,),
                            scientific_sources=synthetic_source_contents(runtime, asset),
                            method_bodies=synthetic_method_bodies())(wrong)
    assert report.blocks[0].code == "BLOCKED_METHOD"
    assert "report.md" not in artifacts(report)
    stale = asset.model_copy(update={"currentness_as_of": "2020-01-01"})
    report = report_session(runtime, authenticated_caller="demo",
                            authorized_view="synthetic-public", scientific_assets=(stale,),
                            scientific_sources=synthetic_source_contents(runtime, asset),
                            method_bodies=synthetic_method_bodies())(request)
    assert report.blocks[0].code == "BLOCKED_METHOD"


def test_r02_uses_same_two_separate_claim_chains(tmp_path):
    runtime, asset, request, _ = _compose(tmp_path)
    r02 = request.model_copy(update={"report_id": "R02"})
    report = report_session(runtime, authenticated_caller="demo",
                            authorized_view="synthetic-public", scientific_assets=(asset,),
                            scientific_sources=synthetic_source_contents(runtime, asset),
                            method_bodies=synthetic_method_bodies())(r02)
    assert report.status == "SOURCE_GROUNDED_UNREVIEWED"
    assert len(report.scientific_asset.subassemblies) == 2
    assert "report.md" in artifacts(report)


def test_e5_stays_a_proposal(tmp_path):
    _, asset, _, _ = _compose(tmp_path)
    first = asset.subassemblies[0]
    proposal = first.claims[0].model_copy(update={"stage": "E5_PROPOSAL",
                                           "text": "Предлагается сравнение с будущей внешней выборкой."})
    changed = asset.model_copy(update={"subassemblies": (
        first.model_copy(update={"claims": (proposal,)}), asset.subassemblies[1])})
    markdown = render_markdown(changed)
    assert "E5_PROPOSAL" in markdown
    assert "не подтверждённую внешнюю новизну" in markdown


def test_source_drift_and_object_collapse_rejected(tmp_path):
    runtime, asset, request, _ = _compose(tmp_path)
    sub = asset.subassemblies[0]
    claim = sub.claims[0].model_copy(update={"source_sha256": "0" * 64})
    drift = asset.model_copy(update={"subassemblies": (
        sub.model_copy(update={"claims": (claim,)}), *asset.subassemblies[1:])})
    with pytest.raises(ValueError, match="SCIENTIFIC_SOURCE_CHANGED"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(drift,),
                       scientific_sources=synthetic_source_contents(runtime, asset),
                       method_bodies=synthetic_method_bodies())(request)
    with pytest.raises(ValueError, match="SCIENTIFIC_SOURCE_UNREADABLE"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(asset,), scientific_sources={},
                       method_bodies=synthetic_method_bodies())(request)
    with pytest.raises(ValueError, match="SCIENTIFIC_SOURCE_UNREADABLE"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(asset,),
                       scientific_sources={asset.source_member.carriers[0].carrier_id: b"wrong"},
                       method_bodies=synthetic_method_bodies())(request)
    with pytest.raises(ValueError, match="SCIENTIFIC_METHOD_UNREADABLE"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(asset,),
                       scientific_sources=synthetic_source_contents(runtime, asset))(request)
    with pytest.raises(ValueError, match="SCIENTIFIC_METHOD_UNREADABLE"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(asset,),
                       scientific_sources=synthetic_source_contents(runtime, asset),
                       method_bodies={asset.method_body_version: b"wrong"})(request)
    with pytest.raises(ValueError, match="CLAIM_OBJECT_COLLAPSE"):
        Subassembly(subassembly_id="one", functional_object="object", method="method",
                    material="material", result="result", counterexample_or_unknown="unknown",
                    claims=(AnchoredClaim(stage="E1_OBSERVATION", subassembly_id="two",
                                          text="text", carrier_id="c", source_version="1",
                                          source_sha256="0" * 64, page=1),))
    collapsed = asset.model_copy(update={"subassemblies": asset.subassemblies[:1]})
    with pytest.raises(ValueError, match="CLAIM_OBJECT_COLLAPSE"):
        report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                       scientific_assets=(collapsed,),
                       scientific_sources=synthetic_source_contents(runtime, asset),
                       method_bodies=synthetic_method_bodies())(request)


def test_scientific_batch_replay_verifies_markdown(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    runtime = install_fixture(source_dir, "meteorology")
    asset = synthetic_scientific_asset(runtime, "meteorology")
    manifest = demo_manifest("meteorology", runtime, batch_id="synthetic-fixed",
                             scientific_asset=asset)
    root = tmp_path / "batch"
    first = run_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
                      scientific_assets=(asset,),
                      scientific_sources=synthetic_source_contents(runtime, asset),
                      method_bodies=synthetic_method_bodies())
    assert (root / "items" / "r01-readable" / "report.md").is_file()
    again = resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
                         scientific_assets=(asset,),
                         scientific_sources=synthetic_source_contents(runtime, asset),
                         method_bodies=synthetic_method_bodies())
    assert [(i.item_id, i.state) for i in first.items] == [
        (i.item_id, i.state) for i in again.items]
    (root / "items" / "r01-readable" / "report.md").write_text("tampered", encoding="utf-8")
    repaired = resume_batch(root, manifest, runtime, caller_id="demo",
                            rights_scope="synthetic-public", scientific_assets=(asset,),
                            scientific_sources=synthetic_source_contents(runtime, asset),
                            method_bodies=synthetic_method_bodies())
    assert "tampered" not in (root / "items" / "r01-readable" / "report.md").read_text(
        encoding="utf-8")
    assert repaired.items[0].attempts > again.items[0].attempts
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="BATCH_MANIFEST_TAMPERED"):
        resume_batch(root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
                     scientific_assets=(asset,),
                     scientific_sources=synthetic_source_contents(runtime, asset),
                     method_bodies=synthetic_method_bodies())


@pytest.mark.parametrize("asset_change", [
    {"caller_id": "unauthorized-caller"},
    {"rights_scope": "other-tenant"},
    {"object_id": "unselected-research-object"},
])
def test_wrong_scientific_asset_authority_is_invisible(tmp_path, asset_change):
    runtime, asset, request, _ = _compose(tmp_path)
    baseline = report_session(runtime, authenticated_caller="demo",
                              authorized_view="synthetic-public")(request)
    denied = asset.model_copy(update={
        **asset_change, "producer_id": "PRIVATE_SCIENCE_MUST_NOT_LEAK"})
    report = report_session(
        runtime, authenticated_caller="demo", authorized_view="synthetic-public",
        scientific_assets=(denied,),
        scientific_sources=synthetic_source_contents(runtime, asset),
        method_bodies=synthetic_method_bodies(),
    )(request)
    assert report.status == "PARTIAL_METADATA"
    assert "report.md" not in artifacts(report)
    assert artifacts(report) == artifacts(baseline)
    for raw in artifacts(report).values():
        assert b"PRIVATE_SCIENCE_MUST_NOT_LEAK" not in raw


def test_multiple_visible_scientific_assets_fail_closed(tmp_path):
    runtime, asset, request, _ = _compose(tmp_path)
    baseline = report_session(runtime, authenticated_caller="demo",
                              authorized_view="synthetic-public")(request)
    conflicting = asset.model_copy(update={
        "analytic_state_version": "different-and-unreviewed",
        "producer_id": "PRIVATE_DUPLICATE_DO_NOT_RENDER"})
    report = report_session(
        runtime, authenticated_caller="demo", authorized_view="synthetic-public",
        scientific_assets=(asset, conflicting),
        scientific_sources=synthetic_source_contents(runtime, asset),
        method_bodies=synthetic_method_bodies(),
    )(request)
    assert report.status == "PARTIAL_METADATA"
    assert "report.md" not in artifacts(report)
    assert artifacts(report) == artifacts(baseline)
    for raw in artifacts(report).values():
        assert b"PRIVATE_DUPLICATE_DO_NOT_RENDER" not in raw


def test_science_asset_after_rights_revocation_cannot_render(tmp_path):
    import json
    from seshat.corpus_host import HostConfiguration
    from seshat.report_demo import pin_package

    runtime, asset, request, compose = _compose(tmp_path)
    assert compose(request).status == "SOURCE_GROUNDED_UNREVIEWED"
    cfg = runtime._configuration
    rights = json.loads(cfg.rights.path.read_text(encoding="utf-8"))
    rights["epoch"] = "after-access-revocation"
    for grant in rights["grants"]:
        grant["object_ids"] = []
        grant["carrier_ids"] = []
    runtime.install(HostConfiguration(
        host_id=cfg.host_id, primary=cfg.primary,
        rights=pin_package(tmp_path / "rights-revoked.json", rights),
        temporal=cfg.temporal,
    ))
    with pytest.raises(ValueError, match="R01_REQUIRES_ONE_RESEARCH_OBJECT"):
        compose(request)


def test_owner_assertion_cannot_forge_verified_synthetic_locator(tmp_path):
    runtime, asset, request, _ = _compose(tmp_path)
    first = asset.subassemblies[0]
    forged = first.claims[0].model_copy(
        update={"page_locator_state": "VERIFIED_IN_SYNTHETIC_SOURCE"}
    )
    bad = asset.model_copy(update={"subassemblies": (
        first.model_copy(update={"claims": (forged,)}), *asset.subassemblies[1:],
    )})
    with pytest.raises(ValueError, match="SCIENTIFIC_LOCATOR_UNVERIFIED"):
        report_session(
            runtime, authenticated_caller="demo", authorized_view="synthetic-public",
            scientific_assets=(bad,),
            scientific_sources=synthetic_source_contents(runtime, asset),
            method_bodies=synthetic_method_bodies(),
        )(request)
