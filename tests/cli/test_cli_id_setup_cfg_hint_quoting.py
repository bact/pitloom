# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression test for the ``id-registry`` config hint's quoting: a
``setup.cfg``-configured project's hint must be unquoted, since
``setup.cfg``'s ``[tool:pitloom]`` values are read with ``str.strip()``
only (see
:func:`pitloom.extract.project.setuptools_cfg._read_pitloom_config_from_cfg`)
-- never quote-stripped like TOML syntax is. A ``json.dumps``-quoted hint
pasted verbatim under ``[tool:pitloom]`` would bake the quote characters
into the value itself, so the next run looks for a file literally named
``"loom-id-registry.json"`` (quotes included) and fails with "not found".

See also: test_cli_id_config_errors.py (the rest of the setup.cfg-config
regression tests), test_cli_id.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser


def _run(args: list[str]) -> int:
    parser = _build_parser()
    return _run_id_command(parser.parse_args(args))


def test_setup_cfg_hint_is_unquoted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A setup.cfg-only project's fresh-registry hint has no quote
    characters around the path -- unlike the pyproject.toml variant,
    which is a ``json.dumps``-quoted TOML string literal."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n", encoding="utf-8"
    )
    registry_path = tmp_path / "loom-id-registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            ["id", "generate", "--project-dir", str(tmp_path), "-o", str(registry_path)]
        )

    assert exit_code == 0
    assert "id-registry = loom-id-registry.json" in caplog.text
    assert '"loom-id-registry.json"' not in caplog.text


def test_pasting_setup_cfg_hint_is_usable_by_next_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end: generate a registry for a setup.cfg project, paste the
    hint's ``id-registry = ...`` line verbatim under ``[tool:pitloom]``,
    and confirm `loom project .` then finds and uses that registry file
    (exit 0) -- the bug this regression closes made the pasted line
    quote-wrapped, so the next run looked for a nonexistent
    quote-included filename."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n", encoding="utf-8"
    )
    registry_path = tmp_path / "loom-id-registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            ["id", "generate", "--project-dir", str(tmp_path), "-o", str(registry_path)]
        )
    assert exit_code == 0

    full_line = next(
        line for line in caplog.text.splitlines() if "id-registry = " in line
    )
    hint_line = full_line[full_line.index("id-registry = ") :].strip()
    with (tmp_path / "setup.cfg").open("a", encoding="utf-8") as handle:
        handle.write(f"\n[tool:pitloom]\n{hint_line}\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["loom", "project", "."])
    assert __main__.main() == 0
