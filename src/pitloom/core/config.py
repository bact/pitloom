# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom tool configuration read from ``[tool.pitloom]`` in ``pyproject.toml``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pitloom.core.creation import Creator, ToolInfo

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


#: Old (pre-multi-creator) ``[tool.pitloom.creation]`` keys that moved to
#: ``[[tool.pitloom.creator]]`` / ``[[tool.pitloom.creation-tool]]``.
_MOVED_CREATION_KEYS: dict[str, str] = {
    "creator-name": "[[tool.pitloom.creator]] (key: name)",
    "creator_name": "[[tool.pitloom.creator]] (key: name)",
    "creator-email": "[[tool.pitloom.creator]] (key: email)",
    "creator_email": "[[tool.pitloom.creator]] (key: email)",
    "creator-type": "[[tool.pitloom.creator]] (key: type)",
    "creator_type": "[[tool.pitloom.creator]] (key: type)",
    "creation-tool": "[[tool.pitloom.creation-tool]] (key: name)",
    "creation_tool": "[[tool.pitloom.creation-tool]] (key: name)",
}


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
        creators: Named creators read from ``[[tool.pitloom.creator]]``
            array-of-tables.  Empty when none are configured.
        tools: Creation tools read from ``[[tool.pitloom.creation-tool]]``
            array-of-tables.  ``None`` when not configured (caller default
            applies); an explicit ``no-creation-tool = true`` under
            ``[tool.pitloom.creation]`` maps to an empty list.
        creation_datetime: Optional creation timestamp override from
            ``[tool.pitloom.creation]``.
        creation_comment: Optional comment mapped to SPDX ``CreationInfo.comment``.
    """

    fragments: list[str] = field(default_factory=list)
    pretty: bool = False
    describe_relationship: bool | None = None
    sbom_basename: str | None = None
    creators: list[Creator] = field(default_factory=list)
    tools: list[ToolInfo] | None = None
    creation_datetime: str | None = None
    creation_comment: str | None = None


def _check_moved_creation_keys(
    pitloom_data: dict[str, Any], creation_data: dict[str, Any]
) -> None:
    """Raise a clear error if old single-valued creator/tool keys are present.

    These keys used to be accepted either directly under ``[tool.pitloom]``
    or under ``[tool.pitloom.creation]`` -- both locations are checked here.

    ``[tool.pitloom]`` needs an extra check that ``[tool.pitloom.creation]``
    doesn't: the new ``[[tool.pitloom.creation-tool]]`` array-of-tables
    legitimately reuses the top-level key name ``creation-tool`` (as a list
    of tables), so only a *string* value under that name at the top level
    is the old, moved, single-valued usage -- a list is the new form and
    must not be flagged.
    """
    for key in pitloom_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is not None and isinstance(pitloom_data[key], str):
            raise ValueError(
                f"[tool.pitloom] {key!r} has moved to {moved_to}. "
                "Update your pyproject.toml."
            )
    for key in creation_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is not None:
            raise ValueError(
                f"[tool.pitloom.creation] {key!r} has moved to {moved_to}. "
                "Update your pyproject.toml."
            )


def _read_creators(pitloom_data: dict[str, Any]) -> list[Creator]:
    """Read ``[[tool.pitloom.creator]]`` array-of-tables into ``Creator`` objects."""
    raw = pitloom_data.get("creator", [])
    if not isinstance(raw, list):
        return []
    creators: list[Creator] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        creator_type = entry.get("type")
        email = entry.get("email")
        creators.append(
            Creator(
                name=name,
                type=creator_type if isinstance(creator_type, str) else "person",
                email=email if isinstance(email, str) else None,
            )
        )
    return creators


def _read_tools(pitloom_data: dict[str, Any]) -> list[ToolInfo] | None:
    """Read ``[[tool.pitloom.creation-tool]]`` array-of-tables into ``ToolInfo``."""
    raw = pitloom_data.get("creation-tool", pitloom_data.get("creation_tool"))
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    tools: list[ToolInfo] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            tools.append(ToolInfo(name=name))
    return tools


def _read_pitloom_config(data: dict[str, Any]) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`.

    Creators come from ``[[tool.pitloom.creator]]``, tools from
    ``[[tool.pitloom.creation-tool]]``; ``[tool.pitloom.creation]`` still
    carries the document-level singletons: ``creation-datetime``,
    ``creation-comment``, and ``no-creation-tool``.

    Raises:
        ValueError: If ``[tool.pitloom]`` or ``[tool.pitloom.creation]``
            still has old single-valued ``creator-name``/``creator-email``/
            ``creator-type``/``creation-tool`` keys -- these moved to the
            array-of-tables form.
    """
    pitloom_data = data.get("tool", {}).get("pitloom", {})
    creation_data = pitloom_data.get("creation", {})
    if not isinstance(creation_data, dict):
        creation_data = {}

    _check_moved_creation_keys(pitloom_data, creation_data)

    def _pick_str(*sources: tuple[dict[str, Any], tuple[str, ...]]) -> str | None:
        """Return the first string found by key, scanning *sources* in order.

        Each source is checked fully (all its keys) before moving to the
        next, so an explicit empty string in a higher-priority source is
        returned as-is -- it does not fall through to a lower-priority
        source the way ``a or b`` would.
        """
        for source, keys in sources:
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

    creators = _read_creators(pitloom_data)
    tools = _read_tools(pitloom_data)
    no_creation_tool = creation_data.get("no-creation-tool")
    if no_creation_tool is None:
        no_creation_tool = creation_data.get("no_creation_tool")
    if no_creation_tool:
        tools = []

    creation_datetime = _pick_str(
        (creation_data, ("creation-datetime", "creation_datetime", "datetime")),
        (pitloom_data, ("creation-datetime", "creation_datetime")),
    )
    creation_comment = _pick_str(
        (creation_data, ("creation-comment", "creation_comment", "comment")),
        (pitloom_data, ("creation-comment", "creation_comment")),
    )

    return PitloomConfig(
        pretty=pretty,
        fragments=fragments,
        describe_relationship=desc_rel,
        sbom_basename=sbom_basename,
        creators=creators,
        tools=tools,
        creation_datetime=creation_datetime,
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
