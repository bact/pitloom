# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ID registry's codes: the file named as given (a typed spelling, a URL
in it masked, a control character escaped, a Windows path as written), the
literals the catalogue holds for the registry, and a ``loom id generate``
PATH that is not there, or goes away, on the library surface.

See also: tests/id_registry/test_registry_format_load.py (every load
failure), tests/id_registry/test_surfaces_failures.py (every surface),
tests/cli/test_cli_id_path_errors.py (the command line).
"""

from __future__ import annotations

import errno
import json
import sys
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import pytest

import pitloom.id_registry._types as types_mod
from pitloom import __main__
from pitloom.core.given_path import GivenPath, TypedPath
from pitloom.core.internal_error import InternalError
from pitloom.id_registry import IdRegistry
from pitloom.id_registry._counters import MAX_ID_NUMBER
from pitloom.id_registry._types import _REGISTRY_VERSION, _iter_files
from pitloom.id_registry.resolve import resolve_registry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import CodedValueError, code_of
from pitloom.messages.files import REGISTRY_USE, dir_unlistable_error
from pitloom.messages.id_registry import (
    COUNTERS_LINE,
    MAX_COUNTER,
    REGISTRY_MALFORMED,
    REGISTRY_VERSION,
)
from tests.id_registry.shared import valid_registry_data

pytestmark = pytest.mark.platform


def test_the_catalogue_literals_are_the_registrys_own() -> None:
    """``pitloom.messages`` cannot import the registry: its copies of the
    version and the largest counter are held equal here."""
    assert (REGISTRY_VERSION, MAX_COUNTER) == (_REGISTRY_VERSION, MAX_ID_NUMBER)


@pytest.mark.parametrize(
    ("file", "shown"),
    [
        (
            TypedPath(GivenPath("/abs/r.json", "https://u:SECRET@h/r.json")),
            "https://***:***@h/r.json",
        ),
        ("reg\n\x1b.json", "'reg\\n\\x1b.json'"),
        (PureWindowsPath(r"C:\proj\r.json"), r"C:\proj\r.json"),
        (TypedPath(GivenPath("/abs/r.json", "./x/../r.json")), "./x/../r.json"),
    ],
    ids=["url-masked", "control", "windows", "typed"],
)
def test_the_file_is_named_as_given_on_one_line(file: object, shown: str) -> None:
    exc = CodedValueError(REGISTRY_MALFORMED, line=COUNTERS_LINE, file=file)
    assert str(exc) == f"ID registry: FILE={shown}: 'id_counters' is not an object"
    assert "SECRET" not in str(exc)


def _v3(path: Path) -> bytes:
    path.write_text(json.dumps({**valid_registry_data(), "version": 3}))
    return path.read_bytes()


@pytest.mark.parametrize(
    "source",
    ["r.json", GivenPath("ignored", "cfg/../r.json")],
    ids=["configured", "given"],
)
def test_resolve_names_a_registry_that_does_not_load_as_given(
    tmp_path: Path, source: str
) -> None:
    """The same spelling ``input-not-found`` names, never the resolved path."""
    _v3(tmp_path / "r.json")
    given = source if isinstance(source, GivenPath) else None
    if given is not None:
        source = GivenPath(tmp_path / "r.json", given.given)

    with pytest.raises(ValueError) as caught:
        resolve_registry(source, None, tmp_path)

    typed = "cfg/../r.json" if given is not None else "r.json"
    assert str(caught.value).startswith(f"ID registry: FILE={typed}: version 3, ")
    assert code_of(caught.value) == "registry-wrong-format"


def test_load_keeps_the_typed_spelling_on_its_path(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps(valid_registry_data()))

    loaded = IdRegistry.load(TypedPath(GivenPath(path, "x/../r.json")))

    assert loaded.path == path
    assert isinstance(loaded.path, TypedPath) and loaded.path.given == "x/../r.json"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX spelling of sub/..")
@pytest.mark.parametrize(
    ("argv", "typed"),
    [(["-o", "./sub/../r.json"], "./sub/../r.json"), ([], "sub/../r.json")],
    ids=["flag", "configured"],
)
def test_id_generate_names_the_registry_as_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    typed: str,
) -> None:
    """``-o``, or the project's ``id-registry``, keeps its spelling: the line
    names what was typed, the file is left as it is."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pitloom]\nid-registry = "sub/../r.json"\n', encoding="utf-8"
    )
    before = _v3(tmp_path / "r.json")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "id", "generate", *argv])

    assert __main__.main() == 1

    (error,) = capsys.readouterr().err.splitlines()
    assert error.startswith(f"ERROR: loom id generate: ID registry: FILE={typed}:")
    assert error.endswith(" [registry-wrong-format]")
    assert (tmp_path / "r.json").read_bytes() == before


