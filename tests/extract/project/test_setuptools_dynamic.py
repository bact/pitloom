# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``dependencies`` and ``optional-dependencies`` from requirements files
named in ``[tool.setuptools.dynamic]``, as the wheel setuptools builds lists
them.

See also: tests/extract/project/test_optional_dependencies.py (static
extras) and tests/extract/project/test_real_world_extras.py (dinglehopper).
"""

from __future__ import annotations

import email
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.extract.project import _requirements_files, read_project
from pitloom.extract.project._requirements_files import requirements_and_options
from tests._setuptools_build import run_build
from tests._symlink import CAN_SYMLINK, case_sensitive

_DYN = "tool.setuptools.dynamic"
_BACKEND = '[build-system]\nbuild-backend = "setuptools.build_meta"\n'


@pytest.mark.parametrize(
    ("text", "requirements", "options"),
    [
        ("", [], []),
        ("# c\n\n  a\n  # x\nb  # why\nu#frag\n", ["a", "b", "u#frag"], []),
        ("a\r\nb\r\n", ["a", "b"], []),
        ("﻿a\n", ["﻿a"], []),
        ("x; python_version < '3.11'\n", ["x; python_version < '3.11'"], []),
        ("not a req !!\n", ["not a req !!"], []),
        ("-r o\n-e .\n--index-url=https://u@h\nc", ["c"], ["-r", "-e", "--index-url"]),
        ("six \\\n  >=1\n", ["six>=1"], []),
        ("six\\\n>=1\n", ["si>=1"], []),
        ("a\nb \\\n", ["a"], []),
    ],
    ids=["empty", "comments", "crlf", "bom", "marker", "invalid", "options",
         "continued", "continued-quirk", "continued-at-end"],
)  # fmt: skip
def test_requirements_and_options(
    text: str, requirements: list[str], options: list[str]
) -> None:
    """Lines split as setuptools splits them: see each id."""
    assert requirements_and_options(text) == (requirements, options)


def _project(
    root: Path, dynamic: str, table: str, files: dict[str, bytes], head: str = ""
) -> Path:
    """A project directory ``root/p`` with *files* in it."""
    project = root / "p"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        f"{head or _BACKEND}[project]\n"
        f'name = "demo"\nversion = "1"\ndynamic = [{dynamic}]\n'
        f"[{_DYN}]\n{table}",
        encoding="utf-8",
    )
    for name, data in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return project


_D = '"dependencies"'
_O = '"optional-dependencies"'
_DEPS = f"Field: {_DYN}.dependencies"
_OPTS = f"Field: {_DYN}.optional-dependencies"
_SIX = {"a.txt": b"six\n"}
_POSIX = sys.platform != "win32"
_INVALID = {"a.txt": b"!!\n\xef\xbb\xbfsix\nc\n"}

#: (dynamic, table, files, dependencies, provenance, warning; None = no
#: provenance / no WARNING)
_ROWS: list[Any] = [
    pytest.param(
        _O, 'optional-dependencies.X = {file = "x.txt"}\n', {"x.txt": b"np\n"},
        ['np; extra == "x"'], _OPTS, None, id="extra-file-str",
    ),
    pytest.param(
        f"{_D}, {_O}",
        'dependencies = {file = ["a.txt", "b.txt"]}\n'
        "optional-dependencies.x = {file = []}\n",
        {"a.txt": b"six", "b.txt": b"attrs\n"},
        ["six", "attrs"], f"{_DEPS}, {_DYN}.optional", None, id="deps-file-list",
    ),
    pytest.param(
        _D, 'dependencies = {file = ["gone.txt", "a.txt", "./gone.txt"]}\n', _SIX,
        ["six"], _DEPS,
        f"FILE=gone.txt: could not read for {_DYN}.dependencies; not found",
        id="missing-listed-twice",
    ),
    pytest.param(
        _D, 'dependencies = {file = "sub"}\n', {"sub/a.txt": b"six\n"}, [],
        _DEPS, "not a regular file", id="directory",
    ),
    pytest.param(
        _D, 'dependencies = {file = "../out.txt"}\n', {}, [], _DEPS,
        "FILE=../out.txt: could not read for tool.setuptools.dynamic.dependencies;"
        " outside the project directory",
        id="dotdot-escape",
    ),
    pytest.param(
        _D, 'dependencies = {file = "a\\u0000.txt"}\n', _SIX, [], _DEPS,
        f"could not read for {_DYN}.dependencies", id="nul-in-name",
    ),
    pytest.param(
        _D, 'dependencies = {file = "s/../a.txt"}\n', {**_SIX, "s/k": b""}, ["six"],
        _DEPS, None, id="dotdot-inside",
    ),
    # The OS decides `..` at the open, as for setuptools: POSIX needs `s`
    # to exist, Win32 collapses `s/..` first.
    pytest.param(
        _D, 'dependencies = {file = "s/../a.txt"}\n', _SIX,
        [] if _POSIX else ["six"], _DEPS,
        f"FILE=s/../a.txt: could not read for {_DYN}.dependencies; not found"
        if _POSIX else None,
        id="dotdot-missing-dir",
    ),
    # Regression: read-once was keyed by resolved path, so the extra was
    # served `a.txt`'s text although `missing/..` cannot be opened.
    pytest.param(
        f"{_D}, {_O}",
        'dependencies = {file = "a.txt"}\n'
        'optional-dependencies.x = {file = "missing/../a.txt"}\n',
        _SIX, ["six"] + ([] if _POSIX else ['six; extra == "x"']),
        f"{_DEPS}, {_DYN}.optional",
        f"FILE=missing/../a.txt: could not read for {_DYN}.optional-dependencies.x;"
        " not found" if _POSIX else None,
        id="dotdot-missing-dir-after-read",
    ),
    pytest.param(
        _D, 'dependencies = {file = "a.txt"}\n', {"a.txt": b"six\xff\n"}, [],
        _DEPS, "not UTF-8", id="non-utf8",
    ),
    pytest.param(
        _D, 'dependencies = {file = "a.txt"}\n',
        {"a.txt": b"a\n" * (512 * 1024) + b"b"}, [], _DEPS,
        "FILE=a.txt: larger than the 1048576-byte requirements-file cap; skipped",
        id="oversize",
    ),
    pytest.param(
        _D, 'dependencies = {file = "a.txt"}\n', {"a.txt": b""}, [], _DEPS, None,
        id="empty-file",
    ),
    # Read once, as resolved (setuptools reads it each time).
    pytest.param(
        _D, 'dependencies = {file = ["a.txt", "./a.txt", "s/../a.txt", "a.txt"]}\n',
        {**_SIX, "s/k": b""}, ["six"], _DEPS, None, id="listed-again",
    ),
    pytest.param(
        _D, 'dependencies = {file = "a.txt"}\n', {"a.txt": b"-r b.txt\n-e .\nc\n"},
        ["c"], _DEPS,
        f"skipping pip option line(s) -r, -e in {_DYN}.dependencies", id="options",
    ),
    pytest.param(
        _O, 'optional-dependencies.x = {file = "a.txt"}\n', {"a.txt": b"!!\nc\n"},
        ['c; extra == "x"'], _OPTS,
        f"Skipping extra entry '!!' of 'x' ({_DYN}.optional-dependencies)",
        id="invalid-extra-line",
    ),
    pytest.param(
        _O, 'optional-dependencies.x = {file = "a.txt"}\n',
        {"a.txt": b"\xef\xbb\xbfsix\nc\n"}, ['c; extra == "x"'], _OPTS,
        "Skipping extra entry '\\ufeffsix' of 'x'", id="bom-extra-line",
    ),
    # Skipped as an extra's (setuptools fails the build on it).
    pytest.param(
        _D, 'dependencies = {file = "a.txt"}\n', {"a.txt": b"!!\nc\n"}, ["c"],
        _DEPS,
        f"Skipping dependency '!!' ({_DYN}.dependencies): not a valid PEP 508",
        id="invalid-line-skipped",
    ),
    pytest.param(
        _D, 'dependencies = {attr = "pkg.X"}\n', {}, [], None,
        "has 'attr', not supported", id="attr",
    ),
    pytest.param(
        _D, 'dependencies = "a.txt"\n', _SIX, [], None,
        "is not a table with 'file'", id="not-a-table",
    ),
    pytest.param(
        _D, "dependencies = {file = 3}\n", {}, [], None, "has 'file' int",
        id="file-int",
    ),
    pytest.param(
        _O, 'optional-dependencies = "a.txt"\n', _SIX, [], None,
        "is str, expected table", id="extras-not-a-table",
    ),
    pytest.param(
        _D, "", {}, [], None, None, id="no-key",
    ),
    pytest.param(
        "", 'dependencies = {file = "a.txt"}\n', _SIX, [], None, None,
        id="not-listed-in-dynamic",
    ),
]  # fmt: skip


@pytest.mark.parametrize(
    ("dynamic", "table", "files", "deps", "prov", "warning"), _ROWS
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_read_project_dynamic_dependencies(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    dynamic: str,
    table: str,
    files: dict[str, bytes],
    deps: list[str],
    prov: str | None,
    warning: str | None,
) -> None:
    """Each row: the dependencies read, the provenance field credited and
    the one ``WARNING:`` (or none)."""
    (tmp_path / "out.txt").write_bytes(b"leak\n")
    project = _project(tmp_path, dynamic, table, files)

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == deps
    if prov is None:
        assert "dependencies" not in metadata.provenance
    else:
        assert prov in metadata.provenance["dependencies"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == (warning is not None)
    assert all((warning or "") in w for w in warnings)


def test_invalid_dependency_line_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """End to end, an invalid line (here also a BOM-prefixed one) of a
    ``dependencies`` file gets exactly one ``WARNING:`` naming it: skipped
    when read, never reaching assembly."""
    project = _project(tmp_path, _D, 'dependencies = {file = "a.txt"}\n', _INVALID)

    with caplog.at_level(logging.WARNING):
        generate_project_sbom(project, offline=True)

    for line in ("'!!'", "'\\ufeffsix'"):
        assert [m for m in caplog.messages if line in m] == [
            f"Skipping dependency {line} ({_DYN}.dependencies): not a valid PEP 508"
            " requirement"
        ], line


def test_absolute_path_is_not_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An absolute path (built at run time, so it has a drive on Windows)
    is outside the project directory too."""
    outside = tmp_path / "out.txt"
    outside.write_bytes(b"leak\n")
    project = _project(tmp_path, _D, f"dependencies = {{file = '{outside}'}}\n", {})

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == []
    assert "outside the project directory" in caplog.text


