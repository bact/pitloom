# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A newline in a path argument never starts a second, forged line on stderr:
every command's error stays one tagged line.

See also: tests/test_logging_config.py (the formatter and `print_error`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main

_HOSTILE = "a\nWARNING: forged"


@pytest.mark.parametrize(
    "argv",
    [
        ["fragment", "validate", _HOSTILE],
        ["verify-wheel", _HOSTILE],
        ["embed-wheel", "c\nWARNING: x*.whl"],
        ["model", _HOSTILE],
        ["enrich", _HOSTILE],
        ["wheel", _HOSTILE],
        ["merge", _HOSTILE],
        ["project", _HOSTILE],
        ["id", "generate", "--id-registry", _HOSTILE + ".json"],
        ["id", "import", _HOSTILE],
        ["id", "generate", "--project-dir", _HOSTILE],
    ],
    ids=lambda argv: " ".join(argv[:2]),
)
def test_a_hostile_path_cannot_forge_a_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert main() != 0
    lines = capsys.readouterr().err.splitlines()
    assert lines, "no error was reported"
    assert all(line.startswith(("ERROR: ", "WARNING: ", "INFO: ")) for line in lines)
    assert not any(line.startswith("WARNING: forged") for line in lines)
