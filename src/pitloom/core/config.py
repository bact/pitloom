# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom tool configuration read from ``[tool.pitloom]`` in ``pyproject.toml``."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pitloom.core.creation import Creator, Tool
from pitloom.core.provenance import ProvenanceConfig

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

#: Subset of ``_MOVED_CREATION_KEYS`` where a top-level ``list`` value is
#: valid (the new array-of-tables form) rather than stale -- see
#: :func:`_check_moved_creation_keys`.
_MOVED_CREATION_KEYS_LIST_VALID: frozenset[str] = frozenset(
    {"creation-tool", "creation_tool"}
)

#: Valid ``[tool.pitloom.provenance] format`` values -- see
#: :mod:`pitloom.assemble.spdx3.provenance`. Kept here as a plain literal
#: set (not imported from the assemble layer) because ``core`` must not
#: import from ``assemble``; an unknown *schema* id (as opposed to
#: *format*) is instead caught at build time by
#: :func:`~pitloom.assemble.spdx3.provenance.resolve_encoder`, which is the
#: single source of truth for registered schema ids.
_VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})

#: Default ``[tool.pitloom.provenance] schema`` -- must match
#: ``pitloom.assemble.spdx3.provenance.DEFAULT_SCHEMA_ID``.
_DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"

#: Valid ``[tool.pitloom.provenance] detail`` values. ``minimal`` (default)
#: emits a field-source Annotation only when the source adds signal the native
#: SPDX value cannot convey (inference/detection/sub-file location/declared
#: constraint); ``full`` emits the per-field source map for every field.
_VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})

#: Valid ``[tool.pitloom.provenance] preserve-source-metadata`` values.
#: ``auto`` (default) embeds an artifact's verbatim original metadata blob only
#: when the artifact is not shipped with the distribution (and thus cannot be
#: re-extracted later); ``always``/``never`` are explicit overrides.
_VALID_PRESERVE_SOURCE_METADATA: frozenset[str] = frozenset({"auto", "always", "never"})


