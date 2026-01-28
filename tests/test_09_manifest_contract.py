from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_collector_manifest_contract(tmp_path: Path):
    """
    Produces a bundle via scripts/phio_llm_collect.sh and validates manifest.json structure.

    This is intentionally *structural*:
    - does not judge semantic content
    - ensures the collector output remains well-formed and internally consistent
    """
    repo_root = Path(__file__).resolve().parents[1]
    collector = repo_root / "scripts" / "phio_llm_collect.sh"
    validator = repo_root / "scripts" / "validate_manifest.py"

    outdir = tmp_path / "_out"
    outdir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["QUIET"] = "1"
    env["INCLUDE_CONCAT"] = "0"
    env["INCLUDE_PIP_FREEZE"] = "0"
    env["INCLUDE_TEST_OUTPUTS"] = "0"

    # Collect from a tiny synthetic root to keep the test fast and stable.
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    (root / "b.json").write_text('{"k": 1}\n', encoding="utf-8")

    subprocess.run(
        ["bash", str(collector), str(root), str(outdir)],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    manifest = outdir / "manifest.json"
    assert manifest.is_file(), "collector did not produce manifest.json"

    subprocess.run(
        ["python3", str(validator), str(manifest)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
