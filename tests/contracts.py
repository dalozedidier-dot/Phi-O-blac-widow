from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------
# CLI helpers (used by tests)
# ----------------------------

def run_help(instrument_path: str) -> str:
    """Run instrument --help and return combined stdout+stderr (never raises)."""
    res = subprocess.run(
        ["python3", instrument_path, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return (res.stdout or "") + (res.stderr or "")


def parse_help_flags(help_text: str) -> List[str]:
    """
    Extract long flags from argparse-like help.
    Supports unicode flag tokens (ex: --agg_τ).
    Returns unique sorted list.
    """
    # capture tokens starting with -- and including unicode letters like τ
    flags = re.findall(r"(?<!\w)(--[0-9A-Za-z_\-τ]+)", help_text)
    # also accept some argparse formats like "--foo, -f"
    flags = [f.strip() for f in flags if f.strip()]
    return sorted(set(flags))


def detect_tau_agg_flag(help_or_flags: Any) -> Dict[str, bool]:
    """
    Detect presence of tau aggregation flags.
    Accepts either:
      - help text (str) -> parses flags
