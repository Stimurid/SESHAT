"""Run from OUTSIDE the checkout using an isolated wheel-installed interpreter."""
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile

import seshat


def main():
    installed = Path(seshat.__file__).resolve()
    assert "site-packages" in installed.parts, "Must test installed wheel, not source checkout"
    executable = Path(sysconfig.get_path("scripts")) / "seshat-fabric-demo"
    if sys.platform == "win32":
        executable = executable.with_suffix(".exe")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        subprocess.run([str(executable), "--scenario", "all", "--output-dir", str(root / "out")],
                       cwd=root, check=True)
        docs = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in (root / "out").glob("s[123]-*.json")}
        assert len(docs) == 4
        assert docs["s1-s1-repair"]["run"]["outcome"] == "APORIA"
        for stem, doc in docs.items():
            assert doc["ledger"]["activations"]
            assert doc["sediment"]
            assert doc["run"]["resonance_ids"]
            assert (root / "out" / (stem + ".html")).stat().st_size
            assert (root / "out" / (stem + ".svg")).stat().st_size
        before, after = docs["s3-s3-init"], docs["s3-s3-after-delta"]
        assert all(e["run_id"] == "s3-init" for e in before["ledger"]["events"])
        changed = {a["thread_id"] for a in after["ledger"]["activations"]
                   if a["run_id"] == "s3-after-delta"}
        assert changed == {"A", "B", "C"}
    print("INSTALLED_WHEEL_SMOKE_PASS", installed)


if __name__ == "__main__":
    main()
