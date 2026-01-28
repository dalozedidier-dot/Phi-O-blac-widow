#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""run_pipeline.py

Minimal orchestrator:
- run a collector profile
- feed the collected dataset into a core profile

Kept intentionally simple to preserve PhiO traceability:
collector and core communicate only via files.

Usage:
  python scripts/run_pipeline.py --profile profiles/pipeline_example.toml
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_toml(path: Path) -> dict:
    import tomllib  # py3.11+

    return tomllib.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="TOML pipeline profile")
    ap.add_argument("--run-id", default=None, help="Shared run id for collector+core")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    profile_path = (repo_root / args.profile).resolve() if not os.path.isabs(args.profile) else Path(args.profile)
    cfg = _load_toml(profile_path)
    pipe = cfg.get("pipeline")
    if not isinstance(pipe, dict):
        raise SystemExit(f"Invalid pipeline profile: missing [pipeline] section: {profile_path}")

    collector_profile = pipe.get("collector_profile")
    core_profile = pipe.get("core_profile")
    out_override = str(pipe.get("core_out_base_override", "")).strip()

    if not collector_profile or not core_profile:
        raise SystemExit(
            f"Invalid pipeline profile: collector_profile and core_profile are required: {profile_path}"
        )

    run_id = args.run_id or _utc_run_id()

    # 1) collector
    from scripts.run_collector import _collector_local_copy, _parse_profile as _parse_collector

    cprof_path = (repo_root / str(collector_profile)).resolve()
    cprof = _parse_collector(cprof_path)
    collected_dataset = _collector_local_copy(repo_root, cprof, run_id)

    # 2) core, but override input to the collected dataset
    from scripts.run_core import _parse_profile as _parse_core, _run_instrument, _ensure_dir

    core_prof_path = (repo_root / str(core_profile)).resolve()
    kprof = _parse_core(core_prof_path)

    instrument = (repo_root / kprof.instrument).resolve() if not os.path.isabs(kprof.instrument) else Path(kprof.instrument)
    out_base = (
        (repo_root / out_override).resolve()
        if out_override
        else ((repo_root / kprof.out_base).resolve() if not os.path.isabs(kprof.out_base) else Path(kprof.out_base))
    )
    outdir = out_base / run_id
    _ensure_dir(outdir)

    rc = _run_instrument(instrument, collected_dataset, outdir, kprof.extra_args)
    print(f"[run_pipeline] done: run_id={run_id} rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
