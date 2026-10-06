# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata and Pitloom config from setup.cfg.

See also: :mod:`pitloom.extract.project.setuptools_py` (AST parsing for setup.py),
:mod:`pitloom.extract.project._setup_cfg_directives` (``file:``/``attr:``)
and :mod:`pitloom.extract.project.setuptools` (facade).
"""

from __future__ import annotations

import configparser
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitloom.core.config import (
    _MOVED_CREATION_KEYS,
    KNOWN_KEYS,
    PitloomConfig,
    parse_pitloom_config,
)
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project._setup_cfg_directives import (
    _resolve_cfg_file_directive,
    _resolve_cfg_version,
)
from pitloom.extract.project._setup_cfg_values import (
    coerce_cfg_value,
    parse_sub_section,
)
from pitloom.extract.project._setuptools_options import (
    SetupOption,
    SetupOptions,
    build_setuptools_metadata,
    requirement_lines,
)
from pitloom.logging_config import one_line


class _NoProjectNameError(ValueError):
    """``setup.cfg`` has no project name, read alone."""


def _section_dict(cfg: configparser.ConfigParser, section: str) -> dict[str, str]:
    """Return a section's items as a plain dict, or empty dict if absent.

    Includes ``[DEFAULT]``-inherited values (``cfg.items()``'s normal,
    intended behaviour) -- correct for *resolving* a value, but not for
    asking whether *this section* declared a key: see
    :func:`_section_declares_key` for that question.
    """
    return dict(cfg.items(section)) if cfg.has_section(section) else {}


#: ``setup.cfg`` spellings of Pitloom keys, folded into others on reading,
#: by the section that reads them.
_CREATION_CFG_KEYS = frozenset(
    {"tool"}
    | {f"creator{sep}{part}" for sep in "-_" for part in ("name", "type", "email")}
)
_CFG_ONLY_KEYS: dict[str, frozenset[str]] = {
    "": _CREATION_CFG_KEYS | {"fragments"},
    "creation": _CREATION_CFG_KEYS,
}


def _pitloom_section(cfg: configparser.ConfigParser, section: str) -> dict[str, str]:
    """A ``[tool:pitloom...]`` section's items. A ``[DEFAULT]`` key (merged
    in by ``configparser``, e.g. for ``%(here)s``) is kept only when the
    section reads it, so it never warns as unknown."""
    table = section.removeprefix("tool:pitloom").removeprefix(":")
    takes = KNOWN_KEYS.get(table, frozenset()) | _CFG_ONLY_KEYS.get(table, frozenset())
    return _own_items(cfg, section, takes)


def _own_items(
    cfg: configparser.ConfigParser, section: str, takes: frozenset[str] = frozenset()
) -> dict[str, str]:
    """*section*'s items, keeping a ``[DEFAULT]``-inherited one only when its
    key is in *takes*."""
    return {
        key: value
        for key, value in _section_dict(cfg, section).items()
        if key in takes or _section_declares_key(cfg, section, key)
    }


def _section_declares_key(
    cfg: configparser.ConfigParser, section: str, key: str
) -> bool:
    """Return whether *section* itself declares *key*, ignoring any value
    only inherited from ``[DEFAULT]``.

    ``cfg.items(section)`` merges in ``[DEFAULT]``, so a shared value would
    make every section look as if it declared the key. ``cfg._sections``
    holds each section's own keys; the public API has no such accessor.
    """
    # pylint: disable-next=protected-access
    sections: dict[str, dict[str, str]] = cfg._sections  # type: ignore[attr-defined]
    return key in sections.get(section, {})


def _parse_cfg_keywords(raw: str) -> list[str]:
    """Parse keywords from ``setup.cfg``: space, comma, or newline separated."""
    return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]


def _parse_cfg_project_urls(raw: str) -> dict[str, str]:
    """Parse ``project_urls`` (``Label = URL`` lines) into a dict."""
    urls: dict[str, str] = {}
    for line in raw.splitlines():
        key, sep, val = line.partition("=")
        if sep and key.strip() and val.strip():
            urls[key.strip()] = val.strip()
    return urls


#: Provenance of a licence taken from a ``setup.cfg`` classifier.
CFG_CLASSIFIER_LICENSE_SOURCE = "Source: setup.cfg | Field: metadata.classifiers"


def _cfg_list(value: str) -> list[str]:
    """A list-valued ``setup.cfg`` option as setuptools reads it
    (``ConfigHandler._parse_list``): one item per line when *value* has a
    newline, else comma-separated; items stripped, blanks left out."""
    items = value.splitlines() if "\n" in value else value.split(",")
    return [item.strip() for item in items if item.strip()]


def _cfg_requirements(value: str) -> list[str]:
    """``install_requires`` as setuptools reads it
    (``ConfigHandler._parse_requirements_list``): one item per line when
    *value* has a newline, else ``;``-separated, ``#`` items left out, then
    :func:`~pitloom.extract.project._setuptools_options.requirement_lines`.
    A ``file:`` directive is not read."""
    items = value.splitlines() if "\n" in value else value.split(";")
    kept = (item.strip() for item in items)
    return requirement_lines("\n".join(i for i in kept if not i.startswith("#")))


def _cfg_source(field: str) -> str:
    return f"Source: setup.cfg | Field: {field}"


def _str_or_none(value: str) -> str | None:
    return value.strip() or None


#: (section, option, provenance field, parser) for each option read as is.
_PLAIN_OPTIONS: tuple[tuple[str, str, str, Callable[[str], Any]], ...] = (
    ("metadata", "name", "metadata.name", _str_or_none),
    ("metadata", "license", "metadata.license", _str_or_none),
    ("metadata", "keywords", "metadata.keywords", _parse_cfg_keywords),
    ("metadata", "author", "metadata.author/author_email", _str_or_none),
    ("metadata", "author_email", "metadata.author/author_email", _str_or_none),
    ("metadata", "url", "metadata.url/project_urls", _str_or_none),
    ("metadata", "project_urls", "metadata.url/project_urls", _parse_cfg_project_urls),
    ("options", "install_requires", "options.install_requires", _cfg_requirements),
    ("options", "python_requires", "options.python_requires", _str_or_none),
)


def _resolved_options(metadata: dict[str, str], project_dir: Path) -> SetupOptions:
    """The options whose value needs a directive resolved or two spellings."""
    options: SetupOptions = {}
    if "version" in metadata:
        version, source = _resolve_cfg_version(metadata["version"].strip(), project_dir)
        options["version"] = SetupOption(version, source or "", bool(version))
    description = metadata.get("description") or metadata.get("summary")
    if description is not None:
        options["description"] = SetupOption(
            _str_or_none(description), _cfg_source("metadata.description")
        )
    if "long_description" in metadata:
        readme = _resolve_cfg_file_directive(
            metadata["long_description"].strip(),
            project_dir,
            "metadata.long_description",
        )
        options["long_description"] = SetupOption(
            readme, _cfg_source("metadata.long_description")
        )
    if "classifiers" in metadata:
        classifiers = _resolve_cfg_file_directive(
            metadata["classifiers"].strip(), project_dir, "metadata.classifiers"
        )
        options["classifiers"] = SetupOption(
            _cfg_list(classifiers or ""), CFG_CLASSIFIER_LICENSE_SOURCE
        )
    return options


def read_setup_cfg_options(
    project_dir: Path, *, read_config: bool = True
) -> tuple[SetupOptions, PitloomConfig]:
    """The setuptools options ``setup.cfg``'s ``[metadata]`` and
    ``[options]`` state, ``name`` not required, and its ``[tool:pitloom]``
    settings -- parsed only when ``[metadata]`` names the project and
    *read_config* is set, else the defaults, so an unused or replaced one
    cannot fail the read.

    A value inherited from ``[DEFAULT]`` is an option, as in setuptools,
    but not declared (:func:`_section_declares_key`).

    Raises:
        FileNotFoundError: no ``setup.cfg`` file (a directory is none, as
            for setuptools).
        ValueError: ``setup.cfg`` cannot be read or parsed, or its
            ``[tool:pitloom]`` settings are invalid; one line.
    """
    setup_cfg_path = project_dir / "setup.cfg"
    if not os.path.isfile(setup_cfg_path):
        raise FileNotFoundError(f"setup.cfg not found at {setup_cfg_path}")
    cfg = configparser.ConfigParser()
    try:
        # read_file, not read: read() skips a file it cannot open.
        with setup_cfg_path.open(encoding="utf-8") as stream:
            cfg.read_file(stream)
        sections = {s: _section_dict(cfg, s) for s in ("metadata", "options")}
    # configparser.Error: also a value's bad % interpolation
    except (OSError, UnicodeDecodeError, configparser.Error) as exc:
        raise ValueError(f"Could not parse setup.cfg: {one_line(exc)}") from exc
    options = _resolved_options(sections["metadata"], project_dir)
    for section, key, field, parse in _PLAIN_OPTIONS:
        if key in sections[section]:
            options[key] = SetupOption(
                parse(sections[section][key]),
                _cfg_source(field),
                declared=_section_declares_key(cfg, section, key),
            )
    named = bool(options.get("name") and options["name"].value)
    try:
        config = _config_if_read(cfg, read_config and named, str(setup_cfg_path))
    except configparser.Error as exc:  # a [tool:pitloom] value's bad %
        raise ValueError(f"Could not parse setup.cfg: {one_line(exc)}") from exc
    return options, config


def read_setup_cfg(
    project_dir: Path, *, read_config: bool = True
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg`` alone, by
    :func:`read_setup_cfg_options`. Pitloom settings can be placed under a
    ``[tool:pitloom]`` section (note the colon separator used by
    ``setup.cfg`` convention). Without *read_config* that section is not
    parsed and the defaults are returned -- for a caller whose explicit
    config replaces it, so a fault in it cannot fail the read.

    Raises:
        FileNotFoundError: no ``setup.cfg``.
        ValueError: as :func:`read_setup_cfg_options`.
        _NoProjectNameError: ``[metadata]`` has no ``name``.
    """
    options, config = read_setup_cfg_options(project_dir, read_config=read_config)
    metadata = build_setuptools_metadata(options, {})
    if not metadata.name:
        raise _NoProjectNameError(
            "Project name is required in setup.cfg [metadata] section"
        )
    return metadata, config


