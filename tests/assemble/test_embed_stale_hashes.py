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
from pitloom.embed import embed_wheel_sbom
from tests._raw_archive import METADATA, write_raw_zip

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
        "WARNING: Options: demo_pkg-1.0.0-py3-none-any.whl: "
        "--allow-signed-wheel has no effect without --embed"
    ]


@pytest.mark.parametrize("allow", [False, True])
def test_non_conforming_signature_name_is_refused_for_its_name(
    tmp_path: Path, allow: bool
) -> None:
    """A signature stored as ``./...RECORD.jws`` is refused for its name with
    or without the flag, never with the misleading hint that the flag would
    remove it; nothing is written."""
    wheel = write_raw_zip(
        tmp_path / "demo-1.0.0-py3-none-any.whl",
        {
            "demo-1.0.0.dist-info/METADATA": METADATA,
            "demo-1.0.0.dist-info/RECORD": b"",
            "./demo-1.0.0.dist-info/RECORD.jws": b"jws",
        },
    )
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="non-conforming name") as raised:
        embed_wheel_sbom(wheel, allow_signed_wheel=allow)

    assert "--allow-signed-wheel" not in str(raised.value)
    assert wheel.read_bytes() == before


@pytest.mark.parametrize("signed", [True, False])
def test_refusal_comes_before_the_sbom_is_generated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signed: bool
) -> None:
    """A refused wheel costs no generation (a build, with ``--allow-build``);
    the unsigned control proves the spy is reached."""
    wheel = _make_dummy_wheel(
        tmp_path, "demo_pkg", "1.0.0", extra_members=_SIGS if signed else None
    )
    calls: list[str] = []

    def spy(*_args: object, **_kwargs: object) -> None:
        calls.append("generated")
        raise RuntimeError("stop after generation")

    monkeypatch.setattr("pitloom.embed._generate_embed_sbom_json", spy)

    with pytest.raises(ValueError if signed else RuntimeError):
        embed_wheel_sbom(wheel)

    assert calls == ([] if signed else ["generated"])


def test_both_embed_commands_refuse_a_signed_wheel_alike(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A signed wheel whose only ``.dist-info`` its file name does not name:
    ``embed-wheel`` and ``wheel --embed`` give the same refusal and no
    ``WARNING:`` (neither generates first, so neither warns first)."""
    members = {
        "other-2.0.dist-info/METADATA": METADATA,
        "other-2.0.dist-info/RECORD": b"",
        "other-2.0.dist-info/RECORD.jws": b"jws",
    }
    errors = {}
    for command in _COMMANDS:
        directory = tmp_path / command
        directory.mkdir()
        wheel = write_raw_zip(directory / "demo-1.0.0-py3-none-any.whl", members)
        assert _embed(monkeypatch, command, wheel) != 0
        errors[command] = capsys.readouterr().err

    assert "WARNING:" not in errors["embed-wheel"] + errors["wheel"]
    refusals = {c: e[e.index("ARCHIVE=") :] for c, e in errors.items()}
    assert refusals["embed-wheel"] == refusals["wheel"]
    assert "RECORD.jws" in refusals["wheel"]
