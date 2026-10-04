# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel named ``x.WHL`` on every surface that takes a wheel path.

``pip`` and ``packaging`` accept only ``.whl``, so each surface refuses
``x.WHL`` with the same ``not a .whl file`` message, writes nothing and
leaves the file as it was: ``loom wheel``, ``loom generate``,
``loom wheel --embed``, ``loom embed-wheel``, ``loom verify-wheel``,
``loom validate-wheel``, and the library's ``generate_wheel_sbom()``,
``generate()``, ``read_wheel()``, ``embed_wheel_sbom()`` and
``find_embedded_sbom()``.

The name is judged as given, never as resolved: a symlink ``x.whl -> blob`` is
a wheel, ``alias.WHL -> real.whl`` is not.

See also: tests/core/test_wheel_dist_info.py (``WheelRefused``,
``open_wheel_zip``).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import glob
import os
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_wheel_sbom
from pitloom.cli.commands import utils, validate_wheel
from pitloom.core.wheel_dist_info import (
    WheelRefused,
    is_wheel_path,
    looks_like_wheel_path,
)
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom, find_embedded_sbom
from pitloom.extract.wheel import read_wheel
from tests._wheel_damage import damaged_wheel

_NAME = "demo-1.0-py3-none-any"


def _can_symlink() -> bool:
    """Whether this process may create a file symlink (Windows needs a
    privilege)."""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "target"
        target.write_bytes(b"")
        try:
            (Path(directory) / "link").symlink_to(target)
        except (OSError, NotImplementedError):
            return False
    return True


_SYMLINKS = _can_symlink()
_DOTDOT = _SYMLINKS and sys.platform != "win32"  # Win32 collapses ".." textually

_CLI: dict[str, list[str]] = {
    "wheel": ["wheel", "{w}"],
    "generate": ["generate", "{w}", "-o", "out.spdx3.json"],
    "wheel-embed": ["wheel", "{w}", "--embed"],
    "embed-wheel": ["embed-wheel", "{w}"],
    "verify-wheel": ["verify-wheel", "{w}"],
    "validate-wheel": ["validate-wheel", "{w}"],
    "embed-wheel-verify": ["embed-wheel", "{w}", "--verify"],
    "embed-wheel-validate": ["embed-wheel", "{w}", "--validate"],
}

_LIB: dict[str, Callable[[Path], object]] = {
    "generate_wheel_sbom": lambda w: generate_wheel_sbom(w, offline=True),
    "generate": lambda w: generate(w, offline=True),
    "read_wheel": read_wheel,
    "embed_wheel_sbom": embed_wheel_sbom,
    "find_embedded_sbom": find_embedded_sbom,
}


def _wheel(directory: Path, name: str, *, sbom: bool = False) -> Path:
    """A wheel at *directory*/*name*; with *sbom*, one that carries an SBOM
    (embedded through a ``.whl`` name, then moved)."""
    directory.mkdir(exist_ok=True)
    first = directory / f"{_NAME}.whl"
    with zipfile.ZipFile(first, "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", "Name: demo\nVersion: 1.0\n")
        zf.writestr("demo/__init__.py", "")
    if sbom:
        embed_wheel_sbom(first)
    path = directory / name
    if path.name != first.name:  # not ``!=``: Windows compares paths without case
        first.rename(path)
    assert path.name in os.listdir(directory)  # the case on disk is the one asked
    return path


def _cli(command: str, wheel: Path | str) -> list[str]:
    return ["loom", *(a.format(w=wheel) for a in _CLI[command])]


def _run(argv: list[str], mp: pytest.MonkeyPatch) -> int:
    mp.setattr(sys, "argv", argv)
    return __main__.main()


@pytest.fixture(autouse=True)
def _validator_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """``validate-wheel`` runs ``spdx3-validate``, which fetches a schema."""
    monkeypatch.setattr(
        validate_wheel, "_validate_spdx3_documents", lambda *_a, **_k: 0
    )


