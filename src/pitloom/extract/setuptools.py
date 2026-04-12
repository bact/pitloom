# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from setup.cfg and setup.py.

Supports setuptools-based projects that declare metadata in ``setup.cfg``
(configparser format) or ``setup.py`` (AST-parsed).  When both files exist,
``setup.cfg`` values take precedence, following setuptools conventions.

.. rubric:: Conflict resolution

When multiple sources are present, fields are merged with this priority order
(highest to lowest):

1. ``pyproject.toml [project]`` — handled upstream by
   :func:`~pitloom.extract.pyproject.read_pyproject`; merged via
   :func:`merge_metadata` by the assembler.
2. ``setup.cfg [metadata]`` / ``[options]``
3. ``setup.py`` ``setup()`` keyword arguments (AST-extracted literals only)

For each field the highest-priority non-empty value wins; provenance is
recorded per field so consumers can audit the source.

.. rubric:: Limitations (static analysis)

- Dynamic values in ``setup.py`` (variables, function calls, conditional
  expressions) are **not resolvable** — they are silently skipped.
- ``version = attr: package.__version__`` in ``setup.cfg`` uses best-effort
  file scanning via AST parsing of the referenced module file.
- Build-time metadata obtained via PEP 517
  ``prepare_metadata_for_build_wheel`` may differ from statically extracted
  values.  PEP 517 integration is planned as a future enhancement.

See Also:
    https://setuptools.pypa.io/en/latest/userguide/declarative_config.html
    https://peps.python.org/pep-0517/
"""

from __future__ import annotations

import ast
import configparser
import re
import sys
from pathlib import Path
from typing import Any

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# Matches "file: some/path" or "attr: module.attribute"
_DIRECTIVE_RE = re.compile(r"^(file|attr):\s*(.+)$")


def detect_build_backend(project_dir: Path) -> str | None:
    """Detect the build backend declared in ``pyproject.toml``.

    Reads the ``[build-system] build-backend`` field and returns a
    lower-case identifier.  Falls back to ``"setuptools"`` when no
    ``pyproject.toml`` is present but ``setup.cfg`` or ``setup.py`` exists.

    Args:
        project_dir: Project root directory.

    Returns:
        A lower-case backend string such as ``"setuptools"`` or
        ``"hatchling"``, or ``None`` when no backend can be determined.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        if (project_dir / "setup.cfg").exists() or (project_dir / "setup.py").exists():
            return "setuptools"
        return None

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        build_backend: str = data.get("build-system", {}).get("build-backend", "")
        for backend in ("setuptools", "hatchling", "flit", "poetry", "pdm"):
            if backend in build_backend:
                return backend
        if build_backend:
            return build_backend.split(".")[0].lower()
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


