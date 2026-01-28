# PhiO pipeline minimal (collector -> core)

This update adds a small, modular pipeline you can test while you refine what a
"clean" output should look like.

Design rules (PhiO compatible)

- Collector and core are separate.
- Collector never runs DD/DD-R/E.
- Core never fetches data.
- They communicate only by files.
- No semantic judgement is introduced: only structure + traceability.

Quick test

1) Collector only

```bash
python scripts/run_collector.py --profile collectors/local_copy_example.toml
```

It writes a new folder under `./collected/<run_id>/` and a
`collector_manifest.json` with sha256 + provenance.

2) Core only

```bash
python scripts/run_core.py --profile profiles/core_example.toml --write-run-manifest
```

It runs the instrument CLI `score` command and stores outputs under
`./runs/<run_id>/`.

3) End-to-end pipeline

```bash
python scripts/run_pipeline.py --profile profiles/pipeline_example.toml
```

Profiles

- `collectors/local_copy_example.toml`: minimal collector example (copies a local dataset).
- `profiles/core_example.toml`: minimal core example.
- `profiles/pipeline_example.toml`: chains both with the same `run_id`.

Notes

- Profiles are TOML to keep dependencies at zero (Python 3.11 stdlib: `tomllib`).
- The shipped collector is intentionally minimal (`local_copy`) to avoid mixing
  data acquisition complexity into PhiO until you freeze the contracts.
