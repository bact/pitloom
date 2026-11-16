# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``KEY=VALUE`` value on stdout is data: a URL in it is printed without
its credentials, but a path that only looks like an scp-style address
(``meet 10:30@ab:c.json``) is printed as given, so a consumer (the GitHub
Action's ``sbom-path``) reads back the file the command wrote.

See also: tests/cli/test_cli_kv_stdout.py and
tests/core/url_masking/test_url_masking_credentials.py.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.kv_output import kv_line, log_kv
from tests.assemble.embed_surfaces_shared import demo_project
from tests.kv_helpers import kv_stdout

pytestmark = pytest.mark.platform

SECRET = "PLANTSECRET"
#: ``:`` is not allowed in a Windows file name.
_WINDOWS = sys.platform == "win32"


@pytest.mark.parametrize(
    "value",
    ["out/meet 10:30@ab:c.json", "alice:b@c:d.json", "C:\\x\\u:p@h:o.json"],
    ids=["meeting", "short", "drive"],
)
def test_a_lookalike_path_is_printed_as_given(value: str) -> None:
    assert kv_line(PATH=value) == f"PATH={value}"


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (f"https://u:{SECRET}@h/x", "https://***:***@h/x"),
        (f"https://h/x?token={SECRET}", "https://h/x?token=***"),
        (f"out/https:/u:{SECRET}@h/x.json", "out/https:/***:***@h/x.json"),
        (f"https://h/a b?token={SECRET}", "https://h/a b?token=***"),
        (f"https\u200b://h/x?token={SECRET}", "https://h/x?token=***"),
        (f"a https\u200b://u:{SECRET}@h/x", "a https://***:***@h/x"),
        (f"\ufeffhttps://h/a b?token={SECRET}", "https://h/a b?token=***"),
    ],
    ids=[
        *("userinfo", "token", "collapsed", "space-in-path"),
        *("format-in-scheme", "format-in-text", "bom-then-space"),
    ],
)
def test_a_url_value_is_masked(
    value: str, shown: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A value that starts with a URL is read whole: a space in its path
    does not end it (``-v`` details and stdout alike)."""
    assert kv_line(SOURCE=value) == f"SOURCE={shown}"
    with caplog.at_level(logging.INFO, logger="pitloom"):
        log_kv(SOURCE=value)
    assert SECRET not in caplog.text and f"SOURCE={shown}" in caplog.text


@pytest.mark.skipif(_WINDOWS, reason="':' is not allowed in a Windows file name")
def test_generate_prints_the_lookalike_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The output path ``loom generate`` prints is the file it wrote."""
    out = tmp_path / "meet 10:30@ab:c.json"
    argv = ["generate", str(demo_project(tmp_path)), "--offline", "-o", str(out)]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0
    (record,) = kv_stdout(capsys.readouterr().out)
    assert Path(record["PITLOOM_SBOM_OUTPUT_PATH"]) == out
    assert out.is_file()
