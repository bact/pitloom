# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the "registry location is required everywhere,
never assumed" decision: `pitloom id generate`/`pitloom id import` with
neither ``--id-registry``/``-o`` nor a declared project ``id-registry``
key must print exactly one ``ERROR:`` line, exit 1, and write nothing --
no implicit ``loom-id-registry.json`` fallback file.

See also: test_cli_id.py (the rest of `pitloom id`'s CLI tests),
test_cli_id_config_errors.py (broken-config precedence and the
"add to [tool.pitloom]" hint, both unaffected by this decision).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME

_EXPECTED_ERROR = (
    "ERROR: no ID registry declared: pass --id-registry FILE or set id-registry in "
)


def _run(args: list[str]) -> int:
    parser = _build_parser()
    return _run_id_command(parser.parse_args(args))


def _assert_no_default_registry_anywhere(project_dir: Path, cwd: Path) -> None:
    assert not (project_dir / DEFAULT_ID_REGISTRY_FILENAME).exists()
    assert not (cwd / DEFAULT_ID_REGISTRY_FILENAME).exists()


# ---------------------------------------------------------------------------
# No flag, no key: exactly one ERROR line, exit 1, nothing written
# ---------------------------------------------------------------------------


def test_id_generate_no_flag_no_key_is_exact_error_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert err_lines == [_EXPECTED_ERROR + "[tool.pitloom]"]
    _assert_no_default_registry_anywhere(tmp_path, other_cwd)


def test_id_import_no_flag_no_key_is_exact_error_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["id", "import", str(sbom_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert err_lines == [_EXPECTED_ERROR + "[tool.pitloom]"]
    _assert_no_default_registry_anywhere(tmp_path, tmp_path)


def test_id_generate_no_flag_no_key_no_config_file_at_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No pyproject.toml/setup.cfg/setup.py at all -- still the same
    ERROR, not a crash and not the default-file fallback."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert err_lines == [_EXPECTED_ERROR + "[tool.pitloom]"]
    _assert_no_default_registry_anywhere(tmp_path, tmp_path)


# ---------------------------------------------------------------------------
# pyproject.toml vs setup.cfg wording
# ---------------------------------------------------------------------------


def test_id_generate_no_flag_no_key_setup_cfg_wording(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A setup.cfg-only project (no pyproject.toml) with no declared
    ``id-registry`` key: the ERROR names ``[tool:pitloom]``, not
    ``[tool.pitloom]``."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n", encoding="utf-8"
    )

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert err_lines == [_EXPECTED_ERROR + "[tool:pitloom]"]
    _assert_no_default_registry_anywhere(tmp_path, tmp_path)


def test_id_import_no_flag_no_key_setup_cfg_wording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n", encoding="utf-8"
    )
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["id", "import", str(sbom_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert err_lines == [_EXPECTED_ERROR + "[tool:pitloom]"]


# ---------------------------------------------------------------------------
# Broken config precedence: a broken project config still wins over the
# "nothing declared" ERROR (its own single ERROR: <config error> line).
# ---------------------------------------------------------------------------


def test_id_generate_broken_config_precedes_no_registry_declared_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text("not [ valid toml", encoding="utf-8")

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")
    assert "no ID registry declared" not in err_lines[0]


# ---------------------------------------------------------------------------
# Key declared -> used, no ERROR
# ---------------------------------------------------------------------------


def test_id_generate_declared_key_used_no_error(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "registry.json"\n',
        encoding="utf-8",
    )

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "registry.json").is_file()


def test_id_import_declared_key_used_no_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "registry.json"\n',
        encoding="utf-8",
    )
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["id", "import", str(sbom_path)])

    assert exit_code == 0
    assert (tmp_path / "registry.json").is_file()
