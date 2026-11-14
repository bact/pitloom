# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`loom id generate` argument errors and warnings: a missing or unreadable
PATH, a bad ``--project-dir``, a PATH named like a skipped directory, ``..``
after a symlink, ``-o -``, and a declared registry named anything.

See also: test_cli_id_path_validation.py (PATH confinement).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.core.quote_source import quote_source
from tests._symlink import CAN_SYMLINK
from tests._unreadable import POSIX_NON_ROOT


def _run(args: list[str]) -> int:
    return _run_id_command(_build_parser().parse_args(args))


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    return project


def _keys(registry: Path) -> set[str]:
    data = json.loads(registry.read_text(encoding="utf-8"))
    return set(data["elements"].get("software_File", {}))


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
@pytest.mark.parametrize("kind", ["dir", "file"])
def test_unreadable_path_argument_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    project = _project(tmp_path)
    target = project / "src" / ("locked" if kind == "dir" else "locked.txt")
    if kind == "dir":
        target.mkdir()
    else:
        target.write_text("x", encoding="utf-8")
    target.chmod(0)
    out = tmp_path / "r.json"
    try:
        code = _run(
            ["id", "generate", "--project-dir", str(project), str(target)]
            + ["-o", str(out)]
        )
    finally:
        target.chmod(0o755)

    assert code == 1
    err = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err) == 1
    said = {
        "dir": "DIR={}: could not list for ID registry indexing; Permission denied "
        "[dir-unlistable]",
        "file": "FILE={}: could not read for ID registry indexing; Permission denied "
        "[file-unreadable]",
    }[kind]
    assert err[0] == "ERROR: " + said.format(target)
    assert not out.exists()


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_project_dir_not_a_directory_is_one_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    project = _project(tmp_path)
    bad = project / "src" / "a.py" if kind == "file" else tmp_path / "nope"
    out = tmp_path / "r.json"

    code = _run(["id", "generate", "--project-dir", str(bad), "-o", str(out), "src"])

    assert code == 1
    err = [line for line in capsys.readouterr().err.splitlines() if line]
    shown = quote_source(bad.resolve())
    tail = " is not a directory" if kind == "file" else ""
    assert err == [
        f"ERROR: project directory not found: {shown}{tail} [input-not-found]"
    ]
    assert not out.exists()


@pytest.mark.parametrize("name", ["build", "dist"])
def test_explicit_path_named_like_a_skipped_directory_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    project = _project(tmp_path)
    (project / name).mkdir()
    (project / name / "b.txt").write_text("b", encoding="utf-8")
    out = tmp_path / "r.json"

    code = _run(
        ["id", "generate", "--project-dir", str(project), "-o", str(out)]
        + [str(project / name)]
    )

    assert code == 0
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert f"skipped directory name ({name})" in warnings[0]
    assert not _keys(out)


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlinks")
def test_dotdot_after_a_symlink_is_collapsed_lexically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``link/..`` is the directory above ``link`` as written (outside the
    project), not above its target (inside it)."""
    project = _project(tmp_path)
    (project / "src" / "deep").mkdir()
    os.symlink(project / "src" / "deep", tmp_path / "link")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "r.json"

    code = _run(
        ["id", "generate", "--project-dir", str(project), "link/..", "-o", str(out)]
    )

    assert code == 1
    assert "is outside --project-dir" in capsys.readouterr().err
    assert not out.exists()


def test_dash_o_dash_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _run(["id", "generate", "--project-dir", str(project), "-o", "-"])

    assert excinfo.value.code == 2
    assert not (tmp_path / "-").exists()


def test_stray_file_named_like_the_suggested_registry_is_indexed(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    (project / "src" / "loom-id-registry.json").write_text("{}", encoding="utf-8")
    out = project / "src" / "my-ids.json"

    assert _run(["id", "generate", "--project-dir", str(project), "-o", str(out)]) == 0
    assert _run(["id", "generate", "--project-dir", str(project), "-o", str(out)]) == 0

    assert _keys(out) == {"src/a.py", "src/loom-id-registry.json"}


@pytest.mark.parametrize(
    "paths",
    [["typo"], ["src", "typo"], ["typo", "typo"]],
    ids=["alone", "after-a-good-one", "twice"],
)
def test_a_missing_path_is_one_error_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    paths: list[str],
) -> None:
    """A PATH that is not there is an input not found, named as typed,
    said once; nothing is written (it was a warning, exit 0)."""
    _project(tmp_path)
    monkeypatch.chdir(tmp_path / "proj")
    out = tmp_path / "r.json"

    assert _run(["id", "generate", *paths, "-o", str(out)]) == 1

    err = [line for line in capsys.readouterr().err.splitlines() if line]
    assert err == ["ERROR: PATH not found: 'typo' [input-not-found]"]
    assert not out.exists()


def test_existing_paths_still_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory and a file PATH that are there index as before."""
    project = _project(tmp_path)
    (project / "data").mkdir()
    (project / "data" / "d.csv").write_text("a\n", encoding="utf-8")
    monkeypatch.chdir(project)
    out = tmp_path / "r.json"

    assert _run(["id", "generate", "src", "data/d.csv", "-o", str(out)]) == 0
    assert _keys(out) == {"src/a.py", "data/d.csv"}
