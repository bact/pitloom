# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""Detect ML frameworks from project dependencies and source imports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

_FRAMEWORK_DEPS: dict[str, str] = {
    "torch": "PyTorch",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "jax": "JAX",
    "flax": "Flax",
    "scikit-learn": "scikit-learn",
}

_FRAMEWORK_IMPORTS: dict[str, str] = {
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "jax": "JAX",
    "flax": "Flax",
    "sklearn": "scikit-learn",
}


def detect_frameworks(
    dependencies: Sequence[str],
    source_dirs: Sequence[Path] | None = None,
) -> set[str]:
    """Detect ML frameworks from package dependencies and Python source imports.

    Args:
        dependencies: Requirement strings from project metadata.
        source_dirs: Directories to scan for ``import`` statements.

    Returns:
        A set of canonical framework names detected.
    """
    detected: set[str] = set()

    for dep in dependencies:
        name = re.split(r"[\[<>=!~;\s]", dep.strip())[0].lower()
        for pattern, framework in _FRAMEWORK_DEPS.items():
            if pattern == name:
                detected.add(framework)
                break

    if source_dirs:
        for src_dir in source_dirs:
            if not src_dir.is_dir():
                continue
            for py_file in src_dir.rglob("*.py"):
                try:
                    text = py_file.read_text(encoding="utf-8")
                    for imp_name, framework in _FRAMEWORK_IMPORTS.items():
                        if re.search(rf"\bimport\s+{re.escape(imp_name)}\b", text) or \
                           re.search(rf"\bfrom\s+{re.escape(imp_name)}\s+import\b", text):
                            detected.add(framework)
                except (OSError, UnicodeDecodeError):
                    continue

    return detected
