# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A token after an ANSI colour sequence in a missing input path is masked on
the CLI and in the library: the sequence is escaped to ``\\x1b[33m`` only
after the token in the raw text is masked.

See also: tests/logging/test_credential_sinks_cut.py,
tests/logging/test_credential_sinks_factory.py,
tests/logging/test_credential_sinks_root.py,
tests/cli/test_cli_typed_spelling.py.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom

pytestmark = pytest.mark.platform

# A fake token, built at run time so no secret-shaped literal sits in source.
TOKEN = "ghp_" + "A1b2" * 9


def _missing_wheel(tmp_path: Path) -> str:
    """A wheel path, never created (ESC is invalid in a Windows file name),
    naming the token after an ANSI colour sequence."""
    path = str(tmp_path / f"x\x1b[33m{TOKEN}.whl")
    assert not Path(path).exists()
    return path


def _assert_masked(shown: str) -> None:
    """*shown* holds the masked token and no piece of the real one."""
    assert "ghp_***" in shown
    assert TOKEN not in shown and TOKEN[4:20] not in shown


def test_the_cli_masks_a_token_after_an_ansi_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", _missing_wheel(tmp_path)])
    assert __main__.main() == 1
    captured = capsys.readouterr()
    (line,) = [text for text in captured.err.splitlines() if text.startswith("ERROR")]
    assert line.endswith(".whl' [input-not-found]")
    _assert_masked(line)
    assert TOKEN[4:20] not in captured.out + captured.err


def test_the_library_masks_a_token_after_an_ansi_sequence(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        with pytest.raises(FileNotFoundError) as caught:
            generate_wheel_sbom(_missing_wheel(tmp_path))
    assert getattr(caught.value, "pitloom_code", None) == "input-not-found"
    _assert_masked(str(caught.value))
    captured = capsys.readouterr()
    assert TOKEN[4:20] not in caplog.text + captured.out + captured.err
