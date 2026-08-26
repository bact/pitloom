# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pitloom.__about__ import __version__
from pitloom.cli.commands.embed_wheel import add_parser as add_embed_wheel
from pitloom.cli.commands.enrich import add_parser as add_enrich
from pitloom.cli.commands.env import add_parser as add_env
from pitloom.cli.commands.generate import add_parser as add_generate
from pitloom.cli.commands.merge import add_parser as add_merge
from pitloom.cli.commands.model import add_parser as add_model
from pitloom.cli.commands.project import add_parser as add_project
from pitloom.cli.commands.wheel import add_parser as add_wheel
from pitloom.cli.ids import add_parser as add_ids
from pitloom.core.config import VALID_CONTENT_TYPE_METHODS
from pitloom.core.creation import (
    VALID_CREATOR_TYPES,
    Creator,
)


class _CreatorNameAction(argparse.Action):
    """``--creator-name`` starts a new :class:`Creator`, appended in order."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] = getattr(namespace, self.dest) or []
        creators.append(Creator(name=values))
        setattr(namespace, self.dest, creators)


class _CreatorTypeAction(argparse.Action):
    """``--creator-type`` sets the type of the most recently named creator."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] | None = getattr(namespace, self.dest)
        if creators is None or len(creators) == 0:
            parser.error(f"{option_string} must come after a --creator-name")
            return  # type: ignore[unreachable]
        creators[-1] = Creator(
            name=creators[-1].name,
            type=values,
            email=creators[-1].email,
        )


class _CreatorEmailAction(argparse.Action):
    """``--creator-email`` sets the email of the most recently named creator."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        creators: list[Creator] | None = getattr(namespace, self.dest)
        if creators is None or len(creators) == 0:
            parser.error(f"{option_string} must come after a --creator-name")
            return  # type: ignore[unreachable]
        creators[-1] = Creator(
            name=creators[-1].name,
            type=creators[-1].type,
            email=values,
        )


def _build_parent_parser() -> argparse.ArgumentParser:
    """Build shared parent parser with common options."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="FILE",
        help="Write JSON-LD SBOM to FILE.",
    )
    parent.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Indent JSON output with 2 spaces.",
    )
    parent.add_argument(
        "--describe-relationship",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include human-readable text on SPDX relationships.",
    )
    parent.add_argument(
        "--enrich",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Run local README/model-card enrichment for discovered AI "
            "models. Defers to [tool.pitloom] enrich (off by default) "
            "when omitted."
        ),
    )
    parent.add_argument(
        "--extract-file-header",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Scan each source file's leading comment header for SPDX-File* "
            "tags (FileCopyrightText, FileContributor, FileType) and a "
            "per-file SPDX-License-Identifier. Defers to "
            "[tool.pitloom] extract-file-header (on by default) when "
            "omitted."
        ),
    )
    parent.add_argument(
        "--content-type",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Detect each file's real content type via magika/mimetypes, "
            "independent of --extract-file-header. Defers to "
            "[tool.pitloom.content-type] enabled (off by default -- real "
            "per-file cost) when omitted."
        ),
    )
    parent.add_argument(
        "--content-type-method",
        choices=VALID_CONTENT_TYPE_METHODS,
        default=None,
        help=(
            "Which detector resolves --content-type's contentType values: "
            "'auto' (try magika, fall back to a filename-extension guess), "
            "'magika' (same, but error immediately if the magika package "
            "isn't installed), or 'extension' (skip magika entirely, "
            "stdlib-only). Defers to [tool.pitloom.content-type] method "
            "('auto' by default) when omitted."
        ),
    )
    parent.add_argument(
        "--max-source-metadata-bytes",
        type=int,
        default=None,
        metavar="BYTES",
        help=(
            "Cap the artifact-metadata preservation Annotation's serialized "
            "size to this many UTF-8 bytes; truncates the largest metadata "
            "entries first when exceeded. 0 (or any value too small to "
            "hold data) disables the cap. Defers to "
            "[tool.pitloom.provenance] max-source-metadata-bytes (0, "
            "unbounded, by default) when omitted."
        ),
    )
    parent.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose execution and option details.",
    )
    parent.add_argument(
        "--registry",
        type=Path,
        default=None,
        metavar="FILE",
        help="Loom ID registry JSON file path.",
    )
    parent.add_argument(
        "--update-registry",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "After generating, harvest newly-minted ids back into the "
            "resolved Loom ID registry and save it. Defers to "
            "[tool.pitloom] update-registry (on by default) when omitted; "
            "no effect when no registry is resolved. Only consulted by "
            "'project'/'wheel'/'env'/'generate' -- accepted but has no "
            "effect on 'model'/'enrich'/'embed-wheel', which don't "
            "auto-update the registry."
        ),
    )

    creator_group = parent.add_argument_group("Creator metadata")
    creator_group.add_argument(
        "--creator-name",
        action=_CreatorNameAction,
        dest="creators",
        default=None,
        metavar="NAME",
        help="Name of creator.",
    )
    creator_group.add_argument(
        "--creator-type",
        action=_CreatorTypeAction,
        dest="creators",
        default=None,
        choices=VALID_CREATOR_TYPES,
        metavar="TYPE",
        help=f"Type of creator ({', '.join(VALID_CREATOR_TYPES)}).",
    )
    creator_group.add_argument(
        "--creator-email",
        action=_CreatorEmailAction,
        dest="creators",
        default=None,
        metavar="EMAIL",
        help="Email of creator.",
    )
    creator_group.add_argument(
        "--creation-tool",
        action="append",
        dest="creation_tools",
        default=None,
        metavar="NAME",
        help="Tool name used to create SBOM.",
    )
    creator_group.add_argument(
        "--no-creation-tool",
        action="store_true",
        help="Omit createdUsing tool list.",
    )
    creator_group.add_argument(
        "--creation-datetime",
        default=None,
        metavar="ISO8601",
        help="Creation timestamp in UTC ISO 8601 format.",
    )
    creator_group.add_argument(
        "--creation-comment",
        default=None,
        metavar="TEXT",
        help="Comment string for CreationInfo.",
    )
    return parent


def _build_parser() -> argparse.ArgumentParser:
    """Build the main CLI ArgumentParser."""
    parent_parser = _build_parent_parser()

    parser = argparse.ArgumentParser(
        prog="loom",
        description="Pitloom - Generate SPDX 3 SBOMs for Python projects and AI models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"Pitloom {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_generate(subparsers, parent_parser)
    add_project(subparsers, parent_parser)
    add_wheel(subparsers, parent_parser)
    add_embed_wheel(subparsers, parent_parser)
    add_model(subparsers, parent_parser)
    add_enrich(subparsers, parent_parser)
    add_env(subparsers, parent_parser)
    add_merge(subparsers, parent_parser)
    add_ids(subparsers, parent_parser)

    return parser
