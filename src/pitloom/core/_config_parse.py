# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing helpers for ``[tool.pitloom]`` configuration data (from
``pyproject.toml``, ``setup.cfg`` or a ``--config`` file).

See also: :mod:`pitloom.core._config_read`,
:mod:`pitloom.core._config_parse_fragment` (``fragment.files``),
:mod:`pitloom.core._config_parse_scan`, :mod:`pitloom.core._config_types` and
:mod:`pitloom.core.config`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom._toml_io import load_toml_file
from pitloom.core._config_keys import warn_unknown_keys
from pitloom.core._config_legacy import (
    _check_moved_creation_keys,
    _check_moved_flat_keys,
    _check_moved_top_level_tables,
)
from pitloom.core._config_parse_fragment import _read_fragments
from pitloom.core._config_parse_scan import (
    _read_content_type_settings,
    _read_extract_file_header,
    _read_max_dataset_hash_bytes,
    _read_max_download_bytes,
    _read_max_model_extract_bytes,
    _read_max_source_metadata_bytes,
    _read_scan_model_usage,
)
from pitloom.core._config_read import (
    _optional_str,
    _read_array_of_tables,
    _read_bool_setting,
    _read_table,
    _require_choice,
)
from pitloom.core._config_types import _DEFAULT_PROVENANCE_SCHEMA, PitloomConfig
from pitloom.core.creation import (
    Creator,
    Tool,
    creator_type_problem,
    iso_datetime_or_none,
)
from pitloom.core.credential_policy import read_accept_key, read_mode_key
from pitloom.core.file_names import (
    CONFIG_BASENAME_PLACE,
    is_plain_file_name,
    sbom_base_name,
)
from pitloom.messages.config import MISSING, ConfigError, ConfigPlace, config_invalid
from pitloom.messages.targets import input_not_found, is_input_file

_TOOL = ConfigPlace("tool")
_PITLOOM = ConfigPlace("tool.pitloom")
_CREATION = ConfigPlace("tool.pitloom.creation")
_CREATOR = ConfigPlace("tool.pitloom.creator")
_PROVENANCE = ConfigPlace("tool.pitloom.provenance")

_VALID_PROVENANCE_FORMATS: frozenset[str] = frozenset({"annotation", "comment", "both"})
_VALID_PROVENANCE_DETAIL: frozenset[str] = frozenset({"minimal", "full"})
_VALID_PRESERVE_SOURCE_METADATA: frozenset[str] = frozenset({"auto", "always", "never"})


def _name_or_raise(entry: dict[str, Any], place: ConfigPlace) -> str:
    """*entry*'s ``name`` at *place* (an entry of an array of tables): a
    string with something besides whitespace, else ``config-invalid``."""
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise config_invalid(
            place.at("name"), "non-empty", got=entry.get("name", MISSING)
        )
    return name


def _read_creators(pitloom_data: dict[str, Any]) -> list[Creator]:
    """Read ``[[tool.pitloom.creator]]`` array-of-tables into ``Creator`` objects."""
    raw = pitloom_data.get("creator")
    if raw is None:
        return []
    creators: list[Creator] = []
    for index, entry in enumerate(_read_array_of_tables(raw, _CREATOR)):
        place = _CREATOR.entry_at(index)
        name = _name_or_raise(entry, place)
        creator_type = _optional_str(entry, "type", place)
        email = _optional_str(entry, "email", place)
        if creator_type is not None and (
            creator_type_problem(creator_type) == "creator-type"
        ):
            raise config_invalid(place.at("type"), "creator-type", got=creator_type)
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
    key = "creation-tool" if "creation-tool" in pitloom_data else "creation_tool"
    raw = pitloom_data.get(key)
    if raw is None:
        return None
    array = ConfigPlace(f"tool.pitloom.{key}")
    return [
        Tool(name=_name_or_raise(entry, array.entry_at(index)))
        for index, entry in enumerate(_read_array_of_tables(raw, array))
    ]


def _present_key(table: dict[str, Any], keys: tuple[str, ...]) -> str:
    """The first of *keys* that *table* holds as written, else the first."""
    return next((k for k in keys if k in table), keys[0])


def _provenance_str(raw: dict[str, Any], keys: tuple[str, ...], default: str) -> str:
    """Return the first present ``[tool.pitloom.provenance]`` key as a string."""
    for key in keys:
        if key in raw:
            value = raw[key]
            if not isinstance(value, str):
                raise config_invalid(_PROVENANCE.at(key), "string", got=value)
            return value
    return default


