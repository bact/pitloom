# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata and Pitloom config from setup.cfg.

See also: :mod:`pitloom.extract.project.setuptools_py` (AST parsing for setup.py)
and :mod:`pitloom.extract.project.setuptools` (facade).
"""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path
from typing import Any

from pitloom.core.config import (
    _MOVED_CREATION_KEYS,
    KNOWN_KEYS,
    PitloomConfig,
    parse_pitloom_config,
)
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project._setup_cfg_values import (
    coerce_cfg_value,
    parse_sub_section,
)
from pitloom.logging_config import one_line

# Matches "file: some/path" or "attr: module.attribute"
_DIRECTIVE_RE = re.compile(r"^(file|attr):\s*(.+)$")


class _NoProjectNameError(ValueError):
    """A setup.cfg/setup.py file has no project name -- try the next source."""


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


def _resolve_cfg_version_file_directive(
    value: str, project_dir: Path
) -> tuple[str | None, str | None]:
    """Resolve a file: directive for version from setup.cfg."""
    ver_file = project_dir / value
    if ver_file.exists():
        content = ver_file.read_text(encoding="utf-8").strip()
        if content and "\n" not in content and not content.startswith("#"):
            return content, f"Source: {value} | Method: file_directive"
    return None, None


def _resolve_cfg_attr_directive(
    value: str, project_dir: Path
) -> tuple[str | None, str | None]:
    """Resolve an attr: directive from setup.cfg."""
    parts = value.rsplit(".", 1)
    if len(parts) != 2:
        return None, None
    module_path, attr_name = parts
    module_rel = module_path.replace(".", "/")
    candidates = [
        project_dir / (module_rel + ".py"),
        project_dir / module_rel / "__init__.py",
        project_dir / "src" / (module_rel + ".py"),
        project_dir / "src" / module_rel / "__init__.py",
    ]
    for module_file in candidates:
        if module_file.exists():
            version = _read_version_attr(module_file, attr_name)
            if version:
                rel = module_file.relative_to(project_dir).as_posix()
                return version, f"Source: {rel} | Method: attr_directive"
    return None, None


def _resolve_cfg_version(
    raw: str,
    project_dir: Path,
) -> tuple[str | None, str | None]:
    """Resolve a version string from ``setup.cfg``, handling directives.

    Supports:
    * Literal values: ``version = 1.2.3``
    * File directive: ``version = file: VERSION``
    * Attr directive (best-effort): ``version = attr: package.__version__``
    """
    if not raw:
        return None, None

    m = _DIRECTIVE_RE.match(raw)
    if not m:
        return raw, "Source: setup.cfg | Field: metadata.version"

    directive, value = m.group(1), m.group(2).strip()
    if directive == "file":
        return _resolve_cfg_version_file_directive(value, project_dir)
    # _DIRECTIVE_RE only captures "file" or "attr" in this group, so
    # "attr" is the only remaining case.
    return _resolve_cfg_attr_directive(value, project_dir)


def _resolve_cfg_file_directive(raw: str, project_dir: Path) -> str | None:
    """Resolve a ``file: path`` directive or return the raw string unchanged."""
    if not raw:
        return None
    m = _DIRECTIVE_RE.match(raw)
    if m and m.group(1) == "file":
        file_path = project_dir / m.group(2).strip()
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return m.group(2).strip()
    return raw or None


def _read_version_attr(file_path: Path, attr_name: str) -> str | None:
    """Extract a named string attribute from a Python source file via AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if (
                    isinstance(target, ast.Name)
                    and target.id == attr_name
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    return node.value.value
    except (OSError, SyntaxError):
        pass
    return None


def _parse_cfg_authors(metadata: dict[str, str]) -> list[dict[str, str]]:
    """Combine ``author`` and ``author_email`` into a list of author dicts."""
    author_name = metadata.get("author", "").strip()
    author_email = metadata.get("author_email", "").strip()
    if not author_name and not author_email:
        return []
    entry: dict[str, str] = {}
    if author_name:
        entry["name"] = author_name
    if author_email:
        entry["email"] = author_email
    return [entry]


def _parse_cfg_keywords(raw: str) -> list[str]:
    """Parse keywords from ``setup.cfg``: space, comma, or newline separated."""
    if not raw:
        return []
    return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]


def _parse_cfg_urls(metadata: dict[str, str]) -> dict[str, str]:
    """Parse ``url`` and ``project_urls`` into a uniform URL dict."""
    urls: dict[str, str] = {}

    single_url = metadata.get("url", "").strip()
    if single_url:
        urls["Homepage"] = single_url

    project_urls_raw = metadata.get("project_urls", "")
    for line in project_urls_raw.splitlines():
        line = line.strip()
        if "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and val:
                urls[key] = val

    return urls


