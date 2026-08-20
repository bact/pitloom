# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing helpers for ``[tool.pitloom]`` configuration in ``pyproject.toml``.

See also: :mod:`pitloom.core._config_types` and :mod:`pitloom.core.config`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from pitloom.core._config_legacy import (
    _check_moved_creation_keys,
    _check_moved_top_level_tables,
)
from pitloom.core._config_types import (
    _DEFAULT_PROVENANCE_SCHEMA,
    VALID_CONTENT_TYPE_METHODS,
    PitloomConfig,
)
from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.creation import Creator, Tool

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})
_VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})
_VALID_PRESERVE_SOURCE_METADATA: frozenset[str] = frozenset({"auto", "always", "never"})

_CONTENT_TYPE_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _read_bool_setting(
    data: dict[str, Any],
    key: str,
    default: bool,
    table_path: str = "[tool.pitloom]",
) -> bool:
    """Read a boolean key from data, defaulting to default when absent."""
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"{table_path} {key!r} must be a boolean, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _require_choice(
    value: str, valid: frozenset[str], table_path: str, key: str
) -> None:
    """Raise ValueError unless value is one of valid."""
    if value not in valid:
        options = ", ".join(sorted(valid))
        raise ValueError(
            f"{table_path} {key!r} must be one of {options}, got {value!r}"
        )


def _read_array_of_tables(raw: Any, table_repr: str) -> list[dict[str, Any]]:
    """Validate raw is a TOML array-of-tables and return its entries."""
    if not isinstance(raw, list):
        raise ValueError(
            f"{table_repr} must be an array of tables, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{table_repr} entry must be a table, got "
                f"{type(entry).__name__}: {entry!r}"
            )
    return raw


def _read_creators(pitloom_data: dict[str, Any]) -> list[Creator]:
    """Read ``[[tool.pitloom.creator]]`` array-of-tables into ``Creator`` objects."""
    raw = pitloom_data.get("creator")
    if raw is None:
        return []
    creators: list[Creator] = []
    for entry in _read_array_of_tables(raw, "[[tool.pitloom.creator]]"):
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
    """Read ``[[tool.pitloom.creation-tool]]`` array-of-tables into ``Tool``."""
    raw = pitloom_data.get("creation-tool", pitloom_data.get("creation_tool"))
    if raw is None:
        return None
    tools: list[Tool] = []
    for entry in _read_array_of_tables(raw, "[[tool.pitloom.creation-tool]]"):
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                "[[tool.pitloom.creation-tool]] entry is missing a valid "
                f"'name' (got {name!r})"
            )
        tools.append(Tool(name=name))
    return tools


def _provenance_str(raw: dict[str, Any], keys: tuple[str, ...], default: str) -> str:
    """Return the first present ``[tool.pitloom.provenance]`` key as a string."""
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
    """Read ``[tool.pitloom.provenance]`` settings."""
    raw = pitloom_data.get("provenance", {})
    if not isinstance(raw, dict):
        raise ValueError(
            "[tool.pitloom.provenance] must be a table, got "
            f"{type(raw).__name__}: {raw!r}"
        )

    fmt = _provenance_str(raw, ("format",), "both")
    _require_choice(
        fmt, _VALID_PROVENANCE_FORMATS, "[tool.pitloom.provenance]", "format"
    )

    schema = _provenance_str(raw, ("schema",), _DEFAULT_PROVENANCE_SCHEMA)

    detail = _provenance_str(raw, ("detail",), "minimal")
    _require_choice(
        detail, _VALID_PROVENANCE_DETAIL, "[tool.pitloom.provenance]", "detail"
    )

    preserve = _provenance_str(
        raw, ("preserve-source-metadata", "preserve_source_metadata"), "auto"
    )
    _require_choice(
        preserve,
        _VALID_PRESERVE_SOURCE_METADATA,
        "[tool.pitloom.provenance]",
        "preserve-source-metadata",
    )

    return fmt, schema, detail, preserve


def _read_ids_file(pitloom_data: dict[str, Any]) -> str | None:
    """Read ``[tool.pitloom] ids-file``."""
    ids_file = pitloom_data.get("ids-file")
    if ids_file is not None and not isinstance(ids_file, str):
        raise ValueError(
            "[tool.pitloom] 'ids-file' must be a string, got "
            f"{type(ids_file).__name__}: {ids_file!r}"
        )
    return ids_file


