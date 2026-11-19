# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every ``[tool.pitloom]`` key, read with a bad value, is a coded error.

An uncoded ``ValueError`` from the settings reader is an
:class:`pitloom.core.internal_error.InternalError`
(:func:`pitloom.core.config_cascade.load_config_file`, the sdist route), and a
second writer of ``field_conflicts`` is one too: these tests are what make
both safe. A new key that raises a plain ``ValueError`` fails here, not for
a user.

See also: ``tests/core/test_config_uncoded_residue.py``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.core._config_keys import KNOWN_ENTRY_KEYS, KNOWN_KEYS
from pitloom.core.config_cascade import load_config_file
from pitloom.extract.project.sdist import read_sdist
from pitloom.messages import code_of
from tests._message_drift import SRC_ROOT
from tests.assemble.conftest import _make_sdist

pytestmark = pytest.mark.platform

#: A wrong type, a NUL, an overlong integer (written, not built: the limit is
#: the reader's) and an empty value, as TOML text.
_VALUES = {
    "wrong-type": "{x = 1}",
    "nul": json.dumps("a\x00b"),
    "huge-int": "1" + "0" * 5000,
    "empty": '""',
}


def _header(table: str) -> str:
    return "[tool.pitloom]" if table == "" else f"[tool.pitloom.{table}]"


def _texts() -> dict[str, str]:
    """Each probe: the whole file text, by a short id."""
    cases = {}
    for table, keys in KNOWN_KEYS.items():
        for key in sorted(keys):
            for kind, value in _VALUES.items():
                cases[f"{table or '.'}:{key}:{kind}"] = (
                    f"{_header(table)}\n{key} = {value}\n"
                )
    for (table, key), entry_keys in KNOWN_ENTRY_KEYS.items():
        for entry_key in sorted(entry_keys):
            for kind, value in _VALUES.items():
                cases[f"{table or '.'}:{key}.{entry_key}:{kind}"] = (
                    f"{_header(table)}\n{key} = [{{{entry_key} = {value}}}]\n"
                )
    return cases


_CASES = _texts()


def _outcome(read: Any) -> str:
    """``accepted``, ``coded``, or what an uncoded error was."""
    try:
        read()
    except ValueError as exc:
        return "coded" if code_of(exc) is not None else f"uncoded {exc!s:.60}"
    return "accepted"


def test_every_key_with_a_bad_value_is_accepted_or_a_coded_error(
    tmp_path: Path,
) -> None:
    config = tmp_path / "pyproject.toml"
    outcomes = {}
    for name, text in _CASES.items():
        config.write_bytes(text.encode("utf-8"))
        outcomes[name] = _outcome(lambda: load_config_file(config))
    assert not {n: o for n, o in outcomes.items() if o.startswith("uncoded")}
    # not vacuous: the probe reaches errors and acceptance both
    assert {"coded", "accepted"} <= set(outcomes.values())


def test_every_key_with_a_bad_value_is_coded_in_an_sdist(tmp_path: Path) -> None:
    """The archive route reads the same table through its own member."""
    uncoded = {}
    for index, (name, text) in enumerate(_CASES.items()):
        if index % 4:  # one value kind per key keeps the archives few
            continue
        root = tmp_path / str(index)
        root.mkdir()
        sdist = _make_sdist(root, members={"pyproject.toml": text.encode()}, fmt="tar")
        outcome = _outcome(lambda sdist=sdist: read_sdist(sdist))
        if outcome.startswith("uncoded"):
            uncoded[name] = outcome
    assert not uncoded


def test_only_two_readers_write_field_conflicts() -> None:
    """``merge_project_metadata`` raises ``InternalError`` for a field both
    sides hold a conflict for, which holds only while the writers are the
    setuptools reader and the installed-metadata reconciliation."""
    callers = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if rel.startswith("messages/") or rel.endswith("_field_agreement.py"):
            continue
        for node in ast.walk(ast.parse(path.read_bytes())):
            func = node.func if isinstance(node, ast.Call) else None
            if isinstance(func, ast.Name) and func.id == "add_conflict":
                callers.add(rel)
    assert callers == {
        "extract/project/_installed_reconcile.py",
        "extract/project/_setuptools_options.py",
    }