def read_setuptools(project_dir: Path) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg`` and/or ``setup.py``.

    Merges metadata from both files with ``setup.cfg`` taking precedence
    over ``setup.py``, following modern setuptools conventions.

    Args:
        project_dir: Project root directory.

    Returns:
        A 2-tuple of :class:`~pitloom.core.project.ProjectMetadata` and
        :class:`~pitloom.core.config.PitloomConfig`.  The config is populated
        from ``[tool:pitloom]`` in ``setup.cfg`` when present, otherwise
        defaults apply.

    Raises:
        FileNotFoundError: If neither ``setup.cfg`` nor ``setup.py`` exist,
            or neither contains a project name.
        ValueError: If a project name cannot be found in any source.
    """
    setup_cfg = project_dir / "setup.cfg"
    setup_py = project_dir / "setup.py"

    cfg_metadata: ProjectMetadata | None = None
    cfg_config: PitloomConfig = PitloomConfig()
    py_metadata: ProjectMetadata | None = None

    if setup_cfg.exists():
        try:
            cfg_metadata, cfg_config = read_setup_cfg(project_dir)
        except (FileNotFoundError, ValueError):
            pass

    if setup_py.exists():
        try:
            py_metadata, _ = read_setup_py(project_dir)
        except (FileNotFoundError, ValueError):
            pass

    if cfg_metadata is None and py_metadata is None:
        raise FileNotFoundError(
            f"No usable project metadata found in {project_dir}. "
            "Expected setup.cfg [metadata] name or setup.py setup(name=...)."
        )

    if cfg_metadata is not None and py_metadata is not None:
        return merge_metadata(cfg_metadata, py_metadata), cfg_config

    if cfg_metadata is not None:
        return cfg_metadata, cfg_config

    # Only setup.py succeeded
    assert py_metadata is not None
    return py_metadata, PitloomConfig()


# pylint: disable=too-many-locals
def read_setup_cfg(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.cfg``.

    Parses ``[metadata]`` for core project info and ``[options]`` for
    dependency declarations.  Pitloom settings can be placed under a
    ``[tool:pitloom]`` section (note the colon separator used by
    ``setup.cfg`` convention).

    Args:
        project_dir: Project root directory containing ``setup.cfg``.

    Returns:
        A 2-tuple of :class:`~pitloom.core.project.ProjectMetadata` and
        :class:`~pitloom.core.config.PitloomConfig`.

    Raises:
        FileNotFoundError: If ``setup.cfg`` is not found.
        ValueError: If ``name`` is absent from the ``[metadata]`` section.
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
        raise ValueError("Project name is required in setup.cfg [metadata] section")

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


# pylint: disable=too-many-locals
def read_setup_py(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.py`` using AST parsing.

    Extracts keyword arguments from ``setup()`` or ``setuptools.setup()``
    calls.  Only **literal** values (strings, lists, dicts, tuples) are
    extracted; dynamic values (variables, function calls, f-strings) are
    silently skipped.

    Args:
        project_dir: Project root directory containing ``setup.py``.

    Returns:
        A 2-tuple of :class:`~pitloom.core.project.ProjectMetadata` and a
        default :class:`~pitloom.core.config.PitloomConfig` (``setup.py``
        has no Pitloom configuration section).

    Raises:
        FileNotFoundError: If ``setup.py`` is not found.
        ValueError: If the file cannot be parsed or no project name is found.
    """
    setup_py_path = project_dir / "setup.py"
    if not setup_py_path.exists():
        raise FileNotFoundError(f"setup.py not found at {setup_py_path}")

    try:
        source = setup_py_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename="setup.py")
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"Could not parse setup.py: {exc}") from exc

    kwargs = _extract_setup_kwargs(tree)

    name = kwargs.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "Could not extract project name from setup.py. "
            "The name= argument must be a string literal."
        )
    name = name.strip()

    raw_version = kwargs.get("version")
    version = raw_version.strip() if isinstance(raw_version, str) else None

    description = kwargs.get("description")
    description = (
        description.strip() if isinstance(description, str) and description else None
    )

    readme_raw = kwargs.get("long_description")
    readme = (
        readme_raw.strip()
        if isinstance(readme_raw, str) and readme_raw.strip()
        else None
    )

    requires_python = kwargs.get("python_requires")
    requires_python = (
        requires_python.strip()
        if isinstance(requires_python, str) and requires_python
        else None
    )

    license_raw = kwargs.get("license")
    license_name = (
        license_raw.strip() if isinstance(license_raw, str) and license_raw else None
    )

    keywords_raw = kwargs.get("keywords", [])
    if isinstance(keywords_raw, str):
        keywords = [
            k.strip() for k in keywords_raw.replace(",", " ").split() if k.strip()
        ]
    elif isinstance(keywords_raw, (list, tuple)):
        keywords = [str(k).strip() for k in keywords_raw if k]
    else:
        keywords = []

    urls: dict[str, str] = {}
    url = kwargs.get("url", "")
    if isinstance(url, str) and url.strip():
        urls["Homepage"] = url.strip()
    project_urls_raw = kwargs.get("project_urls", {})
    if isinstance(project_urls_raw, dict):
        for k, v in project_urls_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                urls[k] = v

    author_name = kwargs.get("author")
    author_email = kwargs.get("author_email")
    authors: list[dict[str, str]] = []
    if isinstance(author_name, str) and author_name.strip():
        entry: dict[str, str] = {"name": author_name.strip()}
        if isinstance(author_email, str) and author_email.strip():
            entry["email"] = author_email.strip()
        authors.append(entry)

    install_requires = kwargs.get("install_requires", [])
    dependencies = (
        [str(d).strip() for d in install_requires if d]
        if isinstance(install_requires, (list, tuple))
        else []
    )

    prov: dict[str, str] = {"name": "Source: setup.py | Field: setup(name=...)"}
    if version:
        prov["version"] = "Source: setup.py | Field: setup(version=...)"
    if description:
        prov["description"] = "Source: setup.py | Field: setup(description=...)"
    if readme:
        prov["readme"] = "Source: setup.py | Field: setup(long_description=...)"
    if license_name:
        prov["license"] = "Source: setup.py | Field: setup(license=...)"
    if authors:
        prov["authors"] = "Source: setup.py | Field: setup(author=...)"
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )
    if urls:
        prov["urls"] = "Source: setup.py | Field: setup(url=...)"
    if dependencies:
        prov["dependencies"] = "Source: setup.py | Field: setup(install_requires=...)"
    if requires_python:
        prov["requires_python"] = "Source: setup.py | Field: setup(python_requires=...)"
    if keywords:
        prov["keywords"] = "Source: setup.py | Field: setup(keywords=...)"

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
    return project_metadata, PitloomConfig()


