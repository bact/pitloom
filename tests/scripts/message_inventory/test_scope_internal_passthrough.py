# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``: only its class makes a raise an
internal invariant (``InternalError``), never its text; a bare ``%s``
template is out of scope only where the site forwards the code of the text
it says (``extra=code_extra_of(exc)``, or a name the function binds to
``relay_extra(...)``).

Each case is a line of :data:`SOURCE` ending in ``# in: <id>`` (the ratchet
counts it) or ``# out: <id>`` (it does not).

See also: test_scope_library.py (library misuse), test_inventory.py.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
import logging

from pitloom.core.internal_error import InternalError
from pitloom.messages import code_extra_of, relay_extra

_log = logging.getLogger(__name__)


def raises(value):
    raise RuntimeError("EmbedFileCache is already entered")  # in: old-text
    raise ValueError("no ID registry loaded in this session")  # in: old-value
    raise RuntimeError(f"Duplicate spdxId {value}: a and b")  # in: old-format
    raise InternalError("EmbedFileCache is already entered")  # out: internal


def bare(text):
    _log.warning("%s", text)  # in: bare


def forward_inline(exc, text):
    _log.warning("%s", text, extra=code_extra_of(exc))  # out: forward-inline


def forward_by_name(record, text):
    extra = None if record is None else relay_extra(record, "WARNING", text)
    _log.warning("%s", text, extra=extra)  # out: forward-by-name


def name_without_code(text):
    extra = {"x": 1}
    _log.warning("%s", text, extra=extra)  # in: name-no-code


def name_in_nested_scope(record, text):
    def inner():
        extra = relay_extra(record, "WARNING", text)
        return extra

    extra = None
    _log.warning("%s", text, extra=extra)  # in: name-nested


def other_name(record, text):
    fwd = relay_extra(record, "WARNING", text)
    extra = None
    _log.warning("%s", text, extra=extra)  # in: other-name


class _CodedByName(Exception):
    def __init__(self, text):
        extra = {"pitloom_code": "x"}
        super().__init__(text, extra=extra)


def raises_coded_by_name(text):
    raise _CodedByName(text)


def forward_with_text(exc, text):
    _log.warning("%s; skipped", text, extra=code_extra_of(exc))  # in: own-text


def two(exc, a, b):
    _log.error("%s%s", a, b, extra=code_extra_of(exc))  # in: two-parts
"""

_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (n, mark[0] == "in", mark[1])
    for n, line in enumerate(SOURCE.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` as ``src/pitloom/sayer.py``."""
    root = tmp_path_factory.mktemp("internal-passthrough")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (package / "sayer.py").write_bytes(SOURCE.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def test_every_case_is_found() -> None:
    assert len(CASES) == 12


@pytest.mark.parametrize(
    ("line", "scoped"),
    [(n, scoped) for n, scoped, _ in CASES],
    ids=[case_id for _, _, case_id in CASES],
)
def test_only_the_class_or_a_forwarded_code_leaves_a_site_out(
    mi: ModuleType, records: list[dict[str, Any]], line: int, scoped: bool
) -> None:
    (site,) = [r for r in records if r["line"] == line]
    assert not site["coded"]
    assert mi.in_scope(site) is scoped


def test_a_class_coding_by_name_codes_its_raise(
    records: list[dict[str, Any]],
) -> None:
    """A class body's ``extra=<name>`` is read through the method that
    binds the name, as at a site: a raise of the class is coded."""
    (site,) = [r for r in records if r["function"] == "raises_coded_by_name"]
    assert site["emitter"] == "raise" and site["coded"]


def test_no_text_pattern_marks_an_internal_invariant(mi: ModuleType) -> None:
    """The list of internal texts is gone for good: a raise is internal by
    its class alone."""
    scope = importlib.import_module(f"{mi.__name__}._scope")
    assert not hasattr(scope, "INTERNAL_PAT")
