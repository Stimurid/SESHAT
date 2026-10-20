"""Invented two-world witnesses; run only in isolated exact-tree CI."""

import itertools

import pytest

from seshat.corpus import (
    CorpusSpaceSnapshot, EvidenceField, ManifestPin, PopulationManifest,
    UnverifiedCurrentnessError, build_corpus_space, canonical_population_digest,
    require_current,
)
from test_corpus_selection import MANIFEST, Rights, ids, spec, study, year


class ExplodingReader:
    def current_pin(self, manifest_id):
        raise AssertionError("private reader must not be invoked")

    def resolve(self, pin):
        raise AssertionError("private reader must not be invoked")


@pytest.mark.parametrize("forged", [False, True])
@pytest.mark.parametrize("require_verified", [False, True])
def test_coherent_reader_and_recomputed_pin_never_establish_authority(forged, require_verified):
    row = study("visible", 2099 if forged else 2025, "forged" if forged else "A")
    if forged:
        row = row.model_copy(update={"fields": tuple(
            value.model_copy(update={"evidence_ref": "fabricated:primary-source"})
            for value in row.fields
        )})
    pin = ManifestPin(manifest_id="coherent", version="1", sha256=canonical_population_digest(
        "coherent", "1", MANIFEST.declared_fields, [row]))
    manifest = PopulationManifest(pin=pin, declared_fields=MANIFEST.declared_fields)

    class SelfConsistentReader:
        def current_pin(self, manifest_id):
            return pin

        def resolve(self, pin):
            return manifest, (row,)

    query = spec(year(2000, 2100), manifest=pin)
    for reader in (None, SelfConsistentReader(), ExplodingReader()):
        result = build_corpus_space(query, manifest, [row], Rights(),
                                    trusted_manifest=reader, require_verified=require_verified)
        assert ids(result) == ["visible"]
        assert result.source_state == "METADATA_ONLY"
        assert result.evidence_state == "PENDING_HOST_ATTESTATION"
        assert result.selection_state == "PROVISIONAL"
        assert result.currentness_state == "UNVERIFIED_CURRENTNESS"
        assert result.members[0].carriers[0].identity_state == "PIN_ASSERTED_NOT_VERIFIED"
        assert result.semantic_acceptance_state == "NOT_ASSERTED"
        assert "EVIDENCE_VERIFIED" not in result.model_dump_json()
        with pytest.raises(ValueError):
            CorpusSpaceSnapshot.model_validate({**result.model_dump(),
                                               "source_state": "EVIDENCE_VERIFIED"})


def outcome(call):
    try:
        return ("receipt", call().model_dump_json())
    except Exception as exc:
        return ("error", type(exc).__name__, str(exc))


@pytest.mark.parametrize("require_verified", [False, True])
def test_fixed_request_hidden_worlds_receipt_digest_status_and_error(require_verified):
    public = study("visible", 2025)
    hidden = study("secret", 2024, paired=True)
    corrupt = hidden.model_copy(update={"fields": (object(),)})
    mutated = hidden.model_copy(update={"carriers": tuple(
        c.model_copy(update={"version": "secret-epoch", "content_sha256": "f" * 64})
        for c in hidden.carriers
    )})
    # Collide with an admitted study ID, but deny the candidate's carrier.
    collision = study("visible", 2099).model_copy(update={"carriers": (
        public.carriers[0].model_copy(update={"carrier_id": "denied-carrier",
                                             "content_sha256": "invalid"}),
    )})
    worlds = ([public], [public, hidden], [public, mutated],
              [public, hidden, corrupt], [collision, public], [public, collision])
    rights = Rights(denied={"secret"}, denied_carriers={"denied-carrier"})
    query = spec(year(2025, 2025))  # SAME request in every universe, including its pin
    baseline = outcome(lambda: build_corpus_space(query, MANIFEST, [public], rights))
    assert baseline[0] == "receipt"
    for n, world in enumerate(worlds):
        rights.version = f"private-policy-{n}"
        changed_manifest = MANIFEST.model_copy(update={"pin": ManifestPin(
            manifest_id="rotated-private-population", version=str(n), sha256=f"{n:064x}"
        )})
        for ordered in (world, list(reversed(world))):
            actual = outcome(lambda: build_corpus_space(
                query, changed_manifest, ordered, rights,
                trusted_manifest=ExplodingReader(), require_verified=require_verified))
            assert actual == baseline