@pytest.mark.parametrize("command", sorted(_CLI))
def test_cli_refuses_an_uppercase_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    wheel = _wheel(tmp_path / "up", f"{_NAME}.WHL")
    before = wheel.read_bytes()

    assert _run(_cli(command, wheel), monkeypatch) == 1

    assert capsys.readouterr().err == f"ERROR: not a .whl file: {wheel}\n"
    assert wheel.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["up"]


@pytest.mark.parametrize("command", sorted(_CLI))
def test_cli_lowercase_control_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Guards the refusal test above against passing for the wrong reason."""
    monkeypatch.chdir(tmp_path)
    wheel = _wheel(tmp_path / "lo", f"{_NAME}.whl", sbom=True)

    assert _run(_cli(command, wheel), monkeypatch) == 0

    captured = capsys.readouterr()
    assert "ERROR:" not in captured.err
    if command in {"generate", "wheel"}:
        assert (tmp_path / "out.spdx3.json").is_file() or "PITLOOM_" in captured.out


@pytest.mark.parametrize("command", sorted(_CLI))
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_cli_judges_a_symlink_by_its_own_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """``x.whl -> blob`` is a wheel, though the resolved name is not."""
    monkeypatch.chdir(tmp_path)
    blob = _wheel(tmp_path / "store", "store-blob", sbom=True)
    link = tmp_path / f"{_NAME}.whl"
    link.symlink_to(blob)

    assert _run(_cli(command, link), monkeypatch) == 0

    assert "ERROR:" not in capsys.readouterr().err
    assert link.is_symlink()


@pytest.mark.parametrize("command", sorted(_CLI))
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_cli_refuses_a_symlink_named_uppercase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """``alias.WHL -> real.whl`` is not a wheel, though the target is."""
    monkeypatch.chdir(tmp_path)
    real = _wheel(tmp_path / "store", f"{_NAME}.whl", sbom=True)
    alias = tmp_path / "alias.WHL"
    alias.symlink_to(real)

    assert _run(_cli(command, alias), monkeypatch) == 1

    assert capsys.readouterr().err == f"ERROR: not a .whl file: {alias}\n"


@pytest.mark.parametrize("command", ["wheel", "generate", "embed-wheel"])
def test_cli_judges_the_name_before_whether_the_file_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _run(_cli(command, "nothere.WHL"), monkeypatch) == 1

    assert capsys.readouterr().err == "ERROR: not a .whl file: nothere.WHL\n"


@pytest.mark.parametrize("command", sorted(_CLI))
@pytest.mark.skipif(not _DOTDOT, reason="needs POSIX '..' through a symlink")
def test_cli_reads_dotdot_through_a_symlinked_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """``linkdir/../x.whl`` is the file the OS finds, not ``./x.whl``."""
    path, decoy = _dotdot(tmp_path, monkeypatch)

    assert _run(_cli(command, path), monkeypatch) == 0

    assert "ERROR:" not in capsys.readouterr().err
    assert decoy.read_bytes() == b"decoy"


@pytest.mark.parametrize("name", sorted(_LIB))
@pytest.mark.skipif(not _DOTDOT, reason="needs POSIX '..' through a symlink")
def test_library_reads_dotdot_through_a_symlinked_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    path, decoy = _dotdot(tmp_path, monkeypatch)

    _LIB[name](path)

    assert decoy.read_bytes() == b"decoy"


@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_embed_reports_the_wheel_by_the_name_it_was_given(tmp_path: Path) -> None:
    blob = _wheel(tmp_path / "store", "store-blob")
    link = tmp_path / f"{_NAME}.whl"
    link.symlink_to(blob)

    reported = embed_wheel_sbom(link)[0]

    assert reported == link.absolute()


def _dotdot(tmp_path: Path, mp: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The relative path ``linkdir/../x.whl`` to a wheel with an SBOM, and a
    different file of the same name in the current directory, which a text
    normalisation of the path would pick."""
    real = _wheel(tmp_path / "other", f"{_NAME}.whl", sbom=True)
    (tmp_path / "other" / "deep").mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "linkdir").symlink_to(Path("..") / "other" / "deep")
    decoy = cwd / real.name
    decoy.write_bytes(b"decoy")
    mp.chdir(cwd)
    return Path("linkdir") / ".." / real.name, decoy


