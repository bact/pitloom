# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for `pitloom id generate`/`pitloom id import`'s own
project-config resolution: a broken/invalid config must be one ``ERROR:``
line and exit 1 (never a traceback), a ``setup.cfg``-only project's
``[tool:pitloom] id-registry`` must be honoured the same way a
``pyproject.toml``'s is, a dangling symlink target must not be written
through, and the "add to [tool.pitloom]" hint must name the right table
and be suppressed exactly when the target is already the project's own
declared file.

See also: test_cli_id.py (the rest of `pitloom id`'s CLI tests).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser


def _run(args: list[str]) -> int:
    parser = _build_parser()
    return _run_id_command(parser.parse_args(args))


# ---------------------------------------------------------------------------
# H1: a broken/invalid project config must not crash `id generate`/`id import`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pyproject_text",
    [
        pytest.param("not [ valid toml", id="invalid-toml"),
        pytest.param(
            '[project]\nname = "demo"\n\n[tool.pitloom.ids]\nfile = "x.json"\n',
            id="moved-key",
        ),
        pytest.param(
            '[project]\nname = "demo"\n\n[tool.pitloom]\nid-registry = 123\n',
            id="wrong-typed",
        ),
    ],
)
def test_id_generate_broken_pyproject_is_one_error_line(
    tmp_path: Path,
    pyproject_text: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A broken/invalid pyproject.toml is caught and reported as exactly
    one ``ERROR:`` line, never an uncaught traceback."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


@pytest.mark.parametrize(
    "pyproject_text",
    [
        pytest.param("not [ valid toml", id="invalid-toml"),
        pytest.param(
            '[project]\nname = "demo"\n\n[tool.pitloom.ids]\nfile = "x.json"\n',
            id="moved-key",
        ),
        pytest.param(
            '[project]\nname = "demo"\n\n[tool.pitloom]\nid-registry = 123\n',
            id="wrong-typed",
        ),
    ],
)
def test_id_import_broken_pyproject_is_one_error_line(
    tmp_path: Path,
    pyproject_text: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same as above for `id import` (project dir is always cwd there)."""
    (tmp_path / "pyproject.toml").write_text(pyproject_text, encoding="utf-8")
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
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


# ---------------------------------------------------------------------------
# H1-bis: a setup.py-only project with no resolvable name (bare setup())
# must not crash `id generate`/`id import` with a FileNotFoundError
# traceback -- read_project() raises FileNotFoundError, not ValueError,
# for that case, and it must be caught the same way.
# ---------------------------------------------------------------------------


def test_id_generate_bare_setup_py_no_flag_is_one_error_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A setup.py-only project whose ``setup()`` call carries no
    resolvable name: no ``-o`` given, so the project config *must* be
    read -- the read's ``FileNotFoundError`` is caught and reported as
    one ``ERROR:`` line, never an uncaught traceback."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    err_lines = [line for line in err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


def test_id_generate_bare_setup_py_with_flag_ignores_read_failure(
    tmp_path: Path,
) -> None:
    """Same bare ``setup()`` project, but ``-o`` already names the
    target: the config read (best-effort, only used to decide whether
    the flag matches the project's own declared file) must not fail the
    run at all."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    registry_path = tmp_path / "custom-registry.json"

    exit_code = _run(
        ["id", "generate", "--project-dir", str(tmp_path), "-o", str(registry_path)]
    )

    assert exit_code == 0
    assert registry_path.is_file()


def test_id_import_bare_setup_py_no_flag_is_one_error_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same as above for `id import` (project dir is always cwd there)."""
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
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
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


def test_id_import_bare_setup_py_with_flag_ignores_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same bare ``setup()`` project for `id import`, but ``-o`` already
    names the target: the config read must not fail the run."""
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "custom-registry.json"

    exit_code = _run(["id", "import", str(sbom_path), "-o", str(registry_path)])

    assert exit_code == 0
    assert registry_path.is_file()


# ---------------------------------------------------------------------------
# LOW 3: a relative `-o` with ".." segments displays normalized, not raw
# ---------------------------------------------------------------------------


def test_id_generate_dotdot_flag_path_displays_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`-o ../registry.json`, run from a subdirectory of the project, is
    written to and reported at its normalized absolute path -- no
    literal ``..`` segment survives into the printed confirmation."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)

    exit_code = _run(
        [
            "id",
            "generate",
            "--project-dir",
            str(tmp_path),
            "-o",
            str(Path("..") / "registry.json"),
        ]
    )

    assert exit_code == 0
    expected = tmp_path / "registry.json"
    assert expected.is_file()
    out = capsys.readouterr().out
    assert ".." not in out
    assert str(expected) in out


def test_id_import_with_flag_ignores_broken_cwd_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-o`/`--id-registry` given explicitly: a broken cwd pyproject.toml
    must not fail the run at all -- the project config is never read
    when the flag already names the target."""
    (tmp_path / "pyproject.toml").write_text("not [ valid toml", encoding="utf-8")
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "custom-registry.json"

    exit_code = _run(["id", "import", str(sbom_path), "-o", str(registry_path)])

    assert exit_code == 0
    assert registry_path.is_file()


# ---------------------------------------------------------------------------
# M1: setup.cfg's [tool:pitloom] id-registry is honoured the same way
# ---------------------------------------------------------------------------


def test_id_generate_honours_setup_cfg_id_registry_key(
    tmp_path: Path,
) -> None:
    """A project with no pyproject.toml, only setup.cfg's
    ``[tool:pitloom] id-registry``, has that key honoured -- the same
    selection every other Pitloom surface (generators, hook) uses."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n\n"
        "[tool:pitloom]\nid-registry = custom/from-setup-cfg.json\n",
        encoding="utf-8",
    )

    exit_code = _run(["id", "generate", "--project-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "custom" / "from-setup-cfg.json").is_file()


def test_id_generate_setup_cfg_hint_names_setup_cfg_table(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A setup.cfg-only project with no declared id-registry key: since
    there's no key, ``-o`` must name the target explicitly (registry
    location is required everywhere); the "add a key" hint after that
    fresh write names ``[tool:pitloom]`` in ``setup.cfg``, not
    ``[tool.pitloom]`` in ``pyproject.toml``."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 0.1.0\n", encoding="utf-8"
    )
    registry_path = tmp_path / "registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            ["id", "generate", "--project-dir", str(tmp_path), "-o", str(registry_path)]
        )

    assert exit_code == 0
    assert "[tool:pitloom] in setup.cfg" in caplog.text
    assert "[tool.pitloom] in pyproject.toml" not in caplog.text


def test_id_generate_pyproject_hint_names_pyproject_table(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A pyproject.toml-configured project with no declared id-registry
    key: since there's no key, ``-o`` must name the target explicitly;
    the hint names ``[tool.pitloom]`` in ``pyproject.toml``."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    registry_path = tmp_path / "registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            ["id", "generate", "--project-dir", str(tmp_path), "-o", str(registry_path)]
        )

    assert exit_code == 0
    assert "[tool.pitloom] in pyproject.toml" in caplog.text


# ---------------------------------------------------------------------------
# L2: a dangling symlink target must be an ERROR, never written through
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_id_generate_dangling_symlink_target_is_error_not_write_through(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`-o` naming a dangling symlink is a load ERROR at the symlink's
    own path -- not silently resolved through to its (nonexistent)
    target and created there."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    link_path = tmp_path / "registry-link.json"
    missing_target = tmp_path / "nowhere" / "registry.json"
    link_path.symlink_to(missing_target)

    exit_code = _run(
        ["id", "generate", "--project-dir", str(tmp_path), "-o", str(link_path)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ERROR: ID registry file" in err
    assert "not found or not a file" in err
    # Never written through to the dangling symlink's target.
    assert not missing_target.exists()


# ---------------------------------------------------------------------------
# L3: the config hint is suppressed exactly when -o names the declared file
# ---------------------------------------------------------------------------


def test_id_generate_flag_matching_declared_key_suppresses_hint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`-o` naming exactly the project's own declared ``id-registry``
    file must not print the "add a key" hint -- it's already declared."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "custom/registry.json"\n',
        encoding="utf-8",
    )
    declared_path = tmp_path / "custom" / "registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            [
                "id",
                "generate",
                "--project-dir",
                str(tmp_path),
                "-o",
                str(declared_path),
            ]
        )

    assert exit_code == 0
    assert declared_path.is_file()
    assert "to use this registry" not in caplog.text


def test_id_generate_flag_different_from_declared_key_still_hints(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`-o` naming a *different* file than the project's own declared
    ``id-registry`` still gets the hint -- only an exact match suppresses
    it -- worded as a change of that key, never a second one."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "custom/registry.json"\n',
        encoding="utf-8",
    )
    other_path = tmp_path / "other-registry.json"

    with caplog.at_level("INFO"):
        exit_code = _run(
            ["id", "generate", "--project-dir", str(tmp_path), "-o", str(other_path)]
        )

    assert exit_code == 0
    assert other_path.is_file()
    assert (
        "to use this registry, change id-registry in [tool.pitloom] in "
        'pyproject.toml to: id-registry = "other-registry.json"'
    ) in caplog.text
    assert "add to" not in caplog.text
