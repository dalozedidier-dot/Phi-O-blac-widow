import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.config import INSTRUMENT_PATH


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=cwd)


@pytest.fixture(scope="session")
def instrument_path():
    assert INSTRUMENT_PATH.exists(), f"Instrument introuvable: {INSTRUMENT_PATH}"
    return str(INSTRUMENT_PATH)


@pytest.fixture
def run_cli(tmp_path, instrument_path):
    """Exécute le CLI comme une boîte noire.

    Compatibilité: certains tests attendent `proc = run_cli([...])`, d'autres
    attendent `proc, outdir = run_cli([...])`. On retourne un wrapper
    itérable qui supporte les deux.
    """

    class CliResult:
        def __init__(self, proc, outdir):
            self._proc = proc
            self.outdir = outdir

        def __iter__(self):
            yield self._proc
            yield self.outdir

        def __getattr__(self, name):
            return getattr(self._proc, name)

        @property
        def proc(self):
            return self._proc

    def _runner(args, input_json=None, outdir=None):
        outdir_p = Path(outdir) if outdir else (tmp_path / "out")
        outdir_p.mkdir(parents=True, exist_ok=True)

        cmd = ["python3", instrument_path] + list(args)

        tmp_input = None
        if input_json is not None:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(input_json, f, ensure_ascii=False, indent=2)
                tmp_input = Path(f.name)

            # Replace existing --input target if present; otherwise inject --input <file>
            if "--input" in cmd:
                i = cmd.index("--input")
                if i + 1 < len(cmd):
                    cmd[i + 1] = str(tmp_input)
                else:
                    cmd.append(str(tmp_input))
            else:
                # Also handle --input=<path>
                replaced = False
                for i, a in enumerate(cmd):
                    if isinstance(a, str) and a.startswith("--input="):
                        cmd[i] = f"--input={tmp_input}"
                        replaced = True
                        break
                if not replaced:
                    cmd += ["--input", str(tmp_input)]

        # ensure outdir for score (mais pas pour score --help)
        if "score" in cmd and "--help" not in cmd and ("--outdir" not in cmd):
            cmd += ["--outdir", str(outdir_p)]

        res = _run(cmd)

        if tmp_input and tmp_input.exists():
            tmp_input.unlink(missing_ok=True)

        return CliResult(res, outdir_p)

    return _runner


@pytest.fixture
def template_json(run_cli, tmp_path):
    """Template généré via CLI: source de vérité pour le schéma + labels."""
    # écrire le template dans le tmp_path pour éviter contamination du cwd
    out = tmp_path / "pytest_template.json"
    res, _ = run_cli(["new-template", "--name", "PyTestTemplate", "--out", str(out)])
    assert res.returncode == 0, res.stderr or res.stdout
    assert out.exists()
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture
def infer_dimensions(template_json):
    dims = []
    for it in template_json.get("items", []):
        d = it.get("dimension")
        if d and d not in dims:
            dims.append(d)
    return dims


@pytest.fixture
def load_results():
    def _load(outdir: Path):
        p = Path(outdir) / "results.json"
        assert p.exists(), f"results.json absent dans {outdir}"
        return json.loads(p.read_text(encoding="utf-8"))

    return _load
