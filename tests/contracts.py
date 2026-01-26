import ast
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def run_help(instrument_path: str) -> str:
    res = subprocess.run(
        ["python3", instrument_path, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # even if returncode != 0, keep stdout+stderr for diagnostics
    return (res.stdout or "") + "\n" + (res.stderr or "")


def parse_help_flags(help_text: str) -> Dict[str, bool]:
    ht = help_text.lower()
    return {
        "has_new_template": "new-template" in ht or "new_template" in ht,
        "has_score": re.search(r"\bscore\b", ht) is not None,
        "mentions_bottleneck": "bottleneck" in ht,
        "mentions_agg": "--agg" in ht or "agg_" in ht,
        "mentions_outdir": "--outdir" in ht,
        "mentions_input": "--input" in ht,
        "mentions_tau_unicode": "--agg_τ" in help_text,
        "mentions_tau_ascii": "--agg_tau" in ht,
    }


def detect_tau_agg_flag(help_text: str) -> Optional[str]:
    # Priority: explicit mention in --help
    if "--agg_τ" in help_text:
        return "--agg_τ"
    if "--agg_tau" in help_text.lower():
        return "--agg_tau"
    return None


# -------------------------
# ZONES: AST extraction
# -------------------------

def extract_zone_thresholds_ast(instrument_path: str) -> Dict[str, Any]:
    """
    Heuristic AST extraction of zone logic.

    CONTRAT (stabilité):
      - Ne renvoie JAMAIS None.
      - Renvoie toujours un dict contenant au minimum:
          {
            "constants": dict[str, int|float|str],
            "if_chain": list[tuple[str, float, str]],
            "pattern": str,
          }
      - Ajoute "error" si une étape échoue.

    Objectif:
      - Rester conservateur (ne pas halluciner),
      - Mais produire des "constants" littérales (int/float/str)
        pour que contract_probe puisse compter des zones (>0) quand une structure est détectée.
    """
    out: Dict[str, Any] = {
        "constants": {},
        "if_chain": [],
        "pattern": "none",
    }

    p = Path(instrument_path)
    if not p.exists():
        out["pattern"] = "missing_file"
        out["error"] = f"instrument not found: {instrument_path}"
        return out

    src = p.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        out["pattern"] = "syntax_error"
        out["error"] = str(e)
        return out

    # 1) Look for assignments to obvious names
    candidate_names = {
        "ZONE_THRESHOLDS", "ZONES", "ZONE_BOUNDS", "ZONE_LIMITS", "ZONE_CUTS", "THRESHOLDS"
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in candidate_names:
                    val = _literal_eval_safe(node.value)

                    # a) list/tuple numeric thresholds
                    if isinstance(val, (list, tuple)) and all(_is_number(x) for x in val):
                        ths = [float(x) for x in val]
                        out["pattern"] = "assign_thresholds"
                        out["name"] = t.id
                        out["thresholds"] = ths
                        # Convert to literal constants
                        for i, th in enumerate(ths):
                            out["constants"][f"ZONE_THRESHOLD_{i}"] = th
                        return out

                    # b) dict mapping (try to flatten conservatively)
                    if isinstance(val, dict):
                        out["pattern"] = "assign_mapping"
                        out["name"] = t.id
                        out["mapping"] = val
                        _flatten_mapping_into_constants(val, out["constants"])
                        return out

    # 2) Look for if/elif chain setting zone based on T comparisons
    # Try to find comparisons like: if T < a: zone="A" elif T < b: zone="B" ...
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            chain = _collect_if_chain(node)
            if not chain:
                continue

            ths, zlabels = _parse_if_chain_for_T(chain)
            if ths and zlabels and len(ths) == len(zlabels):
                out["pattern"] = "if_chain"
                # if_chain normalized: list of (op, threshold, zone_label)
                out["if_chain"] = [("Lt", float(ths[i]), str(zlabels[i])) for i in range(len(ths))]
                # Also emit literal constants for counting/traceability
                for i, th in enumerate(ths):
                    out["constants"][f"ZONE_IF_THRESHOLD_{i}"] = float(th)
                    out["constants"][f"ZONE_IF_LABEL_{i}"] = str(zlabels[i])
                out["thresholds"] = [float(x) for x in ths]
                out["zones"] = [str(x) for x in zlabels]
                return out

    # Nothing detected (conservateur) => pattern none, constants empty
    return out


def _literal_eval_safe(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _collect_if_chain(node: ast.If) -> List[Tuple[ast.AST, List[ast.stmt]]]:
    chain: List[Tuple[ast.AST, List[ast.stmt]]] = []
    cur = node
    while isinstance(cur, ast.If):
        chain.append((cur.test, cur.body))
        if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
            cur = cur.orelse[0]
        else:
            break
    return chain


def _parse_if_chain_for_T(chain: List[Tuple[ast.AST, List[ast.stmt]]]) -> Tuple[List[float], List[str]]:
    thresholds: List[float] = []
    zones: List[str] = []
    for test, body in chain:
        th = _extract_threshold_from_test(test)
        zn = _extract_zone_from_body(body)
        if th is None or zn is None:
            return [], []
        thresholds.append(th)
        zones.append(zn)

    # require strictly increasing thresholds to reduce false matches
    if any(thresholds[i] >= thresholds[i + 1] for i in range(len(thresholds) - 1)):
        return [], []
    return thresholds, zones


def _extract_threshold_from_test(test: ast.AST) -> Optional[float]:
    # Accept patterns:
    #   T < 3
    #   T <= 3
    # Require Name 'T' or Attribute ending with '.T'
    if not isinstance(test, ast.Compare):
        return None
    if len(test.ops) != 1 or len(test.comparators) != 1:
        return None

    op = test.ops[0]
    if not isinstance(op, (ast.Lt, ast.LtE)):
        return None

    left = test.left
    if isinstance(left, ast.Name) and left.id != "T":
        return None
    if isinstance(left, ast.Attribute) and left.attr != "T":
        return None
    if not isinstance(left, (ast.Name, ast.Attribute)):
        return None

    comp = test.comparators[0]
    val = _literal_eval_safe(comp)
    if _is_number(val):
        return float(val)
    return None


def _extract_subscript_key(slice_node: ast.AST) -> Any:
    """
    Python 3.8: Subscript.slice can be ast.Index(value=...)
    Python 3.9+: slice is directly ast.Constant / ast.Tuple / ...
    """
    if isinstance(slice_node, ast.Index):  # pragma: no cover (py<3.9)
        return _literal_eval_safe(slice_node.value)
    return _literal_eval_safe(slice_node)


def _extract_zone_from_body(body: List[ast.stmt]) -> Optional[str]:
    # Look for assignment: zone = "A" or results["zone"] = "A"
    for st in body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1:
            target = st.targets[0]
            val = _literal_eval_safe(st.value)
            if isinstance(val, str) and 1 <= len(val) <= 12:
                if isinstance(target, ast.Name) and target.id in {"zone", "Zone"}:
                    return val
                if isinstance(target, ast.Subscript):
                    key = _extract_subscript_key(target.slice)
                    if key == "zone":
                        return val
    return None


def _flatten_mapping_into_constants(mapping: Dict[Any, Any], out_constants: Dict[str, Any]) -> None:
    """
    Flatten conservatively a mapping into literal constants (int/float/str).
    - keys are stringified to keep deterministic names.
    - nested containers are flattened only one level when safe.
    """
    for k, v in mapping.items():
        k_str = str(k)

        # literal
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            out_constants[f"ZONE_MAP_{k_str}"] = v
            continue

        # list/tuple of literals -> flatten indices
        if isinstance(v, (list, tuple)):
            for i, it in enumerate(v):
                if isinstance(it, (int, float, str)) and not isinstance(it, bool):
                    out_constants[f"ZONE_MAP_{k_str}_{i}"] = it
            continue

        # dict one-level -> flatten key/value if literal
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, (int, float, str)) and not isinstance(vv, bool):
                    out_constants[f"ZONE_MAP_{k_str}_{str(kk)}"] = vv
            continue
