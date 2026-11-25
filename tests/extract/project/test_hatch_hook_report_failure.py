# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the Hatchling hook says when its run fails: an exception with no
text is named by its class, and an interrupt or an exit is not a failure of
the SBOM, so it is raised with no ``ERROR:`` line.

See also: tests/messages/test_config_hook.py (the line's text and escapes) and
:mod:`tests.extract.project.test_hatch_hook_hook_basic`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.plugins.hatch import PitloomBuildHook

from ..conftest import make_hook

pytestmark = pytest.mark.platform


def _fail_with(monkeypatch: pytest.MonkeyPatch, raised: BaseException) -> None:
    def fail(*_args: object) -> None:
        raise raised

    monkeypatch.setattr(PitloomBuildHook, "_generate", fail)


@pytest.mark.parametrize(
    ("raised", "tail"),
    [
        (RuntimeError(), "RuntimeError"),
        (ValueError(""), "ValueError"),
        (RuntimeError("boom"), "boom"),
    ],
    ids=["no-args", "empty-text", "text"],
)
def test_an_exception_with_no_text_is_named_by_its_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: Exception,
    tail: str,
) -> None:
    _fail_with(monkeypatch, raised)
    with pytest.raises(type(raised)):
        make_hook(str(tmp_path), {}).initialize("standard", {})
    assert capsys.readouterr().err.splitlines() == [
        f"ERROR: Pitloom build hook: {tail}"
    ]


@pytest.mark.parametrize(
    "raised", [KeyboardInterrupt(), SystemExit(1)], ids=["interrupt", "exit"]
)
def test_an_interrupt_or_an_exit_is_raised_with_no_error_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: BaseException,
) -> None:
    _fail_with(monkeypatch, raised)
    with pytest.raises(type(raised)):
        make_hook(str(tmp_path), {}).initialize("standard", {})
    assert "ERROR:" not in capsys.readouterr().err