def merge_metadata(
    primary: ProjectMetadata,
    secondary: ProjectMetadata,
) -> ProjectMetadata:
    """Merge two :class:`~pitloom.core.project.ProjectMetadata` objects.

    The primary takes precedence field-by-field: for each attribute, the
    primary value is used when non-empty/truthy; otherwise the secondary
    value fills the gap.  The primary ``name`` is always kept.

    Provenance entries from both sources are merged, with primary
    provenance overriding secondary on key conflicts.

    Typical usage::

        # pyproject.toml wins; setup.cfg fills missing fields
        merged = merge_metadata(pyproject_meta, setup_cfg_meta)

        # setup.cfg wins over setup.py
        merged = merge_metadata(cfg_meta, py_meta)

    Args:
        primary: Higher-priority metadata source.
        secondary: Lower-priority metadata source used as fallback.

    Returns:
        A new :class:`~pitloom.core.project.ProjectMetadata` with merged fields.
    """

    def _pick(p: Any, s: Any) -> Any:
        return p if p else s

    merged_provenance = {**secondary.provenance, **primary.provenance}

    return ProjectMetadata(
        name=primary.name,
        version=_pick(primary.version, secondary.version),
        description=_pick(primary.description, secondary.description),
        readme=_pick(primary.readme, secondary.readme),
        requires_python=_pick(primary.requires_python, secondary.requires_python),
        license_name=_pick(primary.license_name, secondary.license_name),
        keywords=_pick(primary.keywords, secondary.keywords),
        authors=_pick(primary.authors, secondary.authors),
        urls=_pick(primary.urls, secondary.urls),
        dependencies=_pick(primary.dependencies, secondary.dependencies),
        provenance=merged_provenance,
        files=_pick(primary.files, secondary.files),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _section_dict(cfg: configparser.ConfigParser, section: str) -> dict[str, str]:
    """Return a section's items as a plain dict, or empty dict if absent."""
    return dict(cfg.items(section)) if cfg.has_section(section) else {}


def _resolve_cfg_version(
    raw: str,
    project_dir: Path,
) -> tuple[str | None, str | None]:
    """Resolve a version string from ``setup.cfg``, handling directives.

    Supports:

    * Literal values: ``version = 1.2.3``
    * File directive: ``version = file: VERSION``
    * Attr directive (best-effort): ``version = attr: package.__version__``

    Returns:
        ``(version_string, provenance_source)`` or ``(None, None)`` if
        the version cannot be resolved.
    """
    if not raw:
        return None, None

    m = _DIRECTIVE_RE.match(raw)
    if not m:
        return raw, "Source: setup.cfg | Field: metadata.version"

    directive, value = m.group(1), m.group(2).strip()

    if directive == "file":
        ver_file = project_dir / value
        if ver_file.exists():
            content = ver_file.read_text(encoding="utf-8").strip()
            # Expect plain version string (possibly with a leading "v")
            if content and "\n" not in content and not content.startswith("#"):
                return content, f"Source: {value} | Method: file_directive"

    elif directive == "attr":
        # attr: package.module.ATTR  →  look for package/module.py or __init__.py
        parts = value.rsplit(".", 1)
        if len(parts) == 2:
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
                        rel = module_file.relative_to(project_dir)
                        return version, f"Source: {rel} | Method: attr_directive"

    return None, None


def _resolve_cfg_file_directive(raw: str, project_dir: Path) -> str | None:
    """Resolve a ``file: path`` directive or return the raw string unchanged.

    Used for ``long_description = file: README.md``.  When the referenced
    file exists its content is returned; when it is absent just the filename
    hint is returned.
    """
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


def _extract_setup_kwargs(tree: ast.Module) -> dict[str, Any]:
    """Extract keyword arguments from a ``setup()`` or ``setuptools.setup()`` call.

    Returns the first matching call's kwargs as a dict.  Non-literal values
    (variables, function calls) are omitted from the result.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_setup_call = (isinstance(func, ast.Name) and func.id == "setup") or (
            isinstance(func, ast.Attribute) and func.attr == "setup"
        )
        if not is_setup_call:
            continue
        kwargs: dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is not None:  # skip **expansion
                value = _ast_literal(kw.value)
                if value is not None:
                    kwargs[kw.arg] = value
        return kwargs
    return {}


def _ast_literal(node: ast.expr) -> Any:
    """Extract a Python literal value from an AST expression.

    Returns ``None`` for non-literal expressions (variables, function calls,
    f-strings, etc.) rather than raising.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [v for elt in node.elts if (v := _ast_literal(elt)) is not None]
    if isinstance(node, ast.Tuple):
        return [v for elt in node.elts if (v := _ast_literal(elt)) is not None]
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key, value in zip(node.keys, node.values, strict=False):
            if key is None:
                continue  # **unpacking
            k = _ast_literal(key)
            v = _ast_literal(value)
            if isinstance(k, str):
                result[k] = v
        return result
    return None


def _read_pitloom_config_from_cfg(
    cfg: configparser.ConfigParser,
) -> PitloomConfig:
    """Read ``[tool:pitloom]`` settings from a parsed ``setup.cfg``.

    ``setup.cfg`` uses a colon as the sub-section separator
    (``[tool:pitloom]``) rather than the dot used in ``pyproject.toml``
    (``[tool.pitloom]``).  An optional ``[tool:pitloom:creation]`` section
    mirrors ``[tool.pitloom.creation]``.
    """
    has_pitloom = cfg.has_section("tool:pitloom")
    has_creation = cfg.has_section("tool:pitloom:creation")
    if not has_pitloom and not has_creation:
        return PitloomConfig()

    raw = _section_dict(cfg, "tool:pitloom")
    creation_raw = _section_dict(cfg, "tool:pitloom:creation")

    def _pick_str(*keys: str) -> str | None:
        for key in keys:
            for src in (creation_raw, raw):
                val = src.get(key, "").strip()
                if val:
                    return val
        return None

    pretty_str = raw.get("pretty", "").strip().lower()
    pretty = pretty_str in ("true", "1", "yes")

    desc_rel_str = (
        (raw.get("describe-relationship") or raw.get("describe_relationship") or "")
        .strip()
        .lower()
    )
    if desc_rel_str in ("true", "1", "yes"):
        desc_rel: bool | None = True
    elif desc_rel_str in ("false", "0", "no"):
        desc_rel = False
    else:
        desc_rel = None

    sbom_basename = (
        raw.get("sbom-basename") or raw.get("sbom_basename") or ""
    ).strip() or None

    fragments_raw = raw.get("fragments", "")
    fragments = [f.strip() for f in fragments_raw.splitlines() if f.strip()]

    return PitloomConfig(
        pretty=pretty,
        describe_relationship=desc_rel,
        sbom_basename=sbom_basename,
        fragments=fragments,
        creation_creator_name=_pick_str("creator-name", "creator_name"),
        creation_creator_email=_pick_str("creator-email", "creator_email"),
        creation_creation_datetime=_pick_str(
            "creation-datetime", "creation_datetime", "datetime"
        ),
        creation_creation_tool=_pick_str("creation-tool", "creation_tool", "tool"),
        creation_comment=_pick_str("creation-comment", "creation_comment", "comment"),
    )
