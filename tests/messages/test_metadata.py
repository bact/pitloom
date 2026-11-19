# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The project-metadata lines of a ``pyproject.toml``, through the real
readers: a ``[project]`` table refused (``metadata-invalid``, an ``ERROR``),
a value ignored (a ``WARNING``), a ``[project]`` table that names nothing
(``metadata-invalid``) against a layout that has none (``DEBUG`` only), a
Poetry table the backend does not read (``metadata-no-effect``) and a
dynamic field the backends cannot resolve without a build
(``dynamic-field-needs-build``, ``dynamic-field-unusable``).

See also: tests/messages/test_metadata_relays.py (the relays),
tests/messages/test_metadata_surfaces.py (the command line, the hook and
the library) and tests/messages/test_metadata_setuptools.py (setup.cfg,
setup.py and the dynamic requirements).
"""

from __future__ import annotations

import ast
import inspect
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.extract.project import (
    pyproject as pyproject_module,
)
from pitloom.extract.project import (
    read_project,
    resolve_project_with_lockfile,
)
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.messages import code_of
from tests._code_records import coded

pytestmark = pytest.mark.platform

_BIG = "9" * 700  # past the digit cap of a version
_HEAD = '[project]\nname = "demo"\nversion = "1.0"\n'
_CFG = "[metadata]\nname = real\nversion = 1.2.3\n"


def _write(root: Path, text: str, **files: str) -> Path:
    """*root* with a ``pyproject.toml`` of *text*; each keyword a file of
    the project (``setup_cfg`` is ``setup.cfg``)."""
    root.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    for name, content in files.items():
        (root / name.replace("_", ".")).write_text(content, encoding="utf-8")
    return root


# -- an ERROR: the [project] table is refused ---------------------------------


@pytest.mark.parametrize(
    ("table", "part"),
    [
        (
            f'[project]\nname = "d"\nversion = "1.{_BIG}"\n',
            "project.version has a number",
        ),
        (
            f'[project]\nname = "d"\nversion = "1"\nrequires-python = ">={_BIG}"\n',
            "project.requires-python has a number",
        ),
        ('[project]\nname = "d"\nversion = "no"\n', "not valid [project]"),
        (
            '[project]\nname = "d"\nversion = "1"\nrequires-python = "garbage"\n',
            "not valid [project]",
        ),
        (
            '[project]\nname = "d"\nversion = "1"\ndependencies = "x"\n',
            "not valid [project]",
        ),
        (  # a refused field beside a licence: refused on the first read
            '[project]\nname = "d"\nversion = "x"\nlicense = "MIT"\n'
            'classifiers = ["License :: OSI Approved :: MIT License"]\n',
            "not valid [project]",
        ),
        ("project = 'x'\n", "[project] is a string 'x', expected a table"),
        ("project = [1]\n", "[project] is an array, expected a table"),
        ("[project]\nname = 5\n", "project.name is an integer 5, expected a string"),
        ("[project]\nname = true\n", "project.name is a boolean"),
        ("[project]\nname = ['a']\n", "project.name is an array, expected a string"),
    ],
    ids=[
        "number-version",
        "number-python",
        "bad-version",
        "bad-python",
        "bad-dependencies",
        "bad-version-with-licence",
        "project-string",
        "project-array",
        "name-integer",
        "name-boolean",
        "name-array",
    ],
)
def test_a_refused_project_table_is_a_coded_error_naming_the_file_once(
    table: str, part: str, tmp_path: Path
) -> None:
    path = _write(tmp_path / "p", table) / "pyproject.toml"
    with pytest.raises(ValueError) as exc:
        read_pyproject(path)
    assert code_of(exc.value) == "metadata-invalid"
    text = str(exc.value)
    assert text.startswith(f"FILE={path}: ")
    assert text.count("FILE=") == 1
    assert part in text
    assert "Failed to parse project metadata" not in text  # the base's frame


# -- row 44: [project] with no name against no [project] at all ---------------


@pytest.mark.parametrize(
    "table",
    [
        '[project]\nversion = "1"\n',
        '[project]\nname = ""\n',
        '[project]\nname = "  "\n',
    ],
    ids=["absent", "empty", "blank"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_a_project_table_with_no_usable_name_is_a_coded_warning(
    table: str, quiet: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Present but invalid (the author wrote a ``[project]``): said, and
    setup.cfg names the project instead."""
    root = _write(tmp_path / "p", table, setup_cfg=_CFG)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        metadata, _, _ = read_project(root, quiet=quiet)
    assert metadata.name == "real"
    said = [(c, m) for c, m in coded(caplog) if c]
    if quiet:
        assert not said
        return
    ((code, message),) = said
    assert code == "metadata-invalid"
    assert message.startswith(f"FILE={root / 'pyproject.toml'}: [project] has no name")


