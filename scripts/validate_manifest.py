#!/usr/bin/env python3
"""
scripts/validate_manifest.py

Lightweight structural validator for the PhiO collector manifest.json.

Design goals:
- Zero third-party dependencies (no jsonschema).
- Enforce *structure* only: required keys, types, and basic integrity checks.
- No semantic judgement of content beyond basic well-formedness.

Exit codes:
- 0: OK
- 2: Validation failed
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple


_SHA_RE = re.compile(r"^(?:[0-9a-fA-F]{64}|NO_SHA256_TOOL|ERROR)$")


def _fail(msg: str) -> int:
    sys.stderr.write(f"[manifest] invalid: {msg}\n")
    return 2


def _is_int(x: Any) -> bool:
    # Reject bool (subclass of int)
    return isinstance(x, int) and not isinstance(x, bool)


def validate_manifest(data: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "root must be an object"

    required_top = ("root", "generated", "count", "entries")
    for k in required_top:
        if k not in data:
            return False, f"missing top-level key: {k}"

    # No extra keys (keep the contract tight but minimal)
    extra = set(data.keys()) - set(required_top)
    if extra:
        return False, f"unexpected top-level keys: {sorted(extra)}"

    if not isinstance(data["root"], str) or not data["root"].strip():
        return False, "root must be a non-empty string"

    if not isinstance(data["generated"], str) or not data["generated"].strip():
        return False, "generated must be a non-empty string"

    if not _is_int(data["count"]) or data["count"] < 0:
        return False, "count must be a non-negative integer"

    entries = data["entries"]
    if not isinstance(entries, list):
        return False, "entries must be an array"

    if data["count"] != len(entries):
        return False, "count must match len(entries)"

    seen_paths = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            return False, f"entries[{i}] must be an object"

        required_entry = ("path", "sha256", "bytes")
        for k in required_entry:
            if k not in e:
                return False, f"entries[{i}] missing key: {k}"

        extra_e = set(e.keys()) - set(required_entry)
        if extra_e:
            return False, f"entries[{i}] unexpected keys: {sorted(extra_e)}"

        path = e["path"]
        if not isinstance(path, str) or not path.strip():
            return False, f"entries[{i}].path must be a non-empty string"
        if path in seen_paths:
            return False, f"duplicate path in entries: {path}"
        seen_paths.add(path)

        sha = e["sha256"]
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            return False, f"entries[{i}].sha256 invalid format: {sha!r}"

        b = e["bytes"]
        if not _is_int(b) or b < 0:
            return False, f"entries[{i}].bytes must be a non-negative integer"

    # Ensure entries are sorted by path (collector promises this)
    paths = [e["path"] for e in entries]
    if paths != sorted(paths):
        return False, "entries must be sorted by path"

    return True, "ok"


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("Usage: validate_manifest.py /path/to/manifest.json\n")
        return 2

    p = argv[1]
    if not os.path.isfile(p):
        return _fail(f"file not found: {p}")

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as ex:
        return _fail(f"cannot read JSON: {ex}")

    ok, msg = validate_manifest(data)
    if not ok:
        return _fail(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
