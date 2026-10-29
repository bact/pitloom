# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The run's report of Git LFS pointers among a document's files.

:func:`~pitloom.assemble.spdx3.document.build` is where the CLI, the
library, the build hook and the Action converge, so it says this once per
document: a ``DEBUG`` line per pointer and one ``WARNING:`` per kind (a
checkout's pointers, and the pointers an archive, a build or the hook
shipped). Both kinds in one run give two lines.
"""

from __future__ import annotations

from collections.abc import Iterable

from pitloom.core.lfs_pointer import log_pointer_not_read, warn_pointers_not_read
from pitloom.core.project import ProjectFile

__all__ = ["report_lfs_pointers"]


def report_lfs_pointers(files: Iterable[ProjectFile]) -> None:
    """Log each pointer among *files* and warn once per kind.

    A checkout's pointer is recorded by its ``oid`` alone (no SHA-512); any
    other pointer was hashed as the bytes it holds.
    """
    checkout: set[str] = set()
    shipped: set[str] = set()
    for project_file in files:
        pointer = project_file.lfs_pointer
        if pointer is None:
            continue
        log_pointer_not_read(project_file.distribution_path, pointer)
        kind = checkout if project_file.digest_sha512 is None else shipped
        kind.add(project_file.distribution_path)
    warn_pointers_not_read(sorted(checkout))
    warn_pointers_not_read(sorted(shipped), archive=True)
