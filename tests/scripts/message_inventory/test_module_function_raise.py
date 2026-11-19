# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory``: ``raise _timed_out(...)``, a module-level
function that builds a coded error with a catalogue constant, is coded at
each raise (the Git runner's two timeout sites).

See also: test_inventory.py (the other coded-site rules).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULES = {
    "remote/_run.py": """\
from pitloom.messages.network import DOWNLOAD_TIMEOUT, GIT_TIMEOUT_LINE


def _timed_out(seconds, what):
    return make_error(
        "git.timeout", DOWNLOAD_TIMEOUT, GIT_TIMEOUT_LINE, command=what, seconds=seconds
    )


class Runner:
    def run(self, left, what):
        if left <= 0:
            raise _timed_out(self.seconds, what)
        status = self.go()
        if status is None:
            raise _timed_out(self.seconds, what)
        return status
""",
}


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`MODULES` under ``src/pitloom``."""
    root = tmp_path_factory.mktemp("module-function-raise")
    package = root / "src" / "pitloom" / "remote"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_bytes(b"")
    (package / "__init__.py").write_bytes(b"")
    for name, source in MODULES.items():
        (package.parent / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


@pytest.mark.parametrize("line", [13, 16], ids=["before-the-call", "during-the-call"])
def test_a_raise_of_a_module_function_that_codes_is_coded(
    mi: ModuleType, records: list[dict[str, Any]], line: int
) -> None:
    (found,) = [
        r for r in records if r["module"] == "pitloom.remote._run" and r["line"] == line
    ]
    assert found["emitter"] == "raise"
    assert found["coded"] and mi.in_scope(found)


def test_the_module_leaves_no_uncoded_count(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    assert "pitloom.remote._run" not in mi.uncoded_counts(records)
