"""Invented metadata only. Never substitutes for the private v4 evaluation."""

import hashlib
import json

import pytest

from seshat.corpus import EvidenceField, PopulationManifest, Predicate, build_corpus_space
from seshat.corpus_adapters import pinned_temporal_metadata, sechenovka_v4_metadata_row
from seshat.corpus_host import (
    Grant, TemporalSourcePackage, _attach_owner_temporal, _temporal_binding,
)
from seshat.corpus_report_input import CorpusReportInput
from test_corpus_selection import PIN, Rights, spec


def intake(cohort=2025, **extra):
    return {"study_id": "invented-temporal", "year": cohort,
            "abstract": {"drive_file_id": "invented-abstract", "sha256": "a" * 64}, **extra}


def evidence(**values):
    raw = json.dumps({"study_id": "invented-temporal", **values}, sort_keys=True).encode()
    return pinned_temporal_metadata(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_object_id="invented-temporal", source_version="invented-master-1")


def adapt(cohort=2025, temporal=None, **extra):
    record = sechenovka_v4_metadata_row(
        intake(cohort, **extra), row_evidence_ref="invented:intake", record_version="v4")
    if temporal is None:
        return record
    # Pure semantic fixture, NOT an authorization test. Actual pinned-file and
    # process-boundary acceptance is exercised in test_corpus_temporal_authority.
    package = TemporalSourcePackage(host_id="synthetic", records=({
        **_temporal_binding(record),
        **{e.source_field: e.source_value for e in temporal.evidence}},))
    grant = Grant(caller_id="reader", view_id="research", object_ids={temporal.object_id},
                  carrier_ids={"invented-abstract"}, temporal_fields={temporal.object_id:
                  {"defended_on", "defense_date", "abstract_published"}})
    return _attach_owner_temporal(record, package, grant)


def selection(record, field, year, declared=True):
    query = spec(Predicate(op="range", field=field, lower=year, upper=year))
    manifest = PopulationManifest(pin=PIN, declared_fields=frozenset({field})
                                  if declared else frozenset())
    return query, build_corpus_space(query, manifest, [record], Rights())


def test_cohort_defense_alternate_date_and_publication_are_independent():
    record = adapt(2025, evidence(defended_on="2026-01-17", defense_date="2026-02-18",
                                  abstract_published="2024-12-01"))
    fields = {f.name: f for f in record.fields}
    assert fields["cohort_year"].value == 2025
    assert fields["defended_on_year"].value == 2026
    assert fields["defended_on"].value == "2026-01-17"
    assert fields["defense_date"].value == "2026-02-18"
    assert fields["abstract_published_year"].value == 2024
    assert fields["defended_on"].temporal_provenance.precision == "DATE"
    assert selection(record, "cohort_year", 2025)[1].selected_studies == 1
    assert selection(record, "defended_on_year", 2025)[1].predicate_false == 1
    assert selection(record, "defended_on_year", 2026)[1].selected_studies == 1
    assert "degree_awarded" not in fields


@pytest.mark.parametrize("temporal", [None, {}, {"defended_on": None},
                                     {"defense_date": "2026-01-17"},
                                     {"abstract_published": 2026}])
def test_missing_defended_on_never_falls_back_to_cohort_or_another_date(temporal):
    record = adapt(2026, None if temporal is None else evidence(**temporal))
    assert "defended_on_year" not in {f.name for f in record.fields}
    result = selection(record, "defended_on_year", 2026)[1]
    assert result.unknown_metadata == 1 and result.selected_studies == 0
    assert selection(record, "defended_on_year", 2026, declared=False)[1].not_evaluable == 1


def test_intake_cannot_invent_defended_year_without_independent_channel():
    record = adapt(2026, defended_on="2025-01-01", defended_on_year=2025,
                   defense_date="2025-01-01", abstract_published=2025)
    assert not any(f.name.startswith(("defended_on", "defense_date", "abstract_published"))
                   for f in record.fields)
    assert selection(record, "defended_on_year", 2026)[1].unknown_metadata == 1


def test_explicit_year_is_not_fabricated_as_calendar_date():
    record = adapt(2025, evidence(defended_on=2026))
    fields = {f.name: f for f in record.fields}
    assert fields["defended_on"].value == 2026
    assert fields["defended_on"].temporal_provenance.precision == "YEAR"
    assert fields["defended_on_year"].value == 2026


@pytest.mark.parametrize("value", ["2026-02-30", "2025-02-29", "2026", "20260101",
                                   "2026-01-01T00:00:00", "", [], {}, True, 2026.0, 0, 10000])
def test_invalid_dates_years_and_coercions_fail_sanitized(value):
    with pytest.raises(ValueError, match="^invalid host temporal metadata$"):
        evidence(defended_on=value)


def test_leap_date_is_valid_and_precision_survives_roundtrip():
    record = adapt(2025, evidence(defended_on="2024-02-29"))
    assert type(record).model_validate_json(record.model_dump_json()) == record


