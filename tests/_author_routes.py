# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared builders for the author surface tests.

See also: tests/test_author_surfaces.py,
tests/test_author_split_surfaces.py and tests/test_author_split_warnings.py
(the users).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pitloom.core.creation import CreationMetadata
from tests.extract.conftest import make_hook

CREATED = CreationMetadata(creation_datetime="2024-05-01T00:00:00Z")
#: In every author split ``WARNING:``, whichever field was split.
SPLIT_MARK = "names on ',' / ';'"


def core_headers(author: str | None, email_: str | None) -> str:
    """A ``demo`` core-metadata text with these ``Author`` and
    ``Author-email`` headers, each left out when ``None``."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
    text += f"Author: {author}\n" if author is not None else ""
    return text + (f"Author-email: {email_}\n" if email_ is not None else "")


def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``[tool.pitloom]`` borrowed from the current directory; a fixed
    creation time (:data:`CREATED`) for the CLI."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1714521600")  # 2024-05-01


def write_wheel(
    tmp_path: Path,
    metadata: str,
    version: str = "1.0",
    dist_info: dict[str, bytes] | None = None,
) -> Path:
    """A ``demo`` wheel with *metadata* as its ``METADATA`` and the
    *dist_info* files (path under the ``.dist-info`` to bytes)."""
    wheel = tmp_path / f"demo-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(f"demo-{version}.dist-info/METADATA", metadata)
        for name, data in (dist_info or {}).items():
            zf.writestr(f"demo-{version}.dist-info/{name}", data)
        zf.writestr("demo/__init__.py", "")
    return wheel


def hook_sbom(project: Path) -> str:
    """The SBOM the Hatchling build hook stages for *project*'s wheel: the
    real ``PitloomBuildHook.initialize()``, not just its metadata step."""
    hook = make_hook(str(project), {})
    build_data: dict[str, list[str]] = {}
    hook.initialize("standard", build_data)
    try:
        (staged,) = build_data["sbom_files"]
        return Path(staged).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")
