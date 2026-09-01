# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import sys
import typing

from pitloom.cli.parser import _build_parser
from pitloom.logging_config import apply_debug_override, configure_logging


def main() -> int:
    """Main entry point for the Pitloom CLI."""
    parser = _build_parser()
    args = parser.parse_args()
    # Parsed before configuring so --debug/--no-debug (parsed here,
    # unlike PITLOOM_DEBUG) can take effect. Routed through PITLOOM_DEBUG
    # itself (see apply_debug_override()'s docstring) rather than passed
    # as configure_logging(debug=...) here, so every subcommand's own
    # bare configure_logging() call agrees with this one instead of
    # silently reverting to INFO. getattr() rather than args.debug: a
    # Namespace missing "func" (see
    # test_main_returns_1_when_parsed_args_have_no_func) may lack every
    # other attribute too.
    apply_debug_override(getattr(args, "debug", None))
    configure_logging()

    if hasattr(args, "func"):
        return typing.cast(int, args.func(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
