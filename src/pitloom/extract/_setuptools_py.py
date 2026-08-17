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
from pathlib import Path
from typing import Any

from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata


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


# pylint: disable=too-many-locals
# pylint: disable-next=too-many-branches
def read_setup_py(
    project_dir: Path,
) -> tuple[ProjectMetadata, PitloomConfig]:
    """Read project metadata from ``setup.py`` using AST parsing.

    Extracts keyword arguments from ``setup()`` or ``setuptools.setup()``
    calls.  Only **literal** values (strings, lists, dicts, tuples) are
    extracted; dynamic values (variables, function calls, f-strings) are
    silently skipped.
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
