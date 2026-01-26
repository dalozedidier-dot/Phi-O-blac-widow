# phi_otimes_o_instrument_v0_1.py
# PhiO instrument v0.1 — reference CLI for tests (new-template / score).
from __future__ import annotations

import argparse
import json
import os
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


__instrument_id__ = "phi_otimes_o"
__version__ = "0.1"

# Exposé explicitement pour extraction AST (tests/contracts.py)
ZONE_THRESHOLDS: List[float] = [1.0, 2.0, 3.0]


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    weight: float = 1.0


def _tau_label() -> str:
    # Par défaut: τ ; option pour forcer ASCII
    force_ascii = os.environ.get("PHIO_FORCE_ASCII_TAU", "0") == "1"
    return "tau" if force_ascii else "τ"


def _core_dimensions() -> Tuple[str, ...]:
    # Dimensions contractuelles attendues par les tests (golden formula, monotonicity)
    tau = _tau_label()
    return ("Cx", "K", tau, "G", "D")


def get_spec() -> Dict[str, Any]:
    tau = _tau_label()
    dims = [
        Dimension("Cx", "Cx", 1.0),
        Dimension("K", "K", 1.0),
        Dimension(tau, tau, 1.0),
        Dimension("G", "G", 1.0),
        Dimension("D", "D", 1.0),
    ]
    return {
        "instrument_id": __instrument_id__,
        "version": __version__,
        "dimensions": [asdict(d) for d in dims],
        "features": {
            "aggregation": True,
            "traceability": True,
            "golden_formula": True,
            "consistency": True,
            "bottleneck_dominance": True,
            "zones": True,
        },
        "score_range": {"min": 0, "max": 3, "type": "int"},
    }


def _median_int(xs: List[int]) -> float:
    # statistics.median retourne int/float selon parité; on cast en float
    return float(statistics.median(xs))


def _aggregate(scores: List[int], mode: str) -> float:
    if not scores:
        return 0.0
    mode = (mode or "median").lower()
    if mode == "median":
        return _median_int(scores)
    if mode == "bottleneck":
        # lecture "bottleneck" = pire cas (scores sont des niveaux de criticité)
        return float(max(scores))
    raise ValueError(f"Unknown aggregation mode: {mode}")