@pytest.mark.parametrize("saved", [True, False], ids=["file", "no-file"])
def test_a_conflict_names_the_registry_file_or_none(
    tmp_path: Path, saved: bool
) -> None:
    """The namespace and project-root conflicts name the registry's own
    file, ``(no file)`` only for one never saved."""
    path = tmp_path / "r.json"
    registry = IdRegistry.new("proj", path if saved else None, project_root=tmp_path)
    named = path if saved else "(no file)"

    with pytest.raises(ValueError) as namespace:
        registry.require_namespace("urn:other")
    assert str(namespace.value).startswith(f"ID registry: FILE={named}: namespace ")
    if saved:
        with pytest.raises(ValueError) as root:
            registry.require_project_root(tmp_path / "elsewhere")
        assert str(root.value).startswith(f"ID registry: FILE={named}: project root ")
        assert code_of(root.value) == "option-conflict"


def test_a_duplicate_key_with_a_control_character_is_one_line(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    data = valid_registry_data()
    text = json.dumps(data)[:-1] + ', "x\\u001b\\n": 1, "x\\u001b\\n": 2}'
    path.write_text(text)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    assert str(caught.value) == f"ID registry: FILE={path}: duplicate key 'x\\x1b\\n'"
    assert code_of(caught.value) == "registry-malformed"


# --- A PATH to index, on the library surface ----------------------------


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_bytes(b"a\n")
    return root


def test_generate_raises_for_a_path_that_is_not_there(tmp_path: Path) -> None:
    root = _project(tmp_path)
    registry = IdRegistry.new("proj")

    with pytest.raises(FileNotFoundError, match=r"^PATH not found: 'gone'$") as caught:
        registry.generate([Path("src"), Path("gone")], root)

    assert code_of(caught.value) == "input-not-found"
    assert not registry.elements


def test_a_default_root_gone_since_it_was_chosen_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Not given by the user: absent data, said nothing of."""
    root = _project(tmp_path)
    registry = IdRegistry.new("proj")

    registry.generate([root / "data", root / "src"], root, explicit=False)

    assert not caplog.records
    assert [key for _, key in registry.elements] == ["src/a.py"]


def test_a_default_root_that_cannot_be_stat_ed_warns_and_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Not given by the user: a read failure is a warning, never an error."""
    root = _project(tmp_path)
    denied = PermissionError(errno.EACCES, "Permission denied")

    def refuse(*_a: object) -> object:
        raise denied

    monkeypatch.setattr(types_mod, "stat_if_present", refuse)

    assert not list(_iter_files([root / "src"], root, explicit=False))
    (record,) = caplog.records
    assert record.levelname == "WARNING"
    assert getattr(record, CODE_ATTR) == "file-unreadable"


def test_a_file_gone_below_a_path_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Listed, then gone before it is read: left out, quietly."""
    root = _project(tmp_path)
    gone = root / "src" / "gone.py"
    monkeypatch.setattr(
        types_mod, "_walk_files", lambda *_a: [root / "src" / "a.py", gone]
    )

    assert list(_iter_files([root / "src"], root)) == [root / "src" / "a.py"]


@pytest.mark.parametrize("kind", ["dir", "file"])
def test_a_path_gone_since_it_was_found_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Gone between the check and the listing or read: not found, never an
    internal error (an absent path is not unreadable)."""
    root = _project(tmp_path)
    target = root / "src" if kind == "dir" else root / "src" / "a.py"
    gone = FileNotFoundError(errno.ENOENT, "No such file or directory", str(target))

    def missing(*_a: object, **_k: object) -> object:
        raise gone

    monkeypatch.setattr(types_mod, "_walk_files", missing)
    with patch("builtins.open", side_effect=gone):
        with pytest.raises(FileNotFoundError, match="^PATH not found: ") as caught:
            list(_iter_files([target], root))

    assert code_of(caught.value) == "input-not-found"


def test_dir_unlistable_error_refuses_an_absent_directory() -> None:
    gone = FileNotFoundError(errno.ENOENT, "No such file or directory")
    with pytest.raises(InternalError):
        dir_unlistable_error(gone, directory="d", use=REGISTRY_USE)
    denied = PermissionError(errno.EACCES, "Permission denied")
    exc = dir_unlistable_error(denied, directory="d", use=REGISTRY_USE)
    assert str(exc) == "DIR=d: could not list for the ID registry; Permission denied"
    assert code_of(exc) == "dir-unlistable"
