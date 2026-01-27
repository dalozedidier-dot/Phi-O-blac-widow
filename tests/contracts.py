from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _debug(msg: str) -> None:
    if os.environ.get("PHIO_DEBUG_PROBE", "0") == "1":
        print(f"[PHIO_DEBUG_PROBE] {msg}")


def _load_local_contracts_module(repo_root: Path):
    """
    Charge ./tests/contracts.py de manière déterministe.
    Évite la dérive d'import où 'tests' peut pointer ailleurs.
    """
    contracts_path = repo_root / "tests" / "contracts.py"
    if not contracts_path.exists():
        _debug(f"no tests/contracts.py at {contracts_path}")
        return None

    spec = importlib.util.spec_from_file_location("phio_repo_tests_contracts", str(contracts_path))
    if spec is None or spec.loader is None:
        _debug("spec_from_file_location failed")
        return None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    _debug(f"loaded contracts module from {contracts_path}")
    return mod


def _run_help_fallback(instrument_path: str) -> str:
    res = subprocess.run(
        ["python3", instrument_path, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return (res.stdout or "") + (res.stderr or "")


def _fallback_regex_thresholds_from_file(instrument_path: Path) -> Optional[Dict[str, Any]]:
    """
    Fallback strict (sans eval) : extrait ZONE_THRESHOLDS = [0.5, 1.5, 2.5]
    ou tuple.
    """
    src = instrument_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(?m)^\s*ZONE_THRESHOLDS\s*=\s*\[([^\]]+)\]\s*$", src)
    if not m:
        m = re.search(r"(?m)^\s*ZONE_THRESHOLDS\s*=\s*\(([^\)]+)\)\s*$", src)
    if not m:
        return None

    inside = m.group(1)
    nums = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", inside)
    if not nums:
        return None

    thresholds = [float(x) for x in nums]
    return {"thresholds": thresholds, "pattern": "fallback_regex", "name": "ZONE_THRESHOLDS"}


def extract_cli_contract(instrument_path: Path, run_help_fn) -> Dict[str, Any]:
    cli: Dict[str, Any] = {
        "help_valid": False,
        "help_len": 0,
        "subcommands": [],
        "flags": [],
        "required_subcommands": ["new-template", "score"],
        "required_flags": ["--input", "--outdir"],
    }
    try:
        help_text = run_help_fn(str(instrument_path))
        cli["help_valid"] = True
        cli["help_len"] = len(help_text or "")
    except Exception as e:
        cli["error"] = str(e)
        return cli

    help_text = help_text or ""
    cli["subcommands"] = [s for s in cli["required_subcommands"] if s in help_text]

    flags = []
    for f in ["--input", "--outdir", "--help", "--agg_tau", "--agg_τ"]:
        if f in help_text:
            flags.append(f)
    cli["flags"] = sorted(set(flags))

    cli["tau_aliases"] = {
        "has_tau_ascii": "--agg_tau" in help_text,
        "has_tau_unicode": "--agg_τ" in help_text,
    }
    return cli


def extract_zones(instrument_path: Path, extractor_fn) -> Dict[str, Any]:
    """
    Zones:
    - appelle extractor_fn si disponible
    - si None => fallback regex interne (ZONE_THRESHOLDS)
    Normalise en zones/constants.
    """
    out: Dict[str, Any] = {
        "zones": {},
        "constants": {},
        "if_chain": [],
        "attempted": True,
        "method": "ast",
    }

    raw = None
    try:
        raw = extractor_fn(str(instrument_path)) if extractor_fn else None
    except Exception as e:
        _debug(f"extractor_fn exception: {e!r}")
        raw = None

    if raw is None:
        fb = _fallback_regex_thresholds_from_file(instrument_path)
        if fb is None:
            out["method"] = "ast_failed"
            out["error"] = "extract_zone_thresholds_ast returned None"
            return out
        out["method"] = "fallback"
        out["fallback"] = "ZONE_THRESHOLDS_regex"
        raw = fb

    if not isinstance(raw, dict):
        out["method"] = "ast_failed"
        out["error"] = f"extract_zone_thresholds_ast returned non-dict: {type(raw).__name__}"
        return out

    # thresholds -> constants THRESH_i
    if isinstance(raw.get("thresholds"), (list, tuple)):
        ths = []
        for x in list(raw.get("thresholds")):
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                ths.append(float(x))
        out["constants"] = {f"THRESH_{i}": v for i, v in enumerate(ths)}
        out["pattern"] = raw.get("pattern", "thresholds")
        out["name"] = raw.get("name")

    # mapping -> constants
    elif isinstance(raw.get("mapping"), dict):
        mp = raw.get("mapping") if isinstance(raw.get("mapping"), dict) else {}
        out["constants"] = {
            str(k): v
            for k, v in mp.items()
            if isinstance(v, (int, float, str)) and not isinstance(v, bool)
        }
        out["pattern"] = raw.get("pattern", "mapping")
        out["name"] = raw.get("name")

    # passthrough
    elif isinstance(raw.get("constants"), dict) or isinstance(raw.get("if_chain"), list):
        out["constants"] = raw.get("constants") if isinstance(raw.get("constants"), dict) else {}
        out["if_chain"] = raw.get("if_chain") if isinstance(raw.get("if_chain"), list) else []
        out["pattern"] = raw.get("pattern", "ast")

    else:
        out["method"] = "ast_failed"
        out["error"] = "extract_zone_thresholds_ast returned dict without recognized keys: " + ", ".join(sorted(raw.keys()))
        return out

    out["zones"] = {
        k: v
        for k, v in (out.get("constants") or {}).items()
        if isinstance(v, (int, float, str)) and not isinstance(v, bool)
    }
    return out


def _run_score_once(
    instrument_path: Path, input_json: Dict[str, Any]
) -> Tuple[int, str, str, Optional[Dict[str, Any]]]:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        in_path = td_path / "input.json"
        out_dir = td_path / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        in_path.write_text(json.dumps(input_json, ensure_ascii=False, indent=2), encoding="utf-8")

        cmd = ["python3", str(instrument_path), "score", "--input", str(in_path), "--outdir", str(out_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

        results_path = out_dir / "results.json"
        results = None
        if results_path.exists():
            try:
                results = json.loads(results_path.read_text(encoding="utf-8"))
            except Exception:
                results = None
        return proc.returncode, proc.stdout or "", proc.stderr or "", results


def check_formula_contract(_instrument_path: Path) -> Dict[str, Any]:
    # volontairement minimal ici (ton pipeline actuel met formula_checked=False)
    return {"golden_attempted": False, "golden_pass": False}


def calculate_compliance_levels(cli_info: Dict[str, Any], zones_info: Dict[str, Any], formula_info: Dict[str, Any]) -> Dict[str, Any]:
    def assess_level(full: bool, partial: bool) -> str:
        if full:
            return "FULL"
        if partial:
            return "PARTIAL"
        return "MINIMAL"

    cli_full = bool(
        cli_info.get("help_valid", False)
        and len(cli_info.get("subcommands", [])) >= 2
        and all(f in (cli_info.get("flags") or []) for f in ["--input", "--outdir"])
    )
    cli_partial = bool(cli_info.get("help_valid", False))
    cli_level = assess_level(cli_full, cli_partial)

    zones = zones_info.get("zones") or {}
    literal_zones = {k: v for k, v in zones.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool)}
    zones_full = len(literal_zones) > 0
    zones_partial = bool(zones_info.get("attempted", False))
    zones_level = assess_level(zones_full, zones_partial)

    formula_full = bool(formula_info.get("golden_pass", False))
    formula_partial = bool(formula_info.get("golden_attempted", False))
    formula_level = assess_level(formula_full, formula_partial)

    order = {"FULL": 3, "PARTIAL": 2, "MINIMAL": 1}
    global_level = min([cli_level, zones_level, formula_level], key=lambda x: order[x])

    return {
        "axes": {"cli": cli_level, "zones": zones_level, "formula": formula_level},
        "global": global_level,
        "summary": f"CLI:{cli_level}/ZONES:{zones_level}/FORMULA:{formula_level}",
    }


def generate_contract_report(instrument_path: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parent
    _debug(f"contract_probe.py path={Path(__file__).resolve()}")
    _debug(f"repo_root={repo_root}")

    contracts_mod = _load_local_contracts_module(repo_root)
    run_help_fn = getattr(contracts_mod, "run_help", _run_help_fallback) if contracts_mod else _run_help_fallback
    extractor_fn = getattr(contracts_mod, "extract_zone_thresholds_ast", None) if contracts_mod else None

    cli = extract_cli_contract(instrument_p_