@pytest.mark.parametrize("name", sorted(_LIB))
def test_library_refuses_an_uppercase_extension(tmp_path: Path, name: str) -> None:
    wheel = _wheel(tmp_path / "up", f"{_NAME}.WHL")
    before = wheel.read_bytes()

    with pytest.raises(WheelRefused, match="not a .whl file"):
        _LIB[name](wheel)

    assert wheel.read_bytes() == before
    assert [p.name for p in wheel.parent.iterdir()] == [wheel.name]


@pytest.mark.parametrize("name", sorted(_LIB))
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_library_judges_a_symlink_by_its_own_name(tmp_path: Path, name: str) -> None:
    blob = _wheel(tmp_path / "store", "store-blob", sbom=True)
    link = tmp_path / f"{_NAME}.whl"
    link.symlink_to(blob)
    alias = tmp_path / "alias.WHL"
    alias.symlink_to(link)

    _LIB[name](link)
    with pytest.raises(WheelRefused, match="not a .whl file"):
        _LIB[name](alias)


@pytest.mark.parametrize(
    ("name", "strict", "routed"),
    [
        ("a.whl", True, True),
        ("dir.WHL/a.whl", True, True),
        ("a.WHL", False, True),
        ("a.Whl", False, True),
        ("a.whl.zip", False, False),
        ("dir.whl/a.txt", False, False),
    ],
)
def test_wheel_name_helpers(name: str, strict: bool, routed: bool) -> None:
    assert is_wheel_path(name) is strict
    assert is_wheel_path(Path(name)) is strict
    assert looks_like_wheel_path(name) is routed


@pytest.mark.parametrize(
    ("hits", "err"),
    [
        (["{up}"], "ERROR: not a .whl file: {up}\n"),
        (["{lo}", "{up}"], "ERROR: not a .whl file: {up}\n"),  # nothing runs
        (["{txt}"], "ERROR: no wheel files matched: dist/*\n"),
    ],
)
def test_cli_glob_hit_that_only_differs_in_case_fails_the_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hits: list[str],
    err: str,
) -> None:
    """A case-insensitive file system (Windows) lets ``*.whl`` match
    ``x.WHL``; the glob is faked, so the case holds on every platform."""
    monkeypatch.chdir(tmp_path)
    paths = {
        "up": _wheel(tmp_path / "up", f"{_NAME}.WHL"),
        "lo": _wheel(tmp_path / "lo", f"{_NAME}.whl", sbom=True),
        "txt": tmp_path / "notes.txt",
    }
    paths["txt"].write_text("x")
    found = [str(paths[h.strip("{}")]) for h in hits]
    monkeypatch.setattr(
        utils, "glob", SimpleNamespace(has_magic=glob.has_magic, glob=lambda _: found)
    )

    assert _run(["loom", "verify-wheel", "dist/*"], monkeypatch) == 1

    expected = err.format(**{k: str(v) for k, v in paths.items()})
    assert capsys.readouterr().err == expected


