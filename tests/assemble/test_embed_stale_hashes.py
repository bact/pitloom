# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression (#269): an embedded SBOM lists payload only, and an embed
refuses a signed wheel unless told to remove the signature.

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
_SIGS = {f"{_DI}RECORD.jws": b"jws", f"{_DI}RECORD.p7s": b"p7s"}
_COMMANDS = {
    "embed-wheel": ["embed-wheel"],
    "wheel": ["wheel", "--embed"],
}


def _embed(
    monkeypatch: pytest.MonkeyPatch, command: str, wheel: Path, *flags: str
) -> int:
    argv = ["loom", *_COMMANDS[command], str(wheel), "--offline", *flags]
    monkeypatch.setattr(sys, "argv", argv)
    return __main__.main()


@pytest.mark.parametrize("command", _COMMANDS)
def test_embedded_sbom_lists_payload_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Embedding twice (the second finds the first's ``sboms/``) lists the
    payload only -- not ``RECORD``, ``METADATA``, ``WHEEL``, ``licenses/`` or
    ``sboms/`` -- every listed hash matches the final wheel, and the
    ``.dist-info`` files stay in the archive, licence bytes untouched."""
    licence = f"{_DI}licenses/LICENSE"
    wheel = _make_dummy_wheel(
        tmp_path, "demo_pkg", "1.0.0", extra_members={licence: b"MIT\n"}
    )
    for _ in range(2):
        assert _embed(monkeypatch, command, wheel) == 0
        with zipfile.ZipFile(wheel) as zf:
            # Not vacuous: what is not listed really is in the wheel.
            assert {f"{_DI}METADATA", f"{_DI}WHEEL", licence} <= set(zf.namelist())
            assert zf.read(licence) == b"MIT\n"
            (sbom,) = [n for n in zf.namelist() if n.startswith(f"{_DI}sboms/")]
            listed = {
                el["name"]: h["hashValue"]
                for el in json.loads(zf.read(sbom))["@graph"]
                if el.get("type") == "software_File"
                for h in el.get("verifiedUsing", [])
            }
            assert listed.keys() == {"demo_pkg/__init__.py"}
            for name, digest in listed.items():
                assert hashlib.sha256(zf.read(name)).hexdigest() == digest


@pytest.mark.parametrize("command", _COMMANDS)
def test_signed_wheel_refused_unless_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """``RECORD.jws``/``RECORD.p7s`` sign the ``RECORD`` an embed rewrites:
    refused (wheel untouched) by default; with the flag both go, from the
    archive and from ``RECORD``, one ``INFO:`` each and no ``WARNING:``."""
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0", extra_members=_SIGS)
    before = wheel.read_bytes()

    assert _embed(monkeypatch, command, wheel) != 0
    assert wheel.read_bytes() == before
    assert "ERROR:" in capsys.readouterr().err

    assert _embed(monkeypatch, command, wheel, "--allow-signed-wheel") == 0
    with zipfile.ZipFile(wheel) as zf:
        assert not _SIGS.keys() & set(zf.namelist())
        assert not any(sig in zf.read(f"{_DI}RECORD").decode() for sig in _SIGS)
    err = capsys.readouterr().err.splitlines()
    assert len([x for x in err if x.startswith("INFO:") and "re-sign" in x]) == 2
    assert not [x for x in err if "WARNING:" in x]


def test_allow_signed_wheel_without_embed_warns_and_changes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom wheel`` writes no wheel without ``--embed``: the flag is a
    stated no-op (one ``WARNING:``), never silently dropped."""
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0", extra_members=_SIGS)
    before = wheel.read_bytes()
    out = tmp_path / "out.spdx3.json"
    argv = ["loom", "wheel", str(wheel), "--offline", "--allow-signed-wheel"]
    monkeypatch.setattr(sys, "argv", [*argv, "-o", str(out)])

    assert __main__.main() == 0
    assert wheel.read_bytes() == before and out.exists()
    err = capsys.readouterr().err.splitlines()
    assert [x for x in err if "WARNING:" in x] == [
        "WARNING: --allow-signed-wheel has no effect without --embed"
    ]
