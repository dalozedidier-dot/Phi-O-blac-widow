"""
contract_probe.py

Génère un rapport contractuel (CLI + zones + formule) pour l'instrument Phi⊗O.

Objectif: un contrat honnête et CI-friendly.
- Zones: extraction statique (AST via tests/contracts.py + fallback regex sur ZONE_THRESHOLDS)
- CLI: présence de sous-commandes/flags attendus via --help
- Formule: optionnelle via run "score" contrôlé
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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


# ---------------------------------------------------------
# Deterministic load of ./tests/contracts.py (no import drift)
# ---------------------------------------------------------

def _load_local_contracts_module(repo_root: Path):
    """
    Charge repo-local tests/contracts.py de manière déterministe.
    Évite qu'un 'tests' externe (site-packages) masque ton module.
    """
    contracts_path = repo_root / "tests" / "contracts.py"
    if not contracts_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("phio_repo_tests_contracts", str(contracts_path))
    if spec is None or spec.loader is None:
        return None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _run_help_fallback(instrument_path: str) -> str:
    res = subprocess.run(
        ["python3", instrument_path, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return (res.stdout or "") + (res.stderr or "")


def _fallback_regex_thresholds(src: str) -> Optional[Dict[str, Any]]:
    """
    Fallback direct (sans eval): extrait ZONE_THRESHOLDS = [0.5, 1.5, 2.5]
    Parse uniquement des nombres.
    """
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


# ----------------------------
# Contract sections
# ----------------------------

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
    Extraction zones:
    - tente extractor_fn (repo-local tests/contracts.py)
    - si None => fallback regex interne sur ZONE_THRESHOLDS
    Ne crashe jamais.
    """
    out: Dict[str, Any] = {
        "zones": {},
        "constants": {},
        "if_chain": [],
        "attempted": True,
        "method": "ast",
    }

    try:
        raw = extractor_fn(str(instrument_path)) if extractor_fn else None

        if raw is None:
            src = instrument_path.read_text(encoding="utf-8", errors="ignore")
            fb = _fallback_regex_thresholds(src)
            if fb is None:
                out["method"] = "ast_failed"
                out["error"] = "extract_zone_thresholds_ast returned None"
                return out
            raw = fb
            out["method"] = "fallback"
            out["fallback"] = "ZONE_THRESHOLDS_regex"

        if not isinstance(raw, dict):
            out["method"] = "ast_failed"
            out["error"] = f"extract_zone_thresholds_ast returned non-dict: {type(raw).__name__}"
            return out

        # Normalisation:
        # - thresholds -> constants THRESH_i
        if isinstance(raw.get("thresholds"), (list, tuple)):
            ths = []
            for x in list(raw.get("thresholds")):
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    ths.append(float(x))
            out["constants"] = {f"THRESH_{i}": v for i, v in enumerate(ths)}
            out["pattern"] = raw.get("pattern", "thresholds")
            out["name"] = raw.get("name")

        # - mapping -> constants
        elif isinstance(raw.get("mapping"), dict):
            mp = raw.get("mapping") if isinstance(raw.get("mapping"), dict) else {}
            out["constants"] = {
                str(k): v for k, v in mp.items()
                if isinstance(v, (int, float, str)) and not isinstance(v, bool)
            }
            out["pattern"] = raw.get("pattern", "mapping")
            out["name"] = raw.get("name")

        # - passthrough format (si ton extracteur retourne déjà constants/if_chain)
        elif isinstance(raw.get("constants"), dict) or isinstance(raw.get("if_chain"), list):
            out["constants"] = raw.get("constants") if isinstance(raw.get("constants"), dict) else {}
            out["if_chain"] = raw.get("if_chain") if isinstance(raw.get("if_chain"), list) else []
            out["pattern"] = raw.get("pattern", "ast")

        else:
            out["method"] = "ast_failed"
            out["error"] = "extract_zone_thresholds_ast returned dict without recognized keys: " + ", ".join(sorted(raw.keys()))
            return out

        # zones = constants (littérales)
        out["zones"] = {
            k: v for k, v in (out.get("constants") or {}).items()
            if isinstance(v, (int, float, str)) and not isinstance(v, bool)
        }
        return out

    except Exception as e:
        out["method"] = "ast_failed"
        out["error"] = str(e)
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


def check_formula_contract(instrument_path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"golden_attempted": True, "golden_pass": False}

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tpath = td_path / "template.json"

        proc = subprocess.run(
            ["python3", str(instrument_path), "new-template", "--name", "ContractProbe", "--out", str(tpath)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0 or not tpath.exists():
            info["error"] = f"new-template failed: {proc.stderr or proc.stdout}"
            return info

        template = json.loads(tpath.read_text(encoding="utf-8"))
        for it in template.get("items", []):
            if "score" in it:
                it["score"] = 2

        rc, _out, err, results = _run_score_once(instrument_path, template)
        if rc != 0 or not results:
            info["error"] = f"score failed: {err}"
            return info

        if "T" not in results or "K_eff" not in results:
            info["error"] = "results.json missing T and/or K_eff"
            return info

        info["golden_pass"] = True
        return info


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


def generate_contract_report(instrument_path: Path, check_formula: bool) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parent
    contracts_mod = _load_local_contracts_module(repo_root)

    run_help_fn = getattr(contracts_mod, "run_help", _run_help_fallback) if contracts_mod else _run_help_fallback
    extractor_fn = getattr(contracts_mod, "extract_zone_thresholds_ast", None) if contracts_mod else None

    cli = extract_cli_contract(instrument_path, run_help_fn=run_help_fn)
    zones = extract_zones(instrument_path, extractor_fn=extractor_fn)
    formula = check_formula_contract(instrument_path) if check_formula else {"golden_attempted": False, "golden_pass": False}
    compliance = calculate_compliance_levels(cli, zones, formula)

    zones_count = len([k for k, v in (zones.get("zones") or {}).items() if isinstance(v, (int, float, str)) and not isinstance(v, bool)])

    return {
        "contract_version": "1.5",
        "instrument_path": str(instrument_path),
        "instrument_hash": f"sha256:{_sha256_file(instrument_path)}",
        "validation_timestamp": datetime.now(timezone.utc).isoformat(),
        "compliance": compliance,
        "summary": {
            "cli_help_valid": cli.get("help_valid", False),
            "zones_attempted": zones.get("attempted", False),
            "zones_count": zones_count,
            "formula_checked": bool(check_formula),
            "formula_pass": bool(formula.get("golden_pass", False)) if check_formula else False,
        },
        "cli": cli,
        "zones": zones,
        "formula": formula,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a contractual validation report for Phi⊗O.")
    ap.add_argument("--instrument", required=True, help="Path to the instrument python file.")
    ap.add_argument("--out", required=True, help="Output JSON report path.")
    ap.add_argument("--check-formula", action="store_true", help="Also run a deterministic score to verify formula.")
    args = ap.parse_args()

    inst = Path(args.instrument).resolve()
    if not inst.exists():
        raise SystemExit(f"Instrument not found: {inst}")

    report = generate_contract_report(inst, check_formula=bool(args.check_formula))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote contract report to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
