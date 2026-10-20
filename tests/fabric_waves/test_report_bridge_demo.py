"""The actual shipped no-network CLI path, distinct from its seam unit tests."""

import json

import pytest

from seshat.fabric_waves.report_bridge_demo import main, run_demo


def test_real_demo_method_report_and_durable_noop_resume(tmp_path):
    dest = tmp_path / "owner-private-demo"
    outcome = run_demo(dest)
    assert outcome["bridge"] == "G1_METHOD_ACTIVATED_TO_F07_F08_F09A"
    assert outcome["batch_resume"] == "VERIFIED_NOOP"
    assert outcome["science_owner_review"] == "NOT_PERFORMED"
    assert outcome["customer_release"] == "NOT_AUTHORIZED"
    visible = (dest / "report" / "report.md").read_text(encoding="utf-8")
    assert "FABRIC_GENERATED_UNREVIEWED" in visible
    assert "VERIFIED_IN_SYNTHETIC_SOURCE" in visible
    assert "Осадки в горном водосборе" in visible
    assert "Температура прибрежного слоя" in visible
    assert "Этот хеш подтверждает текст описания, НЕ исполняемый код" in visible
    private = dest / "owner-private-batch"
    assert (private / "manifest.json").exists()
    assert (private / "batch_ledger.sqlite").exists()
    assert (private / "batch_receipt.json").exists()
    assert (private / "items" / "r01-readable" / "report.md").read_text(
        encoding="utf-8"
    ) == visible
    assert "rights_sha256" not in visible
    assert "primary_sha256" not in visible
    with pytest.raises(FileExistsError):
        run_demo(dest)


def test_cli_entry_runs_real_demo_and_returns_receipt(tmp_path, capsys):
    dest = tmp_path / "owner-private-cli"
    assert main(["--output", str(dest)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["batch_resume"] == "VERIFIED_NOOP"
    assert output["mode"] == "PUBLIC_SYNTHETIC_ONLY"
    assert (dest / "report" / "report.html").exists()
    assert (dest / "owner-private-batch" / "manifest.json").exists()