def test_content_errors_only_from_visible_records_and_same_error_in_hidden_worlds():
    broken = study("visible", 2025).model_copy(update={"fields": (object(),)})
    hidden = study("hidden", 2025).model_copy(update={"fields": (object(),)})
    query = spec(year(2025, 2025))
    rights = Rights(denied={"hidden"})
    baseline = outcome(lambda: build_corpus_space(query, MANIFEST, [broken], rights))
    assert baseline == ("error", "ValueError", "invalid study pin")
    for world in itertools.permutations([broken, hidden]):
        assert outcome(lambda: build_corpus_space(query, MANIFEST, world, rights)) == baseline


def test_authoritative_cache_reuse_always_blocked_and_fresh_projection_rebuilds():
    class ObservedRights(Rights):
        checks = 0

        def visibility(self, *args):
            self.checks += 1
            return super().visibility(*args)

        def revision(self, *args):
            raise AssertionError("private epoch is not a public projection dependency")

    rights = ObservedRights(denied={"hidden"})
    query = spec(year(2025, 2025))
    rows = [study("visible", 2025), study("hidden", 2025)]
    prior = build_corpus_space(query, MANIFEST, rows, rights)
    for epoch in ("same", "rotated", "rotated-again"):
        rights.version = epoch
        checks = rights.checks
        # Fallback deliberately disables caching, rather than simulating host
        # authority with a private attribute or a caller-provided epoch token.
        current = build_corpus_space(query, MANIFEST, rows, rights)
        assert rights.checks == checks + len(rows)
        assert current is not prior
        assert current.model_dump_json() == prior.model_dump_json()
        with pytest.raises(UnverifiedCurrentnessError, match="^UNVERIFIED_CURRENTNESS$"):
            require_current(prior, query, MANIFEST, rows, rights,
                            trusted_manifest=ExplodingReader(), require_verified=True)
    rights.denied.add("visible")
    assert build_corpus_space(query, MANIFEST, rows, rights).selected_studies == 0
    with pytest.raises(UnverifiedCurrentnessError):
        require_current(prior, query, MANIFEST, rows, rights)


def test_count_permission_releases_only_unique_denied_count_not_epoch_or_ids():
    public, hidden = study("visible", 2025), study("secret", 2025)
    rights = Rights(denied={"secret"}, count=True)
    query = spec(year(2025, 2025))
    first = build_corpus_space(query, MANIFEST, [public, hidden, hidden], rights)
    rights.version = "secret-policy"
    changed = MANIFEST.model_copy(update={"pin": MANIFEST.pin.model_copy(
        update={"version": "secret-version", "sha256": "f" * 64})})
    second = build_corpus_space(query, changed, [public, hidden], rights)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.denied_studies == 1
    assert "secret" not in first.model_dump_json()


def test_visible_changes_still_change_projection_with_full_pin_omitted():
    row = study("visible", 2025)
    query = spec(year(2025, 2025))
    first = build_corpus_space(query, MANIFEST, [row], Rights())
    changes = (
        study("visible", 2025, version="2"),
        study("visible", 2026),
        row.model_copy(update={"carriers": (row.carriers[0].model_copy(
            update={"content_sha256": "f" * 64}),)}),
        row.model_copy(update={"fields": (EvidenceField(
            name="cohort_year", value=2025, evidence_ref="changed-visible-source"),)}),
    )
    for changed in changes:
        assert build_corpus_space(query, MANIFEST, [changed], Rights()).snapshot_digest != (
            first.snapshot_digest)


def test_studies_and_shared_carriers_have_independent_denominators():
    first = study("first", 2025)
    second = first.model_copy(update={"research_object": first.research_object.model_copy(
        update={"object_id": "second"})})
    query = spec(year(2025, 2025))
    result = build_corpus_space(query, MANIFEST, [first, second, first], Rights())
    assert result.selected_studies == result.eligible_studies == 2
    assert result.selected_carriers == result.eligible_carriers == 1
    changed = second.model_copy(update={"carriers": (second.carriers[0].model_copy(
        update={"content_sha256": "f" * 64}),)})
    with pytest.raises(ValueError, match="conflicting visible carrier pin"):
        build_corpus_space(query, MANIFEST, [first, changed], Rights())
    # The same carrier conflict is invisible if its study is denied.
    assert build_corpus_space(query, MANIFEST, [first, changed], Rights(denied={"second"})) == (
        build_corpus_space(query, MANIFEST, [first], Rights(denied={"second"})))


@pytest.mark.parametrize("decision", [None, True, "VISIBLE", "DENIED", "unknown"])
def test_invalid_policy_decision_never_grants_visibility(decision):
    class InvalidRights(Rights):
        def visibility(self, *args):
            return decision

    with pytest.raises(ValueError, match="^entitlement check failed$"):
        build_corpus_space(spec(year(2025, 2025)), MANIFEST,
                           [study("private", 2025)], InvalidRights())
