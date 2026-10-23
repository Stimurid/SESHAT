"""Real F09A serial wiring tests over the synthetic F08/I11 corpus only."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

from seshat.batch import BatchItemSpec, resume_batch, run_batch, status_batch
from seshat.batch_demo import demo_manifest
from seshat.f09a_i11_r03_bridge import (
    F09AI11R03BridgeError,
    F09AI11R03StaleBundle,
    I11R03BatchBundle,
    InProcessI11R03Provider,
)
from seshat.report_demo import demo_request, install_fixture


# Reuse the existing verified-byte gate fixture through a path-bound import.  This
# avoids relying on an ambient ``tests`` package, which may be shadowed by a tool.
_support_spec = importlib.util.spec_from_file_location(
    "_seshat_i11_f08_fixture",
    Path(__file__).parent / "fabric_waves" / "test_i11_r03_report_adapter.py",
)
assert _support_spec is not None and _support_spec.loader is not None
_support = importlib.util.module_from_spec(_support_spec)
_support_spec.loader.exec_module(_support)


def _runtime_manifest(tmp_path: Path, batch_id: str, *, two_items: bool = False):
    fixture = tmp_path / f"fixture-{batch_id}"
    fixture.mkdir()
    runtime = install_fixture(fixture, "sechenovka-like")
    manifest = demo_manifest("sechenovka-like", runtime, batch_id=batch_id)
    items = [BatchItemSpec(item_id="r03-one", request=demo_request("R03"))]
    if two_items:
        items.append(BatchItemSpec(item_id="r03-two", request=demo_request("R03")))
    return runtime, manifest.model_copy(update={"items": tuple(items)})


def _gated_bundle(monkeypatch, item_id="r03-one", *, authorized=True, disposition="PASS"):
    projection, admission = _support.gated_builder_projection(monkeypatch)
    return I11R03BatchBundle(
        item_id=item_id,
        projection=projection,
        admission=admission,
        independent_review=_support.review_for(projection, disposition),
        owner_authorized=authorized,
    )


def _run(root, manifest, runtime, provider=None):
    return run_batch(
        root,
        manifest,
        runtime,
        caller_id="demo",
        rights_scope="synthetic-public",
        i11_r03_provider=provider,
    )


def test_absent_bridge_preserves_default_f09a_item_bytes(tmp_path):
    runtime, manifest = _runtime_manifest(tmp_path, "default-compatible")
    plain = tmp_path / "plain"
    empty = tmp_path / "empty-provider"
    first = _run(plain, manifest, runtime)
    second = _run(empty, manifest, runtime, InProcessI11R03Provider(()))
    for name in ("report.json", "report.html", "receipt.json"):
        assert (plain / "items" / "r03-one" / name).read_bytes() == (
            empty / "items" / "r03-one" / name
        ).read_bytes()
    assert first.items[0].input_fingerprint == second.items[0].input_fingerprint
    assert first.items[0].state == second.items[0].state == "DONE_METADATA"


@pytest.mark.parametrize("kind", ["unverified", "missing-gate", "review-fail"])
def test_unsigned_or_absent_gate_is_blocked_in_real_batch(tmp_path, monkeypatch, kind):
    runtime, manifest = _runtime_manifest(tmp_path, f"blocked-{kind}")
    if kind == "unverified":
        projection = _support.unverified_projection()
        review = None
    else:
        projection, verified_admission = _support.gated_builder_projection(monkeypatch)
        review = _support.review_for(
            projection, "FAIL" if kind == "review-fail" else "PASS"
        )
    bundle = I11R03BatchBundle(
        item_id="r03-one",
        projection=projection,
        admission=verified_admission if kind == "review-fail" else None,
        independent_review=review,
        owner_authorized=True,
    )
    root = tmp_path / "batch"
    receipt = _run(root, manifest, runtime, InProcessI11R03Provider((bundle,)))
    report = json.loads((root / "items" / "r03-one" / "report.json").read_bytes())
    assert receipt.items[0].state == "BLOCKED_METHOD"
    assert report["status"] == "BLOCKED"
    assert all(
        claim["state"] == "BLOCKED"
        for section in report["sections"][-1:]
        for claim in section["claims"]
    )
    assert b"alpha exact asserted phrase" not in (root / "items" / "r03-one" / "report.html").read_bytes()


def test_gated_review_pass_is_partial_blocked_and_hash_verified(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "gated-pass")
    bundle = _gated_bundle(monkeypatch)
    root = tmp_path / "batch"
    receipt = _run(root, manifest, runtime, InProcessI11R03Provider((bundle,)))
    item = receipt.items[0]
    item_dir = root / "items" / "r03-one"
    raw = (item_dir / "report.json").read_bytes()
    html = (item_dir / "report.html").read_bytes()
    report = json.loads(raw)
    report_receipt = json.loads((item_dir / "receipt.json").read_bytes())
    candidate = report["sections"][-1]
    assert item.state == "PARTIAL_METADATA"
    assert report["status"] == "PARTIAL_METADATA"
    assert report["scientific_acceptance"] == "NOT_ASSERTED"
    assert all(claim["state"] == "BLOCKED" for claim in candidate["claims"])
    assert any("limitations" in claim["label"] for claim in candidate["claims"])
    assert b"alpha exact asserted phrase" not in raw + html
    assert b"beta exact asserted phrase" not in raw + html
    assert item.report_json_sha256 == hashlib.sha256(raw).hexdigest()
    assert item.report_html_sha256 == hashlib.sha256(html).hexdigest()
    assert report_receipt["status"] == report["status"]
    assert report_receipt["projection_digest"] == report["digest"]
    assert status_batch(root).items[0].projection_digest == report["digest"]


def test_resume_same_bundle_does_not_rewrite(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "same-replay")
    provider = InProcessI11R03Provider((_gated_bundle(monkeypatch),))
    root = tmp_path / "batch"
    first = _run(root, manifest, runtime, provider)
    paths = [root / "items" / "r03-one" / name for name in (
        "report.json", "report.html", "receipt.json"
    )]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    batch_receipt = (root / "batch_receipt.json").read_bytes()
    second = resume_batch(
        root,
        manifest,
        runtime,
        caller_id="demo",
        rights_scope="synthetic-public",
        i11_r03_provider=provider,
    )
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before
    assert (root / "batch_receipt.json").read_bytes() == batch_receipt
    assert second.items[0].attempts == first.items[0].attempts == 1


@pytest.mark.parametrize("mutation", ["review", "authorization", "evidence"])
def test_changed_bundle_is_stale_and_preserves_prior_artifact(
    tmp_path, monkeypatch, mutation
):
    runtime, manifest = _runtime_manifest(tmp_path, f"stale-{mutation}")
    original = _gated_bundle(monkeypatch)
    root = tmp_path / "batch"
    _run(root, manifest, runtime, InProcessI11R03Provider((original,)))
    prior = (root / "items" / "r03-one" / "report.json").read_bytes()
    if mutation == "review":
        changed = I11R03BatchBundle(
            "r03-one", original.projection, original.admission,
            _support.review_for(original.projection.model_dump(mode="json"), "FAIL"), True,
        )
    elif mutation == "authorization":
        changed = I11R03BatchBundle(
            "r03-one", original.projection, original.admission,
            original.independent_review, False,
        )
    else:
        projection = original.projection.model_dump(mode="json")
        projection["comparison_claims"][0]["limits"] = "Changed synthetic candidate limit."
        projection["projection_sha256"] = _support.digest({
            key: value for key, value in projection.items() if key != "projection_sha256"
        })
        changed = I11R03BatchBundle(
            "r03-one", projection, original.admission,
            _support.review_for(projection), True,
        )
    with pytest.raises(F09AI11R03StaleBundle, match="BUNDLE_STALE"):
        resume_batch(
            root,
            manifest,
            runtime,
            caller_id="demo",
            rights_scope="synthetic-public",
            i11_r03_provider=InProcessI11R03Provider((changed,)),
        )
    assert status_batch(root).items[0].state == "STALE"
    assert (root / "items" / "r03-one" / "report.json").read_bytes() == prior


def test_missing_bundle_on_resume_is_stale(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "missing-on-resume")
    root = tmp_path / "batch"
    _run(root, manifest, runtime, InProcessI11R03Provider((_gated_bundle(monkeypatch),)))
    with pytest.raises(F09AI11R03StaleBundle):
        resume_batch(
            root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public"
        )
    assert status_batch(root).items[0].state == "STALE"


def test_new_bundle_cannot_be_appended_to_completed_plain_item(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "new-on-resume")
    root = tmp_path / "batch"
    _run(root, manifest, runtime)
    prior = (root / "items" / "r03-one" / "report.json").read_bytes()
    with pytest.raises(F09AI11R03StaleBundle):
        resume_batch(
            root,
            manifest,
            runtime,
            caller_id="demo",
            rights_scope="synthetic-public",
            i11_r03_provider=InProcessI11R03Provider((_gated_bundle(monkeypatch),)),
        )
    assert status_batch(root).items[0].state == "STALE"
    assert (root / "items" / "r03-one" / "report.json").read_bytes() == prior


def test_denial_and_provider_collisions_fail_closed(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "denied")
    denied = _gated_bundle(monkeypatch, authorized=False)
    root = tmp_path / "denied-batch"
    receipt = _run(root, manifest, runtime, InProcessI11R03Provider((denied,)))
    assert receipt.items[0].state == "BLOCKED_METHOD"

    first = _gated_bundle(monkeypatch, item_id="r03-one")
    with pytest.raises(F09AI11R03BridgeError, match="MULTIPLE_ITEM_COLLISION"):
        InProcessI11R03Provider((first, first))
    reused = I11R03BatchBundle(
        "r03-two", first.projection, first.admission, first.independent_review, True
    )
    with pytest.raises(F09AI11R03BridgeError, match="CROSS_ITEM_COLLISION"):
        InProcessI11R03Provider((first, reused))
    wrong_item = I11R03BatchBundle(
        "not-in-manifest", first.projection, first.admission, first.independent_review, True
    )
    with pytest.raises(F09AI11R03BridgeError, match="CROSS_ITEM_BINDING"):
        _run(
            tmp_path / "wrong-item",
            manifest,
            runtime,
            InProcessI11R03Provider((wrong_item,)),
        )



def test_bridge_removal_stale_receipt_then_recovers_without_bundle(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "recover-removed")
    root = tmp_path / "batch"
    original = _gated_bundle(monkeypatch)
    _run(root, manifest, runtime, InProcessI11R03Provider((original,)))
    report_path = root / "items" / "r03-one" / "report.json"
    previously_authorized = report_path.read_bytes()

    with pytest.raises(F09AI11R03StaleBundle, match="BUNDLE_STALE"):
        resume_batch(
            root, manifest, runtime,
            caller_id="demo", rights_scope="synthetic-public",
        )
    item = status_batch(root).items[0]
    assert item.state == "STALE"
    assert item.projection_digest is None and item.relative_path is None
    receipt = json.loads((root / "batch_receipt.json").read_bytes())
    index = json.loads((root / "index.json").read_bytes())
    assert receipt["items"][0]["state"] == index["items"][0]["state"] == "STALE"
    assert receipt["code_pass"] is False
    assert report_path.read_bytes() == previously_authorized

    recovered = resume_batch(
        root, manifest, runtime, caller_id="demo", rights_scope="synthetic-public",
    )
    assert recovered.items[0].state == "DONE_METADATA"
    assert recovered.items[0].attempts == 2
    new_report = json.loads(report_path.read_bytes())
    assert all(
        not section["title"].startswith("I11 source comparison /")
        for section in new_report["sections"]
    )


def test_authorization_withdrawal_stale_then_blocked(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "recover-withdrawal")
    root = tmp_path / "batch"
    original = _gated_bundle(monkeypatch)
    _run(root, manifest, runtime, InProcessI11R03Provider((original,)))
    old_report = (root / "items" / "r03-one" / "report.json").read_bytes()
    denied = I11R03BatchBundle(
        "r03-one", original.projection, original.admission,
        original.independent_review, False,
    )
    provider = InProcessI11R03Provider((denied,))
    with pytest.raises(F09AI11R03StaleBundle, match="BUNDLE_STALE"):
        resume_batch(
            root, manifest, runtime,
            caller_id="demo", rights_scope="synthetic-public",
            i11_r03_provider=provider,
        )
    assert json.loads((root / "batch_receipt.json").read_bytes())["code_pass"] is False
    assert (root / "items" / "r03-one" / "report.json").read_bytes() == old_report

    recovered = resume_batch(
        root, manifest, runtime,
        caller_id="demo", rights_scope="synthetic-public",
        i11_r03_provider=provider,
    )
    assert recovered.items[0].state == "BLOCKED_METHOD"
    new_report = json.loads((root / "items" / "r03-one" / "report.json").read_bytes())
    assert new_report["status"] == "BLOCKED"
    assert "SOURCE_ADMISSION" not in json.dumps(new_report)
    assert "I11 source comparison / CANDIDATE" not in json.dumps(new_report)


def test_stale_first_item_does_not_abort_sibling_repair(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "stale-sibling", two_items=True)
    root = tmp_path / "batch"
    original = _gated_bundle(monkeypatch)
    _run(root, manifest, runtime, InProcessI11R03Provider((original,)))
    sibling = root / "items" / "r03-two" / "report.html"
    sibling.write_bytes(b"tampered old sibling html")
    with pytest.raises(F09AI11R03StaleBundle):
        resume_batch(
            root, manifest, runtime,
            caller_id="demo", rights_scope="synthetic-public",
        )
    statuses = status_batch(root).items
    assert [item.state for item in statuses] == ["STALE", "DONE_METADATA"]
    assert statuses[1].attempts == 2
    assert b"tampered old sibling html" not in sibling.read_bytes()
    receipt = json.loads((root / "batch_receipt.json").read_bytes())
    assert [item["state"] for item in receipt["items"]] == ["STALE", "DONE_METADATA"]
    assert receipt["code_pass"] is False


def test_custom_protocol_provider_item_mismatch_is_rejected(tmp_path, monkeypatch):
    runtime, manifest = _runtime_manifest(tmp_path, "provider-mismatch")
    foreign_bundle = _gated_bundle(monkeypatch, item_id="other-item")

    class WrongProvider:
        def validate_bindings(self, items):
            return None

        def resolve(self, *, item_id, report_id):
            return foreign_bundle

    with pytest.raises(F09AI11R03BridgeError, match="BRIDGE_ITEM_MISMATCH"):
        _run(tmp_path / "batch", manifest, runtime, WrongProvider())
