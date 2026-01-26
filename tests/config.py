# tests/config.py
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Convention repo: instrument sous scripts/
DEFAULT_INSTRUMENT = REPO_ROOT / "scripts" / "phi_otimes_o_instrument_v0_1.py"

# Permet override via env (CI ou local)
_env = os.environ.get("INSTRUMENT_PATH", "").strip()

if _env:
    p = Path(_env)
    INSTRUMENT_PATH = p if p.is_absolute() else (REPO_ROOT / p).resolve()
else:
    INSTRUMENT_PATH = DEFAULT_INSTRUMENT.resolve()
