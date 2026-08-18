# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata and Pitloom config from setup.cfg.

See also: :mod:`pitloom.extract._setuptools_py` (AST parsing for setup.py)
and :mod:`pitloom.extract._setuptools` (facade).
"""

from __future__ import annotations

import ast
import configparser
import re
from pathlib import Path
from typing import Any

from pitloom.core.config import (
    _MOVED_CREATION_KEYS,
    PitloomConfig,
    parse_pitloom_config,
)
from pitloom.core.project import ProjectMetadata

# Matches "file: some/path" or "attr: module.attribute"
_DIRECTIVE_RE = re.compile(r"^(file|attr):\s*(.+)$")


class _NoProjectNameError(ValueError):
    """A setup.cfg/setup.py file has no project name -- try the next source."""


def _section_dict(cfg: configparser.ConfigParser, section: str) -> dict[str, str]:
    """Return a section's items as a plain dict, or empty dict if absent."""
    return dict(cfg.items(section)) if cfg.has_section(section) else {}


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
    if directive == "attr":
        return _resolve_cfg_attr_directive(value, project_dir)
    return None, None


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
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg``.

    Parses ``[metadata]`` for core project info and ``[options]`` for
    dependency declarations.  Pitloom settings can be placed under a
    ``[tool:pitloom]`` section (note the colon separator used by
    ``setup.cfg`` convention).
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
    if version_source:
        prov["version"] = version_source
    elif version:
        prov["version"] = "Source: setup.cfg | Field: metadata.version"
    if description:
        prov["description"] = "Source: setup.cfg | Field: metadata.description"
    if readme:
        prov["readme"] = "Source: setup.cfg | Field: metadata.long_description"
    if license_name:
        prov["license"] = "Source: setup.cfg | Field: metadata.license"
    if authors:
        prov["authors"] = "Source: setup.cfg | Field: metadata.author/author_email"
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )
    if urls:
        prov["urls"] = "Source: setup.cfg | Field: metadata.url/project_urls"
    if dependencies:
        prov["dependencies"] = "Source: setup.cfg | Field: options.install_requires"
    if requires_python:
        prov["requires_python"] = "Source: setup.cfg | Field: options.python_requires"
    if keywords:
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

    pitloom_config = _read_pitloom_config_from_cfg(cfg)
    return project_metadata, pitloom_config


_KNOWN_BOOL_KEYS = frozenset(
    {
        "pretty",
        "describe-relationship",
        "describe_relationship",
        "offline",
        "no-creation-tool",
        "no_creation_tool",
        "local",
        "enabled",
    }
)


def _bool_val(v: str) -> bool | None:
    """Parse boolean values from INI strings."""
    v = v.strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


def _parse_sub_section(sub_raw: dict[str, str]) -> dict[str, Any]:
    """Parse key-values of a sub-section table in setup.cfg."""
    sub: dict[str, Any] = {}
    for k, v in sub_raw.items():
        if k in _KNOWN_BOOL_KEYS:
            b = _bool_val(v)
            sub[k] = b if b is not None else v.strip()
        elif k == "files":
            sub[k] = [f.strip() for f in v.splitlines() if f.strip()]
        else:
            sub[k] = v.strip()
    return sub


def _pick_cfg_str(
    raw: dict[str, str], creation_raw: dict[str, str], *keys: str
) -> str | None:
    """Pick the first non-empty value matching any of the candidate keys."""
    for key in keys:
        for src in (creation_raw, raw):
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
    for key in _MOVED_CREATION_KEYS:
        tool_pitloom.pop(key, None)
        if "creation" in tool_pitloom:
            tool_pitloom["creation"].pop(key, None)

    for key in ("no-creation-tool", "no_creation_tool"):
        tool_pitloom.pop(key, None)


def _populate_sub_sections_from_cfg(
    cfg: configparser.ConfigParser, tool_pitloom: dict[str, Any]
) -> None:
    """Populate creation, provenance, content-type, and fragment sub-tables."""
    creation_raw = _section_dict(cfg, "tool:pitloom:creation")
    if creation_raw:
        tool_pitloom["creation"] = _parse_sub_section(creation_raw)

    provenance_raw = _section_dict(cfg, "tool:pitloom:provenance")
    if provenance_raw:
        tool_pitloom["provenance"] = _parse_sub_section(provenance_raw)

    content_type_raw = _section_dict(cfg, "tool:pitloom:content-type")
    if content_type_raw:
        ct = _parse_sub_section(content_type_raw)
        override_raw = _section_dict(cfg, "tool:pitloom:content-type:override")
        if override_raw:
            ct["override"] = [
                {"pattern": pat, "content-type": ctype}
                for pat, ctype in override_raw.items()
            ]
        tool_pitloom["content-type"] = ct

    fragment_raw = _section_dict(cfg, "tool:pitloom:fragment")
    if fragment_raw:
        tool_pitloom["fragment"] = _parse_sub_section(fragment_raw)


def _read_pitloom_config_from_cfg(
    cfg: configparser.ConfigParser,
) -> PitloomConfig:
    """Read ``[tool:pitloom]`` settings from a parsed ``setup.cfg``."""
    if not any(
        cfg.has_section(s) for s in cfg.sections() if s.startswith("tool:pitloom")
    ):
        return PitloomConfig()

    raw = _section_dict(cfg, "tool:pitloom")
    creation_raw = _section_dict(cfg, "tool:pitloom:creation")

    tool_pitloom: dict[str, Any] = {}
    data = {"tool": {"pitloom": tool_pitloom}}

    for k, v in raw.items():
        if k in _KNOWN_BOOL_KEYS:
            b = _bool_val(v)
            tool_pitloom[k] = b if b is not None else v.strip()
        elif k == "fragments":
            tool_pitloom["fragment"] = {
                "files": [f.strip() for f in v.splitlines() if f.strip()]
            }
        else:
            tool_pitloom[k] = v.strip()

    _populate_sub_sections_from_cfg(cfg, tool_pitloom)

    creator = _parse_creator_from_cfg(raw, creation_raw)
    if creator:
        tool_pitloom["creator"] = creator

    tool_name = _pick_cfg_str(
        raw, creation_raw, "creation-tool", "creation_tool", "tool"
    )
    if tool_name:
        tool_pitloom["creation-tool"] = [{"name": tool_name}]

    no_creation_tool = _pick_cfg_str(
        raw, creation_raw, "no-creation-tool", "no_creation_tool"
    )
    if no_creation_tool is not None:
        b = _bool_val(no_creation_tool)
        if b is not None:
            if "creation" not in tool_pitloom:
                tool_pitloom["creation"] = {}
            tool_pitloom["creation"]["no-creation-tool"] = b

    _clean_creation_keys(tool_pitloom)
    return parse_pitloom_config(data)
