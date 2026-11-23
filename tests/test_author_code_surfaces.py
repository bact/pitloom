# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The author lines carry their codes on each surface that prints them:
``loom wheel`` (the command line), ``generate_wheel_sbom`` (the library,
``pitloom_code`` on the record), and an embed with a project directory
(``metadata-conflict`` for another project, ``project-unreadable`` for
metadata that cannot be read). The hook reads ``[project].authors`` one by
one, so it prints none of them.

See also: :mod:`tests.messages.test_authors` (the lines),
:mod:`tests.test_author_surfaces` (what each route reads).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom._embed_overlay import adopt_project_authors
from pitloom.assemble import generate_wheel_sbom
from pitloom.core.project import ProjectMetadata
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import trusted_message
from tests._author_routes import CREATED, isolate, write_wheel

pytestmark = pytest.mark.platform

_METADATA = (
    "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nAuthor: Ann and Bob\n"
    "Author-email: Doe, Jane <j@x.org>, nobody@\n"
)
#: The lines that wheel prints, without the level, each with its code.
_LINES = [
    (
        "WARNING",
        "AUTHOR_EMAIL='nobody@': not an email address; not recorded",
        "author-invalid",
    ),
    (
        "WARNING",
        "AUTHOR_EMAIL='Doe, Jane <j@x.org>, nobody@': split into 3 entries on "
        "',' or ';'; an address field cannot tell a list from one name holding "
        "a comma",
        "author-ambiguous",
    ),
    (
        "INFO",
        "AUTHOR='Ann and Bob': read as one author; it may list several",
        "author-ambiguous",
    ),
]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def test_the_cli_prints_each_author_line_with_its_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = write_wheel(tmp_path, _METADATA)
    argv = ["loom", "wheel", str(wheel), "-o", str(tmp_path / "o.json"), "--offline"]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 0
    err = capsys.readouterr().err.splitlines()
    for level, text, code in _LINES:
        line = f"{level}: {text} [{code}]"
        assert line in err, err
        assert trusted_message(line) is not None


def test_the_library_puts_the_code_on_each_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_wheel(tmp_path, _METADATA)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        generate_wheel_sbom(wheel, creation_metadata=CREATED, offline=True)
    said = {
        (r.levelname, r.getMessage(), getattr(r, CODE_ATTR, None))
        for r in caplog.records
    }
    assert set(_LINES) <= said


@pytest.mark.parametrize(
    ("pyproject", "text", "code"),
    [
        (
            '[project]\nname = "other"\nversion = "1"\nauthors = [{name = "A"}]\n',
            "DIR=proj: names project 'other', not the wheel's 'demo'; authors "
            "from the wheel METADATA",
            "metadata-conflict",
        ),
        (
            "[project\n",
            "DIR=proj: project metadata not read; authors from the wheel "
            "METADATA; FILE=",
            "project-unreadable",
        ),
    ],
    ids=["other-project", "unreadable"],
)
def test_an_embed_project_not_used_for_authors_is_coded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    pyproject: str,
    text: str,
    code: str,
) -> None:
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    metadata = ProjectMetadata(name="demo", authors=[{"name": "W"}])
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert not adopt_project_authors(metadata, Path("proj"))
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record.getMessage().startswith(text)
    assert getattr(record, CODE_ATTR) == code
    printed = f"WARNING: {record.getMessage()} [{code}]"
    assert trusted_message(printed) is not None
    assert metadata.authors == [{"name": "W"}]
