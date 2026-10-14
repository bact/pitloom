# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``poetry.lock`` written for a test, shared by test_poetry.py and
test_poetry_integration.py.

See also: tests/extract/lock/test_poetry.py.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["METADATA", "write_lock"]

#: Every real ``poetry lock``-generated file carries this table --
#: `extract_poetry_lock_dependencies()` uses its presence to distinguish
#: a genuine (if empty) poetry.lock from an unrelated/truncated TOML
#: document that merely happens to be named ``poetry.lock``. Appended by
#: :func:`write_lock`, so a test of the ``package`` list need not repeat it.
METADATA = '[metadata]\nlock-version = "2.1"\n'


def write_lock(tmp_dir: Path, content: str) -> None:
    """Write *content*, then :data:`METADATA`, as *tmp_dir*'s ``poetry.lock``."""
    # Appended, not prepended: a bare top-level `key = value` line in
    # *content* (e.g. a malformed `package = "not-a-list"` test fixture)
    # would otherwise land inside the `[metadata]` table itself if
    # `METADATA`'s `[metadata]` header came first in the file.
    (tmp_dir / "poetry.lock").write_text(content + METADATA, encoding="utf-8")
