# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg``'s ``file:`` directive in ``install_requires`` and
``[options.extras_require]``, read by the reader of
``[tool.setuptools.dynamic]``'s files, and a ``[project]`` whose
``dynamic`` dependency fields setuptools fills from ``setup.cfg`` or
``setup.py``.

See also: tests/extract/project/test_setuptools_dynamic.py (the same
reader under ``pyproject.toml``) and
tests/test_requirements_file_surfaces.py (every route).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.project import _requirements_files, read_project
from tests._symlink import CAN_SYMLINK

_HEAD = "[metadata]\nname = demo\nversion = 1\n"
_REQ = "Source: setup.cfg | Field: options.install_requires"
_EXTRAS = "Source: setup.cfg | Field: options.extras_require"
_FOR = "could not read for options.install_requires"


def _project(root: Path, files: dict[str, str | bytes]) -> Path:
    """A project directory ``root/p`` with *files* in it."""
    project = root / "p"
    project.mkdir()
    for name, data in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
    return project


def _cfg(options: str, extras: str = "") -> str:
    text = f"{_HEAD}[options]\n{options}"
    return text + (f"[options.extras_require]\n{extras}" if extras else "")


#: (setup.cfg, files, dependencies, provenance, warning; None = none)
_ROWS: list[Any] = [
    pytest.param(
        _cfg("install_requires = file: r.txt\n"),
        {"r.txt": "Foo_Bar>=1\n# c\nbaz ; python_version>'3'  # why\n"},
        ["Foo_Bar>=1", "baz ; python_version>'3'"], _REQ, None, id="install",
    ),
    pytest.param(
        _cfg("", "dev = file: d.txt\n"), {"d.txt": "pytest\n"},
        ['pytest; extra == "dev"'], _EXTRAS, None, id="extra",
    ),
    pytest.param(
        _cfg("install_requires = file:a.txt, ,b.txt\n"),
        {"a.txt": "foo", "b.txt": "bar\r\n"}, ["foo", "bar"], _REQ, None,
        id="two-files-crlf",
    ),
    pytest.param(
        _cfg("install_requires =\n    file: a.txt,\n    b.txt\n"),
        {"a.txt": "foo\n", "b.txt": "bar\n"}, ["foo", "bar"], _REQ, None,
        id="wrapped",
    ),
    pytest.param(
        _cfg("install_requires = file: a.txt\n"),
        {"a.txt": "foo; python_version>'3'"}, ["foo"], _REQ,
        "Skipping dependency \"python_version>'3'\" (options.install_requires)",
        id="one-line-split-on-semicolon",
    ),
    pytest.param(
        _cfg("install_requires = file: gone.txt\n"), {}, [], _REQ,
        f"FILE=gone.txt: {_FOR}; not found", id="missing",
    ),
    pytest.param(
        _cfg("install_requires = file: ../out.txt\n"), {}, [], _REQ,
        f"FILE=../out.txt: {_FOR}; outside the project directory", id="dotdot",
    ),
    pytest.param(
        _cfg("install_requires = file: a.txt\n"),
        {"a.txt": b"\xef\xbb\xbfsix\nc\n"}, ["six", "c"], _REQ, None,
        id="bom",
    ),
    pytest.param(
        _cfg("install_requires = file: a.txt\n"), {"a.txt": "-r b.txt\nc\n"},
        ["c"], _REQ,
        "setup.cfg: skipping pip option line(s) -r in options.install_requires",
        id="pip-option",
    ),
    pytest.param(
        _cfg("install_requires = file: a.txt\n"),
        {"a.txt": b"a\n" * (512 * 1024) + b"b"}, [], _REQ,
        "FILE=a.txt: larger than the 1048576-byte requirements-file cap;"
        " skipped for options.install_requires",
        id="over-cap",
    ),
    pytest.param(
        _cfg("", "dev = file: d.txt\n"), {"d.txt": "!!\nc\n"},
        ['c; extra == "dev"'], _EXTRAS,
        "Skipping extra entry '!!' of 'dev' (extras_require)", id="extra-invalid",
    ),
    pytest.param(
        _cfg("install_requires = attr: demo.X\n"), {}, [], _REQ,
        "Skipping dependency 'attr: demo.X' (options.install_requires)",
        id="attr-is-no-directive",
    ),
]  # fmt: skip


