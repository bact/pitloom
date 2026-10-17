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
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.metadata import distribution
from pathlib import Path
from unittest.mock import patch

from ntia_conformance_checker import RuleBasedChecker, get_spec

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from tests._author_routes import CREATED
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

AIMODELS = Path(__file__).resolve().parents[1] / "fixtures" / "aimodels"
EXPECTED = (
    Path(__file__).resolve().parents[1] / "fixtures/conformance/g7ai-expected.tsv"
)
MAPPING = (
    Path(__file__).resolve().parents[1]
    / "fixtures/conformance/g7ai2026-to-spdx30.sssom.tsv"
)
OUTCOMES = ("present", "missing", "not-applicable", "out-of-scope")


@contextmanager
def _without_licence_database() -> Iterator[None]:
    """Build as if the ``licenseid`` database were absent.

    CI builds it and a laptop may not; with it, licence IDs are canonicalised
    and the SBOM text changes. The table describes the database-less state.
    """
    with patch("pitloom.extract._license._matcher", return_value=None):
        yield


def _file(relative: str) -> Callable[[], str]:
    def build() -> str:
        with _without_licence_database():
            return generate_model_sbom(
                str(AIMODELS / relative), creation_metadata=CREATED
            )

    return build


#: What the Hub's model_info states of a revision.
_HUB_INFO = {
    "author": "acme",
    "sha": "0123456789abcdef0123456789abcdef01234567",
    "created_at": "2023-09-20T13:03:50+00:00",
    "last_modified": "2024-01-02T03:04:05+00:00",
}


def _hub() -> str:
    card = _make_card_data(license="apache-2.0", datasets=["c4"])
    with (
        _without_licence_database(),
        _patch_hf_calls(card_data=card, hub_info=_HUB_INFO),
    ):
        return generate_model_sbom("acme/model", creation_metadata=CREATED)


def _library() -> str:
    """A model and a licensed, described dataset, built through the assembler
    (no reader yet feeds a dataset licence into a model SBOM)."""
    dataset = DatasetMetadata(
        name="corpus",
        version="1.0",
        description="A text corpus.",
        download_url="https://example.org/corpus.tar",
        license="CC-BY-4.0",
        creator="Alice",
        dataset_types=["text"],
        dataset_size=1000,
    )
    model = AiModelMetadata(
        name="m",
        version="1.0",
        description="A small model.",
        license="Apache-2.0",
        originators=["Alice"],
        parameter_count=7,
        datasets=[DatasetReference(role="trainedOn", metadata=dataset)],
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
    )
    with _without_licence_database():
        return build_model(model, CREATED, digest="ab" * 32).to_json()


#: Scenario name -> SBOM JSON text. Order is the TSV's column order.
SCENARIOS: dict[str, Callable[[], str]] = {
    "gguf": _file("gguf/stories260K.gguf"),
    "safetensors": _file("safetensors/phi-tiny-random.safetensors"),
    "onnx": _file("onnx/gpt2-tiny-decoder.onnx"),
    "hub": _hub,
    "library": _library,
}


def check(sbom: Path, *, evaluated: bool = True) -> RuleBasedChecker:
    """Run the G7 checker on *sbom*; fail loudly when it could not read it.

    The checker only logs a parse failure, then reports every rule missing,
    which would read as a pitloom regression. With *evaluated*, also require
    that it found components to evaluate.
    """
    checker = RuleBasedChecker(str(sbom), compliance="g7ai", sbom_spec="spdx3")
    assert checker.doc is not None, f"checker could not read {sbom}"
    assert not checker.parsing_errors, checker.parsing_errors
    if evaluated:
        assert checker.components_evaluated, f"nothing to evaluate in {sbom}"
    return checker


def outcomes(sbom: Path, *, evaluated: bool = True) -> dict[str, str]:
    """Return the outcome of every G7 rule for *sbom*, by rule id."""
    return check(sbom, evaluated=evaluated).rule_outcomes()


def checker_commit() -> str:
    """Return the checker's git commit (its version string when not a git
    install): the key that tells two reports were made with the same rules."""
    raw = distribution("ntia-conformance-checker").read_text("direct_url.json")
    if raw:
        commit = json.loads(raw).get("vcs_info", {}).get("commit_id")
        if commit:
            return str(commit)
    return distribution("ntia-conformance-checker").version


def provisions() -> dict[str, str]:
    """Return each G7 rule's provision (requirement, recommendation, ...)."""
    spec = get_spec("g7ai")
    return {spec.rule_id(r): r.provision for r in spec.rules}


def read_expected() -> dict[str, dict[str, str]]:
    """Read the expected table: rule id -> scenario -> outcome."""
    with EXPECTED.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["rule"]: {s: r[s] for s in SCENARIOS if s in r} for r in rows}


def render_expected(actual: dict[str, dict[str, str]]) -> str:
    """Render *actual* (scenario -> rule -> outcome) as the TSV text."""
    kinds = provisions()
    lines = ["\t".join(["rule", "provision", *SCENARIOS])]
    for rule in sorted(kinds):
        cells = [actual[s][rule] for s in SCENARIOS]
        lines.append("\t".join([rule, kinds[rule], *cells]))
    return "\n".join(lines) + "\n"
