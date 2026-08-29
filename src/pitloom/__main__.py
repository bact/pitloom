# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import sys
import typing

from pitloom.cli.parser import _build_parser
from pitloom.logging_config import configure_logging


def main() -> int:
    """Main entry point for the Pitloom CLI."""
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
