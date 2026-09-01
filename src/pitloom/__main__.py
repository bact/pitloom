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
    parser = _build_parser()
    args = parser.parse_args()
    # Parsed before configuring so --debug (parsed here, unlike
    # PITLOOM_DEBUG) can select the logger level up front. getattr()
    # rather than args.debug: a Namespace missing "func" (see
    # test_main_returns_1_when_parsed_args_have_no_func) may lack every
    # other attribute too.
    configure_logging(debug=getattr(args, "debug", False) or None)

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