def _parse_cfg_requires(raw: str) -> list[str]:
    """Parse a multiline ``install_requires`` value into a list of PEP 508 strings."""
    deps = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            deps.append(line)
    return deps


# pylint: disable=too-many-locals
def read_setup_cfg(
    project_dir: Path, *, read_config: bool = True
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg``.

    Parses ``[metadata]`` for core project info and ``[options]`` for
    dependency declarations.  Pitloom settings can be placed under a
    ``[tool:pitloom]`` section (note the colon separator used by
    ``setup.cfg`` convention). Without *read_config* that section is not
    parsed and the defaults are returned -- for a caller whose explicit
    config replaces it, so a fault in it cannot fail the read.
    """
    setup_cfg_path = project_dir / "setup.cfg"
    if not setup_cfg_path.exists():
        raise FileNotFoundError(f"setup.cfg not found at {setup_cfg_path}")

    cfg = configparser.ConfigParser()
    cfg.read(setup_cfg_path, encoding="utf-8")

    metadata_raw = _section_dict(cfg, "metadata")
    options_raw = _section_dict(cfg, "options")

    name = metadata_raw.get("name", "").strip()
    if not name:
        raise _NoProjectNameError(
            "Project name is required in setup.cfg [metadata] section"
        )

    raw_version = metadata_raw.get("version", "").strip()
    version, version_source = _resolve_cfg_version(raw_version, project_dir)

    description = (
        metadata_raw.get("description") or metadata_raw.get("summary") or ""
    ).strip() or None

    readme = _resolve_cfg_file_directive(
        metadata_raw.get("long_description", "").strip(), project_dir
    )

    authors = _parse_cfg_authors(metadata_raw)
    keywords = _parse_cfg_keywords(metadata_raw.get("keywords", ""))
    license_name = metadata_raw.get("license", "").strip() or None
    urls = _parse_cfg_urls(metadata_raw)

    requires_python = (options_raw.get("python_requires") or "").strip() or None
    install_requires_raw = options_raw.get("install_requires", "")
    dependencies = _parse_cfg_requires(install_requires_raw)

    prov: dict[str, str] = {"name": "Source: setup.cfg | Field: metadata.name"}
    # _resolve_cfg_version() always returns a paired (version, source) --
    # never one truthy without the other -- so version_source alone gates it.
    if version_source:
        prov["version"] = version_source
    if description:
        prov["description"] = "Source: setup.cfg | Field: metadata.description"
    if readme:
        prov["readme"] = "Source: setup.cfg | Field: metadata.long_description"
    if license_name:
        prov["license"] = "Source: setup.cfg | Field: metadata.license"
    # Provenance for a container field is gated on the raw key's *presence*
    # in the file, not on whether parsing it produced a non-empty result --
    # an explicitly-declared-but-empty value (e.g. `install_requires =`)
    # is a genuine, authoritative "zero" that merge_project_metadata() must
    # not silently fill in from a lower-priority source, the same
    # None-vs-[] distinction pyproject.py's [project]-table path already
    # applies to `keywords`/`urls`/`dependencies`/`authors`.
    if _section_declares_key(cfg, "metadata", "author") or _section_declares_key(
        cfg, "metadata", "author_email"
    ):
        prov["authors"] = "Source: setup.cfg | Field: metadata.author/author_email"
        if authors:
            prov["copyright_text"] = (
                "Source: Pitloom generator | Method: inferred_from_authors"
            )
    if _section_declares_key(cfg, "metadata", "url") or _section_declares_key(
        cfg, "metadata", "project_urls"
    ):
        prov["urls"] = "Source: setup.cfg | Field: metadata.url/project_urls"
    if _section_declares_key(cfg, "options", "install_requires"):
        prov["dependencies"] = "Source: setup.cfg | Field: options.install_requires"
    if _section_declares_key(cfg, "options", "python_requires"):
        prov["requires_python"] = "Source: setup.cfg | Field: options.python_requires"
    if _section_declares_key(cfg, "metadata", "keywords"):
        prov["keywords"] = "Source: setup.cfg | Field: metadata.keywords"

    project_metadata = ProjectMetadata(
        name=name,
        version=version,
        description=description,
        readme=readme,
        requires_python=requires_python,
        license_name=license_name,
        keywords=keywords,
        authors=authors,
        urls=urls,
        dependencies=dependencies,
        provenance=prov,
    )

    return project_metadata, _config_if_read(cfg, read_config, str(setup_cfg_path))


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
