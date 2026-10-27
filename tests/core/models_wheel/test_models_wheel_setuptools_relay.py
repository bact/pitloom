# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What setuptools says during file discovery reaches stderr only as tagged
``pitloom`` records (:mod:`pitloom.core._models_wheel_setuptools_relay`).

See also: tests/test_setuptools_default_backend_surfaces.py (a real ``loom``
process on every surface), tests/extract/test_stderr_capture.py (the capture).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import pytest

from pitloom.core import _models_wheel_setuptools_relay as relay
from pitloom.core._models_wheel_setuptools import discover

_LOGGER = "pitloom.core._models_wheel_setuptools_relay"
_PREFIX = "'proj': setuptools stderr: "


def _relayed(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == _LOGGER]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "warning: no files found matching '*.js'\n",
            [(logging.DEBUG, "warning: no files found matching '*.js'")],
        ),
        (
            "error: bad\r\n  Error: also\r\nno previously-included\r",
            [
                (logging.WARNING, "error: bad"),
                (logging.WARNING, "Error: also"),
                (logging.DEBUG, "no previously-included"),
            ],
        ),
        ("\n  \n\t\n", []),
        (
            "ERROR: forged\nINFO: forged\n",
            [(logging.WARNING, "ERROR: forged"), (logging.DEBUG, "INFO: forged")],
        ),
        ("\x1b[31mred\x1b[0m", [(logging.DEBUG, r"'\x1b[31mred\x1b[0m'")]),
        ("bad \udcff byte", [(logging.DEBUG, r"'bad \udcff byte'")]),
        ("x" * 100_000, [(logging.DEBUG, "x" * 100_000)]),
        ("same\nsame\n", [(logging.DEBUG, "same"), (logging.DEBUG, "same")]),
    ],
    ids=[
        "warning",
        "crlf-cr-error",
        "blank",
        "forged",
        "ansi",
        "non-utf8",
        "long",
        "repeat",
    ],
)
def test_each_line_is_one_tagged_record(
    caplog: pytest.LogCaptureFixture,
    text: str,
    expected: list[tuple[int, str]],
) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        relay.relay_stderr_text(Path("proj"), text)
    assert _relayed(caplog) == [(lvl, _PREFIX + msg) for lvl, msg in expected]
    assert all("\n" not in m and "\r" not in m for _, m in _relayed(caplog))


def test_what_was_not_kept_is_counted(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        relay.relay_stderr_text(Path("proj"), "kept", dropped=7)
    assert _relayed(caplog) == [
        (logging.DEBUG, _PREFIX + "kept"),
        (logging.DEBUG, _PREFIX + "7 more characters not kept"),
    ]


def test_the_block_relays_stderr_records_and_warnings_also_on_error(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``distutils.log`` with no root handler ends in ``logging.lastResort``,
    which writes to ``sys.stderr``; ``distutils.text_file`` writes there itself.
    The capture keeps *STDERR_KEEP* characters and counts the rest."""
    first = "warning: no files found matching '*.js'"
    second = "warning: MANIFEST.in, line 1: continuation\n"
    monkeypatch.setattr(relay, "STDERR_KEEP", len(first) + 1 + 20)
    record = logging.makeLogRecord(
        {"msg": "warning: no files found matching %r", "args": ("*.js",)}
    )
    record.levelno = logging.WARNING
    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER),
        pytest.raises(RuntimeError, match="boom"),
        relay.relay_setuptools_output(Path("proj")),
    ):
        assert logging.lastResort is not None
        logging.lastResort.handle(record)
        sys.stderr.write(second)
        warnings.warn("banner\nline two", DeprecationWarning, stacklevel=1)
        raise RuntimeError("boom")
    assert capsys.readouterr().err == ""
    assert _relayed(caplog) == [
        (logging.DEBUG, _PREFIX + first),
        (logging.DEBUG, _PREFIX + second[:20]),
        (logging.DEBUG, _PREFIX + f"{len(second) - 20} more characters not kept"),
        (logging.DEBUG, "setuptools DeprecationWarning: banner line two"),
    ]


def test_discover_relays_the_manifest_step(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A real discovery: ``distutils.text_file`` writes its warning on a
    trailing continuation in ``MANIFEST.in`` to ``sys.stderr`` itself."""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_bytes(b"")
    (tmp_path / "pyproject.toml").write_bytes(
        b'[project]\nname = "demo"\nversion = "1"\n'
    )
    (tmp_path / "MANIFEST.in").write_bytes(b"include *.js \\")
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        files = discover(tmp_path)
    assert files is not None
    assert capsys.readouterr().err == ""
    messages = [m for _, m in _relayed(caplog)]
    assert any(
        "setuptools stderr: warning: MANIFEST.in, line 1: continuation line" in m
        for m in messages
    )
