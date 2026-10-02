# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel's identity, and a wheel with an unreadable member, on every
surface that reads a wheel: ``loom wheel``, ``loom generate``,
``loom wheel --embed``, ``loom embed-wheel``, ``generate_wheel_sbom()`` and
``embed_wheel_sbom()``; and ``loom verify-wheel`` and ``loom validate-wheel``
where they read members.

Each takes the name and version from the wheel's own top-level
``.dist-info``; each refuses a wheel with an unreadable member, one name
twice or a member name ``zipfile`` cannot open with one ``ERROR:`` line (the
library: one ``ValueError``), writes nothing and leaves the wheel as it was.

See also: tests/extract/test_wheel_identity.py (``read_wheel``),
tests/core/test_wheel_dist_info.py (the selector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.core import wheel_dist_info
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from tests._wheel_damage import (
    METADATA,
    central_name_damaged_wheel,
    corrupt_deflate,
    damaged_wheel,
    raw_wheel,
)
from tests.build_and_read_shared import FakeBuildState, install_fake_build

_WHEEL = "demo-1.0-py3-none-any.whl"
_REAL = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n"
_EVIL = "Metadata-Version: 2.1\nName: evil\nVersion: 9.9\n"
_BULK = b"".join(b"%d,\n" % i for i in range(2000))  # deflates to a few KB


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``[tool.pitloom]`` to borrow from the current directory; a fixed
    creation time."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _hijack_wheel(tmp_path: Path) -> Path:
    path = tmp_path / _WHEEL
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", _REAL)
        zf.writestr("demo/_vendor/zipp-3.23.0.dist-info/METADATA", _EVIL)
        zf.writestr("evil-9.9.dist-info/METADATA", _EVIL)
        zf.writestr("demo/__init__.py", "")
    return path


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _cli(argv: list[str], mp: pytest.MonkeyPatch) -> int:
    mp.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _cli_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    output = wheel.parent / "out.spdx3.json"
    assert _cli(["wheel", str(wheel), "--offline", "-o", str(output)], mp) == 0
    return output.read_text(encoding="utf-8")


def _cli_generate(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    output = wheel.parent / "out.spdx3.json"
    assert _cli(["generate", str(wheel), "--offline", "-o", str(output)], mp) == 0
    return output.read_text(encoding="utf-8")


def _cli_wheel_embed(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    assert _cli(["wheel", str(wheel), "--embed", "--offline"], mp) == 0
    return _embedded(wheel)


def _cli_embed_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    assert _cli(["embed-wheel", str(wheel)], mp) == 0
    return _embedded(wheel)


def _lib_generate(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(wheel, offline=True)


def _lib_embed(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return _embedded(embed_wheel_sbom(wheel)[0])


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-wheel": _cli_wheel,
    "cli-generate": _cli_generate,
    "cli-wheel-embed": _cli_wheel_embed,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate_wheel_sbom": _lib_generate,
    "lib-embed_wheel_sbom": _lib_embed,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_the_identity_is_the_wheels_own_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    wheel = _hijack_wheel(tmp_path)

    sbom = _SURFACES[surface](wheel, monkeypatch)

    packages = [
        (e["name"], e["software_packageVersion"])
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "software_Package"
    ]
    assert packages == [("demo", "1.0")]
    assert "WARNING:" not in capsys.readouterr().err


def _cli_argv(surface: str, wheel: Path) -> list[str]:
    return {
        "cli-wheel": ["wheel", str(wheel), "--offline", "-o", "out.spdx3.json"],
        "cli-generate": ["generate", str(wheel), "--offline", "-o", "out.spdx3.json"],
        "cli-wheel-embed": [
            *["wheel", str(wheel), "--embed", "--offline", "-o", "out.spdx3.json"],
        ],
        "cli-embed-wheel": ["embed-wheel", str(wheel), "-o", "out.spdx3.json"],
        "cli-verify-wheel": ["verify-wheel", str(wheel)],
        "cli-validate-wheel": ["validate-wheel", str(wheel)],
    }[surface]


def _with_sbom(wheel: Path, sbom: bytes = b"{}") -> Path:
    """*wheel* with an SBOM embedded, so a reader goes on to read the rest."""
    with zipfile.ZipFile(wheel, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo-1.0.dist-info/sboms/demo-1.0.spdx3.json", sbom)
    return wheel


def _duplicate_wheel(tmp_path: Path) -> Path:
    """The backslash hijack: one install location under two names."""
    return raw_wheel(
        tmp_path / _WHEEL,
        [
            ("demo-1.0.dist-info/METADATA", _REAL),
            ("demo-1.0.dist-info\\METADATA", _EVIL),
            ("demo/__init__.py", ""),
        ],
    )


def _damaged_metadata_wheel(tmp_path: Path) -> Path:
    return _with_sbom(damaged_wheel(tmp_path, "deflate", in_metadata=True))


def _damaged_sbom_wheel(tmp_path: Path) -> Path:
    wheel = _with_sbom(damaged_wheel(tmp_path, "deflate"), _BULK)
    corrupt_deflate(wheel, "demo-1.0.dist-info/sboms/demo-1.0.spdx3.json")
    return wheel


# cause -> (wheel builder, what the one error says)
_CAUSES: dict[str, tuple[Callable[[Path], Path], str]] = {
    "unreadable-member": (
        lambda d: damaged_wheel(d, "deflate"),
        f"ENTRY={'demo/bad.py'!r}: could not read (zlib.error) -- wheel refused",
    ),
    "duplicate-name": (
        _duplicate_wheel,
        f"ENTRY={'demo-1.0.dist-info/METADATA'!r}: duplicate member name -- wheel",
    ),
    "bad-central-name": (
        central_name_damaged_wheel,
        f"ARCHIVE={_WHEEL!r}: could not open (UnicodeDecodeError) -- wheel refused",
    ),
    "damaged-metadata": (
        _damaged_metadata_wheel,
        f"ENTRY={METADATA!r}: could not read (zlib.error) -- wheel refused",
    ),
    "damaged-sbom": (
        _damaged_sbom_wheel,
        "demo-1.0.spdx3.json': could not read (zlib.error) -- wheel refused",
    ),
}
# The embed and generate surfaces read every member; verify and validate read
# the dist-info's METADATA and the embedded SBOM, and the file list.
_GENERATING = sorted(_SURFACES)
_MATRIX = (
    [(s, c) for s in _GENERATING for c in list(_CAUSES)[:3]]
    + [("cli-verify-wheel", c) for c in list(_CAUSES)[1:]]
    + [
        ("cli-validate-wheel", c)
        for c in ("duplicate-name", "bad-central-name", "damaged-sbom")
    ]
)


@pytest.mark.parametrize(("surface", "cause"), _MATRIX)
def test_a_refused_wheel_is_refused_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    cause: str,
) -> None:
    """One ``ERROR:`` line (the library: one ``ValueError``) in one shape;
    nothing written, the wheel as it was."""
    build, says = _CAUSES[cause]
    wheel = build(tmp_path)
    before = wheel.read_bytes()

    if surface.startswith("lib-"):
        with pytest.raises(ValueError) as excinfo:
            _SURFACES[surface](wheel, monkeypatch)
        lines = [str(excinfo.value)]
    else:
        assert _cli(_cli_argv(surface, wheel), monkeypatch) == 1
        err = capsys.readouterr().err
        lines = [x for x in err.splitlines() if x.startswith("ERROR:")]
        assert "Traceback" not in err
    assert len(lines) == 1 and says in lines[0], lines
    assert "Invalid wheel archive" not in lines[0]  # the refusal, not wrapped
    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.spdx3.json"))
    assert not list(tmp_path.glob("*.tmp"))


def test_a_damaged_wheel_in_an_embed_batch_fails_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The existing per-wheel contract: the others are still processed and
    the exit code is non-zero."""
    bad = damaged_wheel(tmp_path, "deflate")
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    good = _hijack_wheel(good_dir)

    code = _cli(["embed-wheel", str(bad), str(good)], monkeypatch)

    assert code == 1
    assert _embedded(good)
    err = capsys.readouterr().err
    assert len([x for x in err.splitlines() if x.startswith("ERROR:")]) == 1


@pytest.mark.parametrize(
    ("command", "cause"),
    [
        ("verify-wheel", "damaged-metadata"),
        ("verify-wheel", "damaged-sbom"),
        ("validate-wheel", "damaged-sbom"),
    ],
)
def test_a_wheel_verify_or_validate_refuses_fails_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    cause: str,
) -> None:
    """One bad wheel of a batch: its own ``ERROR:``, and the next wheel is
    still checked (its own error, here: it has no SBOM) -- not an abort of
    the run."""
    bad = _CAUSES[cause][0](tmp_path)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = _hijack_wheel(other_dir)

    assert _cli([command, str(bad), str(other)], monkeypatch) == 1

    errors = [x for x in capsys.readouterr().err.splitlines() if x[:6] == "ERROR:"]
    assert len(errors) == 2, errors
    assert "wheel refused" in errors[0] and "no SBOM found" in errors[1]


def test_verify_wheel_says_when_the_file_name_names_another_dist_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wheel = raw_wheel(
        tmp_path / _WHEEL,
        [
            ("evil-9.9.dist-info/METADATA", _EVIL),
            ("evil-9.9.dist-info/sboms/evil-9.9.spdx3.json", "{}"),
        ],
    )

    _cli(["verify-wheel", str(wheel)], monkeypatch)

    messages = [r.getMessage() for r in caplog.records]
    named = [m for m in messages if "names no top-level" in m]
    assert len(named) == 1 and "evil-9.9.dist-info/" in named[0]


def _wheel_with_member(tmp_path: Path, name: str, data: bytes, damage: bool) -> Path:
    wheel = tmp_path / _WHEEL
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", _REAL)
        zf.writestr(name, data)
    if damage:
        corrupt_deflate(wheel, name)
    return wheel


@pytest.mark.parametrize(
    ("member", "data", "damage", "says"),
    [
        # RECORD, read to be rewritten: damaged, and not UTF-8 at all.
        ("demo-1.0.dist-info/RECORD", _BULK, True, "(zlib.error)"),
        ("demo-1.0.dist-info/RECORD", b"\xff\xfe,,\n", False, "(UnicodeDecodeError)"),
        # An SBOM already embedded, read to decide whether Pitloom made it.
        (
            "demo-1.0.dist-info/sboms/old.spdx3.json",
            _BULK,
            True,
            "(zlib.error)",
        ),
    ],
    ids=["record-damaged", "record-not-utf8", "existing-sbom-damaged"],
)
def test_the_embed_refuses_the_members_it_reads_to_rewrite(
    tmp_path: Path, member: str, data: bytes, damage: bool, says: str
) -> None:
    wheel = _wheel_with_member(tmp_path, member, data, damage)
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="could not read") as excinfo:
        embed_sbom_in_wheel(wheel, b'{"x": 1}', sbom_filename="new.spdx3.json")

    assert f"ENTRY={member!r}" in str(excinfo.value) and says in str(excinfo.value)
    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("kind", ["deflate", "encrypted", "name"])
def test_the_embed_rewrite_refuses_an_unreadable_member_too(
    tmp_path: Path, kind: str
) -> None:
    """``embed_sbom_in_wheel()`` takes the SBOM as given, so it reaches the
    archive rewrite without ``read_wheel()``: the same error, the wheel as it
    was and no temporary file left."""
    wheel = damaged_wheel(tmp_path, kind)
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="could not read"):
        embed_sbom_in_wheel(wheel, b'{"x": 1}')

    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("surface", ["lib-embed_wheel_sbom", "cli-embed-wheel"])
def test_the_embed_does_not_read_and_warn_about_metadata_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """``read_wheel`` has said why the identity is unknown; the identity goes
    down to the embed, which makes its default file name from it as it is."""
    monkeypatch.setattr(wheel_dist_info, "MAX_METADATA_HEADERS", 2)
    wheel = _hijack_wheel(tmp_path)

    _SURFACES[surface](wheel, monkeypatch)

    said = [x for x in capsys.readouterr().err.splitlines() if x.endswith("unknown")]
    assert len(said) == 1, said
    with zipfile.ZipFile(wheel) as archive:
        assert "demo-1.0.dist-info/sboms/demo-1.0.spdx3.json" in archive.namelist()


def _record_not_utf8_wheel(tmp_path: Path) -> Path:
    wheel = raw_wheel(tmp_path / _WHEEL, [("demo-1.0.dist-info/METADATA", _REAL)])
    with zipfile.ZipFile(wheel, "a") as zf:
        zf.writestr("demo-1.0.dist-info/RECORD", b"\xff\xfe,,\n")
    return wheel


def _dot_prefixed_wheel(tmp_path: Path) -> Path:
    return raw_wheel(tmp_path / _WHEEL, [("./demo-1.0.dist-info/METADATA", _REAL)])


@pytest.mark.parametrize("surface", ["cli-wheel-embed", "cli-embed-wheel"])
@pytest.mark.parametrize(
    "build", [_record_not_utf8_wheel, _dot_prefixed_wheel], ids=["record", "name"]
)
def test_a_wheel_only_the_embed_refuses_leaves_no_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    build: Callable[[Path], Path],
) -> None:
    """``read_wheel`` accepts these (it only hashes ``RECORD`` and reads the
    ``METADATA`` by its normalised name); the embed does not. ``-o`` is
    written after the embed, so a refusal leaves no copy."""
    wheel = build(tmp_path)
    before = wheel.read_bytes()

    assert _cli(_cli_argv(surface, wheel), monkeypatch) == 1

    err = capsys.readouterr().err
    assert len([x for x in err.splitlines() if x.startswith("ERROR:")]) == 1, err
    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.spdx3.json"))


def test_wheel_embed_writes_its_copy_only_once_the_wheel_is_embedded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _hijack_wheel(tmp_path)

    assert _cli(_cli_argv("cli-wheel-embed", wheel), monkeypatch) == 0

    assert (tmp_path / "out.spdx3.json").read_text(encoding="utf-8") == _embedded(wheel)


def test_a_build_and_read_extraction_keeps_its_own_fallback_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``--allow-build`` reads its just-built wheel itself, not through
    ``read_wheel()``: an unreadable member is the documented discovery
    failure (``None`` and one ``WARNING:``), never a crash. Only reading is
    made to fail, so the fake wheel is really written and the extraction is
    really reached."""
    state: FakeBuildState = install_fake_build(monkeypatch)
    state.entries = {"pkg/__init__.py": b"x = 1\n"}
    real_open = zipfile.ZipFile.open
    reads: list[object] = []

    def damaged(
        self: zipfile.ZipFile,
        name: Any,
        mode: str = "r",
        pwd: bytes | None = None,
        *,
        force_zip64: bool = False,
    ) -> Any:
        if mode != "r":
            return real_open(self, name, "w", pwd, force_zip64=force_zip64)
        reads.append(name)
        raise zlib.error("bad")

    with mock.patch.object(zipfile.ZipFile, "open", autospec=True, side_effect=damaged):
        assert build_and_read_wheel(tmp_path, timeout=60) is None

    assert len(reads) == 1  # the extraction opened the member and failed there
    (warning,) = [r for r in caplog.records if r.levelname == "WARNING"]
    assert "discovery failed" in warning.getMessage()