def _config_if_read(
    cfg: configparser.ConfigParser, read: bool, source: str
) -> PitloomConfig:
    """``[tool:pitloom]`` from *cfg* (the file *source*), or the defaults
    without parsing it."""
    return _read_pitloom_config_from_cfg(cfg, source) if read else PitloomConfig()


def setup_cfg_pitloom_config(text: str, source: str | None = None) -> PitloomConfig:
    """``[tool:pitloom]`` from ``setup.cfg`` *text* (e.g. an sdist member),
    taken as :func:`read_setup_cfg` takes it for a directory: only when
    ``[metadata]`` names the project, else the defaults.

    *source* names the file in an unknown-key ``WARNING:``.

    Only ``[tool:pitloom]`` is interpolated: a ``%`` elsewhere (e.g. in a
    ``[metadata]`` description) is not this function's concern.

    Raises:
        ValueError: the text is not valid INI (``configparser.Error``) or
            its ``[tool:pitloom]`` settings are invalid; one line.
    """
    cfg = configparser.ConfigParser()
    try:
        cfg.read_string(text, source="setup.cfg")
        if not cfg.get("metadata", "name", raw=True, fallback="").strip():
            return PitloomConfig()
        return _read_pitloom_config_from_cfg(cfg, source)
    except configparser.Error as exc:  # also a value's bad % interpolation
        # configparser spreads a parse error over several lines.
        raise ValueError(one_line(exc)) from exc


