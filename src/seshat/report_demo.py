"""Offline synthetic F08 delivery: python -m seshat.report_demo --output NEW_DIR."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from seshat.corpus import CorpusSelectionSpec, ManifestPin, Predicate
from seshat.corpus_host import FilePin, HostConfiguration, HostRuntime
from seshat.reports import ReportRequest, artifacts, report_session
from seshat.scientific_report import AnchoredClaim, ScientificReportAsset, Subassembly

SYNTHETIC_METHOD_BODY = (
    "Synthetic method v1: reconstruct each functional subassembly separately; "
    "name its own material, operation and result; bind every observation to an "
    "actual invented source page; retain unknowns; never claim external novelty "
    "or attribute a measurement to the author without evidence."
).encode("utf-8")


def synthetic_method_bodies():
    return {"synthetic-method-1": SYNTHETIC_METHOD_BODY}


def synthetic_packages(host="sechenovka-like"):
    """Invented, owner-publishable metadata; no private corpus path is accepted."""
    if host not in {"sechenovka-like", "meteorology"}:
        raise ValueError("UNKNOWN_SYNTHETIC_FIXTURE")
    specialties = (("imaging", "materials") if host == "sechenovka-like"
                   else ("atmosphere", "ocean"))
    rows = []
    for i, roles in enumerate((("A",), ("D",), ("A", "D")), 1):
        oid = f"synthetic-{i}"
        carriers = [{"carrier_id": f"{oid}-{role}", "source_identity": f"invented-{role}-{i}",
                     "version": "1", "media_type": "application/pdf",
                     "content_sha256": hashlib.sha256(f"synthetic {host} {i} {role}".encode()).hexdigest()}
                    for role in roles]
        fields = {"title": f"Invented {host} research {i}", "cohort_year": 2025 if i == 1 else 2026}
        if i < 3:
            fields["specialty"] = specialties[i - 1]
        if i == 1:
            fields.update(method_candidate="measurement (source-declared candidate)",
                          infrastructure="synthetic sensor", lab="invented lab")
        rows.append({"research_object": {"object_id": oid, "object_type": "Study",
                     "version": "1", "carrier_ids": [c["carrier_id"] for c in carriers]},
                     "carriers": carriers,
                     "fields": [{"name": k, "value": v, "evidence_ref": "synthetic metadata"}
                                for k, v in fields.items()],
                     "roles": [{"name": "source_role", "value": r,
                                "evidence_ref": f"invented role {r}"} for r in roles]})
    source = {"host_id": host, "manifest_id": "synthetic", "version": "1",
              "declared_fields": ["title", "cohort_year", "specialty", "source_role",
                                  "defended_on_year", "method_candidate", "infrastructure", "lab"],
              "records": rows}
    rights = {"host_id": host, "epoch": "synthetic-owner-1", "grants": [{
        "caller_id": "demo", "view_id": "synthetic-public",
        "object_ids": [r["research_object"]["object_id"] for r in rows],
        "carrier_ids": [c["carrier_id"] for r in rows for c in r["carriers"]],
        "temporal_fields": {"synthetic-1": ["defended_on"], "synthetic-2": ["defended_on"]}}]}
    first = rows[0]
    temporal = {"host_id": host, "records": [{"study_id": "synthetic-1", "record_version": "1",
        "carriers": [{"carrier_id": c["carrier_id"], "source_identity": c["source_identity"],
                      "version": c["version"], "sha256": c["content_sha256"]}
                     for c in first["carriers"]], "defended_on": 2026}]}
    return source, rights, temporal


def pin_package(path, data):
    raw = json.dumps(data, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return FilePin(path=path.resolve(), sha256=hashlib.sha256(raw).hexdigest())


def install_fixture(directory, host="sechenovka-like"):
    source, rights, temporal = synthetic_packages(host)
    # Invented original pages exist as bytes in the disposable fixture directory.
    page_body = ("Осадки в горном водосборе; наземный дождемер; суточная сумма.\n"
                 "SYNTHETIC PAGE 2: Температура прибрежного слоя; буйный термометр; "
                 "средняя температура."
                 if host == "meteorology" else
                 "Оптический модуль датчика; спектральное измерение; отклик модуля.\n"
                 "SYNTHETIC PAGE 2: Механический узел стенда; нагрузочное испытание; "
                 "деформация узла.")
    for row in source["records"]:
        for carrier in row["carriers"]:
            page = (f"SYNTHETIC PAGE 1: {host}; {row['research_object']['object_id']}; "
                    f"{carrier['carrier_id']}\n{page_body}\n")
            content = page.encode("utf-8")
            carrier["content_sha256"] = hashlib.sha256(content).hexdigest()
            carrier["media_type"] = "text/plain"
            (directory / f"{carrier['carrier_id']}.txt").write_bytes(content)
    first = source["records"][0]
    temporal["records"][0]["carriers"] = [
        {"carrier_id": c["carrier_id"], "source_identity": c["source_identity"],
         "version": c["version"], "sha256": c["content_sha256"]}
        for c in first["carriers"]]
    return HostRuntime(HostConfiguration(host_id=host,
        primary=pin_package(directory / "source.json", source),
        rights=pin_package(directory / "rights.json", rights),
        temporal=pin_package(directory / "temporal.json", temporal)))


def demo_request(report_id="R03"):
    selections = tuple(CorpusSelectionSpec(
        selector_id=f"role-{role}", version="1",
        manifest=ManifestPin(manifest_id="public-request", version="1", sha256="0" * 64),
        predicate=Predicate(op="equals", field="source_role", values=(role,)),
        caller_id="demo", view_id="synthetic-public") for role in ("A", "D"))
    if report_id == "R01":
        selections = (selections[0].model_copy(update={
            "predicate": Predicate(op="ids", ids=("synthetic-1",))}),)
    return ReportRequest(report_id=report_id, selections=selections,
                         rights_scope="synthetic-public", as_of="2026-10-15")


def synthetic_scientific_asset(runtime, host="sechenovka-like"):
    """Separately authored invented analytic state; no medical or customer text."""
    member = runtime.session(authenticated_caller="demo", authorized_view="synthetic-public")(
        demo_request("R01").selections[0]).members[0]
    carrier = member.carriers[0]
    if host == "meteorology":
        objects = (("Осадки в горном водосборе", "наземный дождемер", "суточная сумма"),
                   ("Температура прибрежного слоя", "буйный термометр", "средняя температура"))
        problem = "Как различаются осадки и температура в вымышленной сети наблюдений?"
    else:
        objects = (("Оптический модуль датчика", "спектральное измерение", "отклик модуля"),
                   ("Механический узел стенда", "нагрузочное испытание", "деформация узла"))
        problem = "Как работают два независимых узла вымышленного исследовательского стенда?"
    subassemblies = []
    for i, (name, method, result) in enumerate(objects, 1):
        sid = f"component-{i}"
        subassemblies.append(Subassembly(
            subassembly_id=sid, functional_object=name, method=method,
            material="вымышленный образец", result=f"Зафиксирован {result} на синтетической странице.",
            counterexample_or_unknown="Перенос результата на другие образцы не установлен.",
            claims=(AnchoredClaim(
                stage="E1_OBSERVATION", subassembly_id=sid,
                text=f"Синтетическая страница обозначает {name} как отдельный предмет описания.",
                carrier_id=carrier.carrier_id, source_version=carrier.version,
                source_sha256=carrier.sha256, page=i),)))
    return ScientificReportAsset(
        object_id=member.object_id, caller_id="demo", rights_scope="synthetic-public",
        producer_id="synthetic-fixture-author", rights_basis="invented-public-test-fixture",
        currentness_as_of="2026-10-15",
        source_member=member, method_body_version="synthetic-method-1",
        method_body_sha256=hashlib.sha256(SYNTHETIC_METHOD_BODY).hexdigest(),
        analytic_state_version="synthetic-state-1", research_problem=problem,
        author_scope="Авторство конкретных измерительных операций не установлено.",
        evidence_subassembly_ids=("component-1", "component-2"),
        subassemblies=tuple(subassemblies))


def synthetic_source_contents(runtime, asset):
    """Owner fixture reads the actual invented source bytes; never emitted."""
    directory = runtime._configuration.primary.path.parent
    return {c.carrier_id: (directory / f"{c.carrier_id}.txt").read_bytes()
            for c in asset.source_member.carriers}


def write_artifacts(output: Path, files: dict[str, bytes]):
    """Create a new directory under an existing non-link parent; never overwrite.

    Local trusted filesystem only; not an attacker-writable shared parent.
    Reject symlinks and Windows junction/reparse ancestors before creation.
    """
    output = output.absolute()
    if not {"report.html", "report.json", "receipt.json"} <= set(files) or (
            set(files) - {"report.html", "report.json", "receipt.json"} - {"report.md"}):
        raise ValueError("INVALID_ARTIFACT_SET")
    for parent in (output, *output.parents):
        if parent.is_symlink():
            raise ValueError("UNSAFE_OUTPUT_DIRECTORY")
        if parent.exists():
            info = parent.lstat()
            if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ValueError("UNSAFE_OUTPUT_DIRECTORY")
    output.mkdir(parents=False, exist_ok=False)
    for name, data in files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic, offline metadata report demonstration")
    parser.add_argument("--fixture", choices=("sechenovka-like", "meteorology"),
                        default="sechenovka-like")
    parser.add_argument("--report", choices=tuple(f"R{i:02}" for i in range(1, 10)), default="R03")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scientific", action="store_true",
                        help="Use separately authored synthetic scientific claims for R01/R02")
    args = parser.parse_args(argv)
    if args.scientific and args.report not in {"R01", "R02"}:
        parser.error("SCIENTIFIC_MODE_REQUIRES_R01_OR_R02")
    with TemporaryDirectory(prefix="seshat-synthetic-") as scratch:
        runtime = install_fixture(Path(scratch), args.fixture)
        asset = synthetic_scientific_asset(runtime, args.fixture) if args.scientific else None
        compose = report_session(runtime, authenticated_caller="demo", authorized_view="synthetic-public",
                                 scientific_assets=(asset,) if asset else (),
                                 scientific_sources=synthetic_source_contents(runtime, asset)
                                 if asset else {},
                                 method_bodies=synthetic_method_bodies()
                                 if asset else {})
        request = demo_request(args.report)
        if asset:
            request = request.model_copy(update={
                "selections": demo_request("R01").selections,
                "expected_method_body_version": asset.method_body_version})
        result = compose(request)
        write_artifacts(args.output, artifacts(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