@dataclass
# pylint: disable=too-many-instance-attributes
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
        ids_file: Path to the Loom ID registry, from
            ``[tool.pitloom.ids] file``, relative to the project directory.
            ``None`` (default) means auto-discover ``loom-ids.json`` by
            walking up from the project directory -- see
            :meth:`pitloom.ids.IdRegistry.find`.
        provenance_format: How to record metadata provenance, from
            ``[tool.pitloom.provenance] format``. One of ``"annotation"``
            (SPDX Core/Annotation elements only), ``"comment"`` (legacy
            ``Element.comment`` strings only), or ``"both"`` (default).
        provenance_schema: Which statement schema encodes provenance
            Annotations, from ``[tool.pitloom.provenance] schema``.
            Defaults to Pitloom's own ``"pitloom/1"`` schema; see
            :mod:`pitloom.assemble.spdx3.provenance`. An unknown id is not
            rejected here (``core`` must not import the assemble layer's
            encoder registry) -- it is caught with a clear error the first
            time an SBOM is generated.
        provenance_detail: How much per-field provenance to record, from
            ``[tool.pitloom.provenance] detail``. ``"minimal"`` (default)
            emits a field-source Annotation only when the source adds signal
            the native SPDX value cannot convey (a value that was inferred/
            detected rather than read verbatim, a sub-file extraction location,
            a declared constraint differing from the resolved value);
            ``"full"`` emits the per-field source map for every field, for an
            exhaustive extraction audit.
        provenance_preserve_source_metadata: Whether to embed an artifact's
            verbatim original metadata (e.g. an AI model's own header), from
            ``[tool.pitloom.provenance] preserve-source-metadata``. ``"auto"``
            (default) preserves it only when the artifact is not shipped with
            the distribution and thus cannot be re-extracted later;
            ``"always"``/``"never"`` are explicit overrides.
    """

    fragments: list[str] = field(default_factory=list)
    pretty: bool = False
    describe_relationship: bool | None = None
    sbom_basename: str | None = None
    creators: list[Creator] = field(default_factory=list)
    tools: list[Tool] | None = None
    creation_datetime: str | None = None
    creation_comment: str | None = None
    ids_file: str | None = None
    provenance_format: str = "both"
    provenance_schema: str = _DEFAULT_PROVENANCE_SCHEMA
    provenance_detail: str = "minimal"
    provenance_preserve_source_metadata: str = "auto"

    @property
    def provenance(self) -> ProvenanceConfig:
        """Return ProvenanceConfig constructed from current config settings."""
        return ProvenanceConfig(
            format=self.provenance_format,
            schema=self.provenance_schema,
            detail=self.provenance_detail,
            preserve_source_metadata=self.provenance_preserve_source_metadata,
        )


def _check_moved_creation_keys(
    pitloom_data: dict[str, Any], creation_data: dict[str, Any]
) -> None:
    """Raise a clear error if single-valued creator/tool keys are present
    directly under ``[tool.pitloom]`` or ``[tool.pitloom.creation]``; they
    belong in ``[[tool.pitloom.creator]]`` / ``[[tool.pitloom.creation-tool]]``.

    A top-level *list* ``creation-tool`` is the valid array-of-tables form
    and must not be flagged; any other value there (string, int, bool,
    ...) is the old/invalid single-valued form. The other moved keys
    (``creator-name``/``creator-email``/``creator-type``) have no valid
    form at all under ``[tool.pitloom]``, so any value present there --
    regardless of type -- is flagged.
    """
    for key in pitloom_data:
        moved_to = _MOVED_CREATION_KEYS.get(key)
        if moved_to is None:
            continue
        if key in _MOVED_CREATION_KEYS_LIST_VALID and isinstance(
            pitloom_data[key], list
        ):
            continue
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
    """Read ``[[tool.pitloom.creator]]`` array-of-tables into ``Creator`` objects.

    Raises:
        ValueError: If ``creator`` is present but not an array of tables
            (e.g. a single ``[tool.pitloom.creator]`` table, or
            ``creator = ["Alice"]``), or if an entry is not a table or is
            missing a valid (non-empty string) ``name``, or if an entry's
            ``type`` or ``email`` is present but not a string.
    """
    raw = pitloom_data.get("creator")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            "[tool.pitloom.creator] must be an array of tables "
            f"([[tool.pitloom.creator]]), got {type(raw).__name__}"
        )
    creators: list[Creator] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                "[[tool.pitloom.creator]] entry must be a table, got "
                f"{type(entry).__name__}: {entry!r}"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                "[[tool.pitloom.creator]] entry is missing a valid 'name' "
                f"(got {name!r})"
            )
        creator_type = entry.get("type")
        if creator_type is not None and not isinstance(creator_type, str):
            raise ValueError(
                "[[tool.pitloom.creator]] entry 'type' must be a string, got "
                f"{type(creator_type).__name__}: {creator_type!r}"
            )
        email = entry.get("email")
        if email is not None and not isinstance(email, str):
            raise ValueError(
                "[[tool.pitloom.creator]] entry 'email' must be a string, got "
                f"{type(email).__name__}: {email!r}"
            )
        creators.append(
            Creator(
                name=name,
                type=creator_type if creator_type is not None else "person",
                email=email,
            )
        )
    return creators


def _read_tools(pitloom_data: dict[str, Any]) -> list[Tool] | None:
    """Read ``[[tool.pitloom.creation-tool]]`` array-of-tables into ``Tool``.

    Raises:
        ValueError: If ``creation-tool`` is present but not an array of
            tables (e.g. a single ``[tool.pitloom.creation-tool]`` table, or
            ``creation-tool = ["MyWrapper"]``), or if an entry is not a
            table or is missing a valid (non-empty string) ``name``.
    """
    raw = pitloom_data.get("creation-tool", pitloom_data.get("creation_tool"))
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError(
            "[tool.pitloom.creation-tool] must be an array of tables "
            f"([[tool.pitloom.creation-tool]]), got {type(raw).__name__}"
        )
    tools: list[Tool] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                "[[tool.pitloom.creation-tool]] entry must be a table, got "
                f"{type(entry).__name__}: {entry!r}"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                "[[tool.pitloom.creation-tool]] entry is missing a valid "
                f"'name' (got {name!r})"
            )
        tools.append(Tool(name=name))
    return tools


def _provenance_str(raw: dict[str, Any], keys: tuple[str, ...], default: str) -> str:
    """Return the first present ``[tool.pitloom.provenance]`` key as a string.

    Accepts both hyphen and underscore spellings (``keys`` in preference
    order). Raises ``ValueError`` if a present value is not a string.
    """
    for key in keys:
        if key in raw:
            value = raw[key]
            if not isinstance(value, str):
                raise ValueError(
                    f"[tool.pitloom.provenance] {key!r} must be a string, got "
                    f"{type(value).__name__}: {value!r}"
                )
            return value
    return default


def _read_provenance_settings(
    pitloom_data: dict[str, Any],
) -> tuple[str, str, str, str]:
    """Read ``[tool.pitloom.provenance]`` and return
    ``(format, schema, detail, preserve_source_metadata)``.

    Raises:
        ValueError: If ``provenance`` is present but not a table, if any value
            is present but not a string, or if ``format``/``detail``/
            ``preserve-source-metadata`` is not one of its allowed values.
    """
    raw = pitloom_data.get("provenance", {})
    if not isinstance(raw, dict):
        raise ValueError(
            "[tool.pitloom.provenance] must be a table, got "
            f"{type(raw).__name__}: {raw!r}"
        )

    fmt = _provenance_str(raw, ("format",), "both")
    if fmt not in _VALID_PROVENANCE_FORMATS:
        valid = ", ".join(sorted(_VALID_PROVENANCE_FORMATS))
        raise ValueError(
            f"[tool.pitloom.provenance] 'format' must be one of {valid}, got {fmt!r}"
        )

    schema = _provenance_str(raw, ("schema",), _DEFAULT_PROVENANCE_SCHEMA)

    detail = _provenance_str(raw, ("detail",), "minimal")
    if detail not in _VALID_PROVENANCE_DETAIL:
        valid = ", ".join(sorted(_VALID_PROVENANCE_DETAIL))
        raise ValueError(
            f"[tool.pitloom.provenance] 'detail' must be one of {valid}, got {detail!r}"
        )

    preserve = _provenance_str(
        raw, ("preserve-source-metadata", "preserve_source_metadata"), "auto"
    )
    if preserve not in _VALID_PRESERVE_SOURCE_METADATA:
        valid = ", ".join(sorted(_VALID_PRESERVE_SOURCE_METADATA))
        raise ValueError(
            "[tool.pitloom.provenance] 'preserve-source-metadata' must be one of "
            f"{valid}, got {preserve!r}"
        )

    return fmt, schema, detail, preserve


def _read_pitloom_config(data: dict[str, Any]) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`.

    Creators come from ``[[tool.pitloom.creator]]``, tools from
    ``[[tool.pitloom.creation-tool]]``; ``[tool.pitloom.creation]`` still
    carries the document-level singletons: ``creation-datetime``,
    ``creation-comment``, and ``no-creation-tool``.

    Raises:
        ValueError: If ``[tool.pitloom]`` or ``[tool.pitloom.creation]``
            still has old single-valued ``creator-name``/``creator-email``/
            ``creator-type``/``creation-tool`` keys -- these belong under
            the array-of-tables form -- or if ``no-creation-tool`` is
            present but not a boolean (e.g. the string ``"false"``, which
            is truthy in Python).
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
    raw_ids = pitloom_data.get("ids", {})
    ids_file = raw_ids.get("file") if isinstance(raw_ids, dict) else None
    if ids_file is not None and not isinstance(ids_file, str):
        raise ValueError(
            "[tool.pitloom.ids] 'file' must be a string, got "
            f"{type(ids_file).__name__}: {ids_file!r}"
        )
    (
        provenance_format,
        provenance_schema,
        provenance_detail,
        provenance_preserve,
    ) = _read_provenance_settings(pitloom_data)
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
    if no_creation_tool is not None and not isinstance(no_creation_tool, bool):
        raise ValueError(
            "[tool.pitloom.creation] 'no-creation-tool' must be a boolean, "
            f"got {type(no_creation_tool).__name__}: {no_creation_tool!r}"
        )
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
        ids_file=ids_file,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve,
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
