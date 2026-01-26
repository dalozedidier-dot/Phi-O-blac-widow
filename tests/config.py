# --- v0.1.0 patch: ensure pytest_template.json exists in each tmp_path --------
import json
import os
import importlib.util
from pathlib import Path

import pytest


def _load_instrument_module(instrument_file: Path):
    spec = importlib.util.spec_from_file_location("phio_instrument", str(instrument_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load instrument module from: {instrument_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_pytest_template(mod) -> dict:
    if hasattr(mod, "get_spec") and callable(getattr(mod, "get_spec")):
        spec_dict = mod.get_spec()
    elif hasattr(mod, "SPEC"):
        spec_obj = getattr(mod, "SPEC")
        spec_dict = spec_obj.to_dict() if hasattr(spec_obj, "to_dict") else {"spec": str(spec_obj)}
    else:
        spec_dict = {
            "instrument_id": getattr(mod, "__instrument_id__", "unknown"),
            "version": getattr(mod, "__version__", "0"),
        }

    return {
        "instrument": {
            "id": spec_dict.get("instrument_id") or getattr(mod, "__instrument_id__", "unknown"),
            "version": spec_dict.get("version") or getattr(mod, "__version__", "0"),
        },
        "spec": spec_dict,
        "generated_by": "tests/conftest.py autouse fixture",
    }


@pytest.fixture(autouse=True)
def _ensure_pytest_template_json(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    env_path = os.environ.get("INSTRUMENT_PATH", "").strip()

    instrument_file = (repo_root / env_path).resolve() if env_path else (
        repo_root / "scripts" / "phi_otimes_o_instrument_v0_1.py"
    )

    out_file = tmp_path / "pytest_template.json"
    if not out_file.exists():
        mod = _load_instrument_module(instrument_file)
        payload = _build_pytest_template(mod)
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return out_file