@pytest.mark.parametrize(
    ("head", "read"),
    [
        ("", True),
        ('[build-system]\nrequires = ["setuptools"]\n', True),
        ('[build-system]\nbuild-backend = "hatchling.build"\n', False),
    ],
    ids=["no-build-system", "no-backend", "hatchling"],
)
def test_only_setuptools_reads_the_table(tmp_path: Path, head: str, read: bool) -> None:
    """No ``build-backend`` means setuptools (PEP 517); another backend
    does not read ``[tool.setuptools.dynamic]``."""
    project = _project(
        tmp_path, _D, 'dependencies = {file = "a.txt"}\n', _SIX, head=head or "\n"
    )

    metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == (["six"] if read else [])


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symlink")
@pytest.mark.parametrize(
    ("target", "deps", "why"),
    [("p/real/a.txt", ["six"], ""), ("P/real/a.txt", ["six"], ""),
     ("out.txt", [], "outside the project directory"),
     ("gone/x.txt", [], "not found")],
    ids=["inside", "inside-other-case", "outside", "dangling-outside"],
)  # fmt: skip
def test_a_symlink_is_read_only_inside_the_project(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    target: str,
    deps: list[str],
    why: str,
) -> None:
    """As for a licence source: read through a symlink only when it
    resolves inside the project, by identity too (a case-insensitive file
    system spells the project two ways); one out of it is not read, with
    one ``WARNING:`` (a dangling one is not found, as the open says)."""
    project = _project(
        tmp_path, _D, 'dependencies = {file = "l.txt"}\n', {"real/a.txt": b"six\n"}
    )
    if target.startswith("P/") and case_sensitive(tmp_path):
        pytest.skip("file system is case-sensitive")
    (tmp_path / "out.txt").write_bytes(b"leak\n")
    (project / "l.txt").symlink_to(tmp_path / target)

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == deps
    assert caplog.messages == (
        [f"FILE=l.txt: could not read for {_DYN}.dependencies; {why}"] if why else []
    )


