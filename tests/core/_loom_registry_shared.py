# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_loom_registry.py and test_loom_registry_set_model.py.

See also: test_loom_registry.py, test_loom_registry_set_model.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# An existing on-disk file, stable across the test run, used as a stand-in
# "dataset" so add_dataset()'s "name is an existing file" branch engages.
_EXISTING_FILE = "pyproject.toml"


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