@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_a_build_system_only_layout_is_debug_never_a_warning(
    quiet: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Absent data is not an error: a legacy setuptools layout declares only
    ``[build-system]``, so nothing reaches stderr (WARNING and up)."""
    root = _write(
        tmp_path / "p",
        '[build-system]\nrequires = ["x"]\nbuild-backend = "custom_wrapper"\n',
        setup_cfg=_CFG,
    )
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        metadata, _, _ = read_project(root, quiet=quiet)
    assert metadata.name == "real"
    assert not [r for r in caplog.records if r.levelno >= logging.INFO]
    said = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert (not quiet) is any("no [project] table" in m for m in said)
    assert not any("[project] has no name" in m for m in said)


def test_the_fallback_is_said_once_across_the_peek_and_the_reread(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _write(tmp_path / "p", '[project]\nname = ""\n', setup_cfg=_CFG)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _, _ = resolve_project_with_lockfile(root, None)
    assert metadata.name == "real"
    assert [c for c, _ in coded(caplog)].count("metadata-invalid") == 1


# -- D4: what the Poetry reader raises (row 17's catch) ----------------------

_KEYS = (
    "name",
    "version",
    "description",
    "readme",
    "license",
    "keywords",
    "authors",
    "maintainers",
    "homepage",
    "repository",
    "documentation",
    "urls",
    "classifiers",
    "dependencies",
    "extras",
    "group",
    "packages",
    "include",
    "exclude",
    "scripts",
    "plugins",
    "source",
    "requires-poetry",
)
_VALUES: tuple[object, ...] = (5, True, "x", [], {}, [1], {"a": 1}, [["a"]], [{"a": 1}])
#: Nested places a wrong value reaches Poetry's dependency readers.
_NESTED: tuple[Callable[[object], dict[str, object]], ...] = (
    lambda v: {"dependencies": {"python": v}},
    lambda v: {"dependencies": {"requests": v}},
    lambda v: {"dependencies": {"requests": "^1"}, "extras": {"a": v}},
    lambda v: {"dependencies": {"requests": {"version": v}}},
    lambda v: {"group": {"dev": v}},
    lambda v: {"group": {"dev": {"dependencies": {"x": v}}}},
)


@pytest.mark.parametrize(
    "project_name", [False, True], ids=["poetry-name", "project-name"]
)
def test_a_poetry_table_never_raises_anything_but_a_coded_value_error(
    project_name: bool, tmp_path: Path
) -> None:
    """The catch around the Poetry read needs no ``KeyError`` (nor any other
    class): whatever a ``[tool.poetry]`` key holds, the reader returns, or
    raises a ``ValueError`` that carries its code. A key of the wrong type is
    ignored with its own warning."""
    tables = [{key: value} for key in _KEYS for value in _VALUES]
    tables += [nested(value) for nested in _NESTED for value in _VALUES]
    for table in tables:
        poetry = dict(table) if project_name else {"name": "p", **table}
        data: dict[str, object] = {"tool": {"poetry": poetry}}
        if project_name:
            data["project"] = {"name": "p"}
        try:
            extract_poetry_metadata(data, tmp_path, quiet=True)
        except ValueError as exc:
            assert code_of(exc) is not None, f"{table}: {exc}"
    assert len(tables) == len(_KEYS) * len(_VALUES) + len(_NESTED) * len(_VALUES)


def test_the_poetry_catch_names_no_key_error() -> None:
    """The catch was ``(ValueError, KeyError)``: with the fuzz above it is
    ``ValueError`` alone, so a ``KeyError`` is a bug, not a gap-fill outcome."""
    tree = ast.parse(inspect.getsource(pyproject_module))
    handlers = [
        h
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_try_read_poetry"
        for h in ast.walk(node)
        if isinstance(h, ast.ExceptHandler)
    ]
    assert handlers  # the catch is still there
    named = {n.id for h in handlers for n in ast.walk(h) if isinstance(n, ast.Name)}
    assert "KeyError" not in named


# -- a value of the wrong type: ignored with one WARNING ---------------------


@pytest.mark.parametrize(
    ("value", "got"),
    [
        ("3", "an integer 3"),
        ("true", "a boolean"),
        ("[]", "an array"),
        ("{a = 1}", "a table"),
        ("1.5", "a float"),
    ],
    ids=["integer", "boolean", "array", "table", "float"],
)
def test_a_poetry_value_of_the_wrong_type_is_named_by_its_toml_type(
    value: str, got: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _write(tmp_path / "p", f'[tool.poetry]\nname = "p"\nversion = {value}\n')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _, _ = read_project(root)
    assert metadata.version is None
    ((code, message),) = coded(caplog)
    assert code == "metadata-invalid"
    head = f"FILE={root / 'pyproject.toml'}: [tool.poetry] 'version' is "
    assert message.startswith(head)
    assert got in message
    assert message.endswith("expected a string; ignored")


# -- metadata-no-effect: a Poetry declaration the backend does not read -------


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        (
            _HEAD
            + '[project.optional-dependencies]\na = ["x"]\n'
            + '[tool.poetry.extras]\na = ["x"]\n',
            ("[tool.poetry.extras] not read", "optional-dependencies", "; ignored"),
        ),
        (
            '[build-system]\nrequires = ["hatchling"]\n'
            'build-backend = "hatchling.build"\n'
            '[project]\nname = "p"\nversion = "1"\n'
            '[tool.poetry]\ndescription = "d"\n',
            ("[tool.poetry] description not read", "build-backend hatchling.build"),
        ),
    ],
    ids=["table", "backend"],
)
def test_a_poetry_declaration_that_has_no_effect_is_said_with_its_code(
    text: str, parts: tuple[str, ...], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _write(tmp_path / "p", text)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_project(root)
    ((code, message),) = coded(caplog)
    assert code == "metadata-no-effect"
    assert message.startswith(f"FILE={root / 'pyproject.toml'}: ")
    assert all(part in message for part in parts)


# -- dynamic fields only a build computes ------------------------------------

_PDM = (
    '[build-system]\nrequires = ["pdm-backend"]\nbuild-backend = "pdm.backend"\n'
    '[project]\nname = "d"\ndynamic = ["version"]\n'
)
_FLIT = (
    '[build-system]\nrequires = ["flit_core>=3.9"]\n'
    'build-backend = "flit_core.buildapi"\n'
    '[project]\nname = "nonexistent_pkg"\ndynamic = ["version"]\n'
)


@pytest.mark.parametrize(
    ("text", "member", "expected"),
    [
        (
            _PDM + '[tool.pdm.version]\nsource = "call"\ngetter = "x:y"\n',
            None,
            (
                "dynamic-field-needs-build",
                "PDM version source call is not resolvable without running "
                "project code",
            ),
        ),
        (
            _PDM + '[tool.pdm.version]\nsource = "file"\npath = "d/__init__.py"\n',
            "d/__init__.py",
            ("dynamic-field-unusable", "PDM dynamic version not resolved; "),
        ),
        (
            _FLIT,
            None,
            ("dynamic-field-unusable", "Flit dynamic metadata not resolved; "),
        ),
    ],
    ids=["pdm-source", "pdm-failed", "flit-failed"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["said", "quiet"])
def test_a_dynamic_field_a_backend_cannot_resolve_is_said_once_with_its_code(
    text: str,
    member: str | None,
    expected: tuple[str, str],
    quiet: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = _write(tmp_path / "p", text)
    if member is not None:  # a version file that holds no version
        (root / member).parent.mkdir(parents=True, exist_ok=True)
        (root / member).write_text("x = 1\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_pyproject(root / "pyproject.toml", quiet=quiet)
    assert metadata.version is None
    said = coded(caplog)
    if quiet:
        assert not said
        return
    ((got, message),) = said
    assert got == expected[0]
    assert message.startswith(f"FILE={root / 'pyproject.toml'}: ")
    assert expected[1] in message


@pytest.mark.parametrize(
    "error",
    [
        ValueError("fetch https://user:hunter2@h.example/x failed"),
        ValueError("two\nlines\x1b[31m red"),
    ],
    ids=["credentials", "control-characters"],
)
def test_a_resolver_error_is_masked_and_on_one_line(
    error: Exception,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure is the backend's own text: a URL credential is masked, a
    newline and an escape sequence cannot forge a line."""
    # pylint: disable-next=import-outside-toplevel
    from pdm.backend.hooks.version import DynamicVersionBuildHook

    def fail(*_args: object, **_kwargs: object) -> str:
        raise error

    monkeypatch.setattr(DynamicVersionBuildHook, "resolve_version_from_file", fail)
    root = _write(
        tmp_path / "p",
        _PDM + '[tool.pdm.version]\nsource = "file"\npath = "d/__init__.py"\n',
    )
    (root / "d").mkdir()
    (root / "d" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_pyproject(root / "pyproject.toml")
    ((code, message),) = coded(caplog)
    assert code == "dynamic-field-unusable"
    assert "hunter2" not in message
    assert "\n" not in message and "\x1b" not in message