def test_a_file_over_its_cap_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a file over the size cap warned once per directive
    listing it, without naming one. Now once per resolved file and run
    (here listed by two directives, spelt two ways, the project read
    twice after a quiet read), naming the first directive."""
    monkeypatch.setattr(_requirements_files, "MAX_REQUIREMENTS_FILE_BYTES", 3)
    project = _project(
        tmp_path,
        f"{_D}, {_O}",
        'dependencies = {file = ["big.txt", "./big.txt"]}\n'
        'optional-dependencies.x = {file = ["s/../big.txt"]}\n',
        {"big.txt": b"six\n", "s/k": b""},
    )

    with caplog.at_level(logging.WARNING):
        read_project(project, include_locked_dependencies=False, quiet=True)
        metadata = read_project(project, include_locked_dependencies=False)[0]
        read_project(project, include_locked_dependencies=False)

    assert metadata.dependencies == []
    assert caplog.messages == [
        "FILE=big.txt: larger than the 3-byte requirements-file cap;"
        f" skipped for {_DYN}.dependencies"
    ]


_TOTAL_TABLE = (
    'dependencies = {file = ["a.txt", "b.txt", "c.txt"]}\n'
    'optional-dependencies.x = {file = "a.txt"}\n'
)


@pytest.mark.parametrize(
    ("total", "read", "skipped"),
    [
        (16, ["six", "attrs", "c", 'six; extra == "x"'], 0),
        (15, ["six", "attrs", "c"], 1),
        (10, ["six", "attrs"], 2),
        (9, ["six"], 3),
    ],
    ids=["all", "extra-over", "at-total", "stops-at-first-over"],
)
def test_total_cap_stops_reading(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    total: int,
    read: list[str],
    skipped: int,
) -> None:
    """Regression: only each file was capped, so a table listing one file
    600 times held it 600 times (4.8 GB). The files of the table (4, 6 and
    2 bytes, then the first again for the extra, counted again) are read
    while the total is within the cap: one over it stops the reading, with
    one ``WARNING:`` counting the files not read; *c* would still fit."""
    monkeypatch.setattr(_requirements_files, "MAX_REQUIREMENTS_TOTAL_BYTES", total)
    project = _project(
        tmp_path,
        f"{_D}, {_O}",
        _TOTAL_TABLE,
        {"a.txt": b"six\n", "b.txt": b"attrs\n", "c.txt": b"c\n"},
    )

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == read
    assert caplog.messages == (
        [
            f"FIELD={_DYN}: larger than the {total}-byte requirements-file total"
            f" cap; {skipped} file(s) listed not read"
        ]
        if skipped
        else []
    )


_NASTY = "x\n::error::\x1b[31m"


@pytest.mark.parametrize(
    ("directive", "files", "about"),
    [
        ('{attr = "p.X"}', {}, "has 'attr'"),
        ('{file = "a.txt"}', {"a.txt": b"-r b.txt\n"}, "skipping pip option"),
        ('{file = "gone.txt"}', {}, "FILE=gone.txt: could not read"),
    ],
    ids=["ignored", "options", "unreadable"],
)
def test_extra_name_is_escaped_in_warnings(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    directive: str,
    files: dict[str, bytes],
    about: str,
) -> None:
    """Regression: an extra's name went into the ``WARNING:`` as written,
    so a newline in it forged a second line (``::error::`` a CI annotation)."""
    table = f'optional-dependencies."x\\n::error::\\u001b[31m" = {directive}\n'
    project = _project(tmp_path, _O, table, files)

    with caplog.at_level(logging.WARNING):
        read_project(project, include_locked_dependencies=False)

    (message,) = caplog.messages
    assert about in message
    assert "\n" not in message
    assert "\x1b" not in message
    assert repr(_NASTY)[1:-1] in message


def test_quiet_silences_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """*quiet* (the second read of a peek-then-reread) logs nothing."""
    project = _project(
        tmp_path,
        f"{_D}, {_O}",
        'dependencies = {file = ["gone.txt", "a.txt"]}\n'
        'optional-dependencies.x = {attr = "p.X"}\n',
        {"a.txt": b"-r b.txt\n!!\n"},
    )

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False, quiet=True)[
            0
        ]

    assert not metadata.dependencies
    assert not caplog.records


_BUILT_TABLE = (
    'dependencies = {file = ["req.txt", "req-extra.txt"]}\n'
    'optional-dependencies.cli = {file = "cli.txt"}\n'
    'optional-dependencies.test = {file = ["test.txt"]}\n'
)
_BUILT_FILES = {
    "req.txt": b"# base\r\nrequests>=2  # why\r\n\r\nclick; python_version<'3.11'",
    "req-extra.txt": b"six \\\n  >=1\n",
    "cli.txt": b"rich\n",
    "test.txt": b"pytest>=8; sys_platform != 'win32'\n",
    "pkg/__init__.py": b"",
}


def test_matches_setuptools_built_metadata(tmp_path: Path) -> None:
    """Drift guard: the directory read lists the ``Requires-Dist`` that
    setuptools writes for the same project (built offline, in a child)."""
    project = _project(
        tmp_path, f"{_D}, {_O}", _BUILT_TABLE, _BUILT_FILES,
        head=_BACKEND + '[tool.setuptools]\npackages = ["pkg"]\n',
    )  # fmt: skip
    out = tmp_path / "out"
    out.mkdir()
    build = (
        "import sys, setuptools.build_meta as b;"
        " print(b.prepare_metadata_for_build_wheel(sys.argv[1]))"
    )
    run_build(["-c", build, str(out)], cwd=project)
    built = email.message_from_bytes(
        next(out.glob("*.dist-info/METADATA")).read_bytes()
    ).get_all("Requires-Dist")

    metadata = read_project(project, include_locked_dependencies=False)[0]

    assert len(built or []) == 5
    assert metadata.dependencies == built
