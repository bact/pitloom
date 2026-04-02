# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom tool configuration read from ``[tool.pitloom]`` in ``pyproject.toml``."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PitloomConfig:
    """Settings from the ``[tool.pitloom]`` section of ``pyproject.toml``.

    All fields have safe defaults so that a project without a ``[tool.pitloom]``
    section works out of the box.  Adding new ``[tool.pitloom]`` options in
    future versions only requires adding a new field here with a default value.

    Attributes:
        fragments: List of paths to pre-generated SPDX 3 JSON-LD fragment
            files, relative to the project directory.  These are merged into
            the final SBOM document at generation time.
        pretty: When ``True``, the serialised SBOM JSON is indented with
            2 spaces for human readability.  Defaults to ``False`` (compact,
            machine-optimised output).
        sbom_basename: Base name for the generated SBOM file (no extension).
            The full filename is derived by appending the format-specific
            extension (e.g., ``".spdx3.json"``).
            When ``None``, callers choose a context-appropriate default.
        creation_creator_name: Optional creator name override from
            ``[tool.pitloom.creation]``.
        creation_creator_email: Optional creator email override from
            ``[tool.pitloom.creation]``.
        creation_creation_datetime: Optional creation timestamp override from
            ``[tool.pitloom.creation]``.
        creation_creation_tool: Optional creation tool name override from
            ``[tool.pitloom.creation]``.
        creation_comment: Optional comment mapped to SPDX ``CreationInfo.comment``.
    """

    fragments: list[str] = field(default_factory=list)
    pretty: bool = False
    describe_relationship: bool | None = None
    sbom_basename: str | None = None
    creation_creator_name: str | None = None
    creation_creator_email: str | None = None
    creation_creation_datetime: str | None = None
    creation_creation_tool: str | None = None
    creation_comment: str | None = None


__all__ = ["PitloomConfig"]
