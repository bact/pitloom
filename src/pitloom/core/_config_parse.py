# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing helpers for ``[tool.pitloom]`` configuration in ``pyproject.toml``.

See also: :mod:`pitloom.core._config_read`,
:mod:`pitloom.core._config_parse_scan`, :mod:`pitloom.core._config_types` and
:mod:`pitloom.core.config`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom.core._config_legacy import (
    _check_moved_creation_keys,
    _check_moved_flat_keys,
    _check_moved_top_level_tables,
)
from pitloom.core._config_parse_scan import (
    _read_content_type_settings,
    _read_extract_file_header,
)
from pitloom.core._config_read import (
    _read_array_of_tables,
    _read_bool_setting,
    _read_int_setting,
    _read_table,
    _require_choice,
)
from pitloom.core._config_types import (
    _DEFAULT_PROVENANCE_SCHEMA,
    FragmentConfig,
    PitloomConfig,
)
from pitloom.core.creation import Creator, Tool
from pitloom.core.file_names import is_plain_file_name
from pitloom.core.provenance import normalize_max_source_metadata_bytes
from pitloom.extract._toml_io import load_toml_file

_VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})
_VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})
_VALID_PRESERVE_SOURCE_METADATA: frozenset[str] = frozenset({"auto", "always", "never"})


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


