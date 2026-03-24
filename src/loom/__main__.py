# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Loom SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from loom.__about__ import __version__
from loom.generator import generate_sbom_to_file


def main() -> int:
    """Main entry point for the Loom CLI.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Loom - Generate SPDX 3.0 SBOM for Python projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"loom {__version__}",
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to the project directory (containing pyproject.toml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="sbom.spdx3.json",
        help="Output file path (default: sbom.spdx3.json)",
    )
    parser.add_argument(
        "--creator-name",
        type=str,
        help="Name of the SBOM creator (default: Loom)",
    )
    parser.add_argument(
        "--creator-email",
        type=str,
        help="Email of the SBOM creator",
    )

    args = parser.parse_args()

    try:
        project_dir = args.project_dir.resolve()
        if not project_dir.exists():
            print(f"Error: Project directory not found: {project_dir}", file=sys.stderr)
            return 1

        pyproject_path = project_dir / "pyproject.toml"
        if not pyproject_path.exists():
            print(
                f"Error: pyproject.toml not found in {project_dir}",
                file=sys.stderr,
            )
            return 1

        print(f"Generating SBOM for project in: {project_dir}")
        generate_sbom_to_file(
            project_dir,
            args.output,
            creator_name=args.creator_name,
            creator_email=args.creator_email,
        )
        print(f"SBOM written to: {args.output}")
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