def _read_enrich_settings(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] enrich``."""
    return _read_bool_setting(pitloom_data, "enrich", False)


def _read_content_type_overrides(
    raw: dict[str, Any],
) -> tuple[ContentTypeOverride, ...]:
    """Read ``[[tool.pitloom.content-type.override]]``."""
    raw_overrides = raw.get("override", [])
    overrides: list[ContentTypeOverride] = []
    for entry in _read_array_of_tables(
        raw_overrides, "[[tool.pitloom.content-type.override]]"
    ):
        pattern = entry.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(
                "[[tool.pitloom.content-type.override]] "
                f"'pattern' must be a non-empty string, got {pattern!r}"
            )
        content_type = entry.get("content-type")
        if not isinstance(content_type, str) or not _CONTENT_TYPE_RE.match(
            content_type
        ):
            raise ValueError(
                "[[tool.pitloom.content-type.override]] "
                "'content-type' must be a MIME type in 'type/subtype' form "
                f"(e.g. 'image/png'), got {content_type!r}"
            )
        overrides.append(
            ContentTypeOverride(pattern=pattern, content_type=content_type)
        )
    return tuple(overrides)


def _read_extract_file_header(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] extract-file-header``."""
    return _read_bool_setting(pitloom_data, "extract-file-header", True)


def _read_update_registry(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] update-registry``."""
    return _read_bool_setting(pitloom_data, "update-registry", True)


def _read_content_type_settings(
    pitloom_data: dict[str, Any],
) -> tuple[bool, str, tuple[ContentTypeOverride, ...]]:
    """Read ``[tool.pitloom.content-type]`` settings."""
    raw = pitloom_data.get("content-type", {})
    if not isinstance(raw, dict):
        raise ValueError(
            "[tool.pitloom.content-type] must be a table, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    enabled = _read_bool_setting(
        raw, "enabled", False, table_path="[tool.pitloom.content-type]"
    )
    method = raw.get("method", "auto")
    _require_choice(
        method, VALID_CONTENT_TYPE_METHODS, "[tool.pitloom.content-type]", "method"
    )
    overrides = _read_content_type_overrides(raw)
    return enabled, method, overrides


def _read_offline_setting(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] offline``."""
    return _read_bool_setting(pitloom_data, "offline", False)


def _read_fragments(pitloom_data: dict[str, Any]) -> list[str]:
    """Read ``[tool.pitloom.fragment] files``."""
    raw = pitloom_data.get("fragment", {}).get("files", [])
    return [str(f) for f in raw] if isinstance(raw, list) else []


def _apply_no_creation_tool(
    creation_data: dict[str, Any], tools: list[Tool] | None
) -> list[Tool] | None:
    """Apply ``[tool.pitloom.creation] no-creation-tool``."""
    no_creation_tool = creation_data.get("no-creation-tool")
    if no_creation_tool is None:
        no_creation_tool = creation_data.get("no_creation_tool")
    if no_creation_tool is not None and not isinstance(no_creation_tool, bool):
        raise ValueError(
            "[tool.pitloom.creation] 'no-creation-tool' must be a boolean, "
            f"got {type(no_creation_tool).__name__}: {no_creation_tool!r}"
        )
    return [] if no_creation_tool else tools


def _pick_str(*sources: tuple[dict[str, Any], tuple[str, ...]]) -> str | None:
    """Return the first string found by key, scanning sources in order."""
    for source, keys in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str):
                return value
    return None


# pylint: disable=too-many-locals
def parse_pitloom_config(data: dict[str, Any]) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`."""
    pitloom_data = data.get("tool", {}).get("pitloom", {})
    creation_data = pitloom_data.get("creation", {})
    if not isinstance(creation_data, dict):
        creation_data = {}

    _check_moved_creation_keys(pitloom_data, creation_data)
    _check_moved_top_level_tables(pitloom_data)

    fragments = _read_fragments(pitloom_data)
    ids_file = _read_ids_file(pitloom_data)
    (
        provenance_format,
        provenance_schema,
        provenance_detail,
        provenance_preserve,
    ) = _read_provenance_settings(pitloom_data)
    enrich_local = _read_enrich_settings(pitloom_data)
    extract_file_header = _read_extract_file_header(pitloom_data)
    update_registry = _read_update_registry(pitloom_data)
    (
        content_type_enabled,
        content_type_method,
        content_type_overrides,
    ) = _read_content_type_settings(pitloom_data)
    pretty = _read_bool_setting(pitloom_data, "pretty", default=False)
    desc_rel = pitloom_data.get("describe-relationship")
    if desc_rel is None:
        desc_rel = pitloom_data.get("describe_relationship")
    if desc_rel is not None:
        if not isinstance(desc_rel, bool):
            raise ValueError(
                f"[tool.pitloom] describe-relationship must be a boolean, got "
                f"{type(desc_rel).__name__}: {desc_rel!r}"
            )
    sbom_basename: str | None = pitloom_data.get("sbom-basename") or None
    offline = _read_offline_setting(pitloom_data)

    creators = _read_creators(pitloom_data)
    tools = _apply_no_creation_tool(creation_data, _read_tools(pitloom_data))

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
        update_registry=update_registry,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve,
        enrich_local=enrich_local,
        extract_file_header=extract_file_header,
        content_type_enabled=content_type_enabled,
        content_type_method=content_type_method,
        content_type_overrides=content_type_overrides,
        offline=offline,
    )


def read_pitloom_config(pyproject_path: Path) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings directly from a ``pyproject.toml`` file."""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data: dict[str, Any] = tomllib.load(f)

    return parse_pitloom_config(data)