def _pick_cfg_str(
    raw: dict[str, str], creation_raw: dict[str, str], *keys: str
) -> str | None:
    """Pick the first non-empty value matching any of the candidate keys,
    ``[tool:pitloom:creation]`` first whatever the spelling, as ``_pick_str``
    does for the TOML tables."""
    for src in (creation_raw, raw):
        for key in keys:
            val = src.get(key, "").strip()
            if val:
                return val
    return None


def _parse_creator_from_cfg(
    raw: dict[str, str], creation_raw: dict[str, str]
) -> list[dict[str, Any]] | None:
    """Extract creator dictionary from raw and creation tables."""
    creator_name = _pick_cfg_str(raw, creation_raw, "creator-name", "creator_name")
    if not creator_name:
        return None
    creator_dict: dict[str, Any] = {"name": creator_name}
    creator_type = _pick_cfg_str(raw, creation_raw, "creator-type", "creator_type")
    if creator_type:
        creator_dict["type"] = creator_type
    cemail = _pick_cfg_str(raw, creation_raw, "creator-email", "creator_email")
    if cemail:
        creator_dict["email"] = cemail
    return [creator_dict]


def _clean_creation_keys(tool_pitloom: dict[str, Any]) -> None:
    """Strip legacy and moved creation keys from dictionaries."""
    # "tool" is the single-tool spelling of ``creation-tool``, read apart.
    for key in (*_MOVED_CREATION_KEYS, "tool"):
        tool_pitloom.pop(key, None)
        if "creation" in tool_pitloom:
            tool_pitloom["creation"].pop(key, None)

    for key in ("no-creation-tool", "no_creation_tool"):
        tool_pitloom.pop(key, None)


