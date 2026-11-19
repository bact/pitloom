# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``lock-file-*`` families: :func:`~pitloom.messages.lock_files.say_lock_file`
names a lock by its file name once per line, with no prefix, its memo is per
run, the over-cap helper says ``over-cap``, and the closed ``lock_key``,
``source_kind`` and ``value_type`` tables hold what the readers use.

See also: tests/messages/test_lock_entry.py (one entry of a lock).
"""

from __future__ import annotations

import ast
import datetime
import json
import logging
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

import pytest

from pitloom._toml_io import load_toml_bytes
from pitloom.core.internal_error import InternalError
from pitloom.extract.lock import _uv_graph, cascade, pdm, pipfile, poetry, pylock
from pitloom.extract.project import _poetry_requirements
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import Line, trusted_message
from pitloom.messages._field_tables import LOCK_KEYS, SOURCE_KINDS, VALUE_TYPES
from pitloom.messages.files import warn_over_cap
from pitloom.messages.lock_files import (
    LOCK_CONFLICT_LINE,
    LOCK_FILE_CONFLICT,
    LOCK_FILE_MALFORMED,
    LOCK_FILE_OVER_CAP_OUTCOME,
    LOCK_FILE_UNUSABLE,
    LOCK_ORDER,
    NO_MATCH_LINE,
    TOP_KEY_LIST_LINE,
    TOP_LEVEL_LINE,
    VERSION_MINOR_LINE,
    VERSIONS_LINE,
    lock_file_cap,
    say_lock_file,
)
from tests._docs_scan import REPO_ROOT

pytestmark = pytest.mark.platform

_LOG = logging.getLogger("pitloom.lock_file_messages")
_LOCK_DIR = REPO_ROOT / "src" / "pitloom" / "extract" / "lock"


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Each record as stderr prints it: level, text, code."""
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


