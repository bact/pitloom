# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for CLI commands."""

from __future__ import annotations

import glob
import sys
import traceback
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any


def cli_error_handler(
    error_msg: str,
) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """Decorator to standardize CLI error handling and tracebacks."""

    def decorator(func: Callable[..., int]) -> Callable[..., int]:
        @wraps(func)
        def wrapper(args: Any, *pargs: Any, **kwargs: Any) -> int:
            try:
                return func(args, *pargs, **kwargs)
            # pylint: disable=broad-exception-caught
            except Exception as e:
                print(f"ERROR: {error_msg}: {e}", file=sys.stderr)
                if getattr(args, "verbose", False):
                    traceback.print_exc()
                return 1

        return wrapper

    return decorator


def _collect_wheel_paths(patterns: list[str]) -> list[Path]:
    """Resolve and expand wheel file paths and glob patterns.

    Every pattern is validated before returning, and every error is
    reported here -- the caller can treat an empty return as "already
    explained on stderr", with no need to re-inspect the patterns itself.
    """
    wheel_paths: list[Path] = []
    had_error = False
    for pattern in patterns:
        if glob.has_magic(pattern):
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
