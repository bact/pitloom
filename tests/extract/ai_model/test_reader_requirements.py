# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The library a model reader needs is looked up without importing it, and a
missing one gives the same message as the reader's own failed import.

See also: :mod:`tests.extract.scanner.test_scanner_wheel` (a wheel scan does
not copy a model whose library is missing).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model.reader_requirements import (
    REQUIREMENTS,
    Requirement,
    missing_library,
    require_library,
)


@pytest.fixture(autouse=True, name="fake_requirement")
def fixture_fake_requirement(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setitem(
        REQUIREMENTS, AiModelFormat.ONNX, Requirement("pitloom_fake_lib", "needs it")
    )
    return "pitloom_fake_lib"


def test_a_library_that_cannot_be_found_raises_the_readers_message() -> None:
    with pytest.raises(ImportError, match="^needs it$"):
        require_library(AiModelFormat.ONNX)
    assert str(missing_library(AiModelFormat.ONNX)) == "needs it"


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


def test_every_message_names_its_package_and_its_install_command() -> None:
    for fmt, requirement in REQUIREMENTS.items():
        if fmt is AiModelFormat.ONNX:
            continue  # replaced by the fixture
        assert f"'{requirement.module}'" in requirement.message
        assert "pip install" in requirement.message