def test_cli_refused_name_stops_the_whole_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ``x.WHL`` among the paths refuses before any wheel is touched."""
    good = _wheel(tmp_path / "lo", f"{_NAME}.whl")
    bad = _wheel(tmp_path / "up", f"{_NAME}.WHL")
    before = good.read_bytes()

    assert _run(["loom", "embed-wheel", str(good), str(bad)], monkeypatch) == 1
    assert good.read_bytes() == before


def _two_dist_info_link(tmp_path: Path, *, signed: bool = False) -> Path:
    """``demo-1.0-py3-none-any.whl -> store/blob``, holding a second
    ``.dist-info``: only the link's name says which one is the wheel's own."""
    store = tmp_path / "store"
    store.mkdir()
    with zipfile.ZipFile(store / "blob", "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", "Name: demo\nVersion: 1.0\n")
        zf.writestr("other-2.0.dist-info/METADATA", "Name: other\nVersion: 2.0\n")
        if signed:
            zf.writestr("demo-1.0.dist-info/RECORD.jws", "x")
    link = tmp_path / f"{_NAME}.whl"
    link.symlink_to(store / "blob")
    return link


def _sbom_dirs(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as zf:
        return {n.split("/")[0] for n in zf.namelist() if "/sboms/" in n}


_EMBEDS: dict[str, Callable[[Path, pytest.MonkeyPatch], object]] = {
    "embed-wheel": lambda w, mp: _run(["loom", "embed-wheel", str(w)], mp),
    "wheel-embed": lambda w, mp: _run(["loom", "wheel", str(w), "--embed"], mp),
    "embed_wheel_sbom": lambda w, _mp: embed_wheel_sbom(w),
    "embed_sbom_in_wheel": lambda w, _mp: embed_sbom_in_wheel(w, b"{}"),
}


@pytest.mark.parametrize("name", sorted(_EMBEDS))
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_embed_picks_the_dist_info_by_the_name_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    link = _two_dist_info_link(tmp_path)

    _EMBEDS[name](link, monkeypatch)

    assert _sbom_dirs(link) == {"demo-1.0.dist-info"}
    assert "blob" not in capsys.readouterr().err


@pytest.mark.parametrize("name", ["embed-wheel", "wheel-embed"])
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_cli_embed_refusal_names_the_link_not_its_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    link = _two_dist_info_link(tmp_path, signed=True)

    assert _EMBEDS[name](link, monkeypatch) == 1

    err = capsys.readouterr().err
    assert link.name in err
    assert "blob" not in err


@pytest.mark.parametrize("name", ["embed_wheel_sbom", "embed_sbom_in_wheel"])
@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_library_embed_refusal_names_the_link_not_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    link = _two_dist_info_link(tmp_path, signed=True)

    with pytest.raises(WheelRefused) as caught:
        _EMBEDS[name](link, monkeypatch)

    assert link.name in str(caught.value)
    assert "blob" not in str(caught.value)


def _case_insensitive(directory: Path) -> bool:
    probe = directory / "Probe"
    probe.write_bytes(b"")
    return (directory / "pROBE").exists()


def test_collect_keeps_one_spelling_of_a_hard_linked_wheel(tmp_path: Path) -> None:
    first = _wheel(tmp_path, f"{_NAME}.whl")
    second = tmp_path / "other-1.0-py3-none-any.whl"
    os.link(first, second)

    assert utils._collect_wheel_paths([str(first), str(second)]) == [first]


def test_collect_keeps_one_spelling_in_another_letter_case(tmp_path: Path) -> None:
    if not _case_insensitive(tmp_path):
        pytest.skip("a case-sensitive file system")
    first = _wheel(tmp_path / "ctrl", f"{_NAME}.whl")
    other = tmp_path / "CTRL" / first.name

    assert utils._collect_wheel_paths([str(first), str(other)]) == [first]


@pytest.mark.skipif(sys.platform == "win32", reason="a privilege there")
def test_a_posix_process_can_symlink() -> None:
    """Keeps the probe from turning every symlink case into a skip."""
    assert _SYMLINKS is True


def test_collect_falls_back_to_the_resolved_path_without_an_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAT/exFAT report no inode: two wheels stay two, one wheel stays one."""
    monkeypatch.setattr(utils, "file_id", lambda _path: None)
    one = _wheel(tmp_path / "one", f"{_NAME}.whl")
    two = _wheel(tmp_path / "two", f"{_NAME}.whl")

    assert utils._collect_wheel_paths([str(one), str(two)]) == [one, two]
    assert utils._collect_wheel_paths([str(one), str(one)]) == [one]


@pytest.mark.skipif(not _SYMLINKS, reason="needs a symlink")
def test_unreadable_member_is_reported_under_the_name_given(tmp_path: Path) -> None:
    damaged = damaged_wheel(tmp_path, "deflate")
    blob = tmp_path / "blob"
    damaged.rename(blob)
    link = tmp_path / damaged.name
    link.symlink_to(blob)

    with pytest.raises(WheelRefused) as caught:
        embed_sbom_in_wheel(link, b"{}")

    assert link.name in str(caught.value)
    assert "blob" not in str(caught.value)
