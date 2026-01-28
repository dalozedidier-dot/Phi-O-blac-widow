#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""run_core.py

Core runner (DD/DD-R/E harness wrapper).

PhiO principle:
- core == deterministic compute + traceability
- no collection logic here
- no semantic judgement here

Today this script wraps the repo instrument CLI (phi_otimes_o_instrument_v0_1.py)
so you can run stable, reproducible jobs from a profile file.

Profile format: TOML (stdlib tomllib on Python >=3.11)

Usage:
  python scripts/run_core.py --profile profiles/core_example.toml
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_toml(path: Path) -> dict:
    import tomllib  # py3.11+

    return tomllib.loads(path.read_text(encoding="utf-8"))


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class CoreProfile:
    instrument: str
    input: str
    out_base: str
    extra_args: List[str]


def _parse_profile(profile_path: Path) -> CoreProfile:
    cfg = _load_toml(profile_path)
    core = cfg.get("core")
    if not isinstance(core, dict):
        raise SystemExit(f"Invalid profile: missing [core] section: {profile_path}")

    instrument = str(core.get("instrument", "./phi_otimes_o_instrument_v0_1.py"))
    input_path = core.get("input")
    out_base = str(core.get("out_base", "./runs"))
    extra_args = core.get("extra_args", [])

    if not input_path:
        raise SystemExit(f"Invalid profile: [core].input is required: {profile_path}")
    if not isinstance(extra_args, list) or not all(isinstance(x, str) for x in extra_args):
        raise SystemExit(f"Invalid profile: [core].extra_args must be a list of strings: {profile_path}")

    return CoreProfile(
        instrument=instrument,
        input=str(input_path),
        out_base=out_base,
        extra_args=list(extra_args),
    )


def _run_instrument(instrument: Path, input_path: Path, outdir: Path, extra_args: List[str]) -> int:
    cmd = [sys.executable, str(instrument), "score", "--input", str(input_path), "--outdir", str(outdir)]
    cmd.extend(extra_args)

    print("[run_core] cmd:", " ".join(cmd))
    cp = subprocess.run(cmd, text=True, capture_output=False, check=False)
    return cp.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="TOML profile file")
    ap.add_argument("--run-id", default=None, help="Override run id (default: UTC timestamp)")
    ap.add_argument(
        "--write-run-manifest",
        action="store_true",
        help="Write a tiny run manifest next to outputs (structure-only).",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    profile_path = (repo_root / args.profile).resolve() if not os.path.isabs(args.profile) else Path(args.profile)
    prof = _parse_profile(profile_path)

    instrument = (repo_root / prof.instrument).resolve() if not os.path.isabs(prof.instrument) else Path(prof.instrument)
    input_path = (repo_root / prof.input).resolve() if not os.path.isabs(prof.input) else Path(prof.input)
    out_base = (repo_root / prof.out_base).resolve() if not os.path.isabs(prof.out_base) else Path(prof.out_base)

    run_id = args.run_id or _utc_run_id()
    outdir = out_base / run_id
    _ensure_dir(outdir)

    if not instrument.exists():
        raise SystemExit(f"Instrument not found: {instrument}")
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    rc = _run_instrument(instrument, input_path, outdir, prof.extra_args)

    if args.write_run_manifest:
        manifest = {
            "run_id": run_id,
            "profile": str(profile_path),
            "core": asdict(prof),
            "outdir": str(outdir),
            "returncode": rc,
            "utc": datetime.now(timezone.utc).isoformat(),
        }
        (outdir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
