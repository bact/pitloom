# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom tool configuration read from ``[tool.pitloom]`` in ``pyproject.toml``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


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


def _read_pitloom_config(data: dict[str, Any]) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`.

    Creation metadata can be set in either ``[tool.pitloom.creation]``
    (preferred) or legacy flat keys under ``[tool.pitloom]``.
    """
    pitloom_data = data.get("tool", {}).get("pitloom", {})
    creation_data = pitloom_data.get("creation", {})
    if not isinstance(creation_data, dict):
        creation_data = {}

    def _pick_str(source: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str):
                return value
        return None

    raw_fragments = pitloom_data.get("fragments", {}).get("files", [])
    fragments = (
        [str(f) for f in raw_fragments] if isinstance(raw_fragments, list) else []
    )
    pretty = bool(pitloom_data.get("pretty", False))
    desc_rel = pitloom_data.get("describe-relationship")
    if desc_rel is None:
        desc_rel = pitloom_data.get("describe_relationship")
    if desc_rel is not None:
        desc_rel = bool(desc_rel)
    sbom_basename: str | None = pitloom_data.get("sbom-basename") or None
    creation_creator_name = _pick_str(
        creation_data, ("creator-name", "creator_name")
    ) or _pick_str(pitloom_data, ("creator-name", "creator_name"))
    creation_creator_email = _pick_str(
        creation_data, ("creator-email", "creator_email")
    ) or _pick_str(pitloom_data, ("creator-email", "creator_email"))
    creation_creation_datetime = _pick_str(
        creation_data,
        ("creation-datetime", "creation_datetime", "datetime"),
    ) or _pick_str(pitloom_data, ("creation-datetime", "creation_datetime"))
    creation_creation_tool = _pick_str(
        creation_data,
        ("creation-tool", "creation_tool", "tool"),
    ) or _pick_str(pitloom_data, ("creation-tool", "creation_tool"))
    creation_comment = _pick_str(
        creation_data,
        ("creation-comment", "creation_comment", "comment"),
    ) or _pick_str(pitloom_data, ("creation-comment", "creation_comment"))

    return PitloomConfig(
        pretty=pretty,
        fragments=fragments,
        describe_relationship=desc_rel,
        sbom_basename=sbom_basename,
        creation_creator_name=creation_creator_name,
        creation_creator_email=creation_creator_email,
        creation_creation_datetime=creation_creation_datetime,
        creation_creation_tool=creation_creation_tool,
        creation_comment=creation_comment,
    )


def read_pitloom_config(pyproject_path: Path) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings directly from a ``pyproject.toml`` file.

    Thin wrapper around :func:`_read_pitloom_config` for callers that only
    need Pitloom's own settings without re-deriving project metadata (e.g.
    the Hatchling build hook, which gets project metadata from
    :func:`~pitloom.extract.hatchling.metadata_from_hatchling` instead).

    Args:
        pyproject_path: Path to the ``pyproject.toml`` file.

    Returns:
        A :class:`PitloomConfig`; all fields default gracefully when the
        ``[tool.pitloom]`` section is absent.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    return _read_pitloom_config(data)


__all__ = ["PitloomConfig", "read_pitloom_config"]
