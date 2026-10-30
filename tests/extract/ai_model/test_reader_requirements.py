# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The library a model reader needs is looked up without importing it, and a
missing one gives the same error as the reader's own failed import
(``library-missing``, naming the module and the extra to install).

See also: :mod:`tests.extract.scanner.test_scanner_wheel` (a wheel scan does
not copy a model whose library is missing) and
:mod:`tests.core.test_optional_libraries` (each extra exists).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.optional_libraries import Requirement
from pitloom.extract.ai_model.reader_requirements import (
    REQUIREMENTS,
    missing_library,
    require_library,
)
from pitloom.messages import LIBRARY_MISSING, code_of
from tests._message_drift import raised_as


@pytest.fixture(autouse=True, name="fake_requirement")
def fixture_fake_requirement(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setitem(
        REQUIREMENTS, AiModelFormat.ONNX, Requirement("pitloom_fake_lib", "fake")
    )
    return "pitloom_fake_lib"


def test_a_library_that_cannot_be_found_raises_the_readers_error() -> None:
    text = "required library not installed: pitloom_fake_lib; install pitloom[fake]"
    with pytest.raises(ImportError, match=r"^required .*pitloom\[fake\]$") as caught:
        require_library(AiModelFormat.ONNX)
    error = missing_library(AiModelFormat.ONNX)
    assert str(caught.value) == str(error) == text
    assert code_of(caught.value) == code_of(error) == "library-missing"
    assert raised_as(error, LIBRARY_MISSING)


@pytest.mark.parametrize("kind", ["installed", "no-spec"])
def test_an_importable_library_passes(
    kind: str, fake_requirement: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module already imported with no ``__spec__`` makes ``find_spec``
    raise ``ValueError``: it is installed."""
    name = "json" if kind == "installed" else fake_requirement
    if kind == "no-spec":
        module = ModuleType(name)
        module.__spec__ = None
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(REQUIREMENTS, AiModelFormat.ONNX, Requirement(name, "x"))
    require_library(AiModelFormat.ONNX)


def test_a_format_without_a_requirement_needs_none() -> None:
    assert AiModelFormat.KERAS not in REQUIREMENTS
    require_library(AiModelFormat.KERAS)


def test_every_error_names_its_module_and_its_extra() -> None:
    for fmt, requirement in REQUIREMENTS.items():
        if fmt is AiModelFormat.ONNX:
            continue  # replaced by the fixture
        text = str(missing_library(fmt))
        assert f": {requirement.module}; " in text
        assert text.endswith(f"; install pitloom[{requirement.extra}]")