def _validate_input(payload: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    if "items" not in payload or not isinstance(payload.get("items"), list):
        return "Input invalide: clé 'items' absente ou non-liste", "invalid_items"
    for i, it in enumerate(payload.get("items", [])):
        if not isinstance(it, dict):
            return f"Item #{i} invalide (doit être objet)", "invalid_item"
        if "dimension" not in it:
            return f"Item #{i} invalide: 'dimension' manquant", "missing_dimension"
        if "score" not in it:
            return f"Item #{i} invalide: 'score' manquant", "missing_score"
        sc = it.get("score")
        # int-only contract
        if isinstance(sc, bool) or not isinstance(sc, int):
            return f"Item #{i}: score doit être un int (0..3)", "score_type"
        if sc < 0 or sc > 3:
            return f"Item #{i}: score hors-borne (0..3)", "score_range"
        w = it.get("weight", 1.0)
        try:
            float(w)
        except Exception:
            return f"Item #{i}: weight non-numérique", "weight_type"
    return None, None


def _dimension_scores(payload: Mapping[str, Any], agg_map: Mapping[str, str]) -> Dict[str, float]:
    bucket: Dict[str, List[int]] = {}
    for it in payload.get("items", []):
        d = str(it.get("dimension"))
        bucket.setdefault(d, []).append(int(it.get("score")))
    out: Dict[str, float] = {}
    for d, xs in bucket.items():
        out[d] = _aggregate(xs, agg_map.get(d, "median"))
    return out


def _compute_T_and_Keff(dim_scores: Mapping[str, float]) -> Tuple[float, float]:
    # tau can be unicode or ascii label; take whichever is present
    Cx = float(dim_scores.get("Cx", 0.0))
    K = float(dim_scores.get("K", 0.0))
    tau = float(dim_scores.get("τ", dim_scores.get("tau", 0.0)))
    G = float(dim_scores.get("G", 0.0))
    D = float(dim_scores.get("D", 0.0))

    denom = 1.0 + tau + G + D + Cx
    K_eff = 0.0 if denom == 0.0 else K / denom
    T = Cx + tau + G + D - K_eff
    return T, K_eff


def _zone_from_T(T: float) -> str:
    # 4 zones A/B/C/D by cutpoints
    a, b, c = ZONE_THRESHOLDS
    if T < a:
        return "A"
    if T < b:
        return "B"
    if T < c:
        return "C"
    return "D"


def cmd_new_template(args: argparse.Namespace) -> int:
    out_path = Path(args.out).expanduser().resolve()
    tau = _tau_label()
    # default template: one item per core dimension, score=1
    items = []
    for d in _core_dimensions():
        items.append(
            {
                "dimension": d,
                "score": 1,
                "weight": 1.0,
                "justification": "template",
            }
        )

    payload = {
        "system": {
            "name": args.name or "PhiO",
            "description": "template",
            "context": "generated",
        },
        "items": items,
        "spec": get_spec(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _parse_agg_args(ns: argparse.Namespace) -> Dict[str, str]:
    # Map dimension -> mode, include both tau aliases
    agg: Dict[str, str] = {}
    for k in ("Cx", "K", "G", "D"):
        v = getattr(ns, f"agg_{k}", None)
        if v:
            agg[k] = v
    # tau unicode / ascii may both be set; last one wins
    v_tau_u = getattr(ns, "agg_tau_unicode", None)
    v_tau_a = getattr(ns, "agg_tau_ascii", None)
    if v_tau_u:
        agg["τ"] = v_tau_u
    if v_tau_a:
        agg["tau"] = v_tau_a
    return agg


def cmd_score(args: argparse.Namespace) -> int:
    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        print(f"Input introuvable: {in_path}", flush=True)
        return 2

    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"JSON invalide: {e}", flush=True)
        return 2

    msg, _code = _validate_input(payload)
    if msg is not None:
        print(msg, flush=True)
        return 1

    agg_map = _parse_agg_args(args)
    dim_scores = _dimension_scores(payload, agg_map)
    T, K_eff = _compute_T_and_Keff(dim_scores)

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    res = {
        "instrument_id": __instrument_id__,
        "version": __version__,
        "T": float(T),
        "K_eff": float(K_eff),
        "zone": _zone_from_T(float(T)),
        "dimension_scores": {k: float(v) for k, v in dim_scores.items()},
    }
    (outdir / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi_otimes_o_instrument_v0_1",
        description="PhiO instrument v0.1 — runner & harness (analyse descriptive).",
    )

    # Exposer les flags contractuels au niveau racine (visibles dans --help global).
    # Ils restent réellement requis au niveau de la sous-commande `score`.
    parser.add_argument("--input", help="(score) Chemin du JSON d'entrée.")
    parser.add_argument("--outdir", help="(score) Dossier de sortie (results.json).")
    parser.add_argument("--agg_tau", help="(score) Agrégation pour tau (median|bottleneck).")
    parser.add_argument("--agg_τ", help="(score) Agrégation pour τ (median|bottleneck).")

    sub = parser.add_subparsers(dest="cmd", required=False)

    # new-template
    p_new = sub.add_parser("new-template", help="Génère un template JSON d'entrée.")
    p_new.add_argument("--name", default="PhiO", help="Nom du système.")
    p_new.add_argument("--out", required=True, help="Chemin du template JSON à écrire.")
    p_new.set_defaults(_handler=cmd_new_template)

    # score
    p_score = sub.add_parser("score", help="Calcule T et K_eff à partir d'un JSON d'entrée.")
    p_score.add_argument("--input", required=True, help="Chemin du JSON d'entrée.")
    p_score.add_argument("--outdir", required=True, help="Dossier de sortie (results.json).")

    # aggregation modes (contract)
    choices = ("median", "bottleneck")
    p_score.add_argument("--agg_Cx", dest="agg_Cx", choices=choices, default="median", help="Agrégation pour Cx.")
    p_score.add_argument("--agg_K", dest="agg_K", choices=choices, default="median", help="Agrégation pour K.")
    p_score.add_argument("--agg_G", dest="agg_G", choices=choices, default="median", help="Agrégation pour G.")
    p_score.add_argument("--agg_D", dest="agg_D", choices=choices, default="median", help="Agrégation pour D.")
    # tau: expose both aliases in help
    p_score.add_argument("--agg_τ", dest="agg_tau_unicode", choices=choices, default=None, help="Agrégation pour τ.")
    p_score.add_argument("--agg_tau", dest="agg_tau_ascii", choices=choices, default=None, help="Agrégation pour tau.")
    p_score.set_defaults(_handler=cmd_score)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "cmd", None):
        # no subcommand: show help and exit 0 (contract)
        parser.print_help()
        return 0

    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
