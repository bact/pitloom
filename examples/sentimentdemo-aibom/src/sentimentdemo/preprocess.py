# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""Stage 1: Data preprocessing.

Reads the raw labelled text files (``data/raw/pos.txt`` and
``data/raw/neg.txt``), normalises and tokenises them, and writes a
fastText-style train/test split to ``data/processed/``.

Wrapped with the :func:`pitloom.loom.run` decorator so that the
dataset lineage (raw inputs -> processed outputs, with a list of
preprocessing operations) is recorded as an SPDX 3 SBOM fragment at
``fragments/01_preprocess.spdx3.json``.

The preprocessing operation names come from STAV's standardised
vocabulary (https://github.com/bact/stav).  We pull SPDX dataset-type
strings from ``stav.vocab.spdx.dataset`` so the fragment uses the same
IRIs everyone else in the AI SBOM ecosystem uses.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

from stav.vocab import spdx as stav_spdx

from pitloom import loom

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
FRAGMENT_PATH = ROOT / "fragments" / "01_preprocess.spdx3.json"

# Stable STAV IRIs that flow verbatim into SPDX ``dataset_dataPreprocessing``.
PREPROCESSING_STEPS: list[str] = [
    "https://w3id.org/stav/vocab/data#CaseFolding",
    "https://w3id.org/stav/vocab/data#WhitespaceTokenization",
    "https://w3id.org/stav/vocab/data#FastTextLabelling",
    "https://w3id.org/stav/vocab/data#TrainTestSplit",
]


def _tokenize(line: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace in *line*."""
    line = line.strip().lower()
    line = re.sub(r"[^a-z0-9\s]", " ", line)
    return re.sub(r"\s+", " ", line).strip()


def _read_labelled(path: Path, label: str) -> list[str]:
    """Return fastText-formatted lines (``__label__<label> <tokens>``) from *path*."""
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        tokens = _tokenize(line)
        if tokens:
            rows.append(f"__label__{label} {tokens}")
    return rows


@loom.run(FRAGMENT_PATH, pretty=True)
def preprocess() -> tuple[Path, Path]:
    """Tokenise the raw corpus, write the train/test split, and record dataset lineage.

    Returns:
        A 2-tuple of (train_path, test_path) for the processed files.
    """
    loom.add_input_dataset(
        "data/raw/pos.txt",
        dataset_type=stav_spdx.dataset.DatasetType.text.name,
    )
    loom.add_input_dataset(
        "data/raw/neg.txt",
        dataset_type=stav_spdx.dataset.DatasetType.text.name,
    )

    pos = _read_labelled(RAW_DIR / "pos.txt", "pos")
    neg = _read_labelled(RAW_DIR / "neg.txt", "neg")
    rows = pos + neg
    random.Random(42).shuffle(rows)
    split = int(0.8 * len(rows))
    train_rows, test_rows = rows[:split], rows[split:]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    train_path = PROCESSED_DIR / "train.txt"
    test_path = PROCESSED_DIR / "test.txt"
    train_path.write_text("\n".join(train_rows) + "\n", encoding="utf-8")
    test_path.write_text("\n".join(test_rows) + "\n", encoding="utf-8")

    # Each output dataset gets a ``hasInput`` relationship to every input
    # dataset declared above (emitted by loom.Run.finalize).
    loom.add_output_dataset(
        "data/processed/train.txt",
        dataset_type=stav_spdx.dataset.DatasetType.text.name,
        data_preprocessing=PREPROCESSING_STEPS,
    )
    loom.add_output_dataset(
        "data/processed/test.txt",
        dataset_type=stav_spdx.dataset.DatasetType.text.name,
        data_preprocessing=PREPROCESSING_STEPS,
    )

    print(f"[preprocess] wrote {len(train_rows)} train rows -> {train_path}")
    print(f"[preprocess] wrote {len(test_rows)} test rows  -> {test_path}")
    return train_path, test_path


if __name__ == "__main__":
    preprocess()
    print(f"[preprocess] SBOM fragment -> {FRAGMENT_PATH}")
