# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression (#269): an embedded SBOM lists no file the embed rewrites.

See also: test_embed_core.py.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__

from .conftest import _make_dummy_wheel

_DI = "demo_pkg-1.0.0.dist-info/"


@pytest.mark.parametrize("command", ["embed-wheel", "wheel"])
def test_embedded_sbom_lists_no_record_or_sboms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Embedding twice (the second finds the first's ``sboms/``) lists neither
    ``RECORD`` nor ``sboms/``, and every listed hash matches the final wheel."""
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0")
    argv = ["loom", command, str(wheel), "--offline"]
    argv += ["--embed"] if command == "wheel" else []
    monkeypatch.setattr(sys, "argv", argv)
    for _ in range(2):
        assert __main__.main() == 0
        with zipfile.ZipFile(wheel) as zf:
            (sbom,) = [n for n in zf.namelist() if n.startswith(f"{_DI}sboms/")]
            listed = {
                el["name"]: h["hashValue"]
                for el in json.loads(zf.read(sbom))["@graph"]
                if el.get("type") == "software_File"
                for h in el.get("verifiedUsing", [])
            }
            assert f"{_DI}METADATA" in listed  # not vacuous
            assert not [n for n in listed if n == f"{_DI}RECORD" or "/sboms/" in n]
            for name, digest in listed.items():
                assert hashlib.sha256(zf.read(name)).hexdigest() == digest


def test_embed_removes_record_signatures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``RECORD.jws``/``RECORD.p7s`` sign the ``RECORD`` the embed rewrites:
    both go, from the archive and from ``RECORD``, with one WARNING each."""
    sigs = {f"{_DI}RECORD.jws": b"jws", f"{_DI}RECORD.p7s": b"p7s"}
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0", extra_members=sigs)
    with zipfile.ZipFile(wheel) as zf:
        assert sigs.keys() <= set(zf.namelist())  # not vacuous
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(wheel), "--offline"])
    assert __main__.main() == 0
    with zipfile.ZipFile(wheel) as zf:
        assert not sigs.keys() & set(zf.namelist())
        assert not any(s in zf.read(f"{_DI}RECORD").decode() for s in sigs)
    warnings = [x for x in capsys.readouterr().err.splitlines() if "WARNING:" in x]
    assert len(warnings) == len(sigs)
