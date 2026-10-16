#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0
#
# Runs the full Sentiment Demo AI lifecycle end-to-end, producing one SBOM
# fragment per stage plus the final composite AI SBOM embedded in the wheel.
#
# Stage 0 (and the registry refreshes after stages 1 and 2) maintain
# loom-id-registry.json: a stable SPDX ID registry. Every stage --
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
echo "Stage 0/5  -  Pin stable SPDX ids (pitloom id generate)"
echo "================================================================"
# --namespace fixes the registry's document namespace (only the first call
# needs it; an existing registry keeps its own). -e pins each dataset package
# under its path from the project root; the raw files exist, so their pins
# carry the content digest, while the two data/processed/ pins precede the
# data and have none until the next run, whose stage 0 adopts the digest (same
# ids). A single-file dataset package then `contains` its file. The model needs
# no entry here: train.py and evaluate.py pass path= to
# loom.set_model()/use_model(), so loom hashes models/sentimentdemo.bin at run
# exit and records one AI package id, keyed by that file, that the training and
# evaluation fragments share.
python -m pitloom id generate data src \
  --namespace "https://spdx.org/spdxdocs/sentimentdemo-aibom-02679af2-dd22-459c-8143-0d82396823c7" \
  -e data/raw/pos.txt:dataset_DatasetPackage \
  -e data/raw/neg.txt:dataset_DatasetPackage \
  -e data/processed/train.txt:dataset_DatasetPackage \
  -e data/processed/test.txt:dataset_DatasetPackage

echo
echo "================================================================"
echo "Stage 1/5  -  Data preprocessing (loom decorator)"
echo "================================================================"
python -m sentimentdemo.preprocess
# Pin ids for the freshly written data/processed/ files so the training and
# evaluation runs reference them by the same ids the preprocessing fragment
# established (unchanged files keep their ids -- regeneration is stable).
python -m pitloom id generate data src

echo
echo "================================================================"
echo "Stage 2/5  -  Model training (loom context manager)"
echo "================================================================"
python -m sentimentdemo.train
# Pin the id of the freshly written models/sentimentdemo.bin.
python -m pitloom id generate data models src

echo
echo "================================================================"
echo "Stage 3/5  -  Model evaluation (loom context manager)"
echo "================================================================"
python -m sentimentdemo.evaluate

echo
echo "================================================================"
echo "Stage 4/5  -  Direct AI model extraction (loom model)"
echo "================================================================"
loom model models/sentimentdemo.bin -o fragments/04_model_file.spdx3.json --pretty \
  --id-registry loom-id-registry.json

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
