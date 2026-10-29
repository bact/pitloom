# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The build hook's SBOM hashes a Git LFS pointer as the wheel ships it
(its own text, as ``RECORD`` does), not by its ``oid``.

See also: tests/test_lfs_pointer_surfaces.py (every route's flag).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tests._lfs import pointers, tree, write_project

from ..conftest import make_hook, staged_sbom


def test_hook_hashes_a_pointer_as_the_wheel_ships_it(tmp_path: Path) -> None:
    """Each pointer's ``verifiedUsing`` is its text's SHA-256 and SHA-512."""
    files, stated = tree(), pointers()
    write_project(tmp_path, files)
    hook = make_hook(str(tmp_path), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        staged = staged_sbom(build_data)
        assert staged is not None
        graph = json.loads(staged.read_text(encoding="utf-8"))["@graph"]
    finally:
        hook.finalize("standard", build_data, "")
    hashes = {
        element["name"]: {
            h["algorithm"]: h["hashValue"] for h in element["verifiedUsing"]
        }
        for element in graph
        if element["type"] == "software_File" and "verifiedUsing" in element
    }
    for name in stated:
        assert stated[name].oid != hashlib.sha256(files[name]).hexdigest()
        assert hashes[name] == {
            "sha256": hashlib.sha256(files[name]).hexdigest(),
            "sha512": hashlib.sha512(files[name]).hexdigest(),
        }
