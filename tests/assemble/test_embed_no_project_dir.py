# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``embed-wheel`` run without ``--project-dir`` in a directory holding a
``pyproject.toml`` says so with one ``INFO:`` (``option-missing/project-dir``):
the SBOM is built from the wheel alone.

See also: test_embed_cli.py (the other ``embed-wheel`` CLI tests).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.messages import trusted_message

from .conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_CODE = "option-missing/project-dir"


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, pyproject: bool, given: bool
) -> None:
    """Run an embed in a directory with or without a ``pyproject.toml``, with
    or without ``--project-dir``."""
    here = tmp_path / "cwd"
    here.mkdir()
    if pyproject:
        (here / "pyproject.toml").write_text(
            '[project]\nname = "other"\nversion = "9"\n', encoding="utf-8"
        )
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo_pkg", "1.0.0")
    argv = ["loom", "embed-wheel", str(wheel)]
    if given:
        argv += ["--project-dir", str(here)]
    monkeypatch.chdir(here)
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 0


def test_a_project_in_the_current_directory_that_is_not_used_is_said_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run(monkeypatch, tmp_path, pyproject=True, given=False)
    lines = [line for line in capsys.readouterr().err.splitlines() if _CODE in line]
    assert len(lines) == 1
    assert lines[0].startswith("INFO: --project-dir not given; the SBOM is built ")
    found = trusted_message(lines[0])
    assert found is not None and found.code == _CODE


@pytest.mark.parametrize(
    ("pyproject", "given"),
    [(False, False), (True, True)],
    ids=["no-project-here", "project-dir-given"],
)
def test_nothing_is_said_where_nothing_was_expected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pyproject: bool,
    given: bool,
) -> None:
    _run(monkeypatch, tmp_path, pyproject=pyproject, given=given)
    assert _CODE not in capsys.readouterr().err
