# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import glob
import sys
from pathlib import Path


def _collect_wheel_paths(patterns: list[str]) -> list[Path]:
    """Resolve and expand wheel file paths and glob patterns.

    Every pattern is validated before returning, and every error is
    reported here -- the caller can treat an empty return as "already
    explained on stderr", with no need to re-inspect the patterns itself.
    """
    wheel_paths: list[Path] = []
    had_error = False
    for pattern in patterns:
        if any(c in pattern for c in ("*", "?", "[")):
            matched = [
                Path(p).resolve()
                for p in glob.glob(pattern)
                if Path(p).is_file() and p.endswith(".whl")
            ]
            if not matched:
                print(f"ERROR: no wheel files matched: {pattern}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.extend(matched)
        else:
            p = Path(pattern).resolve()
            if not p.exists():
                print(f"ERROR: wheel file not found: {p}", file=sys.stderr)
                had_error = True
                continue
            if not p.name.endswith(".whl"):
                print(f"ERROR: not a .whl file: {p}", file=sys.stderr)
                had_error = True
                continue
            wheel_paths.append(p)
    if had_error:
        return []
    return list(dict.fromkeys(wheel_paths))
