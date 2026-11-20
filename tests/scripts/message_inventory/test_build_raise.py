# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: ``raise build_error(LINE, ...)``, which
raises a ``build-failed`` error written from a catalogue line, is coded at
the raise; ``raise BuildTimeoutError(timeout=..., tree_terminated=...)``, an
exception with no text of its own (said later as ``build-timeout``), is no
message site; a raise of a plain exception with a text stays an uncoded site.

See also: test_module_function_raise.py (the other coded-raise shape) and
test_inventory.py (the other coded-site rules).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULES = {
    "build.py": """\
from pitloom.messages.build import BUILD_EXIT_LINE, BuildTimeoutError, build_error


def run(project, code, tail, seconds):
    if code:
        raise build_error(BUILD_EXIT_LINE, dir=project, exit_code=code, output=tail)
    if seconds:
        raise BuildTimeoutError(timeout=seconds, tree_terminated=True)
    raise RuntimeError("the build could not start")
""",
}


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`MODULES` under ``src/pitloom``."""
    root = tmp_path_factory.mktemp("build-raise")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in MODULES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def _at(records: list[dict[str, Any]], line: int) -> list[dict[str, Any]]:
    return [r for r in records if r["module"] == "pitloom.build" and r["line"] == line]


def test_a_raise_of_build_error_with_a_catalogue_line_is_coded(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    (found,) = _at(records, 6)
    assert found["emitter"] == "raise" and found["exc_class"] == "build_error"
    assert found["coded"] and mi.in_scope(found)


def test_a_raise_of_a_build_timeout_error_is_no_site(
    records: list[dict[str, Any]],
) -> None:
    """No text of its own: keyword arguments only, nothing for the walker."""
    assert not _at(records, 8)


def test_a_plain_raise_with_a_text_stays_an_uncoded_site(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    (found,) = _at(records, 9)
    assert found["emitter"] == "raise" and not found["coded"]
    assert mi.uncoded_counts(records) == {"pitloom.build": 1}
