# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""Stage 3: Model evaluation.

Loads the trained fastText model and scores it on ``data/processed/test.txt``.
The :func:`pitloom.loom.run` context captures the model identity together
with the *validation* dataset, emitting a ``testedOn`` SPDX 3 relationship
into ``fragments/03_evaluate.spdx3.json``.
"""

from __future__ import annotations

from pathlib import Path

import fasttext
from stav.vocab import dpv as stav_dpv
from stav.vocab import spdx as stav_spdx

from pitloom import loom

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "models" / "sentimentdemo.bin"
TEST_FILE = ROOT / "data" / "processed" / "test.txt"
FRAGMENT_PATH = ROOT / "fragments" / "03_evaluate.spdx3.json"


def evaluate() -> tuple[int, float, float]:
    """Score the trained model on the test set and write an SBOM fragment.

    Records the model identity and a ``testedOn`` SPDX relationship to the
    validation dataset in the fragment file.

    Returns:
        A 3-tuple of (n_samples, precision_at_1, recall_at_1).
    """
    with loom.run(FRAGMENT_PATH, pretty=True):
        loom.set_model(
            name="sentimentdemo",
            model_type=str(stav_dpv.ai.AITechnique.SupervisedLearning),
        )
        # Creates a ``testedOn`` SPDX relationship from the model to this dataset.
        loom.add_validation_dataset(
            "data/processed/test.txt",
            dataset_type=stav_spdx.dataset.DatasetType.text.name,
        )

        model = fasttext.load_model(str(MODEL_PATH))
        n, p_at_1, r_at_1 = model.test(str(TEST_FILE))
        print(f"[evaluate] n={n} precision@1={p_at_1:.3f} recall@1={r_at_1:.3f}")

    return n, p_at_1, r_at_1


if __name__ == "__main__":
    evaluate()
    print(f"[evaluate] SBOM fragment -> {FRAGMENT_PATH}")
