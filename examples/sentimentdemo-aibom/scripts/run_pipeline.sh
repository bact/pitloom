#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
#
# Runs the full Sentiment Demo AI lifecycle end-to-end, producing one SBOM
# fragment per stage plus the final composite AI SBOM embedded in the wheel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p fragments models

echo "================================================================"
echo "Stage 1/5  -  Data preprocessing (loom decorator)"
echo "================================================================"
python -m sentimentdemo.preprocess

echo
echo "================================================================"
echo "Stage 2/5  -  Model training (loom context manager)"
echo "================================================================"
python -m sentimentdemo.train

echo
echo "================================================================"
echo "Stage 3/5  -  Model evaluation (loom context manager)"
echo "================================================================"
python -m sentimentdemo.evaluate

echo
echo "================================================================"
echo "Stage 4/5  -  Direct AI model extraction (loom -m)"
echo "================================================================"
loom -m models/sentiment.bin -o fragments/04_model_file.spdx3.json --pretty

echo
echo "================================================================"
echo "Stage 5/5  -  Hatchling build with Pitloom hook"
echo "================================================================"
rm -rf dist/
python -m build --wheel --no-isolation

echo
echo "================================================================"
echo "Done.  Final composite AI SBOM lives inside the wheel:"
echo "================================================================"
WHEEL=$(ls dist/*.whl | head -1)
python - <<PY
import sys, zipfile
wheel = "$WHEEL"
with zipfile.ZipFile(wheel) as zf:
    sboms = [n for n in zf.namelist() if "/sboms/" in n]
    for n in sboms:
        print(f"  {wheel}!{n}")
PY
