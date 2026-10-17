# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Scenario SBOMs and G7 checker outcomes shared by the conformance tests
and ``scripts/g7_coverage_report.py``.

Each scenario builds one SBOM from a fixture model; ``outcomes()`` runs the
G7 checker (``g7ai``, SPDX 3) on it. ``tests/fixtures/conformance/
g7ai-expected.tsv`` holds the expected outcome of every rule per scenario.

See also: tests/conformance/README.md.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

from ntia_conformance_checker import RuleBasedChecker, get_spec

from pitloom.assemble import generate_model_sbom
from tests._author_routes import CREATED
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

AIMODELS = Path(__file__).resolve().parents[1] / "fixtures" / "aimodels"
EXPECTED = (
    Path(__file__).resolve().parents[1] / "fixtures/conformance/g7ai-expected.tsv"
)
OUTCOMES = ("present", "missing", "not-applicable", "out-of-scope")


def _file(relative: str) -> Callable[[], str]:
    def build() -> str:
        return generate_model_sbom(str(AIMODELS / relative), creation_metadata=CREATED)

    return build


def _hub() -> str:
    card = _make_card_data(license="apache-2.0", datasets=["c4"])
    with _patch_hf_calls(card_data=card, hub_info={"author": "acme"}):
        return generate_model_sbom("acme/model", creation_metadata=CREATED)


#: Scenario name -> SBOM JSON text. Order is the TSV's column order.
SCENARIOS: dict[str, Callable[[], str]] = {
    "gguf": _file("gguf/stories260K.gguf"),
    "safetensors": _file("safetensors/phi-tiny-random.safetensors"),
    "onnx": _file("onnx/gpt2-tiny-decoder.onnx"),
    "hub": _hub,
}


def check(sbom: Path) -> RuleBasedChecker:
    """Run the G7 checker on *sbom*; fail loudly when it could not parse it.

    The checker only logs a parse failure, then reports every rule missing,
    which would read as a pitloom regression.
    """
    checker = RuleBasedChecker(str(sbom), compliance="g7ai", sbom_spec="spdx3")
    assert checker.doc is not None, f"checker could not read {sbom}"
    assert not checker.parsing_errors, checker.parsing_errors
    return checker


def outcomes(sbom: Path) -> dict[str, str]:
    """Return the outcome of every G7 rule for *sbom*, by rule id."""
    return check(sbom).rule_outcomes()


def provisions() -> dict[str, str]:
    """Return each G7 rule's provision (requirement, recommendation, ...)."""
    spec = get_spec("g7ai")
    return {spec.rule_id(r): r.provision for r in spec.rules}


def read_expected() -> dict[str, dict[str, str]]:
    """Read the expected table: rule id -> scenario -> outcome."""
    with EXPECTED.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["rule"]: {s: r[s] for s in SCENARIOS} for r in rows}


def render_expected(actual: dict[str, dict[str, str]]) -> str:
    """Render *actual* (scenario -> rule -> outcome) as the TSV text."""
    kinds = provisions()
    lines = ["\t".join(["rule", "provision", *SCENARIOS])]
    for rule in sorted(kinds):
        cells = [actual[s][rule] for s in SCENARIOS]
        lines.append("\t".join([rule, kinds[rule], *cells]))
    return "\n".join(lines) + "\n"
