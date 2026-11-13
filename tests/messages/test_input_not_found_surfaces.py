# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found`` and its neighbours on every surface: each input kind
reads as one line with its code, and the command line and the library say
the same text for the same fault.

See also: tests/messages/test_input_not_found.py (the helpers).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_merged_sbom
from pitloom.core.config_cascade import load_config_file
from pitloom.core.wheel_dist_info import WheelRefused, require_wheel_path
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.reader import read_project
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.project.setuptools_cfg import read_setup_cfg
from pitloom.extract.project.setuptools_py import read_setup_py
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    INPUT_KINDS,
)
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    TARGET_WRONG_FORMAT,
    input_not_found,
)
from tests._message_drift import raised_as

pytestmark = pytest.mark.platform


@pytest.mark.parametrize("kind", INPUT_KINDS)
def test_every_kind_reads_as_one_coded_line(kind: str) -> None:
    exc = input_not_found(kind, "gone/x y")
    assert str(exc) == f"{kind} not found: 'gone/x y'"
    assert raised_as(exc, INPUT_NOT_FOUND)


@pytest.mark.parametrize(
    "read",
    [
        lambda p: read_pyproject(p / "pyproject.toml"),
        read_setup_cfg,
        read_setup_py,
        lambda p: read_sdist(p / "a-1.tar.gz"),
        lambda p: read_project(p / "none"),
        lambda p: load_config_file(p / "c.toml"),
        lambda p: IdRegistry.load(p / "r.json"),
    ],
    ids=[
        "pyproject",
        "setup.cfg",
        "setup.py",
        "sdist",
        "project",
        "config",
        "registry",
    ],
)
def test_a_missing_input_raises_the_coded_error(tmp_path: Path, read: object) -> None:
    with pytest.raises(FileNotFoundError) as caught:
        read(tmp_path)  # type: ignore[operator]
    assert raised_as(caught.value, INPUT_NOT_FOUND)
    assert " not found: " in str(caught.value) and "\n" not in str(caught.value)


def _loom(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, err: pytest.CaptureFixture[str]
) -> list[str]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    return err.readouterr().err.splitlines()


def test_merge_says_the_same_on_the_command_line_and_in_the_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing directory, then an empty one."""
    missing, empty = tmp_path / "gone", tmp_path / "empty"
    empty.mkdir()
    for fragments, line in (
        (missing, f"fragments directory not found: '{missing}'"),
        (empty, f"no JSON fragment file in '{empty}'"),
    ):
        (cli,) = _loom(
            ["merge", str(fragments), "-o", str(tmp_path / "o.json")],
            monkeypatch,
            capsys,
        )
        assert cli == f"ERROR: loom merge: {line} [input-not-found]"
        with pytest.raises((FileNotFoundError, ValueError)) as caught:
            generate_merged_sbom(fragments)
        assert str(caught.value) == line
        assert getattr(caught.value, CODE_ATTR) == "input-not-found"


def test_a_fragments_directory_that_is_a_file_says_so(tmp_path: Path) -> None:
    exc = input_not_found("fragments directory", tmp_path / "f.json")
    assert str(exc).endswith("f.json'")
    (tmp_path / "f.json").write_text("{}")
    assert str(input_not_found("fragments directory", tmp_path / "f.json")).endswith(
        " is not a directory"
    )


def test_a_not_wheel_name_is_the_same_line_on_both_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "a\nb.txt"
    with pytest.raises(WheelRefused) as caught:
        require_wheel_path(path)
    assert raised_as(caught.value, TARGET_WRONG_FORMAT)
    assert "\n" not in str(caught.value)
    (cli,) = _loom(["embed-wheel", str(path)], monkeypatch, capsys)
    assert cli == f"ERROR: loom embed-wheel: {caught.value} [target-wrong-format]"


def test_generate_without_output_is_coded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (cli,) = _loom(["generate", "."], monkeypatch, capsys)
    assert cli.startswith("ERROR: loom generate: -o/--output is required: ")
    assert cli.endswith(" [option-missing]")


def test_a_wheel_pattern_that_matches_nothing_is_coded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pattern = str(tmp_path / "*.whl")
    (cli,) = _loom(["verify-wheel", pattern], monkeypatch, capsys)
    assert cli == (
        f"ERROR: loom verify-wheel: no wheel file matches '{pattern}' [input-not-found]"
    )
