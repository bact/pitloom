# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python project metadata from setup.py using AST parsing.

See also: :mod:`pitloom.extract._setuptools_cfg` (setup.cfg parsing)
and :mod:`pitloom.extract._setuptools` (facade).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata


def iter_setup_calls(tree: ast.AST) -> Iterator[ast.Call]:
    """Yield every ``setup()``/``x.setup()``-named call in *tree*, in
    ``ast.walk`` order -- matched on the callable's own name only (bound
    to any object, e.g. ``setuptools.setup``), not on where it's
    imported from. A caller that only wants the real setuptools call
    among several matches (e.g. an unrelated ``logger.setup()`` earlier
    in the file) must inspect the yielded calls itself; this generator
    makes no such distinction."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "setup") or (
            isinstance(func, ast.Attribute) and func.attr == "setup"
        ):
            yield node


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


def _extract_setup_kwargs(tree: ast.Module) -> dict[str, Any]:
    """Extract keyword arguments from a ``setup()`` or ``setuptools.setup()`` call.

    Returns the first matching call's kwargs as a dict.  Non-literal values
    (variables, function calls) are omitted from the result.
    """
    node = next(iter_setup_calls(tree), None)
    if node is None:
        return {}
    kwargs: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is not None:  # skip **expansion
            value = _ast_literal(kw.value)
            if value is not None:
                kwargs[kw.arg] = value
    return kwargs


def _parse_setup_keywords(kwargs: dict[str, Any]) -> list[str]:
    """Extract normalized keyword list from setup() kwargs."""
    keywords_raw = kwargs.get("keywords", [])
    if isinstance(keywords_raw, str):
        return [k.strip() for k in keywords_raw.replace(",", " ").split() if k.strip()]
    if isinstance(keywords_raw, (list, tuple)):
        return [str(k).strip() for k in keywords_raw if k]
    return []


def _parse_setup_urls(kwargs: dict[str, Any]) -> dict[str, str]:
    """Extract URLs dictionary from setup() kwargs."""
    urls: dict[str, str] = {}
    url = kwargs.get("url", "")
    if isinstance(url, str) and url.strip():
        urls["Homepage"] = url.strip()
    project_urls_raw = kwargs.get("project_urls", {})
    if isinstance(project_urls_raw, dict):
        for k, v in project_urls_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                urls[k] = v
    return urls


def _parse_setup_authors(kwargs: dict[str, Any]) -> list[dict[str, str]]:
    """Extract authors list from setup() kwargs."""
    author_name = kwargs.get("author")
    author_email = kwargs.get("author_email")
    authors: list[dict[str, str]] = []
    if isinstance(author_name, str) and author_name.strip():
        entry: dict[str, str] = {"name": author_name.strip()}
        if isinstance(author_email, str) and author_email.strip():
            entry["email"] = author_email.strip()
        authors.append(entry)
    return authors


# pylint: disable=too-many-arguments
def _build_setup_py_provenance(
    *,
    has_version: bool,
    has_description: bool,
    has_readme: bool,
    has_license: bool,
    has_authors: bool,
    has_urls: bool,
    has_dependencies: bool,
    has_requires_python: bool,
    has_keywords: bool,
) -> dict[str, str]:
    """Build provenance dictionary for extracted setup.py fields."""
    prov: dict[str, str] = {"name": "Source: setup.py | Field: setup(name=...)"}
    if has_version:
        prov["version"] = "Source: setup.py | Field: setup(version=...)"
    if has_description:
        prov["description"] = "Source: setup.py | Field: setup(description=...)"
    if has_readme:
        prov["readme"] = "Source: setup.py | Field: setup(long_description=...)"
    if has_license:
        prov["license"] = "Source: setup.py | Field: setup(license=...)"
    if has_authors:
        prov["authors"] = "Source: setup.py | Field: setup(author=...)"
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )
    if has_urls:
        prov["urls"] = "Source: setup.py | Field: setup(url=...)"
    if has_dependencies:
        prov["dependencies"] = "Source: setup.py | Field: setup(install_requires=...)"
    if has_requires_python:
        prov["requires_python"] = "Source: setup.py | Field: setup(python_requires=...)"
    if has_keywords:
        prov["keywords"] = "Source: setup.py | Field: setup(keywords=...)"
    return prov


def _extract_str_kwarg(kwargs: dict[str, Any], key: str) -> str | None:
    """Extract a stripped string kwarg if non-empty."""
    val = kwargs.get(key)
    return val.strip() if isinstance(val, str) and val.strip() else None


# pylint: disable=too-many-locals
def read_setup_py(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.py`` using AST parsing."""
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

    version = _extract_str_kwarg(kwargs, "version")
    description = _extract_str_kwarg(kwargs, "description")
    readme = _extract_str_kwarg(kwargs, "long_description")
    requires_python = _extract_str_kwarg(kwargs, "python_requires")
    license_name = _extract_str_kwarg(kwargs, "license")
    keywords = _parse_setup_keywords(kwargs)
    urls = _parse_setup_urls(kwargs)
    authors = _parse_setup_authors(kwargs)

    install_requires = kwargs.get("install_requires", [])
    dependencies = (
        [str(d).strip() for d in install_requires if d]
        if isinstance(install_requires, (list, tuple))
        else []
    )

    prov = _build_setup_py_provenance(
        has_version=bool(version),
        has_description=bool(description),
        has_readme=bool(readme),
        has_license=bool(license_name),
        has_authors=bool(authors),
        has_urls=bool(urls),
        has_dependencies=bool(dependencies),
        has_requires_python=bool(requires_python),
        has_keywords=bool(keywords),
    )

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