def test_sha_identity_version_and_join_are_checked():
    raw = b'{"study_id":"invented-temporal","defended_on":2026}'
    for digest, identity, version in (("f" * 64, "invented-temporal", "1"),
                                      (hashlib.sha256(raw).hexdigest(), "other", "1"),
                                      (hashlib.sha256(raw).hexdigest(), "invented-temporal", "")):
        with pytest.raises(ValueError, match="^invalid host temporal metadata$"):
            pinned_temporal_metadata(raw, expected_sha256=digest,
                                     expected_object_id=identity, source_version=version)
    with pytest.raises(ValueError, match="UNTRUSTED_TEMPORAL_METADATA"):
        sechenovka_v4_metadata_row(
            intake(), row_evidence_ref="invented", record_version="v4",
            temporal_metadata=evidence(defended_on=2026).model_copy(update={"object_id": "other"}))


def test_temporal_fields_cannot_be_relabelled_or_forged():
    with pytest.raises(ValueError, match="requires explicit source provenance"):
        EvidenceField(name="defended_on_year", value=2025, evidence_ref="intake:year")
    provenance = evidence(abstract_published=2025).evidence[0]
    with pytest.raises(ValueError, match="does not match its source"):
        EvidenceField(name="defended_on_year", value=2025, evidence_ref="invented",
                      temporal_provenance=provenance)
    provenance = evidence(defended_on="2026-01-17").evidence[0]
    with pytest.raises(ValueError, match="does not match its source"):
        EvidenceField(name="defended_on_year", value=2025, evidence_ref="invented",
                      temporal_provenance=provenance)


def test_provenance_changes_invalidate_selection_input_digest():
    first = adapt(temporal=evidence(defended_on="2026-01-17"))
    second = adapt(temporal=evidence(defended_on="2026-02-18"))
    a = selection(first, "defended_on_year", 2026)[1]
    b = selection(second, "defended_on_year", 2026)[1]
    assert a.members == b.members and a.input_digest != b.input_digest


def test_conflicting_date_and_year_provenance_is_rejected():
    record = adapt(temporal=evidence(defended_on="2026-01-17"))
    other = adapt(temporal=evidence(defended_on="2026-02-18"))
    replacement = next(f for f in other.fields if f.name == "defended_on_year")
    payload = record.model_dump()
    payload["fields"] = [replacement.model_dump() if f.name == "defended_on_year"
                         else f.model_dump() for f in record.fields]
    with pytest.raises(ValueError, match="conflicting temporal source provenance"):
        type(record).model_validate(payload)


def test_host_admission_keeps_temporal_provenance_and_private_epochs_separate(tmp_path):
    from seshat.corpus_host import HostRuntime
    from test_corpus_host import config, pin_file

    record = adapt(temporal=evidence(defended_on="2026-01-17"))
    configuration = config(tmp_path, [record], allowed=("invented-temporal",))
    source = json.loads(configuration.primary.path.read_bytes())
    source["declared_fields"].append("defended_on_year")
    configuration = configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, source)})
    rights = json.loads(configuration.rights.path.read_bytes())
    rights["grants"][0]["temporal_fields"] = {"invented-temporal": ["defended_on"]}
    configuration = configuration.model_copy(update={
        "rights": pin_file(configuration.rights.path, rights),
        "temporal": pin_file(tmp_path / "temporal.json", {
            "host_id": configuration.host_id,
            "records": [{**_temporal_binding(record), "defended_on": "2026-01-17"}]}),
    })
    runtime = HostRuntime(configuration)
    select = runtime.session(authenticated_caller="reader", authorized_view="research")
    query = spec(Predicate(op="range", field="defended_on_year", lower=2026, upper=2026))
    baseline = select(query).model_dump_json()
    assert select(query).selected_studies == 1
    source["version"] = "private-rotation"
    source["records"].append({"research_object": {"object_id": "denied"},
                              "fields": "bad temporal data", "carriers": None})
    runtime.install(configuration.model_copy(update={
        "primary": pin_file(configuration.primary.path, source)}))
    assert select(query).model_dump_json() == baseline


@pytest.mark.parametrize("report_id", [f"R{i:02}" for i in range(1, 10)])
def test_reports_preserve_explicit_temporal_selector_and_unknowns(report_id):
    record = adapt(2026)
    for field in ("cohort_year", "defended_on_year"):
        query, snapshot = selection(record, field, 2026)
        report = CorpusReportInput(report_id=report_id, selection=query, corpus=snapshot)
        assert report.selection.predicate.field == field
        assert report.temporal_semantics == "EXPLICIT_FIELDS_ONLY_NO_COHORT_DEFENSE_FALLBACK"
        assert report.corpus.selected_studies == (1 if field == "cohort_year" else 0)
        assert report.corpus.unknown_metadata == (0 if field == "cohort_year" else 1)