@pytest.mark.parametrize(("cfg", "files", "deps", "prov", "warning"), _ROWS)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_setup_cfg_file_directive(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    cfg: str,
    files: dict[str, str | bytes],
    deps: list[str],
    prov: str,
    warning: str | None,
) -> None:
    """Regression: ``file: r.txt`` was a dependency named ``file: r.txt``.
    Each row: the dependencies read as setuptools reads them, the
    provenance and the one ``WARNING:`` (or none)."""
    (tmp_path / "out.txt").write_bytes(b"leak\n")
    project = _project(tmp_path, {"setup.cfg": cfg, **files})

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == deps
    assert metadata.provenance["dependencies"] == prov
    assert len(caplog.messages) == (warning is not None)
    assert all((warning or "") in m for m in caplog.messages)


def test_absolute_and_symlinked_paths_are_not_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An absolute path (built at run time: a drive on Windows) and a
    symlink out of the project are outside it: not read, one ``WARNING:``
    each."""
    outside = tmp_path / "out.txt"
    outside.write_bytes(b"leak\n")
    names = [str(outside)] + (["l.txt"] if CAN_SYMLINK else [])
    project = _project(
        tmp_path, {"setup.cfg": _cfg(f"install_requires = file: {', '.join(names)}\n")}
    )
    if CAN_SYMLINK:
        (project / "l.txt").symlink_to(outside)

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == []
    assert len(caplog.messages) == len(names)
    assert all("outside the project directory" in m for m in caplog.messages)


def test_one_reader_for_the_whole_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``install_requires`` and every extra share one total cap (here 9
    bytes: ``a.txt`` twice, 4 + 4, then ``b.txt`` is one over it), with
    one ``WARNING:``; the files read are the declared dependency files."""
    monkeypatch.setattr(_requirements_files, "MAX_REQUIREMENTS_TOTAL_BYTES", 9)
    cfg = _cfg("install_requires = file: a.txt\n", "x = file: a.txt, b.txt\n")
    project = _project(tmp_path, {"setup.cfg": cfg, "a.txt": "six\n", "b.txt": "c\n"})

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == ["six", 'six; extra == "x"']
    assert metadata.dependency_files == ["a.txt"]
    assert caplog.messages == [
        "FIELD=options: larger than the 9-byte requirements-file total cap;"
        " 1 file(s) listed not read"
    ]


def test_requirements_file_is_not_also_a_lock(tmp_path: Path) -> None:
    """Regression: ``file: requirements.txt`` was not read, so the same
    pinned file was also taken as the project's lock."""
    project = _project(
        tmp_path,
        {
            "setup.cfg": _cfg("install_requires = file: requirements.txt\n"),
            "requirements.txt": "six==1.16.0\n",
        },
    )

    metadata = read_project(project)[0]

    assert metadata.dependencies == ["six==1.16.0"]
    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance


def test_quiet_silences_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """*quiet* (the second read of a peek-then-reread) logs nothing."""
    cfg = _cfg("install_requires = file: gone.txt, a.txt\n", "x = file: a.txt\n")
    project = _project(tmp_path, {"setup.cfg": cfg, "a.txt": "-r b.txt\n!!\n"})

    with caplog.at_level(logging.WARNING):
        metadata = read_project(project, include_locked_dependencies=False, quiet=True)

    assert metadata[0].dependencies == []
    assert not caplog.records