def _populate_sub_sections_from_cfg(
    cfg: configparser.ConfigParser, tool_pitloom: dict[str, Any]
) -> None:
    """Populate creation, provenance, content-type, and fragment sub-tables."""
    creation_raw = _pitloom_section(cfg, "tool:pitloom:creation")
    if creation_raw:
        tool_pitloom["creation"] = parse_sub_section("creation", creation_raw)

    provenance_raw = _pitloom_section(cfg, "tool:pitloom:provenance")
    if provenance_raw:
        tool_pitloom["provenance"] = parse_sub_section("provenance", provenance_raw)

    content_type_raw = _pitloom_section(cfg, "tool:pitloom:content-type")
    if content_type_raw:
        ct = parse_sub_section("content-type", content_type_raw)
        # Every key is a pattern: none comes from [DEFAULT].
        override_raw = _own_items(cfg, "tool:pitloom:content-type:override")
        if override_raw:
            ct["override"] = [
                {"pattern": pat, "content-type": ctype}
                for pat, ctype in override_raw.items()
            ]
        tool_pitloom["content-type"] = ct

    fragment_raw = _pitloom_section(cfg, "tool:pitloom:fragment")
    if fragment_raw:
        tool_pitloom["fragment"] = parse_sub_section("fragment", fragment_raw)


def _read_pitloom_config_from_cfg(
    cfg: configparser.ConfigParser, source: str | None = None
) -> PitloomConfig:
    """Read ``[tool:pitloom]`` settings from a parsed ``setup.cfg``, named
    *source* in an unknown-key ``WARNING:``."""
    if not any(
        cfg.has_section(s) for s in cfg.sections() if s.startswith("tool:pitloom")
    ):
        return PitloomConfig()

    raw = _pitloom_section(cfg, "tool:pitloom")
    creation_raw = _pitloom_section(cfg, "tool:pitloom:creation")

    tool_pitloom: dict[str, Any] = {}
    data = {"tool": {"pitloom": tool_pitloom}}

    for k, v in raw.items():
        if k == "fragments":
            tool_pitloom["fragment"] = {
                "files": [f.strip() for f in v.splitlines() if f.strip()]
            }
        else:
            tool_pitloom[k] = coerce_cfg_value("", k, v)

    _populate_sub_sections_from_cfg(cfg, tool_pitloom)

    creator = _parse_creator_from_cfg(raw, creation_raw)
    if creator:
        tool_pitloom["creator"] = creator

    # [tool:pitloom] no-creation-tool, unless [tool:pitloom:creation] has
    # either spelling
    no_tool_keys = ("no-creation-tool", "no_creation_tool")
    if not any(k in creation_raw for k in no_tool_keys):
        for key in no_tool_keys:
            if key in raw:
                tool_pitloom.setdefault("creation", {})[key] = coerce_cfg_value(
                    "creation", key, raw[key]
                )

    _clean_creation_keys(tool_pitloom)
    # After the clean-up, which drops every single-valued spelling of it.
    tool_name = _pick_cfg_str(
        raw, creation_raw, "creation-tool", "creation_tool", "tool"
    )
    if tool_name:
        tool_pitloom["creation-tool"] = [{"name": tool_name}]
    return parse_pitloom_config(data, is_setup_cfg=True, source=source)
