# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project directory whose one named file exists but cannot be read, on
every platform and for any user (a permission bit cannot be set on Windows
and means nothing to root): the file's ``open()`` and ``read_bytes()`` raise
an ``OSError``, patched on this path class only, so no other thread sees it.

See also: tests/_code_records.py (the coded lines a test captured).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast


def unreadable(root: Path, member: str, error: OSError | None = None) -> Path:
    """*root*, as a path whose file named *member* raises *error* (default a
    ``PermissionError``) when it is opened or read: a read failure after the
    existence check, as a file made unreadable since."""
    raised = PermissionError(13, "denied") if error is None else error

    # pylint: disable-next=too-few-public-methods
    class _Path(type(root)):  # type: ignore[misc]
        def open(self, *args: Any, **kwargs: Any) -> Any:
            if self.name == member:
                raise raised
            return super().open(*args, **kwargs)

        def read_bytes(self) -> bytes:
            if self.name == member:
                raise raised
            return cast(bytes, super().read_bytes())

    return cast(Path, _Path(root))
