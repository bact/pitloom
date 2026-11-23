# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project reader that catches a coded error and reads on says it again as
a ``WARNING:`` through :func:`pitloom.messages.metadata.relay_coded_warning`:
the inner error's own line and code, no prefix and no outcome tail. The
helper (every inner code a relay can carry, an error with no twin), the
structural guarantee (no error the three readers raise is uncoded or
twinless) and the three relays: a Poetry read for ``poetry.lock`` (row 17),
``setup.py`` beside ``setup.cfg`` (row 27) and the setuptools dynamic fields
(row 37).

See also: tests/messages/test_metadata.py (the readers' own lines) and
tests/test_message_ratchet.py (the relay rule of the inventory).
"""

# pylint: disable=protected-access

from __future__ import annotations

import ast
import logging
import types
from collections.abc import Callable
from pathlib import Path

import pytest

import pitloom
from pitloom.core.internal_error import InternalError
from pitloom.extract.project._setuptools_dynamic import read_setuptools_dynamic
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.setuptools import read_setuptools
from pitloom.extract.project.setuptools_cfg import read_setup_cfg_options
from pitloom.extract.project.setuptools_py import read_setup_py_options
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    MESSAGES,
    CodedFileNotFoundError,
    CodedValueError,
    Line,
    Message,
    code_of,
    config,
    files,
    metadata,
    trusted_message,
)
from pitloom.messages.config import (
    CONFIG_MALFORMED,
    INI_FILE_LINE,
    INI_LINE,
    INTERPOLATION_FILE_LINE,
    INTERPOLATION_LINE,
    TOML_LINE,
)
from pitloom.messages.files import file_unreadable_error
from pitloom.messages.metadata import (
    METADATA_INVALID,
    METADATA_MALFORMED,
    METADATA_USE,
    POETRY_NAME_LINE,
    PROJECT_NAME_MISSING,
    PYTHON_LINE,
    SETUP_CFG_NAME_LINE,
    SETUP_PY_NAME_LINE,
    SETUPTOOLS_NAME_LINE,
    TYPE_ERROR_LINE,
    relay_coded_warning,
)
from pitloom.messages.targets import PROJECT_NOT_FOUND, PROJECT_NOT_FOUND_LINE
from tests._code_records import coded
from tests._unreadable_path import unreadable

pytestmark = pytest.mark.platform

_FILE = Path("proj") / "pyproject.toml"
_LOG = logging.getLogger("pitloom.test_relays")


def _inner(entry: Message, line: Line, **values: object) -> CodedValueError:
    """The coded error of *entry*'s *line* for the project file."""
    return CodedValueError(entry, line=line, file=_FILE, **values)


_NOT_UTF8 = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
_TYPE = {"field": "[tool.poetry]", "got": "x", "expected": "table"}
_BAD = {"failure": ValueError("x")}
#: Every coded error a relay carries: (id, error, its code).
_INNER = [
    (
        "malformed-python",
        _inner(METADATA_MALFORMED, PYTHON_LINE, failure=SyntaxError("x")),
        "metadata-malformed",
    ),
    (
        "invalid-type",
        _inner(METADATA_INVALID, TYPE_ERROR_LINE, **_TYPE),
        "metadata-invalid",
    ),
    (
        "poetry-name",
        _inner(PROJECT_NAME_MISSING, POETRY_NAME_LINE),
        "project-name-missing",
    ),
    (
        "unreadable",
        file_unreadable_error(OSError(13, "denied"), file=_FILE, use=METADATA_USE),
        "file-unreadable",
    ),
    (
        "not-utf8",
        file_unreadable_error(_NOT_UTF8, file=_FILE, use=METADATA_USE),
        "file-unreadable/not-utf8",
    ),
    ("toml", _inner(CONFIG_MALFORMED, TOML_LINE, **_BAD), "config-malformed"),
    ("ini", _inner(CONFIG_MALFORMED, INI_FILE_LINE, **_BAD), "config-malformed"),
    (
        "interpolation",
        _inner(CONFIG_MALFORMED, INTERPOLATION_FILE_LINE, error="bad %"),
        "config-malformed",
    ),
]
_INNER_IDS = [i for i, _, _ in _INNER]


@pytest.mark.parametrize(
    ("exc", "code"), [(e, c) for _, e, c in _INNER], ids=_INNER_IDS
)
def test_an_inner_error_is_said_again_as_a_warning_with_its_code(
    exc: CodedValueError, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        relay_coded_warning(_LOG, exc, quiet=False)
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert getattr(record, CODE_ATTR) == code
    assert record.getMessage() == str(exc)  # its own words, no prefix, no tail
    assert record.getMessage().startswith("FILE=")
    line = f"WARNING: {record.getMessage()} [{code}]"
    assert trusted_message(line) is not None  # a line of the entry, as a WARNING


@pytest.mark.parametrize("exc", [e for _, e, _ in _INNER], ids=_INNER_IDS)
def test_a_quiet_relay_says_nothing(
    exc: CodedValueError, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        relay_coded_warning(_LOG, exc, quiet=True)
    assert not caplog.records


# The setuptools name lines have twins since PR 15 ('loom fragment list'
# relays them); project-not-found has none (see test_metadata_fragment_relay).
_TWINLESS = [
    CodedFileNotFoundError(PROJECT_NOT_FOUND, line=PROJECT_NOT_FOUND_LINE, path=_FILE),
    ValueError("not coded"),
    RuntimeError("not coded"),
]


@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
@pytest.mark.parametrize(
    "exc",
    _TWINLESS,
    ids=["project-not-found", "uncoded-value", "uncoded-runtime"],
)
def test_a_relay_without_a_twin_is_an_internal_error_even_when_quiet(
    exc: BaseException, quiet: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Never said uncoded, and never silent only because *quiet*: a twin
    missing is a programming error caught the first time it is relayed."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        with pytest.raises(InternalError):
            relay_coded_warning(_LOG, exc, quiet=quiet)
    assert not caplog.records


# -- no error the three readers raise is uncoded or twinless -----------------

_PY = "from setuptools import setup\nsetup(name='demo')\n"


def _refuse(error: BaseException) -> Callable[..., object]:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    return fail


_CFG_FILES = {
    "cfg-not-utf8": b"[metadata]\nname = d\x80\xff\n",
    "cfg-ini": b"[metadata\nname = demo\n",
    "cfg-interpolation": b"[metadata]\nname = demo\ndescription = 100% sure\n",
    "cfg-unreadable": b"[metadata]\nname = demo\n",
}
_PY_FILES = {
    "py-syntax": b"setup(name='a'\n",
    "py-nul": b"setup(name='a')\x00\n",
    "py-unreadable": _PY.encode(),
    "py-recursion": _PY.encode(),
    "py-memory": _PY.encode(),
}


@pytest.mark.parametrize("which", sorted(_CFG_FILES))
def test_a_setup_cfg_fault_is_coded_and_relayable(which: str, tmp_path: Path) -> None:
    (tmp_path / "setup.cfg").write_bytes(_CFG_FILES[which])
    root = unreadable(tmp_path, "setup.cfg") if which == "cfg-unreadable" else tmp_path
    with pytest.raises(ValueError) as exc:
        read_setup_cfg_options(root)
    assert code_of(exc.value) is not None, str(exc.value)
    relay_coded_warning(_LOG, exc.value, quiet=True)  # has its twin


@pytest.mark.parametrize("which", sorted(_PY_FILES))
def test_a_setup_py_fault_is_coded_and_relayable(
    which: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "setup.py").write_bytes(_PY_FILES[which])
    root = tmp_path
    if which == "py-unreadable":
        root = unreadable(tmp_path, "setup.py")
    elif which in {"py-recursion", "py-memory"}:
        error = RecursionError() if which == "py-recursion" else MemoryError()
        monkeypatch.setattr(
            "pitloom.extract.project.setuptools_py.ast",
            types.SimpleNamespace(parse=_refuse(error)),
        )
    with pytest.raises(ValueError) as exc:
        read_setup_py_options(root)
    assert code_of(exc.value) is not None, str(exc.value)
    relay_coded_warning(_LOG, exc.value, quiet=True)


@pytest.mark.parametrize(
    "data",
    [{"tool": {"poetry": "x"}}, {"tool": {"poetry": 5}}, {"tool": {"poetry": ["a"]}}],
    ids=["string", "integer", "array"],
)
def test_a_poetry_table_that_is_no_table_is_coded_and_relayable(
    data: dict[str, object], tmp_path: Path
) -> None:
    with pytest.raises(ValueError) as exc:
        extract_poetry_metadata(data, tmp_path, quiet=True)
    assert code_of(exc.value) == "metadata-invalid"
    relay_coded_warning(_LOG, exc.value, quiet=True)


@pytest.mark.parametrize(
    "data",
    [{}, {"tool": {}}, {"tool": "x"}, {"tool": {"poetry": {}}}],
    ids=["empty", "no-poetry", "tool-string", "empty-poetry"],
)
def test_an_absent_poetry_table_is_an_internal_error_not_an_uncoded_value_error(
    data: dict[str, object], tmp_path: Path
) -> None:
    """Row 19: the one caller returns before it, so reaching it is a
    programming error, said as one, never a ``ValueError`` a relay cannot
    carry."""
    with pytest.raises(InternalError):
        extract_poetry_metadata(data, tmp_path, quiet=True)


#: The modules whose coded errors the three relayed readers raise.
_READERS = (
    "setuptools_cfg.py",
    "setuptools_py.py",
    "poetry.py",
    "_poetry_fields.py",
    "_poetry_extras.py",
    "_poetry_requirements.py",
    "setup_cfg_interpolation.py",
    "_setup_cfg_values.py",
    "_setup_cfg_directives.py",
)
#: Raised by the whole-file wrappers (``read_setup_cfg``, ``read_setup_py``)
#: and by the ``[tool:pitloom]`` reader of a setup.cfg text (a ``--config``
#: style line that names no file): no reader catches them, no twin.
_UNRELAYED = {
    SETUPTOOLS_NAME_LINE,
    SETUP_CFG_NAME_LINE,
    SETUP_PY_NAME_LINE,
    INI_LINE,
    INTERPOLATION_LINE,
}


def test_every_error_line_the_relayed_readers_name_has_a_twin() -> None:
    """Static side of the guarantee above: an ``ERROR`` line a reader module
    refers to by name is relayed as a ``WARNING`` of the same text. A reader
    that names none is not coded yet, so the floor fails."""
    errors = {
        name: line
        for module in (metadata, config, files)
        for name, line in vars(module).items()
        if isinstance(line, Line) and line.level == "ERROR"
    }
    root = Path(pitloom.__file__).parent / "extract" / "project"
    named = {
        node.id
        for module in _READERS
        for node in ast.walk(ast.parse((root / module).read_bytes()))
        if isinstance(node, ast.Name) and node.id in errors
    }
    lines = {errors[name] for name in named} - _UNRELAYED
    assert {PYTHON_LINE, INI_FILE_LINE, INTERPOLATION_FILE_LINE} <= lines
    twins = {
        (ln.template)
        for entry in MESSAGES.values()
        for ln in entry.lines
        if ln.level == "WARNING"
    }
    assert {ln.template for ln in lines} <= twins


# -- row 17: a Poetry read for poetry.lock ------------------------------------

_LOCK = (
    '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
    '[metadata]\nlock-version = "2.1"\n'
)


def _poetry_project(root: Path, pyproject: str, *, lock: bool) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    if lock:
        (root / "poetry.lock").write_text(_LOCK, encoding="utf-8")
    return root / "pyproject.toml"


@pytest.mark.parametrize("lock", [True, False], ids=["lock", "no-lock"])
def test_a_poetry_table_that_is_no_table_is_said_once(
    lock: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The wrong-typed table says so itself, with a lock or without: the
    relay of the failed gap-fill adds no second line (the pins still apply)."""
    path = _poetry_project(tmp_path / "p", '[tool]\npoetry = "x"\n', lock=lock)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found, _ = read_pyproject(path)
    said = [m for c, m in coded(caplog) if c == "metadata-invalid"]
    assert len(said) == 1 and said[0].endswith("; ignored")
    assert said[0].startswith(f"FILE={path}: [tool.poetry] is ")
    assert bool(found.locked_dependencies) is lock
    assert not any("could not be parsed" in m for _, m in coded(caplog))  # no tail


def test_a_poetry_table_with_no_name_anywhere_relays_the_missing_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _poetry_project(tmp_path / "p", '[tool.poetry]\nversion = "1"\n', lock=True)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found, _ = read_pyproject(path)
    ((code, message),) = coded(caplog)
    assert code == "project-name-missing"
    assert message.startswith(f"FILE={path}: neither [tool.poetry] nor [project]")
    assert found.locked_dependencies == ["requests==2.31.0"]


def test_a_poetry_table_with_no_name_and_no_lock_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _poetry_project(tmp_path / "p", '[tool.poetry]\nversion = "1"\n', lock=False)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_pyproject(path)
    assert not caplog.records


# -- row 27: setup.py beside setup.cfg ---------------------------------------


def _setup_files(root: Path, cfg: str | None, py: bytes | None) -> Path:
    root.mkdir()
    if cfg is not None:
        (root / "setup.cfg").write_text(cfg, encoding="utf-8")
    if py is not None:
        (root / "setup.py").write_bytes(py)
    return root


@pytest.mark.parametrize(
    ("cfg", "has_name"),
    [
        ("[metadata]\nname = demo\nversion = 1\n", True),
        ("[metadata]\nversion = 1\n", False),
    ],
    ids=["cfg-names", "cfg-nameless"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_a_setup_py_that_does_not_parse_is_relayed_whether_or_not_cfg_names_the_project(
    cfg: str,
    has_name: bool,
    quiet: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D2: the inner error is said whenever not quiet; the missing name is
    then raised plainly (``project-name-missing``), never stacked behind
    ``Could not parse setup.py``."""
    root = _setup_files(tmp_path / "p", cfg, b"setup(name='a'\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if has_name:
            found, _ = read_setuptools(root, quiet=quiet)
            assert found.name == "demo"
        else:
            with pytest.raises(FileNotFoundError) as exc:
                read_setuptools(root, quiet=quiet)
            assert code_of(exc.value) == "project-name-missing"
            assert str(exc.value).startswith("DIR=")
            assert "Could not parse" not in str(exc.value)
    said = coded(caplog)
    if quiet:
        assert not said
        return
    ((code, message),) = said
    assert code == "metadata-malformed"
    assert message.startswith(f"FILE={root / 'setup.py'}: not valid Python; ")
    assert "reading setup.cfg alone" not in message  # the outcome is `did`'s


@pytest.mark.parametrize(
    "py", [None, _PY.encode()], ids=["no-setup-py", "setup-py-fine"]
)
def test_a_setup_py_that_is_absent_or_parses_is_not_relayed(
    py: bytes | None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _setup_files(tmp_path / "p", "[metadata]\nname = demo\nversion = 1\n", py)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setuptools(root)
    assert not caplog.records


def test_a_setup_py_that_cannot_be_read_is_relayed_asunreadable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _setup_files(tmp_path / "p", "[metadata]\nname = demo\n", _PY.encode())
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setuptools(unreadable(root, "setup.py"))
    ((code, message),) = coded(caplog)
    assert code == "file-unreadable"
    assert "for the project metadata" in message


# -- row 37: the dynamic fields of a setuptools project ------------------------

_DYNAMIC = {"project": {"name": "demo", "dynamic": ["dependencies"]}}


@pytest.mark.parametrize(
    ("which", "code"),
    [
        ("cfg-not-utf8", "file-unreadable/not-utf8"),
        ("cfg-ini", "config-malformed"),
        ("cfg-interpolation", "config-malformed"),
        ("cfg-unreadable", "file-unreadable"),
        ("py-syntax", "metadata-malformed"),
        ("py-nul", "metadata-malformed"),
        ("py-unreadable", "file-unreadable"),
    ],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_each_inner_error_of_the_dynamic_fields_is_relayed_with_its_own_code(
    which: str,
    code: str,
    quiet: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = tmp_path
    if which.startswith("cfg"):
        (tmp_path / "setup.cfg").write_bytes(_CFG_FILES[which])
    else:
        (tmp_path / "setup.py").write_bytes(_PY_FILES[which])
    if which.endswith("unreadable"):
        root = unreadable(
            tmp_path, "setup.cfg" if which.startswith("cfg") else "setup.py"
        )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setuptools_dynamic(_DYNAMIC, root, quiet=quiet)
    said = coded(caplog)
    if quiet:
        assert not said
        return
    ((got, message),) = said
    assert got == code
    assert message.startswith("FILE=")  # no `pyproject.toml: dynamic ...` frame
    assert "pyproject.toml: dynamic" not in message


def test_a_setuptools_dynamic_read_with_good_files_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "setup.cfg").write_text(
        "[options]\ninstall_requires =\n    requests\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = read_setuptools_dynamic(_DYNAMIC, tmp_path)
    assert found.dependencies == ["requests"]
    assert not caplog.records
