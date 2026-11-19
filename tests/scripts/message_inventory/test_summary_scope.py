# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``: a summary (a call of the
catalogue's ``say_summary``) is out of scope by the definition the call
reaches, never by the call's name or its text.

See also: test_inventory.py (the other scope rules), test_relay_scope.py.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULES = {
    "messages/_summary.py": """\
def say_summary(log, summary, **values):
    log.info(summary.template, values)
""",
    # Named to sort after "messages", so a first-found pick would be wrong.
    "zz_caller.py": """\
import logging

from pitloom.messages._summary import say_summary

_log = logging.getLogger(__name__)


def report(summary, key):
    say_summary(_log, summary, key=key)
    _log.info("ID registry: %s keyed by its path", key)
""",
    "zz_local.py": """\
import logging

_log = logging.getLogger(__name__)


def say_summary(log, summary):
    log.info("ID registry: own words %s", summary)


def report(summary):
    say_summary(_log, summary)
""",
}


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`MODULES` under ``src/pitloom``."""
    root = tmp_path_factory.mktemp("summaries")
    package = root / "src" / "pitloom"
    (package / "messages").mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in MODULES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def _site(records: list[dict[str, Any]], module: str, line: int) -> dict[str, Any]:
    (found,) = [r for r in records if r["module"] == module and r["line"] == line]
    return found


@pytest.mark.parametrize(
    ("module", "line", "summary", "scoped"),
    [
        ("pitloom.zz_caller", 9, True, False),  # the catalogue's say_summary
        ("pitloom.zz_caller", 10, False, True),  # a plain log.info beside it
        ("pitloom.zz_local", 11, False, False),  # own say_summary: its body counts
        ("pitloom.zz_local", 7, False, True),  # ... here
    ],
    ids=["catalogue-call", "plain-info", "local-call", "local-body"],
)
def test_a_summary_is_out_of_scope_by_its_definition(
    mi: ModuleType,
    records: list[dict[str, Any]],
    module: str,
    line: int,
    summary: bool,
    scoped: bool,
) -> None:
    site = _site(records, module, line)
    assert mi.is_summary(site) is summary
    assert mi.in_scope(site) is scoped


def test_the_rule_needs_the_catalogue_definition(
    mi: ModuleType, records: list[dict[str, Any]]
) -> None:
    """The same call reaching another module's definition is no summary."""
    site = dict(_site(records, "pitloom.zz_caller", 9))
    site["helper_def"] = "src/pitloom/zz_local.py:6"
    assert not mi.is_summary(site)
    site["helper_def"] = "src/pitloom/messages/_summary.py:1"
    site["helper"] = "say_other"
    assert not mi.is_summary(site)
