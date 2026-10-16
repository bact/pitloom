# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by the two sync-claim test modules.

See also: test_generator_registry_sync_claim.py,
test_generator_registry_sync_claim_resolve.py.
"""

from __future__ import annotations

import hashlib

from pitloom.core.project import ProjectFile


def _files_for(contents: dict[str, str]) -> list[ProjectFile]:
    """One ``ProjectFile`` per ``{name: content}`` entry, sorted by name
    for deterministic iteration order."""
    return [
        ProjectFile(
            physical_path=f"demo/{name}",
            distribution_path=f"demo/{name}",
            digest_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
        for name, content in sorted(contents.items())
    ]