@pytest.mark.parametrize(
    "file",
    [
        "uv.lock",
        Path("proj") / "uv.lock",
        PurePosixPath("/abs/proj/uv.lock"),
        PureWindowsPath(r"C:\proj\uv.lock"),
    ],
    ids=["name", "path", "posix", "windows"],
)
def test_a_lock_is_named_by_its_file_name_once(
    file: str | PurePath, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_file(_LOG, TOP_KEY_LIST_LINE, file=file, lock_key="package", value_type={})
    (line,) = _printed(caplog)
    assert line == (
        "WARNING: FILE=uv.lock: top-level package is dict, expected a list; "
        "no pins read from it [lock-file-malformed]"
    )
    assert line.count("FILE=") == 1 and line.count("uv.lock") == 1
    assert trusted_message(line) is LOCK_FILE_MALFORMED


def test_no_candidate_names_the_lock_once(caplog: pytest.LogCaptureFixture) -> None:
    """``_uv_graph.py:109`` printed the path and ``uv.lock`` both."""
    caplog.set_level(logging.WARNING)
    say_lock_file(_LOG, NO_MATCH_LINE, file="uv.lock", number=2, package="demo")
    (line,) = _printed(caplog)
    assert line.count("uv.lock") == 1
    assert trusted_message(line) is LOCK_FILE_UNUSABLE


@pytest.mark.parametrize(
    ("name", "shown"),
    [("u\nv.lock", r"'u\nv.lock'"), ("u\x1bv.lock", r"'u\x1bv.lock'")],
    ids=["newline", "escape"],
)
def test_a_control_character_in_the_name_is_escaped(
    name: str, shown: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_file(_LOG, TOP_LEVEL_LINE, file=name, value_type=[])
    (line,) = _printed(caplog)
    assert "\n" not in line and "\x1b" not in line
    assert line.startswith(f"WARNING: FILE={shown}: ")


def test_a_newer_minor_version_is_read(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_file(
        _LOG,
        VERSION_MINOR_LINE,
        file="pylock.toml",
        lock_key="lock-version",
        lock_value="1.1",
    )
    assert _printed(caplog) == [
        "WARNING: FILE=pylock.toml: lock-version '1.1' is newer than the version "
        "Pitloom reads; read; newer keys not read [lock-file-wrong-format]"
    ]


def test_a_conflict_names_kept_and_dropped_in_lower_case(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    say_lock_file(_LOG, LOCK_CONFLICT_LINE, kept="uv.lock", dropped="poetry.lock")
    (line,) = _printed(caplog)
    assert line.endswith("; kept 'uv.lock', dropped 'poetry.lock' [lock-file-conflict]")
    assert "KEPT=" not in line and "DROPPED=" not in line
    assert trusted_message(line) is LOCK_FILE_CONFLICT


@pytest.mark.parametrize(
    ("shape", "file"), [(LOCK_CONFLICT_LINE, "uv.lock"), (TOP_LEVEL_LINE, None)]
)
def test_file_is_given_exactly_when_the_line_names_one(
    shape: Line, file: str | None
) -> None:
    values: dict[str, Any] = (
        {"kept": "a", "dropped": "b"}
        if shape is LOCK_CONFLICT_LINE
        else {"value_type": 1}
    )
    with pytest.raises(ValueError, match="not one of its WARNING lines"):
        say_lock_file(_LOG, shape, file=file, **values)


def test_a_line_of_another_helper_is_an_internal_error() -> None:
    with pytest.raises(InternalError, match="not a line of this helper"):
        say_lock_file(_LOG, VERSIONS_LINE, file="uv.lock", package="a", dropped="1")


def test_the_memo_is_per_run(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    said: set[tuple[str, ...]] = set()
    for _ in range(2):
        say_lock_file(_LOG, TOP_LEVEL_LINE, file="uv.lock", value_type=[], said=said)
    assert len(caplog.records) == 1
    say_lock_file(_LOG, TOP_LEVEL_LINE, file="uv.lock", value_type=[], said=set())
    say_lock_file(_LOG, TOP_LEVEL_LINE, file="uv.lock", value_type=[])
    assert len(caplog.records) == 3


def test_an_over_cap_lock_says_over_cap(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    warn_over_cap(_LOG, lock_file_cap(10), "uv.lock", LOCK_FILE_OVER_CAP_OUTCOME)
    assert _printed(caplog) == [
        "WARNING: FILE=uv.lock: larger than the 10-byte lock-file cap; "
        "no dependency pins read [over-cap]"
    ]


def _readers_strings() -> set[str]:
    """Every string constant of the lock readers' modules."""
    found: set[str] = set()
    for path in sorted(_LOCK_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return found


def test_every_lock_key_is_a_key_the_readers_check() -> None:
    strings = _readers_strings()
    missing = [
        key for key in LOCK_KEYS if not all(p in strings for p in key.split("."))
    ]
    assert not missing


def test_the_source_kinds_are_the_readers_non_registry_keys() -> None:
    """The readers' tables are private: read by name, the drift test is the
    one place that ties the catalogue to them."""
    tables = [
        (pdm, "_NON_REGISTRY_KEYS"),
        (pipfile, "_NON_REGISTRY_KEYS"),
        (poetry, "_NON_PEP508_SOURCE_TYPES"),
        (pylock, "_NON_REGISTRY_SOURCE_KEYS"),
        (_uv_graph, "_NON_REGISTRY_SOURCE_KEYS"),
        (_poetry_requirements, "_LOCAL_SOURCES"),
    ]
    readers = {kind for module, name in tables for kind in getattr(module, name)}
    assert set(SOURCE_KINDS) == readers


def test_the_value_types_are_every_type_toml_and_json_load() -> None:
    toml = load_toml_bytes(
        b"a = true\nb = 1979-05-27\nc = 1979-05-27T07:32:00\nd = {}\ne = 1.5\n"
        b'f = 1\ng = []\nh = "s"\ni = 07:32:00\n'
    )
    loaded = {type(v).__name__ for v in toml.values()}
    loaded |= {type(v).__name__ for v in json.loads("[null, 1, 1.5, true, {}, []]")}
    assert loaded == set(VALUE_TYPES)
    assert {datetime.date, datetime.datetime, datetime.time} <= {
        type(v) for v in toml.values()
    }


def test_the_lock_order_is_the_cascade_order() -> None:
    sources = "_LOCK_SOURCES"
    names = [source.name for source in getattr(cascade, sources)]
    positions = [LOCK_ORDER.index(name) for name in names]
    assert positions == sorted(positions)