def _read_provenance_settings(
    pitloom_data: dict[str, Any],
) -> tuple[str, str, str, str, int]:
    """Read ``[tool.pitloom.provenance]`` settings."""
    raw = pitloom_data.get("provenance", {})
    if not isinstance(raw, dict):
        raise config_invalid(_PROVENANCE, "table", got=raw)

    fmt = _provenance_str(raw, ("format",), "both")
    _require_choice(
        fmt, _VALID_PROVENANCE_FORMATS, _PROVENANCE.at("format"), "one-of-format"
    )

    schema = _provenance_str(raw, ("schema",), _DEFAULT_PROVENANCE_SCHEMA)

    detail = _provenance_str(raw, ("detail",), "minimal")
    _require_choice(
        detail, _VALID_PROVENANCE_DETAIL, _PROVENANCE.at("detail"), "one-of-detail"
    )

    preserve_keys = ("preserve-source-metadata", "preserve_source_metadata")
    preserve = _provenance_str(raw, preserve_keys, "auto")
    _require_choice(
        preserve,
        _VALID_PRESERVE_SOURCE_METADATA,
        _PROVENANCE.at(_present_key(raw, preserve_keys)),
        "one-of-preserve",
    )

    max_metadata_bytes = _read_max_source_metadata_bytes(raw)

    return fmt, schema, detail, preserve, max_metadata_bytes


def _read_id_registry(pitloom_data: dict[str, Any]) -> str | None:
    """Read ``[tool.pitloom] id-registry``."""
    return _optional_str(pitloom_data, "id-registry", _PITLOOM)


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


def _apply_no_creation_tool(
    creation_data: dict[str, Any], tools: list[Tool] | None
) -> list[Tool] | None:
    """Apply ``[tool.pitloom.creation] no-creation-tool``."""
    key = _present_key(creation_data, ("no-creation-tool", "no_creation_tool"))
    no_creation_tool = creation_data.get(key)
    if no_creation_tool is not None and not isinstance(no_creation_tool, bool):
        raise config_invalid(_CREATION.at(key), "boolean", got=no_creation_tool)
    return [] if no_creation_tool else tools


def _check_sbom_basename(value: str | None) -> str | None:
    """A file name, never a path: a config (possibly a third-party sdist's)
    must not choose a directory to write to
    (:func:`pitloom.core.file_names.is_plain_file_name`).

    A trailing ``.spdx3.json`` is dropped with a ``WARNING:``
    (:func:`pitloom.core.file_names.sbom_base_name`).

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid``: *value* is
            not a plain file name.
    """
    if value is None:
        return None
    if not is_plain_file_name(value):
        raise config_invalid(CONFIG_BASENAME_PLACE, "file-name", got=value)
    return sbom_base_name(value, CONFIG_BASENAME_PLACE)


def _pick_str(
    *sources: tuple[dict[str, Any], ConfigPlace, tuple[str, ...]],
) -> tuple[str, ConfigPlace] | None:
    """Return the first string found by key, scanning sources in order, and
    the place it was found at.

    Each source is a table, its place and the keys to look for.

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid``: a key is
            present with a value that is not a string.
    """
    for source, table, keys in sources:
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise config_invalid(table.at(key), "string", got=value)
            return value, table.at(key)
    return None


def _picked(picked: tuple[str, ConfigPlace] | None) -> str | None:
    """The string :func:`_pick_str` found, if any."""
    return None if picked is None else picked[0]


def _read_creation_datetime(
    creation_data: dict[str, Any], pitloom_data: dict[str, Any]
) -> str | None:
    """Read ``creation-datetime`` (in ``[tool.pitloom.creation]`` or
    ``[tool.pitloom]``): an ISO 8601 date and time, else ``config-invalid``."""
    picked = _pick_str(
        (
            creation_data,
            _CREATION,
            ("creation-datetime", "creation_datetime", "datetime"),
        ),
        (pitloom_data, _PITLOOM, ("creation-datetime", "creation_datetime")),
    )
    # An empty value stays "unset", as every consumer reads it.
    if picked is not None and picked[0] and iso_datetime_or_none(picked[0]) is None:
        raise config_invalid(picked[1], "datetime", got=picked[0])
    return _picked(picked)


def _read_describe_relationship(pitloom_data: dict[str, Any]) -> bool | None:
    """Read ``[tool.pitloom] describe-relationship``; ``None`` when absent."""
    key = _present_key(pitloom_data, ("describe-relationship", "describe_relationship"))
    value = pitloom_data.get(key)
    if value is not None and not isinstance(value, bool):
        raise config_invalid(_PITLOOM.at(key), "boolean", got=value)
    return value


