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
``.dist-info``; each refuses a file that is not a ZIP, a wheel with an
unreadable member, one name twice, a NUL in a name or a name ``zipfile``
cannot open with one ``ERROR:`` line (the library: one ``ValueError``),
writes nothing and leaves the wheel as it was.

See also: tests/extract/test_wheel_identity.py (``read_wheel``),
tests/core/test_wheel_dist_info.py (the selector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.core import wheel_dist_info
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from tests._wheel_damage import (
    METADATA,
    central_name_damaged_wheel,
    corrupt_deflate,
    damaged_wheel,
    raw_wheel,
    zip_version_wheel,
)

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


def _cli_to_file(command: str) -> Callable[[Path, pytest.MonkeyPatch], str]:
    def run(wheel: Path, mp: pytest.MonkeyPatch) -> str:
        output = wheel.parent / "out.spdx3.json"
        assert _cli([command, str(wheel), "--offline", "-o", str(output)], mp) == 0
        return output.read_text(encoding="utf-8")

    return run


def _cli_wheel_embed(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    copy = wheel.parent / "out.spdx3.json"
    assert _cli(_cli_argv("cli-wheel-embed", wheel), mp) == 0
    embedded = _embedded(wheel)
    assert copy.read_text(encoding="utf-8") == embedded  # written once embedded
    return embedded


def _cli_embed_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    assert _cli(["embed-wheel", str(wheel)], mp) == 0
    return _embedded(wheel)


def _lib_generate(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(wheel, offline=True)


def _lib_embed(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return _embedded(embed_wheel_sbom(wheel)[0])


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-wheel": _cli_to_file("wheel"),
    "cli-generate": _cli_to_file("generate"),
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


_NUL_NAME = "nul/__init__.py\0.evil"


def _nul_wheel(tmp_path: Path) -> Path:
    """``zipfile`` cuts the second name at the NUL: an installer extracts it
    over the first."""
    return raw_wheel(
        tmp_path / _WHEEL,
        [
            ("demo-1.0.dist-info/METADATA", _REAL),
            ("nul/__init__.py", "good = 1\n"),
            (_NUL_NAME, "evil = 1\n"),
        ],
    )


def _not_a_zip_wheel(tmp_path: Path) -> Path:
    wheel = tmp_path / _WHEEL
    wheel.write_bytes(b"not a zip file at all")
    return wheel


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
    "nul-name": (
        _nul_wheel,
        f"ENTRY={_NUL_NAME!r}: NUL in member name -- wheel refused",
    ),
    "not-a-zip": (
        _not_a_zip_wheel,
        f"ARCHIVE={_WHEEL!r}: could not open (zipfile.BadZipFile) -- wheel refused",
    ),
    "zip-version": (
        zip_version_wheel,
        f"ARCHIVE={_WHEEL!r}: could not open (NotImplementedError) -- wheel refused",
    ),
}
# The embed and generate surfaces read every member; verify and validate read
# the dist-info's METADATA and the embedded SBOM, and the file list.
_GENERATING = sorted(_SURFACES)
_OPENING = (
    "duplicate-name",
    "bad-central-name",
    "nul-name",
    "not-a-zip",
    "zip-version",
)
_MATRIX = (
    [(s, c) for s in _GENERATING for c in ("unreadable-member", *_OPENING)]
    + [("cli-verify-wheel", c) for c in (*_OPENING, "damaged-metadata", "damaged-sbom")]
    + [("cli-validate-wheel", c) for c in (*_OPENING, "damaged-sbom")]
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


@pytest.mark.parametrize(
    ("command", "cause"),
    [
        ("embed-wheel", "unreadable-member"),
        ("embed-wheel", "nul-name"),
        ("embed-wheel", "not-a-zip"),
        ("embed-wheel", "zip-version"),
        ("verify-wheel", "damaged-metadata"),
        ("verify-wheel", "damaged-sbom"),
        ("verify-wheel", "zip-version"),
        ("validate-wheel", "damaged-sbom"),
        ("validate-wheel", "zip-version"),
    ],
)
def test_a_refused_wheel_of_a_batch_fails_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    cause: str,
) -> None:
    """The per-wheel contract: the bad wheel's own ``ERROR:`` in one shape,
    the next wheel still processed (embedded; or checked, with its own error:
    it has no SBOM), and a non-zero exit -- not an abort of the run."""
    bad = _CAUSES[cause][0](tmp_path)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = _hijack_wheel(other_dir)

    assert _cli([command, str(bad), str(other)], monkeypatch) == 1

    errors = [x for x in capsys.readouterr().err.splitlines() if x[:6] == "ERROR:"]
    assert _CAUSES[cause][1] in errors[0]
    if command == "embed-wheel":
        assert len(errors) == 1, errors
        assert _embedded(other)
    else:
        assert len(errors) == 2 and "no SBOM found" in errors[1], errors


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


def _rewritten_member(member: str, data: bytes, damage: bool) -> Callable[[Path], Path]:
    return lambda d: _wheel_with_member(d, member, data, damage)


_RECORD = "demo-1.0.dist-info/RECORD"
_OLD_SBOM = "demo-1.0.dist-info/sboms/old.spdx3.json"


@pytest.mark.parametrize(
    ("make", "filename", "says"),
    [
        # RECORD, read to be rewritten: damaged, and not UTF-8 at all.
        (
            _rewritten_member(_RECORD, _BULK, True),
            "new.spdx3.json",
            f"ENTRY={_RECORD!r}: could not read (zlib.error)",
        ),
        (
            _rewritten_member(_RECORD, b"\xff\xfe,,\n", False),
            "new.spdx3.json",
            f"ENTRY={_RECORD!r}: could not read (UnicodeDecodeError)",
        ),
        # An SBOM already embedded, read to decide whether Pitloom made it.
        (
            _rewritten_member(_OLD_SBOM, _BULK, True),
            "new.spdx3.json",
            f"ENTRY={_OLD_SBOM!r}: could not read (zlib.error)",
        ),
        # Any member of the rewrite, the default file name made from METADATA.
        (lambda d: damaged_wheel(d, "deflate"), None, "(zlib.error)"),
        (lambda d: damaged_wheel(d, "encrypted"), None, "could not read"),
        (lambda d: damaged_wheel(d, "name"), None, "could not read"),
    ],
    ids=[
        "record-damaged",
        "record-not-utf8",
        "existing-sbom-damaged",
        "member-deflate",
        "member-encrypted",
        "member-name",
    ],
)
def test_the_embed_refuses_the_members_it_reads_to_rewrite(
    tmp_path: Path, make: Callable[[Path], Path], filename: str | None, says: str
) -> None:
    """``embed_sbom_in_wheel()`` takes the SBOM as given, so it reaches the
    archive rewrite without ``read_wheel()``: the wheel-refusing error, the
    wheel as it was and no temporary file left."""
    wheel = make(tmp_path)
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="could not read") as excinfo:
        embed_sbom_in_wheel(wheel, b'{"x": 1}', sbom_filename=filename)

    assert says in str(excinfo.value)
    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def _cli_succeeds(*argv: str) -> Callable[[Path, pytest.MonkeyPatch], None]:
    def run(wheel: Path, mp: pytest.MonkeyPatch) -> None:
        assert _cli([argv[0], str(wheel), *argv[1:]], mp) == 0

    return run


_IDENTITY_READERS: dict[str, Callable[[Path, pytest.MonkeyPatch], object]] = {
    "lib-embed_wheel_sbom": lambda w, _mp: embed_wheel_sbom(w),
    "cli-embed-wheel": _cli_succeeds("embed-wheel"),
    "cli-embed-wheel-verify": _cli_succeeds("embed-wheel", "--verify"),
    "cli-wheel-embed": _cli_succeeds("wheel", "--embed", "--offline"),
    "cli-verify-wheel": lambda w, mp: _cli(
        ["verify-wheel", str(_with_sbom(w, _BULK))], mp
    ),
}


@pytest.mark.parametrize("surface", sorted(_IDENTITY_READERS))
def test_the_embed_does_not_read_and_warn_about_metadata_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """The generation has said why the identity is unknown; the identity goes
    down to the embed, which makes its default file name from it as it is,
    and ``--verify`` does not read ``METADATA`` for a second say.
    ``verify-wheel`` says it once too."""
    monkeypatch.setattr(wheel_dist_info, "MAX_METADATA_HEADERS", 2)
    wheel = _hijack_wheel(tmp_path)

    _IDENTITY_READERS[surface](wheel, monkeypatch)

    said = [x for x in capsys.readouterr().err.splitlines() if x.endswith("unknown")]
    assert len(said) == 1, said
    assert "over 2 headers" in said[0]  # the cap is what made it unknown
    with zipfile.ZipFile(wheel) as archive:
        sboms = [n for n in archive.namelist() if "/sboms/" in n]
    assert sboms == ["demo-1.0.dist-info/sboms/demo-1.0.spdx3.json"]


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
