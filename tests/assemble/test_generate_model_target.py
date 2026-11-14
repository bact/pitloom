# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``generate()`` on a local model file or folder: a file is a model by its
content (as ``loom model`` reads it), a folder with no project is read for
its one model file, and a folder with neither is refused; the classifier
that decides it says nothing.

See also: :mod:`tests.extract.test_model_target` (the resolver) and
:mod:`tests.assemble.test_generate_git_url` (the other target kinds).
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import (
    _classify_target,
    generate,
    generate_model_sbom,
    target_resolves_to_project,
)
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.creation import CreationMetadata
from pitloom.messages import (
    CodedValueError,
    code_of,
)
from pitloom.messages.targets import NO_SBOM_TARGET
from tests._model_fixtures import fixture_path

_FIXED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_DEMO = '[project]\nname = "demo"\nversion = "1.0"\n'


def _gguf_as_dat(folder: Path) -> Path:
    """The GGUF fixture, named ``x.dat`` (no model suffix), in *folder*."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "x.dat"
    target.write_bytes(fixture_path(AiModelFormat.GGUF).read_bytes())
    return target


def _keras_folder(folder: Path) -> Path:
    """A folder holding the Keras fixture and a README."""
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_path(AiModelFormat.KERAS), folder)
    (folder / "README.md").write_text("r\n", encoding="utf-8")
    return folder


def _empty_folder(folder: Path) -> Path:
    folder.mkdir(parents=True)
    return folder


@pytest.mark.parametrize(
    ("build", "kind"),
    [
        (_gguf_as_dat, "model_file"),
        (_keras_folder, "model_folder"),
        (_empty_folder, "model_folder"),
        (lambda d: d / "missing", "project"),
    ],
    ids=["gguf-content", "model-folder", "empty-folder", "missing-path"],
)
def test_a_local_path_is_classified_silently(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    build: Callable[[Path], Path],
    kind: str,
) -> None:
    """By content and project markers only; nothing is logged however often
    it is asked."""
    target = build(tmp_path / "t")
    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            assert _classify_target(target) == kind
    assert target_resolves_to_project(target) is (kind == "project")
    assert not caplog.records


def test_a_folder_with_a_project_is_still_a_project(tmp_path: Path) -> None:
    """A project config wins over the model file beside it."""
    _keras_folder(tmp_path)
    (tmp_path / "pyproject.toml").write_text(_DEMO, encoding="utf-8")
    assert _classify_target(tmp_path) == "project"
    graph = json.loads(generate(tmp_path, creation_metadata=_FIXED))["@graph"]
    names = [e.get("name") for e in graph if e.get("type") == "software_Package"]
    assert names == ["demo"]  # the project's package, and no model's
    assert not [e for e in graph if e.get("type") == "ai_AIPackage"]


@pytest.mark.parametrize(
    "build", [_gguf_as_dat, _keras_folder], ids=["file-by-content", "folder"]
)
def test_generate_reads_the_model_as_the_model_generator_does(
    tmp_path: Path, build: Callable[[Path], Path]
) -> None:
    """The same bytes as ``generate_model_sbom()`` on the model file."""
    target = build(tmp_path / "t")
    model = (
        target if target.is_file() else target / fixture_path(AiModelFormat.KERAS).name
    )
    expected = generate_model_sbom(model, creation_metadata=_FIXED)
    assert generate(target, creation_metadata=_FIXED) == expected
    assert generate(str(target), creation_metadata=_FIXED) == expected


def test_a_folder_with_neither_is_refused(tmp_path: Path) -> None:
    """``project-or-model-not-found``, not a missing ``pyproject.toml``."""
    (tmp_path / "README.md").write_text("r\n", encoding="utf-8")
    with pytest.raises(CodedValueError) as excinfo:
        generate(tmp_path)
    assert code_of(excinfo.value) == NO_SBOM_TARGET.code
