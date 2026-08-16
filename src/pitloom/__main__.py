# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import logging
import sys
import typing

from pitloom.cli.parser import _build_parser

_SPDX3_JSON_EXT = ".spdx3.json"
_PROJECT_PYPROJECT_SOURCE = "pyproject.toml"
_PROJECT_SETUP_CFG_SOURCE = "setup.cfg"
_PROJECT_SETUP_PY_SOURCE = "setup.py"


def _configure_logging() -> None:
    """Prefix internal ``log.warning(...)`` output with ``WARNING: ``.

    Without this, Python's last-resort handler prints library warnings
    (``pitloom.ids``, ``pitloom.loom``, etc.) to stderr with no prefix at
    all, breaking the CLI's shared grep-able ``LEVEL: <description>``
    convention (see ``ERROR:``, used by this module's own ``print()``
    calls). Reconfigures on every call rather than guarding with a
    "configured once" flag, so repeated ``main()`` calls in the same
    process (e.g. across tests) don't stack duplicate handlers.
    Propagation to the root logger is left untouched, so ``pytest``'s
    ``caplog`` fixture still captures these records.
    """
    logger = logging.getLogger("pitloom")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


def main() -> int:
    """Main entry point for the Pitloom CLI."""
    _configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1
