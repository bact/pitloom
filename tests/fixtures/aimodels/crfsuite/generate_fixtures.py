# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: CC0-1.0
"""Generate the CRFsuite test fixtures (python-crfsuite 0.9.12).

Not imported by tests; the committed binaries are the reference (float
weights are not proven byte-identical across platforms). Run from the
repository root, in a throwaway venv that is never a Pitloom dependency:

    python -m venv .crf-venv
    .crf-venv/bin/pip install python-crfsuite==0.9.12
    .crf-venv/bin/python tests/fixtures/aimodels/crfsuite/generate_fixtures.py
"""

from pathlib import Path

import pycrfsuite  # pyright: ignore[reportMissingImports]  # pyrefly: ignore[missing-import]

HERE = Path(__file__).parent

# Labels: Thai, a space, punctuation; first-seen order = id order
COMPLETE_X = [
    [
        ["w=บุคคล", "pos=NN", "bias"],
        ["w=ไป", "pos=VB", "bias"],
        ["w=กรุงเทพ", "pos=NNP", "bias"],
    ],
    [
        ["w=อ", "pos=NN", "bias"],
        ["w=x y", "pos=VB"],
        ["w=Paris", "pos=NNP", "bias"],
    ],
    [["w=ก", "pos=NN"], ["w=ข", "pos=NN"], ["w=ค", "pos=VB"], ["w=ง", "pos=NNP"]],
]
COMPLETE_Y = [
    ["บุคคล", "O", "B-LOC"],
    ["I PER/x", "O", "B-LOC"],
    ["บุคคล", "I PER/x", "O", "E-X:1"],
]
MINIMAL_X = [[["a"], ["b"]], [["b"], ["a"]]]
MINIMAL_Y = [["I", "E"], ["E", "I"]]


def train(xs, ys, path: Path) -> None:
    """Train a tiny L-BFGS model and save it to ``path``."""
    trainer = pycrfsuite.Trainer(algorithm="lbfgs", verbose=False)
    for x, y in zip(xs, ys, strict=True):
        trainer.append(x, y)
    trainer.set_params({"max_iterations": 20})
    trainer.train(str(path))


if __name__ == "__main__":
    train(COMPLETE_X, COMPLETE_Y, HERE / "complete.crfsuite")
    train(MINIMAL_X, MINIMAL_Y, HERE / "minimal.model")
