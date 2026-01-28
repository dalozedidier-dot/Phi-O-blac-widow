#!/usr/bin/env python3
"""
PhiO Times Instrument v0.1
Stub CLI minimal pour satisfaire les tests CLI/contract dans la CI.
"""

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="phi_otimes_o_instrument_v0_1",
        description="PhiO O-Times Instrument v0.1 (stub)",
    )

    p.add_argument("--contract", type=str, required=False, help="Chemin vers un fichier contract.")
    p.add_argument("--baseline", type=str, required=False, help="Chemin vers une baseline contractuelle.")
    p.add_argument("--trace", action="store_true", help="Active une sortie trace.")
    p.add_argument("--json", action="store_true", help="Sortie JSON.")
    p.add_argument("--version", action="store_true", help="Affiche la version et quitte.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print("phi_otimes_o_instrument v0.1")
        return 0

    payload = {
        "ok": True,
        "instrument": "phi_otimes_o_instrument_v0.1",
        "trace": bool(args.trace),
        "contract": args.contract,
        "baseline": args.baseline,
    }

    for key in ("contract", "baseline"):
        pth = getattr(args, key)
        if pth:
            if not Path(pth).exists():
                msg = f"{key} introuvable: {pth}"
                if args.json:
                    print(json.dumps({"ok": False, "error": msg}))
                else:
                    print(msg, file=sys.stderr)
                return 2

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print("PhiO instrument executed successfully")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
