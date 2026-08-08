#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
#
# Runs the full Sentiment Demo AI lifecycle end-to-end, producing one SBOM
# fragment per stage plus the final composite AI SBOM embedded in the wheel.
#
# Stage 0 (and the registry refreshes after stages 1 and 2) maintain
# loom-ids.json: a stable file/entity -> SPDX ID registry. Every stage --
# the loom runs, the `loom model` extractor, and the Hatchling build hook --
# consults it, so the same dataset, script, or model carries the same spdxId
# in every fragment, and the merge step can join the fragments into one
# connected AI-pipeline graph.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p fragments models

echo "================================================================"
echo "Stage 0/5  -  Pin stable SPDX ids (pitloom ids generate)"
echo "================================================================"
# --entity registers the model's id up front, before the model file exists,
# so the training and evaluation fragments already share it.
python -m pitloom ids generate data src --entity sentimentdemo

echo
echo "================================================================"
echo "Stage 1/5  -  Data preprocessing (loom decorator)"
echo "================================================================"
python -m sentimentdemo.preprocess
# Pin ids for the freshly written data/processed/ files so the training and
# evaluation runs reference them by the same ids the preprocessing fragment
# established (unchanged files keep their ids -- regeneration is stable).
python -m pitloom ids generate data src --entity sentimentdemo

echo
echo "================================================================"
echo "Stage 2/5  -  Model training (loom context manager)"
echo "================================================================"
python -m sentimentdemo.train
# Pin the id of the freshly written models/sentimentdemo.bin.
python -m pitloom ids generate data models src --entity sentimentdemo

echo
echo "================================================================"
echo "Stage 3/5  -  Model evaluation (loom context manager)"
echo "================================================================"
python -m sentimentdemo.evaluate

echo
echo "================================================================"
echo "Stage 4/5  -  Direct AI model extraction (loom model)"
echo "================================================================"
loom model models/sentimentdemo.bin -o fragments/04_model_file.spdx3.json --pretty

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
