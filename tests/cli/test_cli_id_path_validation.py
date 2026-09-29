# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for `pitloom id generate` PATH-argument handling:

* a PATH outside ``--project-dir`` (relative or absolute) is a clean,
  single ``ERROR:`` line and exit 1 -- not a raw ``relative_to()``
  traceback from :meth:`pitloom.id_registry.IdRegistry.generate`.
* a PATH reached only through a symlink, but whose real location is
  inside ``--project-dir``, still works (the fix that closed the
  "`loom id generate` crashes on a symlinked path" roadmap item).
* an unwritable/nonexistent ``-o`` target directory is one ``ERROR:``
  line, not a raw traceback -- ``-o`` keeps its own dangling-symlink
  handling (no ``os.path.realpath``), unaffected by the PATH-argument fix.

See also: test_cli_id.py (the rest of `pitloom id`'s CLI tests),
test_cli_id_registry_required.py ("no registry declared" ERROR wording).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser


def _run(args: list[str]) -> int:
    parser = _build_parser()
    return _run_id_command(parser.parse_args(args))


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "registry.json"\n',
        encoding="utf-8",
    )
    return project


def test_id_generate_path_outside_project_dir_relative_is_clean_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "b.py").write_text("y = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = _run(["id", "generate", "--project-dir", str(project), "outside"])

    assert exit_code == 1
    err_lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: PATH ")
    assert "is outside --project-dir" in err_lines[0]
    assert not (project / "registry.json").exists()


def test_id_generate_path_outside_project_dir_absolute_is_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "b.py").write_text("y = 1\n", encoding="utf-8")

    exit_code = _run(["id", "generate", "--project-dir", str(project), str(outside)])

    assert exit_code == 1
    err_lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: PATH ")
    assert "is outside --project-dir" in err_lines[0]
    assert not (project / "registry.json").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_id_generate_symlinked_path_inside_project_works(tmp_path: Path) -> None:
    """A PATH argument reached only through a symlink, whose real
    location is inside ``--project-dir``, must succeed -- the crash this
    fix closes, not a false-positive "outside --project-dir" ERROR."""
    real_project = tmp_path / "real_proj"
    (real_project / "src").mkdir(parents=True)
    (real_project / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (real_project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[tool.pitloom]\nid-registry = "registry.json"\n',
        encoding="utf-8",
    )
    link_src = tmp_path / "linked_src"
    os.symlink(real_project / "src", link_src)

    exit_code = _run(
        ["id", "generate", "--project-dir", str(real_project), str(link_src)]
    )

    assert exit_code == 0
    assert (real_project / "registry.json").is_file()


def test_id_generate_dash_o_nonexistent_dir_is_one_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``-o`` into an unwritable/nonexistent parent (a regular file, not
    a directory) is one clean ``ERROR:`` line and exit 1, not a raw
    traceback -- ``-o`` keeps its dangling-symlink handling (no
    ``os.path.realpath``)."""
    project = _project(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    bad_target = blocker / "r.json"

    exit_code = _run(
        ["id", "generate", "--project-dir", str(project), "-o", str(bad_target)]
    )

    assert exit_code == 1
    err_lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


def test_id_import_dash_o_nonexistent_dir_is_one_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same as the `id generate` case above, for `id import`'s own
    ``registry.save()`` call."""
    _project(tmp_path)
    sbom_path = tmp_path / "external.spdx3.json"
    sbom_path.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    bad_target = blocker / "r.json"

    exit_code = _run(["id", "import", str(sbom_path), "-o", str(bad_target)])

    assert exit_code == 1
    err_lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_id_generate_in_project_symlink_to_outside_dir_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit PATH that is an in-project symlink pointing OUTSIDE
    the project (e.g. ``proj/models -> ../bigdisk/models``) must
    succeed, keyed the same way as the default-path discovery would key
    it -- lexically, under the project, not through the symlink's real
    (outside) location. This is the mirror case of
    ``test_id_generate_symlinked_path_inside_project_works`` above: here
    the symlink itself lives inside the project, but its target does
    not."""
    project = _project(tmp_path)
    outside = tmp_path / "bigdisk" / "models"
    outside.mkdir(parents=True)
    (outside / "w.bin").write_bytes(b"\x00" * 16)
    os.symlink(outside, project / "models")
    monkeypatch.chdir(project)

    exit_code = _run(["id", "generate", "--project-dir", str(project), "models"])

    assert exit_code == 0
    registry_data = json.loads((project / "registry.json").read_text(encoding="utf-8"))
    files = registry_data.get("files", {})
    assert "models/w.bin" in files


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_id_generate_with_symlinked_project_dir_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--project-dir`` itself given as a symlink: PATH resolution must
    try *both* the lexical (as-given) ``--project-dir`` and its
    ``.resolve()``d form (see :func:`pitloom.cli.id._resolve_id_generate_path`'s
    *lexical_project_dir*/*project_dir* pair), not just one -- whichever
    form the PATH argument happens to be expressed relative to.

    ``link`` is a symlink to ``project``; ``project/models`` is itself a
    symlink to an out-of-project ``bigdisk/models`` directory (so its
    only in-project identity is the lexical one, forcing a realpath
    fallback if neither base matches).

    (a) PATH given already qualified by the symlinked ``--project-dir``
    (``<link>/models``, cwd outside both) matches *lexical_project_dir*
    (``link``) directly -- this is what a
    ``for base in (project_dir,):`` mutant (dropping
    *lexical_project_dir* from the search) would miss, falling through to
    the realpath fallback and landing outside the (resolved) project,
    i.e. an ``ERROR:`` instead of exit 0.

    (b) PATH given relative to cwd inside the *real* project directory
    (``models``, cwd = ``project``) only matches *project_dir* (the
    ``.resolve()``d form) -- this is what a
    ``for base in (lexical_project_dir,):`` mutant (dropping *project_dir*
    from the search) would miss, for the same reason.

    Both must resolve to the same registry key, ``models/w.bin``.
    """
    project = _project(tmp_path)
    link = tmp_path / "link"
    os.symlink(project, link)
    outside = tmp_path / "bigdisk" / "models"
    outside.mkdir(parents=True)
    (outside / "w.bin").write_bytes(b"\x00" * 16)
    os.symlink(outside, project / "models")

    monkeypatch.chdir(tmp_path)
    registry_a = tmp_path / "r.json"
    exit_code_a = _run(
        [
            "id",
            "generate",
            "--project-dir",
            str(link),
            str(link / "models"),
            "-o",
            str(registry_a),
        ]
    )
    assert exit_code_a == 0
    files_a = json.loads(registry_a.read_text(encoding="utf-8")).get("files", {})
    assert "models/w.bin" in files_a

    monkeypatch.chdir(project)
    registry_b = tmp_path / "r2.json"
    exit_code_b = _run(
        [
            "id",
            "generate",
            "--project-dir",
            str(link),
            "models",
            "-o",
            str(registry_b),
        ]
    )
    assert exit_code_b == 0
    files_b = json.loads(registry_b.read_text(encoding="utf-8")).get("files", {})
    assert "models/w.bin" in files_b
