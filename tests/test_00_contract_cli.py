# tests/test_00_contract_cli.py

from __future__ import annotations

import os
import subprocess
from typing import Optional


def _is_strict_mode() -> bool:
    """
    Strict mode makes CLI contract tests blocking.
    Enabled when PHIO_STRICT_CLI is set to a truthy value.
    """
    v = os.getenv("PHIO_STRICT_CLI", "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _run_cli_help(instrument_path: str) -> str:
    """
    Execute the instrument CLI with --help and return stdout+stderr text.
    """
    proc = subprocess.run(
        [instrument_path, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return proc.stdout or ""


def test_cli_help_has_core_contract(instrument_path: Optional[str]):
    """
    CLI contract test.

    Dev mode (default):
      - skip if instrument is absent
    Strict mode (PHIO_STRICT_CLI=1):
      - fail if instrument is absent
      - fail if help output does not contain the expected contract marker(s)
    """
    strict = _is_strict_mode()

    if not instrument_path:
        if strict:
            raise AssertionError(
                "Instrument CLI not found but PHIO_STRICT_CLI=1, refusing to skip."
            )
        import pytest

        pytest.skip("Instrument CLI not available in dev mode (PHIO_STRICT_CLI=0).")

    out = _run_cli_help(str(instrument_path))

    # Ajuste ici les marqueurs de contrat attendus.
    # L'idée est de tester un "noyau" stable (ex: nom du tool, options minimales, commandes principales).
    expected_markers = [
        "PhiO",
        "--help",
    ]

    missing = [m for m in expected_markers if m not in out]
    if missing:
        raise AssertionError(
            "CLI help output is missing expected contract marker(s): "
            f"{missing}. Output was:\n{out}"
        )