def _provenance_int(raw: dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    """Return the first present ``[tool.pitloom.provenance]`` key as an int."""
    for key in keys:
        if key in raw:
            return _read_int_setting(raw, key, default, "[tool.pitloom.provenance]")
    return default


def _read_provenance_settings(
    pitloom_data: dict[str, Any],
) -> tuple[str, str, str, str, int]:
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

    max_metadata_bytes = _provenance_int(
        raw, ("max-source-metadata-bytes", "max_source_metadata_bytes"), 0
    )
    max_metadata_bytes = normalize_max_source_metadata_bytes(max_metadata_bytes)

    return fmt, schema, detail, preserve, max_metadata_bytes


def _read_id_registry(pitloom_data: dict[str, Any]) -> str | None:
    """Read ``[tool.pitloom] id-registry``."""
    id_registry = pitloom_data.get("id-registry")
    if id_registry is not None and not isinstance(id_registry, str):
        raise ValueError(
            "[tool.pitloom] 'id-registry' must be a string, got "
            f"{type(id_registry).__name__}: {id_registry!r}"
        )
    return id_registry


def _read_enrich_settings(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] enrich``."""
    return _read_bool_setting(pitloom_data, "enrich", False)


def _read_update_id_registry(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] update-id-registry``."""
    return _read_bool_setting(pitloom_data, "update-id-registry", True)


def _read_offline_setting(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] offline``."""
    return _read_bool_setting(pitloom_data, "offline", False)


def _read_use_lockfile_setting(pitloom_data: dict[str, Any]) -> bool:
    """Read ``[tool.pitloom] use-lockfile`` (on by default)."""
    return _read_bool_setting(pitloom_data, "use-lockfile", True)


def _read_fragments(pitloom_data: dict[str, Any]) -> list[FragmentConfig]:
    """Read ``[tool.pitloom.fragment] files`` into ``FragmentConfig`` entries.

    Each entry is either a plain path string (shorthand for
    ``FragmentConfig(path=...)``) or an inline table with ``path`` plus any
    of ``role``, ``description``, ``required``, ``sha256``, ``link-to-main``.
    """
    raw = _read_table(pitloom_data, "fragment", "[tool.pitloom.fragment]").get(
        "files", []
    )
    if not isinstance(raw, list):
        raise ValueError(
            "[tool.pitloom.fragment] 'files' must be an array, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    fragments: list[FragmentConfig] = []
    for entry in raw:
        if isinstance(entry, str):
            if not entry:
                raise ValueError(
                    "[tool.pitloom.fragment] 'files' entry must not be an empty string"
                )
            fragments.append(FragmentConfig(path=entry))
        elif isinstance(entry, dict):
            fragments.append(_read_fragment_entry(entry))
        else:
            raise ValueError(
                "[tool.pitloom.fragment] 'files' entries must each be a "
                f"string or table, got {type(entry).__name__}: {entry!r}"
            )
    return fragments


def _read_fragment_entry(entry: dict[str, Any]) -> FragmentConfig:
    """Parse one ``[tool.pitloom.fragment] files`` table entry.

    Every field here raises ``ValueError`` on the wrong type, matching
    every ``_read_*`` config reader (``_read_creators`` here,
    ``_read_content_type_overrides``, ``_read_bool_setting``, ...) --
    config errors are never silently coerced or defaulted around, only
    genuinely-absent optional fields get a default.
    """
    path = entry.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError(
            "[tool.pitloom.fragment] 'files' table entry is missing a "
            f"valid 'path' (got {path!r})"
        )
    role = entry.get("role")
    if role is not None and not isinstance(role, str):
        raise ValueError(
            "[tool.pitloom.fragment] 'files' entry 'role' must be a "
            f"string, got {type(role).__name__}: {role!r}"
        )
    description = entry.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(
            "[tool.pitloom.fragment] 'files' entry 'description' must be "
            f"a string, got {type(description).__name__}: {description!r}"
        )
    required = _read_bool_setting(
        entry, "required", False, table_path="[tool.pitloom.fragment] 'files' entry"
    )
    sha256 = entry.get("sha256")
    if sha256 is not None and not isinstance(sha256, str):
        raise ValueError(
            "[tool.pitloom.fragment] 'files' entry 'sha256' must be a "
            f"string, got {type(sha256).__name__}: {sha256!r}"
        )
    link_to_main = entry.get("link-to-main", entry.get("link_to_main"))
    if link_to_main is not None and not isinstance(link_to_main, str):
        raise ValueError(
            "[tool.pitloom.fragment] 'files' entry 'link-to-main' must be "
            f"a string, got {type(link_to_main).__name__}: {link_to_main!r}"
        )
    return FragmentConfig(
        path=path,
        role=role,
        description=description,
        required=required,
        sha256=sha256,
        link_to_main=link_to_main,
    )


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


def _check_sbom_basename(value: str | None) -> str | None:
    """A file name, never a path: a config (possibly a third-party sdist's)
    must not choose a directory to write to
    (:func:`pitloom.core.file_names.is_plain_file_name`).

    Raises:
        ValueError: *value* is not a plain file name.
    """
    if value is not None and not is_plain_file_name(value):
        raise ValueError(
            f"[tool.pitloom] 'sbom-basename' must be a file name, not a path: {value!r}"
        )
    return value


def _pick_str(*sources: tuple[dict[str, Any], tuple[str, ...]]) -> str | None:
    """Return the first string found by key, scanning sources in order.

    Raises:
        ValueError: a key is present with a value that is not a string.
    """
    for source, keys in sources:
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError(
                    f"[tool.pitloom] {key!r} must be a string, got "
                    f"{type(value).__name__}: {value!r}"
                )
            return value
    return None


# pylint: disable=too-many-locals
def parse_pitloom_config(
    data: dict[str, Any], *, is_setup_cfg: bool = False
) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`.

    *is_setup_cfg* names the moved-key errors' own source table
    ``[tool:pitloom]``/``[tool:pitloom:creation]`` instead of
    ``[tool.pitloom]``/``[tool.pitloom.creation]`` -- pass ``True`` only
    for *data* built from a ``setup.cfg`` ``[tool:pitloom]`` section (see
    :func:`pitloom.extract.project.setuptools_cfg.setup_cfg_pitloom_config`'s
    own call), never for a ``pyproject.toml``-derived *data*, whatever
    that TOML file's own basename happens to be.
    """
    tool_data = _read_table(data, "tool", "[tool]")
    pitloom_data = _read_table(tool_data, "pitloom", "[tool.pitloom]")
    creation_data = _read_table(pitloom_data, "creation", "[tool.pitloom.creation]")

    _check_moved_creation_keys(pitloom_data, creation_data, is_setup_cfg=is_setup_cfg)
    _check_moved_top_level_tables(pitloom_data, is_setup_cfg=is_setup_cfg)
    _check_moved_flat_keys(pitloom_data, is_setup_cfg=is_setup_cfg)

    fragments = _read_fragments(pitloom_data)
    id_registry = _read_id_registry(pitloom_data)
    (
        provenance_format,
        provenance_schema,
        provenance_detail,
        provenance_preserve,
        provenance_max_metadata_bytes,
    ) = _read_provenance_settings(pitloom_data)
    enrich_local = _read_enrich_settings(pitloom_data)
    extract_file_header = _read_extract_file_header(pitloom_data)
    update_id_registry = _read_update_id_registry(pitloom_data)
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
    sbom_basename = _check_sbom_basename(
        _pick_str((pitloom_data, ("sbom-basename",))) or None
    )
    offline = _read_offline_setting(pitloom_data)
    use_lockfile = _read_use_lockfile_setting(pitloom_data)

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
        id_registry=id_registry,
        update_id_registry=update_id_registry,
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve,
        provenance_max_source_metadata_bytes=provenance_max_metadata_bytes,
        enrich_local=enrich_local,
        extract_file_header=extract_file_header,
        content_type_enabled=content_type_enabled,
        content_type_method=content_type_method,
        content_type_overrides=content_type_overrides,
        offline=offline,
        use_lockfile=use_lockfile,
    )


def read_pitloom_config(pyproject_path: Path) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings directly from a ``pyproject.toml`` file."""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    data: dict[str, Any] = load_toml_file(pyproject_path)

    return parse_pitloom_config(data)


#: Where :func:`select_project_config` took the config from.
PYPROJECT_SOURCE = "pyproject.toml"
SETUP_CFG_SOURCE = "setup.cfg"


def pyproject_config_applies(data: Any) -> bool:
    """Whether a parsed ``pyproject.toml`` holds the project's config: it
    names the project (``[project]`` or ``[tool.poetry]`` ``name``) or
    declares a ``[tool.pitloom]`` table -- present, even empty or set to the
    defaults, is the user's config (never compared by value)."""
    if not isinstance(data, dict):
        return False
    tool = data.get("tool")
    if isinstance(tool, dict) and "pitloom" in tool:
        return True
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    for table in (data.get("project"), poetry):
        if isinstance(table, dict) and str(table.get("name") or "").strip():
            return True
    return False


def select_project_config(
    pyproject: PitloomConfig | None,
    pyproject_applies: bool,
    setup_cfg: Callable[[], PitloomConfig] | None,
) -> tuple[PitloomConfig, str | None]:
    """Which of a project's configs applies, and its source
    (:data:`PYPROJECT_SOURCE`, :data:`SETUP_CFG_SOURCE` or ``None``): the one
    rule a project directory and an sdist archive share.

    *pyproject* is ``pyproject.toml``'s ``[tool.pitloom]`` (``None`` when
    there is no ``pyproject.toml``); *pyproject_applies* is
    :func:`pyproject_config_applies` for it; *setup_cfg* reads
    ``setup.cfg``'s ``[tool:pitloom]`` (``None`` when there is no
    ``setup.cfg``). ``pyproject.toml`` wins, unless it is absent, or neither
    names the project nor declares ``[tool.pitloom]`` -- a legacy project
    whose real metadata and config live in ``setup.cfg``.
    """
    if pyproject is not None and pyproject_applies:
        return pyproject, PYPROJECT_SOURCE
    if setup_cfg is not None:
        return setup_cfg(), SETUP_CFG_SOURCE
    if pyproject is not None:
        return pyproject, PYPROJECT_SOURCE
    return PitloomConfig(), None
