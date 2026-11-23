# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``: a raise is a library caller's
misuse, out of scope, only through the helpers of ``LIBRARY_EXC`` (the loom
SDK outside a ``loom.run()``) or in a function ``LIBRARY_SITES`` names (a
value of the wrong Python type); a library text alone (``loom SDK: ...``,
``No model set``) or a ``TypeError`` elsewhere stays counted.

Each case is a line of :data:`SOURCE` or :data:`SITE_SOURCE` ending in
``# in: <id>`` (the ratchet counts it) or ``# out: <id>`` (it does not).

See also: test_scope_os_error.py (rule R-a), test_inventory.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
def call(value):
    raise _no_active_run("set_model")  # out: no-active-run
    raise TypeError(f"loom SDK: declared_license is not a str: {value}")  # in: type
    raise TypeError("x")  # in: bare-type
    raise _no_model_set("x")  # in: other-helper
    raise RuntimeError("No active loom.run() found")  # in: library-text
    raise RuntimeError("No model set. Call set_model() first.")  # in: no-model-text
    raise ValueError("loom SDK: croissant= is a URL")  # in: sdk-prefix
    raise ValueError("loom: croissant= is a URL")  # in: old-prefix
    raise ValueError("x is a Hugging Face source; not enriched")  # in: hf
"""
#: The one function ``LIBRARY_SITES`` names, and another in its file.
SITE_SOURCE = """\
def _declared_licence(value):
    raise TypeError(f"loom SDK: declared_license is not a str: {value}")  # out: site
def other(value):
    raise TypeError(f"loom SDK: declared_license is not a str: {value}")  # in: other
"""
_FILES = {"caller.py": SOURCE, "_loom_dataset_meta.py": SITE_SOURCE}

_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (name, n, mark[0] == "in", mark[1])
    for name, source in _FILES.items()
    for n, line in enumerate(source.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` as ``src/pitloom/caller.py``."""
    root = tmp_path_factory.mktemp("library")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in _FILES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def test_every_case_is_found() -> None:
    assert len(CASES) == 11


@pytest.mark.parametrize(
    ("name", "line", "scoped"),
    [(name, n, scoped) for name, n, scoped, _ in CASES],
    ids=[case_id for _, _, _, case_id in CASES],
)
def test_only_the_helper_or_a_named_site_is_library_misuse(
    mi: ModuleType,
    records: list[dict[str, Any]],
    name: str,
    line: int,
    scoped: bool,
) -> None:
    (site,) = [
        r for r in records if r["file"] == f"src/pitloom/{name}" and r["line"] == line
    ]
    assert mi.in_scope(site) is scoped
