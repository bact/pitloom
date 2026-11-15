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

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.kv_output import kv_line
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
    ],
    ids=["userinfo", "token", "collapsed"],
)
def test_a_url_value_is_masked(value: str, shown: str) -> None:
    assert kv_line(SOURCE=value) == f"SOURCE={shown}"


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
