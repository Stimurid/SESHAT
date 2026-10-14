"""F07 mechanical tests use invented IDs only; no owner-private rows or PDFs."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from seshat.blackboard import AmbiguousStateError, Blackboard
from seshat.contracts import AcceptanceState, DependencyEdge, DerivedObject, SourceCarrier
from seshat.corpus import (
    CorpusSelectionSpec, EvidenceField, ManifestPin, PopulationManifest, Predicate,
    StaleCorpusSpaceError, Visibility, build_corpus_space, current_accepted,
    accepted_current_one, require_current,
)
from seshat.corpus_adapters import evidenced_study, sechenovka_v4_metadata_row


class Rights:
    def __init__(self, denied=(), count=False, denied_carriers=()):
        self.denied = set(denied)
        self.denied_carriers = set(denied_carriers)
        self.count = count
        self.version = "rights-1"

    def revision(self, caller_id, view_id):
        return self.version

    def visibility(self, caller_id, view_id, object_id):
        return Visibility.DENIED if object_id in self.denied else Visibility.VISIBLE

    def carrier_visibility(self, caller_id, view_id, object_id, carrier_id):
        return Visibility.DENIED if carrier_id in self.denied_carriers else Visibility.VISIBLE

    def may_count_denied(self, caller_id, view_id):
        return self.count

    def seal_selection(self, caller_id, view_id, canonical_json):
        return hmac.new(b"synthetic-test-key", canonical_json.encode(), hashlib.sha256).hexdigest()


PIN = ManifestPin(manifest_id="synthetic-population", version="1", sha256="a" * 64)
MANIFEST = PopulationManifest(
    pin=PIN, declared_fields=frozenset({
        "cohort_year", "specialty", "lab", "supervisor", "source_role"
    })
)


def spec(predicate, selector="selection", version="1", manifest=PIN):
    return CorpusSelectionSpec(selector_id=selector, version=version, manifest=manifest,
                               predicate=predicate, caller_id="reader", view_id="research")


def year(lo, hi):
    return Predicate(op="range", field="cohort_year", lower=lo, upper=hi)


def field(name, *values):
    return Predicate(op="equals", field=name, values=values)


def study(name, year_value=None, specialty=None, *, paired=False, lab=None, version="1"):
    carriers = [SourceCarrier(
        carrier_id=f"{name}-abstract", source_identity="abstract", version="1",
        content_sha256=hashlib.sha256(name.encode()).hexdigest(),
    )]
    if paired:
        carriers.append(SourceCarrier(
            carrier_id=f"{name}-full", source_identity="dissertation", version="1",
            content_sha256=hashlib.sha256((name + "full").encode()).hexdigest(),
        ))
    fields = []
    for key, value in (("cohort_year", year_value), ("specialty", specialty), ("lab", lab)):
        if value is not None:
            fields.append(EvidenceField(
                name=key, value=value, evidence_ref=f"fixture:{name}:{key}"
            ))
    return evidenced_study(object_id=name, version=version, object_type="study",
                           carriers=carriers, fields=fields)


def ids(view):
    return [item.object_id for item in view.members]


def test_two_selectors_same_manifest_replay_permutation_and_boundaries():
    records = [study("c", 2026, "B"), study("a", 2021, "A", paired=True),
               study("b", 2023, "B")]
    first = build_corpus_space(spec(year(2021, 2023), "early"), MANIFEST, records, Rights())
    second = build_corpus_space(spec(year(2024, 2026), "late"), MANIFEST, records, Rights())
    replay = build_corpus_space(spec(year(2021, 2023), "early"), MANIFEST,
                                list(reversed(records)), Rights())
    assert ids(first) == ["a", "b"]
    assert ids(second) == ["c"]
    assert first.snapshot_digest == replay.snapshot_digest
    assert first.selected_studies == 2 and first.selected_carriers == 3
    assert first.eligible_studies == 3 and first.eligible_carriers == 4
    assert first.source_state == "METADATA_ONLY"
    assert first.snapshot_digest != second.snapshot_digest


def test_cross_specialty_boolean_overlap_and_unique_studies():
    records = [study("a", 2024, "A"), study("b", 2025, "B", paired=True),
               study("c", 2025, "A")]
    both = Predicate(op="and", children=(year(2024, 2025),
                                          Predicate(op="or", children=(field("specialty", "A"),
                                                                       field("specialty", "B")))))
    view = build_corpus_space(spec(both), MANIFEST, records + [records[0]], Rights())
    assert ids(view) == ["a", "b", "c"]
    assert view.eligible_studies == 3 and view.eligible_carriers == 4
    assert len(ids(view)) == len(set(ids(view)))
    reversed_query = Predicate(op="and", children=(
        Predicate(op="or", children=(field("specialty", "B"), field("specialty", "A"))),
        year(2024, 2025),
    ))
    assert spec(both).canonical_json == spec(reversed_query).canonical_json


def test_missing_fields_are_unknown_or_not_evaluable():
    records = [study("a", 2025), study("b", specialty="A")]
    specialty = build_corpus_space(spec(field("specialty", "A")), MANIFEST, records, Rights())
    assert ids(specialty) == ["b"] and specialty.unknown_metadata == 1
    assert build_corpus_space(spec(year(2025, 2025)), MANIFEST, records,
                              Rights()).unknown_metadata == 1
    assert build_corpus_space(spec(field("lab", "L")), MANIFEST, records,
                              Rights()).unknown_metadata == 2
    assert build_corpus_space(spec(field("supervisor", "S")), MANIFEST, records,
                              Rights()).unknown_metadata == 2
    undeclared = PopulationManifest(pin=PIN, declared_fields=frozenset({"cohort_year"}))
    assert build_corpus_space(spec(field("lab", "L")), undeclared, records,
                              Rights()).not_evaluable == 2


def test_denial_revocation_and_no_hidden_identity_or_count():
    hidden = study("SECRET-ROW-9", 2025, paired=True)
    hidden = hidden.model_copy(update={"research_object": hidden.research_object.model_copy(
        update={"metadata": {"authorized": True}}
    )})
    records = [study("public", 2025), hidden]
    rights = Rights(denied={"SECRET-ROW-9"})
    view = build_corpus_space(spec(year(2025, 2025)), MANIFEST, records, rights)
    encoded = view.model_dump_json()
    assert ids(view) == ["public"] and view.eligible_studies == 1
    assert view.denied_studies is None and view.suppressed_remainder
    assert "SECRET-ROW-9" not in encoded and "SECRET-ROW-9" not in view.snapshot_digest
    exact = spec(Predicate(op="ids", ids=("public", "SECRET-ROW-9")), "exact")
    exact_view = build_corpus_space(exact, MANIFEST, records, rights)
    assert ids(exact_view) == ["public"]
    assert "SECRET-ROW-9" not in exact_view.model_dump_json()
    rights.denied.clear()
    rights.version = "rights-2"
    with pytest.raises(StaleCorpusSpaceError, match="stale"):
        require_current(view, spec(year(2025, 2025)), MANIFEST, records, rights)
    now = build_corpus_space(spec(year(2025, 2025)), MANIFEST, records, rights)
    assert now.selected_studies == 2 and now.snapshot_digest != view.snapshot_digest
    rights.denied.add("SECRET-ROW-9")
    rights.version = "rights-3"
    with pytest.raises(StaleCorpusSpaceError):
        require_current(now, spec(year(2025, 2025)), MANIFEST, records, rights)
    counted = build_corpus_space(spec(year(2025, 2025)), MANIFEST, records,
                                 Rights(denied={"SECRET-ROW-9"}, count=True))
    assert counted.denied_studies == 1 and not counted.suppressed_remainder

    class FailingRights(Rights):
        def visibility(self, caller_id, view_id, object_id):
            raise ValueError(f"private failure for {object_id}")

    with pytest.raises(ValueError, match="entitlement check failed") as error:
        build_corpus_space(spec(year(2025, 2025)), MANIFEST, records, FailingRights())
    assert "SECRET-ROW-9" not in str(error.value)


def test_duplicate_conflict_and_source_version_or_provenance_drift():
    a = study("a", 2024)
    prior = build_corpus_space(spec(year(2024, 2024)), MANIFEST, [a], Rights())
    changed = study("a", 2024, version="2")
    with pytest.raises(ValueError, match="conflicting duplicate study"):
        build_corpus_space(spec(year(2024, 2024)), MANIFEST, [a, changed], Rights())
    secret_v1 = study("SECRET-STUDY", 2024)
    secret_v2 = study("SECRET-STUDY", 2024, version="2")
    with pytest.raises(ValueError, match="conflicting duplicate study") as hidden_error:
        build_corpus_space(spec(year(2024, 2024)), MANIFEST, [secret_v1, secret_v2],
                           Rights(denied={"SECRET-STUDY"}))
    assert "SECRET-STUDY" not in str(hidden_error.value)
    assert build_corpus_space(spec(year(2024, 2024)), MANIFEST, [changed],
                              Rights()).snapshot_digest != prior.snapshot_digest
    carrier = a.carriers[0].model_copy(update={"content_sha256": "f" * 64})
    changed_hash = a.model_copy(update={"carriers": (carrier,)})
    with pytest.raises(StaleCorpusSpaceError):
        require_current(prior, spec(year(2024, 2024)), MANIFEST, [changed_hash], Rights())
    changed_version = a.model_copy(update={"carriers": (
        a.carriers[0].model_copy(update={"version": "2"}),
    )})
    with pytest.raises(StaleCorpusSpaceError):
        require_current(prior, spec(year(2024, 2024)), MANIFEST, [changed_version], Rights())
    changed_evidence = a.model_copy(update={"fields": (
        EvidenceField(name="cohort_year", value=2024, evidence_ref="new-source"),)})
    assert build_corpus_space(spec(year(2024, 2024)), MANIFEST, [changed_evidence],
                              Rights()).snapshot_digest != prior.snapshot_digest
    assert spec(year(2024, 2024), version="2").digest != spec(year(2024, 2024)).digest
    next_pin = ManifestPin(manifest_id=PIN.manifest_id, version="2", sha256="b" * 64)
    with pytest.raises(StaleCorpusSpaceError):
        require_current(prior, spec(year(2024, 2024)), PopulationManifest(pin=next_pin,
                                                 declared_fields=MANIFEST.declared_fields),
                        [a], Rights())


def test_invalid_predicate_and_incomplete_carrier_cannot_certify_full_read():
    with pytest.raises(ValueError):
        Predicate(op="range", field="cohort_year", lower=2026, upper=2021)
    with pytest.raises(ValueError):
        Predicate(op="equals", field="specialty", values=("A",), lower=1)
    with pytest.raises(ValueError):
        evidenced_study(object_id="x", version="1", object_type="study", carriers=[
            SourceCarrier(carrier_id="c", source_identity="x", version="1")], fields=[])
    view = build_corpus_space(spec(year(2025, 2025)), MANIFEST, [study("x", 2025)], Rights())
    assert view.source_state == "METADATA_ONLY"
    assert "FULL_REQUIRED" not in view.model_dump_json()
    denied = build_corpus_space(spec(year(2025, 2025)), MANIFEST,
                                [study("x", 2025, paired=True)],
                                Rights(denied_carriers={"x-full"}))
    assert denied.selected_studies == 0 and denied.selected_carriers == 0
    assert denied.denied_studies is None and denied.suppressed_remainder


def test_second_host_arbitrary_fields_and_v4_adapter_no_fabricated_lab():
    second = evidenced_study(
        object_id="archive-x", version="7", object_type="project",
        carriers=[SourceCarrier(carrier_id="note-x", source_identity="field-note",
                                version="7", content_sha256="e" * 64)],
        fields=[EvidenceField(name="season", value="winter", evidence_ref="catalog:7")],
    )
    other_manifest = PopulationManifest(pin=PIN, declared_fields=frozenset({"season"}))
    assert ids(build_corpus_space(spec(field("season", "winter")), other_manifest,
                                  [second], Rights())) == ["archive-x"]
    row = {"study_id": "invented-study", "year": 2025,
           "specialty_raw": None, "source_performed": "Some Institute",
           "abstract": {"drive_file_id": "invented-abstract", "sha256": "a" * 64},
           "dissertation": {"drive_file_id": "invented-full", "sha256": "b" * 64}}
    adapted = sechenovka_v4_metadata_row(row, row_evidence_ref="synthetic:row",
                                          record_version="v4")
    assert len(adapted.carriers) == 2
    assert {f.name for f in adapted.fields} == {"cohort_year"}
    view = build_corpus_space(spec(year(2025, 2025)), MANIFEST, [adapted], Rights())
    assert view.selected_studies == 1 and view.selected_carriers == 2
    assert ids(build_corpus_space(spec(field("source_role", "dissertation")),
                                  MANIFEST, [adapted], Rights())) == ["invented-study"]
    assert build_corpus_space(spec(field("lab", "Some Institute")), MANIFEST,
                              [adapted], Rights()).unknown_metadata == 1


def test_historical_acceptance_is_not_current_acceptance():
    board = Blackboard()
    obj = DerivedObject(derived_id="d", object_type="analysis", version="1",
                        operation_id="fixture", research_object_id="r",
                        payload={}, acceptance_state=AcceptanceState.ACCEPTED)
    board.put(obj)
    assert len(board.accepted_state("r")) == 1
    assert len(current_accepted(board, "r")) == 1
    second = obj.model_copy(update={"derived_id": "d2", "version": "2"})
    board.put(second)
    with pytest.raises(AmbiguousStateError):
        accepted_current_one(board, "r", "analysis")
    board.add_dependency(DependencyEdge(upstream_id="source-pin", downstream_id="d",
                                        dependency_type="source"))
    board.add_dependency(DependencyEdge(upstream_id="source-pin", downstream_id="d2",
                                        dependency_type="source"))
    board.mark_changed("source-pin")
    assert len(board.accepted_state("r")) == 2
    assert current_accepted(board, "r") == ()


def test_synthetic_v4_aggregate_oracles_are_study_based():
    """Invented identities model the public aggregate oracle, not private rows."""
    counts = {2021: 12, 2022: 17, 2023: 25, 2024: 27, 2025: 93, 2026: 12}
    paired = {2021: 12, 2022: 17, 2023: 2, 2024: 13, 2025: 38, 2026: 12}
    known = {2021: 12, 2022: 17, 2023: 22, 2024: 27, 2025: 4, 2026: 0}
    records = [study(f"fake-{year}-{n:03}", year,
                     "synthetic-specialty" if n < known[year] else None,
                     paired=n < paired[year])
               for year, total in counts.items() for n in range(total)]
    rights = Rights()
    whole = build_corpus_space(spec(year(2021, 2026)), MANIFEST, records, rights)
    assert (whole.selected_studies, whole.selected_carriers) == (186, 280)
    for lo, hi, expected in ((2021, 2023, (54, 31, 51, 3)),
                             (2024, 2026, (132, 63, 31, 101)),
                             (2025, 2025, (93, 38, 4, 89)),
                             (2026, 2026, (12, 12, 0, 12))):
        view = build_corpus_space(spec(year(lo, hi), f"years-{lo}-{hi}"),
                                  MANIFEST, records, rights)
        specialty = build_corpus_space(
            spec(Predicate(op="and", children=(year(lo, hi),
                                               field("specialty", "synthetic-specialty"))),
                 f"known-{lo}-{hi}"), MANIFEST, records, rights)
        studies, pair_count, known_count, unknown_count = expected
        assert view.selected_studies == studies
        assert view.selected_carriers == studies + pair_count
        assert specialty.selected_studies == known_count
        assert specialty.unknown_metadata == unknown_count