def parse_pitloom_config(
    data: dict[str, Any], *, is_setup_cfg: bool = False, source: str | None = None
) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings and return a :class:`PitloomConfig`.

    *is_setup_cfg* names a refused value's own source table
    ``[tool:pitloom]``/``[tool:pitloom:creation]`` instead of
    ``[tool.pitloom]``/``[tool.pitloom.creation]`` -- pass ``True`` only
    for *data* built from a ``setup.cfg`` ``[tool:pitloom]`` section (see
    :func:`pitloom.extract.project.setuptools_cfg.setup_cfg_pitloom_config`'s
    own call), never for a ``pyproject.toml``-derived *data*, whatever
    that TOML file's own basename happens to be.

    *source* names the file *data* came from in each unknown-key
    ``WARNING:`` (:func:`~pitloom.core._config_keys.warn_unknown_keys`),
    which is given before any value is read or checked, and in each error
    (``FILE=``).

    Raises:
        pitloom.messages.config.ConfigError: ``config-invalid`` or
            ``config-moved``, naming *source* and the spelling of the table
            as its file writes it (the readers below name neither).
    """
    try:
        return _parse_pitloom_config(data, is_setup_cfg=is_setup_cfg, source=source)
    except ConfigError as exc:
        raise exc.located(source, is_setup_cfg) from None


# pylint: disable-next=too-many-locals
def _parse_pitloom_config(
    data: dict[str, Any], *, is_setup_cfg: bool, source: str | None
) -> PitloomConfig:
    """:func:`parse_pitloom_config` without the file named in its errors."""
    tool_data = _read_table(data, "tool", _TOOL)
    pitloom_data = _read_table(tool_data, "pitloom", _PITLOOM)
    creation_data = _read_table(pitloom_data, "creation", _CREATION)

    _check_moved_creation_keys(pitloom_data, creation_data)
    _check_moved_top_level_tables(pitloom_data)
    _check_moved_flat_keys(pitloom_data)
    warn_unknown_keys(pitloom_data, is_setup_cfg=is_setup_cfg, source=source)

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
    scan_model_usage = _read_scan_model_usage(pitloom_data)
    max_model_extract_bytes = _read_max_model_extract_bytes(pitloom_data)
    max_dataset_hash_bytes = _read_max_dataset_hash_bytes(pitloom_data)
    max_download_bytes = _read_max_download_bytes(pitloom_data)
    update_id_registry = _read_update_id_registry(pitloom_data)
    (
        content_type_enabled,
        content_type_method,
        content_type_overrides,
    ) = _read_content_type_settings(pitloom_data)
    pretty = _read_bool_setting(pitloom_data, "pretty", default=False)
    desc_rel = _read_describe_relationship(pitloom_data)
    sbom_basename = _check_sbom_basename(
        _picked(_pick_str((pitloom_data, _PITLOOM, ("sbom-basename",)))) or None
    )
    offline = _read_offline_setting(pitloom_data)
    use_lockfile = _read_use_lockfile_setting(pitloom_data)

    creators = _read_creators(pitloom_data)
    tools = _apply_no_creation_tool(creation_data, _read_tools(pitloom_data))

    creation_datetime = _read_creation_datetime(creation_data, pitloom_data)
    creation_comment = _picked(
        _pick_str(
            (
                creation_data,
                _CREATION,
                ("creation-comment", "creation_comment", "comment"),
            ),
            (pitloom_data, _PITLOOM, ("creation-comment", "creation_comment")),
        )
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
        table_keys=frozenset(pitloom_data),
        provenance_format=provenance_format,
        provenance_schema=provenance_schema,
        provenance_detail=provenance_detail,
        provenance_preserve_source_metadata=provenance_preserve,
        provenance_max_source_metadata_bytes=provenance_max_metadata_bytes,
        enrich_local=enrich_local,
        extract_file_header=extract_file_header,
        scan_model_usage=scan_model_usage,
        max_model_extract_bytes=max_model_extract_bytes,
        max_dataset_hash_bytes=max_dataset_hash_bytes,
        max_download_bytes=max_download_bytes,
        content_type_enabled=content_type_enabled,
        content_type_method=content_type_method,
        content_type_overrides=content_type_overrides,
        offline=offline,
        use_lockfile=use_lockfile,
        accept_url_credentials=read_accept_key(pitloom_data),
        url_credentials=read_mode_key(pitloom_data),
    )


def read_pitloom_config(
    pyproject_path: Path, *, source: str | None = None
) -> PitloomConfig:
    """Read ``[tool.pitloom]`` settings directly from a ``pyproject.toml`` file.

    *source* is the file as the messages name it (``FILE=``): *pyproject_path*
    as given when ``None``.

    Raises:
        FileNotFoundError: *pyproject_path* does not exist.
        ValueError: the file is not valid TOML or its settings are invalid.
    """
    if not is_input_file(pyproject_path):
        raise input_not_found("pyproject.toml", pyproject_path)

    data: dict[str, Any] = load_toml_file(pyproject_path)

    return parse_pitloom_config(
        data, source=str(pyproject_path) if source is None else source
    )


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
