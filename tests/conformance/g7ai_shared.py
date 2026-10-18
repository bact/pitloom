# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Scenario SBOMs and checker outcomes shared by the conformance tests
and ``scripts/g7_coverage_report.py``.

Each scenario builds one SBOM from a fixture model; ``outcomes()`` runs the
checker (``g7ai``, ``cisa2026`` or ``fsct3``, SPDX 3) on it.
``tests/fixtures/conformance/<standard>-expected.tsv`` holds the expected
outcome of every rule per scenario.

See also: tests/fixtures/conformance/README.md.
"""

from __future__ import annotations

import csv
import json
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.metadata import distribution
from pathlib import Path
from unittest.mock import patch

from ntia_conformance_checker import RuleBasedChecker, get_spec

from pitloom.assemble import generate_model_sbom, generate_project_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.file_hash import HexDigests
from tests._author_routes import CREATED
from tests._wheel_models import safetensors_bytes
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
def without_licence_database() -> Iterator[None]:
    """Build as if the ``licenseid`` database were absent.

    CI builds it and a laptop may not; with it, licence IDs are canonicalised
    and the SBOM text changes. The table describes the database-less state.
    """
    with patch("pitloom.extract._license._matcher", return_value=None):
        yield


def _file(relative: str) -> Callable[[], str]:
    def build() -> str:
        with without_licence_database():
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
        without_licence_database(),
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
    with without_licence_database():
        return build_model(
            model, CREATED, digest=HexDigests("ab" * 32, "cd" * 64)
        ).to_json()


_PROJECT = (
    'name = "demo"\nversion = "1.0.0"\ndescription = "Demo model"\n'
    'requires-python = ">=3.10"\nauthors = [{name = "Alice"}]\n'
    'license = "Apache-2.0"\n'
)
#: Build-backend name -> the ``pyproject.toml`` of the same project. Setuptools
#: ships a data file only when told to, so it says so.
BACKENDS = {
    "hatchling": (
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n[project]\n' + _PROJECT
    ),
    "setuptools": (
        '[build-system]\nrequires = ["setuptools>=77"]\n'
        'build-backend = "setuptools.build_meta"\n[project]\n'
        + _PROJECT
        + '[tool.setuptools.package-data]\ndemo = ["*.safetensors"]\n'
    ),
    "poetry": (
        '[build-system]\nrequires = ["poetry-core>=2"]\n'
        'build-backend = "poetry.core.masonry.api"\n[project]\n' + _PROJECT
    ),
}


def write_project(root: Path, pyproject: str) -> None:
    """Write a project with *pyproject* that holds one Safetensors model."""
    (root / "demo").mkdir()
    (root / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "demo" / "m.safetensors").write_bytes(safetensors_bytes())
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")


def project_sbom(pyproject: str) -> str:
    """The SBOM of a project with *pyproject* that holds one Safetensors model."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_project(root, pyproject)
        with without_licence_database():
            return generate_project_sbom(root, creation_metadata=CREATED, offline=True)


def _project(backend: str) -> Callable[[], str]:
    return lambda: project_sbom(BACKENDS[backend])


#: Scenario name -> SBOM JSON text. Order is the TSV's column order.
SCENARIOS: dict[str, Callable[[], str]] = {
    "gguf": _file("gguf/stories260K.gguf"),
    "safetensors": _file("safetensors/phi-tiny-random.safetensors"),
    "onnx": _file("onnx/gpt2-tiny-decoder.onnx"),
    "numpy": _file("numpy/example-model-v1.npy"),
    "fasttext": _file("fasttext/sentimentdemo.bin"),
    "hub": _hub,
    "library": _library,
    **{f"proj-{backend}": _project(backend) for backend in BACKENDS},
}


def check(
    sbom: Path, *, evaluated: bool = True, standard: str = "g7ai"
) -> RuleBasedChecker:
    """Run the checker for *standard* on *sbom*; fail loudly when it could not read it.

    The checker only logs a parse failure, then reports every rule missing,
    which would read as a pitloom regression. With *evaluated*, also require
    that it found components to evaluate.
    """
    checker = RuleBasedChecker(str(sbom), compliance=standard, sbom_spec="spdx3")
    assert checker.doc is not None, f"checker could not read {sbom}"
    assert not checker.parsing_errors, checker.parsing_errors
    if evaluated:
        assert checker.components_evaluated, f"nothing to evaluate in {sbom}"
    return checker


def outcomes(
    sbom: Path, *, evaluated: bool = True, standard: str = "g7ai"
) -> dict[str, str]:
    """Return the outcome of every rule of *standard* for *sbom*, by rule id."""
    return check(sbom, evaluated=evaluated, standard=standard).rule_outcomes()


def checker_commit() -> str:
    """Return the checker's git commit (its version string when not a git
    install): the key that tells two reports were made with the same rules."""
    raw = distribution("ntia-conformance-checker").read_text("direct_url.json")
    if raw:
        commit = json.loads(raw).get("vcs_info", {}).get("commit_id")
        if commit:
            return str(commit)
    return distribution("ntia-conformance-checker").version


def provisions(standard: str = "g7ai") -> dict[str, str]:
    """Return each rule's provision (requirement, recommendation, ...)."""
    spec = get_spec(standard)
    return {spec.rule_id(r): r.provision for r in spec.rules}


def mapping_path(standard: str) -> Path:
    """Return the vendored SSSOM mapping of *standard* to SPDX 3.0."""
    if standard == "g7ai":
        return MAPPING
    name = {"fsct3": "fsct2024", "bsi": "bsi2025"}.get(standard, standard)
    return MAPPING.parent / f"{name}-to-spdx30.sssom.tsv"


def expected_path(standard: str) -> Path:
    """Return the expected-outcome table of *standard*."""
    if standard == "g7ai":
        return EXPECTED
    return EXPECTED.parent / f"{standard}-expected.tsv"


def read_expected(standard: str = "g7ai") -> dict[str, dict[str, str]]:
    """Read the expected table: rule id -> scenario -> outcome."""
    with expected_path(standard).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["rule"]: {s: r[s] for s in SCENARIOS if s in r} for r in rows}


def render_expected(actual: dict[str, dict[str, str]], standard: str = "g7ai") -> str:
    """Render *actual* (scenario -> rule -> outcome) as the TSV text."""
    kinds = provisions(standard)
    lines = ["\t".join(["rule", "provision", *SCENARIOS])]
    for rule in sorted(kinds):
        cells = [actual[s][rule] for s in SCENARIOS]
        lines.append("\t".join([rule, kinds[rule], *cells]))
    return "\n".join(lines) + "\n"
