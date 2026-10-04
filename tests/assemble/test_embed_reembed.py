# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Re-embedding into a wheel that already carries an SBOM (PEP 770) must not
list the old SBOM as a ``software_File`` and must leave one SBOM, with a RECORD
that matches the final bytes, on every surface that embeds.

See also:
- :mod:`tests.assemble.test_embed_core` for the library-level re-embed test.
- :mod:`tests.assemble.test_embed_cli` for the CLI surface.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

from pitloom import __main__

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel

_STALE = "demo_pkg-1.0.0.dist-info/sboms/stale.spdx3.json"


def _run(monkeypatch: pytest.MonkeyPatch, *argv: str | Path) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *map(str, argv)])
    return __main__.main()


@pytest.mark.parametrize("surface", ["embed-wheel", "project-dir", "wheel-embed"])
def test_reembed_lists_no_prior_sbom(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    wheel = _make_dummy_wheel(
        tmp_path / "dist",
        extra_members={_STALE: _SAMPLE_SPDX3_JSON.encode("utf-8")},
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo_pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    cmd: tuple[str | Path, ...] = {
        "embed-wheel": ("embed-wheel", wheel),
        "project-dir": ("embed-wheel", "--project-dir", tmp_path, wheel),
        "wheel-embed": ("wheel", "--embed", wheel, "-o", tmp_path / "out.json"),
    }[surface]

    snapshots = []
    for _ in range(2):  # first run replaces the stale SBOM, second re-embeds
        assert _run(monkeypatch, *cmd) == 0
        snapshots.append(wheel.read_bytes())
        with zipfile.ZipFile(wheel) as zf:
            sboms = [n for n in zf.namelist() if "/sboms/" in n]
            assert len(sboms) == 1 and _STALE not in sboms
            graph = json.loads(zf.read(sboms[0]))["@graph"]
        files = [e["name"] for e in graph if e.get("type") == "software_File"]
        assert files, "vacuous: the SBOM lists no payload files"
        assert not [f for f in files if "/sboms/" in f]
        with WheelFile.open(wheel) as wf:
            wf.validate_record()
        assert _run(monkeypatch, "verify-wheel", "--fail-on-mismatch", wheel) == 0
    assert snapshots[0] == snapshots[1]
