# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Each optional library names an extra ``pyproject.toml`` declares, and
that extra installs the distribution that provides the module; ``ai``
installs every model reader and the Hub client, as the ``library-missing``
reference says. A missing one is said as ``library-missing``.

See also: :mod:`tests.extract.ai_model.test_reader_requirements` (the
readers' lookup) and :mod:`tests.messages.test_model_stub` (the entry).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import Requirement as Pep508
from packaging.utils import canonicalize_name

import pitloom.core.optional_libraries as libraries
from pitloom._toml_io import load_toml_file
from pitloom.core.optional_libraries import Requirement, missing
from pitloom.extract.ai_model.reader_requirements import REQUIREMENTS
from pitloom.messages import LIBRARY_MISSING, code_of
from tests._message_drift import raised_as

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
#: The distribution that provides each module (PEP 503 names).
_DISTRIBUTIONS = {
    "build": "build",
    "fasttext": "fasttext-community",
    "gguf": "gguf",
    "h5py": "h5py",
    "huggingface_hub": "huggingface-hub",
    "magika": "magika",
    "numpy": "numpy",
    "onnx": "onnx",
    "safetensors": "safetensors",
    "spdx3_validate": "spdx3-validate",
}
_OWN = [v for v in vars(libraries).values() if isinstance(v, Requirement)]
_ALL = [*REQUIREMENTS.values(), *_OWN]


def _extras() -> dict[str, set[str]]:
    """Each extra of ``pyproject.toml`` to the distributions it lists."""
    project = load_toml_file(_PYPROJECT)["project"]
    assert isinstance(project, dict)
    table = project["optional-dependencies"]
    return {
        extra: {canonicalize_name(Pep508(spec).name) for spec in specs}
        for extra, specs in table.items()
    }


def test_the_table_is_found() -> None:
    assert len(_OWN) == 4 and len(REQUIREMENTS) == 6
    assert {r.module for r in _ALL} == set(_DISTRIBUTIONS)


@pytest.mark.parametrize("requirement", _ALL, ids=lambda r: r.module)
def test_each_extra_installs_its_modules_distribution(
    requirement: Requirement,
) -> None:
    extras = _extras()
    assert requirement.extra in extras, requirement
    assert _DISTRIBUTIONS[requirement.module] in extras[requirement.extra]


def test_ai_installs_every_model_reader_and_the_hub() -> None:
    wanted = {_DISTRIBUTIONS[r.module] for r in [*REQUIREMENTS.values(), libraries.HUB]}
    assert wanted <= _extras()["ai"]


@pytest.mark.parametrize("requirement", _ALL, ids=lambda r: r.module)
def test_a_missing_library_is_said_as_library_missing(
    requirement: Requirement,
) -> None:
    error = missing(requirement)
    assert isinstance(error, ImportError)
    assert code_of(error) == "library-missing" and raised_as(error, LIBRARY_MISSING)
    assert str(error) == (
        f"required library not installed: {requirement.module}; "
        f"install {requirement.spec}"
    )
    assert requirement.spec == f"pitloom[{requirement.extra}]"


@pytest.mark.parametrize(
    ("module", "extra"),
    [("Gguf", "gguf"), ("gguf", "Gguf"), ("gguf", "gguf]; pip install x")],
    ids=["module", "extra", "forged"],
)
def test_a_requirement_out_of_shape_is_refused(module: str, extra: str) -> None:
    """A module's name in lower case, an extra's after ``pitloom``: the line
    never names something else to install."""
    with pytest.raises(ValueError) as caught:
        raise missing(Requirement(module, extra))
    assert not isinstance(caught.value, ImportError)
