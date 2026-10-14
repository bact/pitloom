# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""When an author split is warned about, on every surface: once per
document for its dependencies, and by ``embed-wheel`` only when the wheel's
authors (or the project's that replace them) are used; the same for the
``INFO:`` that a name field read as one author may list several.

See also: tests/test_author_split_surfaces.py (what each surface reads).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3._document_deployed import build_deployed
from pitloom.assemble.spdx3.document import build
from pitloom.core.config import PitloomConfig
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.embed import embed_wheel_sbom
from pitloom.extract.authors import AuthorSplit, warn_author_splits
from pitloom.extract.project.sdist import read_sdist
from tests._author_routes import (
    CORE_HINT,
    CREATED,
    ONE_AUTHOR_LINE,
    SPLIT_MARK,
    core_headers,
    isolate,
    one_author_lines,
    write_wheel,
)
from tests.assemble.conftest import _FakeMetadata, _make_sdist


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _stub_split_authors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every installed dependency *x* has the ``Author-email`` ``x One, x Two``."""
    monkeypatch.setattr(
        deps_installed,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author-email": f"{name} One, {name} Two"}),
    )


def _split_document(_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _stub_split_authors(monkeypatch)
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0", dependencies=["a", "b"]),
        creation_metadata=CREATED,
    )
    return build(doc, offline=True)


def _split_environment(_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _stub_split_authors(monkeypatch)
    tree = [
        {"package": {"key": k, "package_name": k, "installed_version": "1"}}
        for k in ("a", "b")
    ]
    doc = DocumentModel(
        project=ProjectMetadata(name="env", version="1"), creation_metadata=CREATED
    )
    return build_deployed(doc, tree, offline=True)


@pytest.mark.parametrize(
    "run", [_split_document, _split_environment], ids=["project", "environment"]
)
def test_dependency_splits_warn_once_per_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    run: Callable[[Path, pytest.MonkeyPatch], Any],
) -> None:
    with caplog.at_level(logging.WARNING):
        run(tmp_path, monkeypatch)
    (line,) = [m for m in caplog.messages if SPLIT_MARK in m]
    assert line.startswith("AUTHOR_EMAIL='a One, a Two': split into 2 entries")
    assert "2 dependencies split in all" in line


_PROJECT_WITH_AUTHORS = {
    "pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n'
    'authors = [{name = "Ann Lee"}, {name = "Bob Ray"}]\n'
}
#: A project whose own free-text address field splits.
_SPLIT_SETUP_CFG = {
    "setup.cfg": "[metadata]\nname = demo\nversion = 1.0\n"
    "author_email = Ann Lee, Bob Ray\n"
}


def _embed(
    tmp_path: Path,
    project: dict[str, str] | None,
    *,
    cli: bool = False,
    config: bool = False,
) -> None:
    """Embed into a wheel whose ``Author-email`` splits, from *project* (file name
    to text) if given; *config*: an explicit config replaces the
    project's."""
    wheel = write_wheel(tmp_path, core_headers(None, "Ann Lee, Bob Ray"))
    project_dir = None
    if project is not None:
        project_dir = tmp_path / "project"
        (project_dir / "demo").mkdir(parents=True)
        (project_dir / "demo" / "__init__.py").write_text("", encoding="utf-8")
        for name, text in project.items():
            (project_dir / name).write_text(text, encoding="utf-8")
    config_file = tmp_path / "config.toml"
    config_file.write_text("[tool.pitloom]\n", encoding="utf-8")
    if not cli:
        embed_wheel_sbom(
            wheel,
            project_dir=project_dir,
            creation_metadata=CREATED,
            pitloom_config=PitloomConfig() if config else None,
        )
        return
    argv = ["loom", "embed-wheel", str(wheel)]
    argv += [] if project_dir is None else ["--project-dir", str(project_dir)]
    argv += ["--config", str(config_file)] if config else []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", argv)
        assert __main__.main() == 0


_NO_AUTHORS = {"pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n'}
_OTHER = {
    "pyproject.toml": _PROJECT_WITH_AUTHORS["pyproject.toml"].replace("demo", "x")
}


@pytest.mark.parametrize(
    ("project", "cli", "config", "warnings"),
    [
        (_PROJECT_WITH_AUTHORS, False, False, 0),
        (_PROJECT_WITH_AUTHORS, True, False, 0),
        (_NO_AUTHORS, False, False, 1),
        (_OTHER, False, False, 1),
        (None, False, False, 1),
        (None, True, False, 1),
        # the project's own authors split: one warning, config given or not
        (_SPLIT_SETUP_CFG, False, False, 1),
        (_SPLIT_SETUP_CFG, False, True, 1),
        (_SPLIT_SETUP_CFG, True, False, 1),
        (_SPLIT_SETUP_CFG, True, True, 1),
    ],
    ids=[
        "lib-replaced",
        "cli-replaced",
        "project-without-authors",
        "other-project",
        "lib-standalone",
        "cli-standalone",
        "lib-project-split",
        "lib-project-split-config",
        "cli-project-split",
        "cli-project-split-config",
    ],
)
def test_embed_wheel_warns_only_when_wheel_authors_used(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    project: dict[str, str] | None,
    cli: bool,
    config: bool,
    warnings: int,
) -> None:
    """A split is warned about once, by the read whose authors are used:
    the wheel's, or the project's that replace them."""
    _embed(tmp_path, project, cli=cli, config=config)
    err = capsys.readouterr().err
    assert err.count(SPLIT_MARK) == warnings


def test_embed_wheel_batch_warns_project_split_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every wheel of a batch adopts the project's authors; their split is
    warned about once for the batch."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "setup.cfg").write_text(
        _SPLIT_SETUP_CFG["setup.cfg"], encoding="utf-8"
    )
    wheels = [
        str(write_wheel(tmp_path, core_headers(None, "Ann Lee, Bob Ray"), version))
        for version in ("1.0", "2.0")
    ]
    argv = ["loom", "embed-wheel", *wheels, "--project-dir", str(project_dir)]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", argv)
        assert __main__.main() == 0
    assert capsys.readouterr().err.count(SPLIT_MARK) == 1


def test_embed_external_sbom_does_not_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An embedded external SBOM does not use the wheel's authors."""
    wheel = write_wheel(tmp_path, core_headers(None, "Ann Lee, Bob Ray"))
    sbom = tmp_path / "sbom.spdx3.json"
    sbom.write_text(
        generate_wheel_sbom(wheel, creation_metadata=CREATED), encoding="utf-8"
    )
    capsys.readouterr()
    embed_wheel_sbom(wheel, sbom_path=sbom)
    assert SPLIT_MARK not in capsys.readouterr().err


def test_one_author_info_once_per_field(caplog: pytest.LogCaptureFixture) -> None:
    """One ``INFO:`` for the name fields read as one author, each field
    once however often read, after the split ``WARNING:``; none when
    quiet."""
    one = AuthorSplit("Ann, Bob", 1, "AUTHOR", True)
    other = AuthorSplit("Cy and Di", 1, "AUTHOR", True)
    cut = AuthorSplit("E <e@x.org>; F <f@x.org>", 2, "AUTHOR", True)
    with caplog.at_level(logging.INFO):
        warn_author_splits([one, cut, one, other], hint="")
        warn_author_splits([one], quiet=True, hint="")
    levels = [record.levelno for record in caplog.records]
    assert levels == [logging.WARNING, logging.INFO]
    assert SPLIT_MARK in caplog.messages[0]
    shown = "['Ann, Bob', 'Cy and Di']"
    assert caplog.messages[1] == ONE_AUTHOR_LINE.format(shown, "")


@pytest.mark.parametrize(
    ("pyproject_tail", "lines"),
    [("", 1), ('authors = [{name = "Ann"}]\n', 0)],
    ids=["pkg-info-used", "pkg-info-discarded"],
)
def test_sdist_one_author_info_only_when_pkg_info_used(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pyproject_tail: str, lines: int
) -> None:
    """An sdist whose ``pyproject.toml`` declares authors discards the
    ``PKG-INFO`` reading, quietly."""
    pkg_info = core_headers("Ann, Bob", None).encode()
    sdist = _make_sdist(tmp_path, pyproject_tail, members={"PKG-INFO": pkg_info})
    with caplog.at_level(logging.INFO):
        read_sdist(sdist)
    assert len(one_author_lines(caplog)) == lines


def _run(argv: list[str]) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", ["loom", *argv])
        assert __main__.main() == 0


@pytest.mark.parametrize(
    ("project", "lines"),
    [(None, 1), (_PROJECT_WITH_AUTHORS, 0)],
    ids=["standalone", "project-authors"],
)
def test_cli_one_author_info_on_stderr_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    project: dict[str, str] | None,
    lines: int,
) -> None:
    """``loom wheel -o -`` keeps stdout the SBOM, the ``INFO:`` once on
    stderr; ``embed-wheel`` gives it only when the wheel's authors are
    used, ``verify-wheel`` never."""
    wheel = write_wheel(tmp_path, core_headers("Ann and Bob", None))
    _run(["wheel", str(wheel), "-o", "-"])
    out, err = capsys.readouterr()
    assert json.loads(out)["@graph"]
    line = "INFO: " + ONE_AUTHOR_LINE.format("'Ann and Bob'", CORE_HINT)
    assert err.splitlines().count(line) == 1
    argv = ["embed-wheel", str(wheel)]
    if project is not None:
        (tmp_path / "project").mkdir()
        for name, text in project.items():
            (tmp_path / "project" / name).write_text(text, encoding="utf-8")
        argv += ["--project-dir", str(tmp_path / "project")]
    _run(argv)
    assert capsys.readouterr().err.splitlines().count(line) == lines
    _run(["verify-wheel", str(wheel)])
    assert "read as one author" not in capsys.readouterr().err
