# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""Stage 2: Model training.

Trains a tiny fastText supervised classifier on ``data/processed/train.txt``
and saves the resulting model to ``models/sentiment.bin``.

The training run is wrapped in a :func:`pitloom.loom.run` context
manager that captures the model name, model type (a STAV / DPV IRI),
hyperparameters, and the training dataset used.  The result is an SBOM
fragment at ``fragments/02_train.spdx3.json``.
"""

from __future__ import annotations

from pathlib import Path

import fasttext
from stav.vocab import dpv as stav_dpv
from stav.vocab import spdx as stav_spdx

from pitloom import loom

ROOT = Path(__file__).resolve().parents[2]
TRAIN_FILE = ROOT / "data" / "processed" / "train.txt"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "sentiment.bin"
FRAGMENT_PATH = ROOT / "fragments" / "02_train.spdx3.json"

HYPERPARAMS: dict[str, str | int | float] = {
    "lr": 0.5,
    "epoch": 25,
    "wordNgrams": 2,
    "dim": 20,
    "loss": "softmax",
}


def train() -> Path:
    """Train a fastText sentiment classifier and write an SBOM fragment.

    Records the model identity, DPV-AI technique IRI (from STAV), hyperparameters,
    and a ``trainedOn`` relationship to the training dataset in the fragment file.

    Returns:
        Path to the saved model file.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with loom.run(FRAGMENT_PATH, pretty=True):
        # ``model_type`` is a stable DPV-AI IRI from STAV so downstream consumers
        # can resolve it to the formal "SupervisedLearning" concept unambiguously.
        loom.set_model(
            name="sentimentdemo",
            model_type=str(stav_dpv.ai.AITechnique.SupervisedLearning),
            hyperparameters={k: str(v) for k, v in HYPERPARAMS.items()},
        )
        # Creates a ``trainedOn`` SPDX relationship from the model to this dataset.
        loom.add_dataset(
            "data/processed/train.txt",
            dataset_type=stav_spdx.dataset.DatasetType.text.name,
        )

        model = fasttext.train_supervised(input=str(TRAIN_FILE), **HYPERPARAMS)
        model.save_model(str(MODEL_PATH))
        print(f"[train] saved fastText model -> {MODEL_PATH}")

    return MODEL_PATH


if __name__ == "__main__":
    train()
    print(f"[train] SBOM fragment -> {FRAGMENT_PATH}")
