```yaml
name: phio-ci

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt

      - name: Sanity check instrument path
        run: |
          ls -la
          ls -la scripts || true
          test -f scripts/phi_otimes_o_instrument_v0_1.py

      - name: Run tests (debug)
        env:
          INSTRUMENT_PATH: scripts/phi_otimes_o_instrument_v0_1.py
        run: |
          python -m pytest -vv -s --maxfail=1

      - name: Debug artifacts
        if: always()
        run: |
          echo "=== pytest_template.json occurrences ==="
          find /tmp/pytest-of-runner -type f -name "pytest_template.json" -print || true
          echo "=== sample files (first 200) ==="
          find /tmp/pytest-of-runner -maxdepth 3 -type f | head -n 200 || true
```