_PYPROJECT = (
    '[build-system]\nbuild-backend = "setuptools.build_meta"\n'
    '[project]\nname = "demo"\nversion = "1"\n'
)
_DYN_DEPS = 'dynamic = ["dependencies"]\n'
_DYN_BOTH = 'dynamic = ["dependencies", "optional-dependencies"]\n'
_TABLE = '[tool.setuptools.dynamic]\ndependencies = {file = "p.txt"}\n'
_SETUP_CFG = _cfg("install_requires = file: r.txt\n", "dev = file: d.txt\n")
_FILES = {"r.txt": "foo\n", "d.txt": "pytest\n", "p.txt": "bar\n"}
_PY = "from setuptools import setup\nsetup(install_requires=['spam'],"
_PY_EXTRAS = _PY + " extras_require={':os_name==\"nt\"': ['w'], 'x': ['y']})\n"

#: (pyproject tail, setup.py, dependencies, provenance; None = no setup.py)
_COMBINED: list[Any] = [
    pytest.param(
        _DYN_DEPS, None, ["foo"], _REQ, id="dynamic-from-setup-cfg",
    ),
    pytest.param(
        'dynamic = ["optional-dependencies"]\n', _PY_EXTRAS,
        ['w; os_name == "nt"', 'y; extra == "x"'],
        "Source: setup.py | Field: setup(extras_require=...)",
        id="only-extras-dynamic",
    ),
    pytest.param(
        _DYN_BOTH, None, ["foo", 'pytest; extra == "dev"'],
        f"{_REQ}, options.extras_require",
        id="dynamic-extras-from-setup-cfg",
    ),
    pytest.param(
        _DYN_DEPS + _TABLE, None, ["bar"],
        "Source: pyproject.toml | Field: tool.setuptools.dynamic.dependencies",
        id="table-beats-setup-cfg",
    ),
    pytest.param(
        'dependencies = ["bar"]\n', None, ["bar"],
        "Source: pyproject.toml | Field: project.dependencies", id="static-wins",
    ),
    pytest.param("", None, [], None, id="not-dynamic-not-read"),
    pytest.param(
        _DYN_BOTH, _PY_EXTRAS,
        ["spam", 'w; os_name == "nt"', 'y; extra == "x"'],
        "Source: setup.py | Field: setup(install_requires=...),"
        " setup(extras_require=...)",
        id="setup-py-beats-setup-cfg",
    ),
]  # fmt: skip


@pytest.mark.parametrize(("tail", "setup_py", "deps", "prov"), _COMBINED)
def test_dynamic_project_fields_from_setup_files(
    tmp_path: Path, tail: str, setup_py: str | None, deps: list[str], prov: str | None
) -> None:
    """As setuptools 84 builds it (measured): a ``dynamic`` dependency
    field the table has no key for keeps ``setup.cfg``'s and
    ``setup.py``'s value; a table key or a static value wins; a field
    neither static nor dynamic is empty."""
    files: dict[str, str | bytes] = {"pyproject.toml": _PYPROJECT + tail}
    files |= {"setup.cfg": _SETUP_CFG, **_FILES}
    if setup_py is not None:
        files["setup.py"] = setup_py
    project = _project(tmp_path, files)

    metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == deps
    assert metadata.provenance.get("dependencies") == prov


@pytest.mark.parametrize(
    ("name", "text", "reason"),
    [
        ("setup.py", "setup(\n", "setup.py"),
        ("setup.cfg", "[options\n", "setup.cfg"),
    ],
    ids=["setup-py", "setup-cfg"],
)
def test_unreadable_setup_file_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
    text: str,
    reason: str,
) -> None:
    """A setup file that cannot be read leaves the dynamic fields it
    would fill unset, with one ``WARNING:`` naming them and it (none for a
    quiet read)."""
    project = _project(tmp_path, {"pyproject.toml": _PYPROJECT + _DYN_BOTH, name: text})

    with caplog.at_level(logging.WARNING):
        read_project(project, include_locked_dependencies=False, quiet=True)
        assert not caplog.messages
        metadata = read_project(project, include_locked_dependencies=False)[0]

    assert metadata.dependencies == []
    (message,) = caplog.messages
    assert message.startswith(
        "pyproject.toml: dynamic dependencies, optional-dependencies not read"
        f" from {reason}: "
    )
