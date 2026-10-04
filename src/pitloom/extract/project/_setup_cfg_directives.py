# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg`` value directives: ``file:`` and ``attr:``.

See also: :mod:`pitloom.extract.project.setuptools_cfg` (the reader).
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Matches "file: some/path" or "attr: module.attribute"
_DIRECTIVE_RE = re.compile(r"^(file|attr):\s*(.+)$")


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


def _resolve_cfg_file_directive(raw: str, project_dir: Path, field: str) -> str | None:
    """*raw*, or for ``file: a.txt, b.txt`` the text of each listed file,
    joined with ``\n`` (setuptools' ``read_files``). A listed file that
    does not exist is skipped, and when none exists the spec itself is
    returned as a filename hint. One that exists but cannot be read (a
    directory, no permission, not UTF-8) is skipped with one ``WARNING:``
    naming it and the setup.cfg *field*; ``None`` when nothing was read."""
    if not raw:
        return None
    m = _DIRECTIVE_RE.match(raw)
    if not (m and m.group(1) == "file"):
        return raw
    names = [part.strip() for part in m.group(2).split(",")]
    texts: list[str] = []
    found = False
    for name in names:
        path = project_dir / name
        if not os.path.lexists(path):
            continue
        found = True
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            log.warning(
                "%s: setup.cfg %s file %s could not be read (%s) -- ignoring it",
                project_dir,
                field,
                name,
                type(exc).__name__,
            )
    if texts:
        return "\n".join(texts)
    return None if found else m.group(2).strip()


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
