# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A newline in a path argument never starts a second, forged line on stderr:
every command's error stays one tagged line, ending in its catalogued code.

See also: tests/test_logging_config.py (the formatter and `print_error`),
tests/messages/test_messages_emit.py (the code a line ends in).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.cli.commands.utils import cli_error_handler, report_error_line
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.messages import (
    CONFIG_MEMBER_LINE,
    LFS_POINTER_MALFORMED,
    OVER_CAP,
    CodedValueError,
    Message,
    trusted_message,
)

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
        ["env", "--python", _HOSTILE, "-o", "o.json"],
        ["generate", _HOSTILE, "-o", "o.json", "-v"],
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
    try:
        code = main()
    except SystemExit as exit_:  # argparse refuses an argument
        code = exit_.code if isinstance(exit_.code, int) else 1
    assert code != 0
    lines = capsys.readouterr().err.splitlines()
    assert lines, "no error was reported"
    assert not any(line.startswith("WARNING: forged") for line in lines)
    # Every line is tagged, a usage line, or part of an indented traceback.
    assert all(
        line.startswith(("ERROR: ", "WARNING: ", "INFO: ", "usage: ", " "))
        for line in lines
    )


_LOOKS = "'m': header looks like a Git LFS pointer but is not a valid one"
_CONFIG = "config file 's.tar.gz:setup.cfg': larger than the 1-byte config-member cap"
_CLONE = "the repository is larger than 1 KiB; git clone was stopped"


@pytest.mark.parametrize(
    ("raised", "tail", "trusted"),
    [
        (
            CodedValueError(LFS_POINTER_MALFORMED, path="m"),
            f"{_LOOKS} [lfs-pointer-malformed]",
            LFS_POINTER_MALFORMED,
        ),
        (
            CodedValueError(
                OVER_CAP,
                line=CONFIG_MEMBER_LINE,
                path="s.tar.gz:setup.cfg",
                limit=1,
                unit="byte",
                purpose="config-member",
            ),
            f"{_CONFIG}; not read [over-cap]",
            OVER_CAP,
        ),
        (
            RemoteSourceError("git.too-large", _CLONE, pitloom_code="over-cap"),
            f"{_CLONE} [over-cap]",
            OVER_CAP,
        ),
        (RemoteSourceError("git.too-large", "x"), "x", None),
    ],
    ids=["catalogued", "over-cap-config", "over-cap-remote", "uncatalogued"],
)
def test_an_error_line_ends_in_a_catalogued_code_only(
    capsys: pytest.CaptureFixture[str],
    raised: Exception,
    tail: str,
    trusted: Message | None,
) -> None:
    """Both CLI error reporters, the per-wheel line and the command wrapper
    (its frame ``model command failed: ``), end in the code, trusted."""

    @cli_error_handler("model command failed")
    def _fail(_args: object) -> int:
        raise raised

    report_error_line(raised)
    assert _fail(object()) == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines == [f"ERROR: {tail}", f"ERROR: model command failed: {tail}"]
    assert [trusted_message(line) for line in lines] == [trusted, trusted]
