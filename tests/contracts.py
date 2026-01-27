from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =========================================================
# CLI helpers (importés par tests/test_00_contract_cli.py)
# =========================================================

def run_help(instrument_path: str) -> str:
    """
    Exécute: python3 <instrument> --help
    Retourne stdout+stderr (ne raise pas).
    """
    res = subprocess.run(
        ["python3", instrument_path, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return (res.stdout or "") + (res.stderr or "")


def _extract_long_flags(help_text: str) -> List[str]:
    """
    Extrait les flags longs depuis un help argparse.
    Supporte unicode τ.
    """
    flags = re.findall(r"(?<!\w)(--[0-9A-Za-z_\-τ]+)", help_text or "")
    return sorted(set(f.strip() for f in flags if f.strip()))


def parse_help_flags(help_text: str) -> Dict[str, Any]:
    """
    Doit retourner un dict (les tests indexent avec flags["mentions_input"], etc.)
    """
    flags_list = _extract_long_flags(help_text)
    txt = (help_text or "").lower()

    return {
        "flags": flags_list,
        "has_new_template": ("new-template" in txt),
        "has_score": (re.search(r"\bscore\b", txt) is not None),
        "mentions_input": ("--input" in flags_list) or ("--input" in txt),
        "mentions_outdir": ("--outdir" in flags_list) or ("--outdir" in txt),
        "mentions_agg": (
            ("--agg_tau" in flags_list)
            or ("--agg_τ" in flags_list)
            or ("--agg" in txt)
            or ("agg_" in txt)
        ),
        "mentions_bottleneck": ("bottleneck" in txt),
    }


def detect_tau_agg_flag(help_text: str) -> Optional[str]:
    """
    Retourne un string (ou None). Les tests attendent:
      - "--agg_τ" prioritaire
      - sinon "--agg_tau"
    """
    flags_list = _extract_long_flags(help_text)
    if "--agg_τ" in flags_list:
        return "--agg_τ"
    if "--agg_tau" in flags_list:
        return "--agg_tau"
    return None


def extract_cli_contract(help_text: str) -> Dict[str, Any]:
    """
    Contrat CLI (utilisable par contract_probe.py si besoin).
    """
    flags_list = _extract_long_flags(help_text)
    txt = help_text or ""

    subcommands: List[str] = []
    for cmd in ["new-template", "score"]:
        if re.search(rf"\b{re.escape(cmd)}\b", txt):
            subcommands.append(cmd)

    tau_aliases = {
        "has_tau_ascii": ("--agg_tau" in flags_list) or ("--agg_tau" in txt),
        "has_tau_unicode": ("--agg_τ" in flags_list) or ("--agg_τ" in txt),
    }

    return {
        "help_valid": len((help_text or "").strip()) > 0,
        "help_len": len(help_text or ""),
        "subcommands": sorted(set(subcommands)),
        "flags": flags_list,
        "required_subcommands": ["new-template", "score"],
        "required_flags": ["--input", "--outdir"],
        "tau_aliases": tau_aliases,
    }


# =========================================================
# Zones extraction (AST + fallback)
# =========================================================

def _literal_eval_safe(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _collect_if_chain(node: ast.If) -> Optional[List[ast.If]]:
    chain: List[ast.If] = []
    cur: Optional[ast.If] = node
    while isinstance(cur, ast.If):
        chain.append(cur)
        if cur.orelse and len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
            cur = cur.orelse[0]
        else:
            break
    return chain if chain else None


def _extract_threshold_from_test(test: ast.AST) -> Optional[float]:
    if not isinstance(test, ast.Compare):
        return None
    if len(test.ops) != 1 or len(test.comparators) != 1:
        return None

    left = test.left
    right = test.comparators[0]

    # Heuristique minimale: variable T ou t
    if not isinstance(left, ast.Name) or left.id not in {"T", "t"}:
        return None

    val = _literal_eval_safe(right)
    return float(val) if _is_number(val) else None


def _extract_zone_from_body(body: List[ast.stmt]) -> Optional[str]:
    for st in body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            if st.targets[0].id in {"zone", "Z", "label"}:
                val = _literal_eval_safe(st.value)
                if isinstance(val, str) and val:
                    return val
    return None


def _parse_if_chain_for_T(chain: List[ast.If]) -> Tuple[List[float], List[str]]:
    thresholds: List[float] = []
    zones: List[str] = []
    for n in chain:
        th = _extract_threshold_from_test(n.test)
        z = _ex_
