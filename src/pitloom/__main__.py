# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom SBOM generator."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pitloom.__about__ import __version__
from pitloom.assemble import generate_sbom
from pitloom.core.creation import CreationMetadata

_SPDX3_JSON_EXT = ".spdx3.json"


def _resolve_output_path(explicit: Path | None, project_dir: Path) -> Path:
    """Return the SBOM output path to use.

    Priority:
    1. Explicit ``-o`` / ``--output`` argument.
    2. ``[tool.pitloom] sbom-basename`` from ``pyproject.toml``
       → ``<basename>.spdx3.json``.
    3. ``<name>-<version>.spdx3.json`` derived from project metadata.
    4. Fallback: ``sbom.spdx3.json``.
    """
    if explicit is not None:
        return explicit

    try:
        # pylint: disable=import-outside-toplevel
        from pitloom.extract.pyproject import read_pyproject

        metadata, pitloom_config = read_pyproject(project_dir / "pyproject.toml")

        if pitloom_config.sbom_basename:
            return Path(f"{pitloom_config.sbom_basename}{_SPDX3_JSON_EXT}")

        parts = [metadata.name] if metadata.name else ["sbom"]
        if metadata.version:
            parts.append(metadata.version)
        return Path("-".join(parts) + _SPDX3_JSON_EXT)

    except Exception:  # pylint: disable=broad-exception-caught
        return Path(f"sbom{_SPDX3_JSON_EXT}")


def main() -> int:
    """Main entry point for the Pitloom CLI.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Pitloom - Generate SPDX 3 SBOM for Python projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"Pitloom {__version__}",
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
        default=None,
        help=(
            "Output file path. "
            "Default: <name>-<version>.spdx3.json derived from pyproject.toml, "
            "or the basename from [tool.pitloom] sbom-basename if set."
        ),
    )
    parser.add_argument(
        "--creator-name",
        type=str,
        help="Name of the SBOM creator (default: Pitloom)",
    )
    parser.add_argument(
        "--creator-email",
        type=str,
        help="Email of the SBOM creator",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=None,
        help=(
            "Pretty-print the SBOM output with 2-space indentation. "
            "Overrides 'pretty' in [tool.pitloom] in pyproject.toml. "
            "Default is compact output (machine-optimized)."
        ),
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

        output_path = _resolve_output_path(args.output, project_dir)

        print(f"Generating SBOM for project in: {project_dir}")
        generate_sbom(
            project_dir,
            output_path=output_path,
            creation_info=CreationMetadata(
                creator_name=args.creator_name or "Pitloom",
                creator_email=args.creator_email or "",
            ),
            pretty=args.pretty,
        )
        print(f"SBOM written to: {output_path}")
        return 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error generating SBOM: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
