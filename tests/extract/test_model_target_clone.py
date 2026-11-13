# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A named file and how a refusal names it, in
:mod:`pitloom.extract.model_target`: a model suffix is one in any case, a
link named in a Git URL's clone is not followed, and the name a refusal
shows is the POSIX one it was given, on every platform.

See also: tests/extract/test_model_target.py (the rule) and
tests/extract/remote/test_git_target_named.py (a Git URL's named file).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.clone_mark import reading_remote_clone
from pitloom.extract import _model_named
from pitloom.extract.ai_model import NotAModel, refusal_error
from pitloom.extract.model_target import (
    AUTO,
    MODEL,
    PROJECT,
    refuse_not_a_model,
    require_model_file,
    resolve_sbom_target,
)
from pitloom.messages import code_of
from pitloom.messages.models import MODEL_WRONG_FORMAT
from tests._model_fixtures import fixture_path
from tests._symlink import CAN_SYMLINK

_PYPROJECT = b'[project]\nname = "demo"\nversion = "1.0"\n'
#: ``os.mkfifo`` is POSIX only.
_NO_FIFO = sys.platform == "win32" or not hasattr(os, "mkfifo")


@pytest.mark.parametrize("name", ["x.GGUF", "m.Onnx", "w.SafeTensors"])
def test_a_model_suffix_in_any_case_makes_a_named_file_strict(
    tmp_path: Path, name: str
) -> None:
    """Under auto, an empty file whose suffix is a model's in another case is
    refused as the lower-case name is, not passed over for the project."""
    (tmp_path / "pyproject.toml").write_bytes(_PYPROJECT)
    (tmp_path / name).write_bytes(b"")
    with pytest.raises(ValueError) as excinfo:
        resolve_sbom_target(tmp_path, subject="d", file=name, mode=AUTO)
    assert code_of(excinfo.value) == MODEL_WRONG_FORMAT.code
    assert f"'{name}'" in str(excinfo.value)


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs symbolic links")
def test_a_named_link_in_a_clone_is_not_followed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A suffix-less link to a model of the folder is the model when read
    locally; in a clone it is not followed (the folder is read), and a link
    with a model suffix is not found."""
    (tmp_path / "pyproject.toml").write_bytes(_PYPROJECT)
    shutil.copyfile(fixture_path(AiModelFormat.GGUF), tmp_path / "real.bin")
    (tmp_path / "m.dat").symlink_to("real.bin")
    (tmp_path / "m.gguf").symlink_to("real.bin")
    assert resolve_sbom_target(tmp_path, subject="d", file="m.dat").kind == MODEL
    with reading_remote_clone():
        with caplog.at_level(logging.INFO, logger="pitloom"):
            target = resolve_sbom_target(tmp_path, subject="d", file="m.dat")
        assert target.kind == PROJECT
        assert "FILE=m.dat: not an AI model file; reading its folder" in caplog.text
        with pytest.raises(FileNotFoundError) as excinfo:
            resolve_sbom_target(tmp_path, subject="d", file="m.gguf", mode=MODEL)
    assert code_of(excinfo.value) == "input-not-found"


def test_a_refusal_hands_the_shown_name_on_as_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The POSIX name a refusal shows is passed as a ``str``: a ``Path``
    would spell it with backslashes on Windows."""
    seen: list[Any] = []
    real = refusal_error

    def spy(path: Any, named: Any, reason: Any) -> ValueError:
        seen.append(path)
        return real(path, named, reason)

    monkeypatch.setattr(_model_named, "refusal_error", spy)
    monkeypatch.setattr(_model_named, "Path", PureWindowsPath)
    with pytest.raises(ValueError) as excinfo:
        refuse_not_a_model(
            Path("tmp", "x.gguf"), NotAModel(), shown="models/sub/x.gguf"
        )
    assert seen == ["models/sub/x.gguf"]
    assert "'models/sub/x.gguf'" in str(excinfo.value)


@pytest.mark.skipif(_NO_FIFO, reason="needs os.mkfifo")
def test_a_named_file_that_is_no_regular_file_is_refused_before_a_read(
    tmp_path: Path,
) -> None:
    """A FIFO is refused on its ``stat()``: its open would wait for a
    writer."""
    os.mkfifo(tmp_path / "m.gguf")
    with pytest.raises(ValueError) as excinfo:
        require_model_file(tmp_path / "m.gguf", "m.gguf")
    assert code_of(excinfo.value) == MODEL_WRONG_FORMAT.code
    assert str(excinfo.value) == "'m.gguf': not an AI model file of a supported format"
