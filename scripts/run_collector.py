#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""run_collector.py

Collector module runner (data acquisition only).

Rules:
- No DD/DD-R/E calculations here
- No semantic judgement
- Write a collector_manifest.json with hashes + provenance

Profile format: TOML (stdlib tomllib on Python >=3.11)

Usage:
  python scripts/run_collector.py --profile collectors/local_copy_example.toml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_toml(path: Path) -> dict:
    import tomllib  # py3.11+

    return tomllib.loads(path.read_text(encoding="utf-8"))


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class CollectorProfile:
    kind: str
    source: str
    out_base: str
    tag: str


def _parse_profile(profile_path: Path) -> CollectorProfile:
    cfg = _load_toml(profile_path)
    c = cfg.get("collector")
    if not isinstance(c, dict):
        raise SystemExit(f"Invalid profile: missing [collector] section: {profile_path}")

    kind = str(c.get("kind", "local_copy")).strip()
    source = c.get("source")
    out_base = str(c.get("out_base", "./collected")).strip()
    tag = str(c.get("tag", "")).strip()

    if kind != "local_copy":
        raise SystemExit(
            f"Unsupported collector kind: {kind}. "
            "This update ships only a local_copy example to keep deps at zero."
        )
    if not source:
        raise SystemExit(f"Invalid profile: [collector].source is required: {profile_path}")

    return CollectorProfile(kind=kind, source=str(source), out_base=out_base, tag=tag)


def _collector_local_copy(repo_root: Path, prof: CollectorProfile, run_id: str) -> Path:
    src = (repo_root / prof.source).resolve() if not os.path.isabs(prof.source) else Path(prof.source)
    out_base = (repo_root / prof.out_base).resolve() if not os.path.isabs(prof.out_base) else Path(prof.out_base)
    outdir = out_base / run_id
    _ensure_dir(outdir)

    if not src.exists() or not src.is_file():
        raise SystemExit(f"Collector source not found: {src}")

    dst = outdir / src.name
    dst.write_bytes(src.read_bytes())

    manifest = {
        "run_id": run_id,
        "kind": prof.kind,
        "tag": prof.tag,
        "source": str(src),
        "output": str(dst),
        "sha256": _sha256_file(dst),
        "utc": datetime.now(timezone.utc).isoformat(),
        "profile": asdict(prof),
    }
    (outdir / "collector_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="TOML collector profile")
    ap.add_argument("--run-id", default=None, help="Override run id (default: UTC timestamp)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    profile_path = (repo_root / args.profile).resolve() if not os.path.isabs(args.profile) else Path(args.profile)
    prof = _parse_profile(profile_path)
    run_id = args.run_id or _utc_run_id()

    _ = _collector_local_copy(repo_root, prof, run_id)
    print(f"[run_collector] ok: {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
