# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``embed-wheel --sbom-basename`` that is a path is refused before the SBOM is
generated (a build runs inside that), as ``option-invalid``; a name the reader accepts
(``x.spdx3.json``, stripped) is embedded as before.

See also: test_embed_cli.py (the other ``embed-wheel`` CLI tests) and
test_embed_core.py (the library's own name guard).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from pitloom import __main__
from pitloom.embed import checked_embed_basename, embed_wheel_sbom
from pitloom.messages import code_of

from .conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

#: spelling -> a path or device, refused (none is a plain file name)
_REFUSED = {
    "parent": "../x",
    "nested": "a/b",
    "backslash": "a\\b",
    "drive": "C:x",
    "device": "con",
    "nul": "a\0b",
}

#: spelling -> the file name it is embedded under
_ACCEPTED = {
    "plain": ("x", "x.spdx3.json"),
    "extension-stripped": ("x.spdx3.json", "x.spdx3.json"),
    "extension-upper-case": ("X.SPDX3.JSON", "X.spdx3.json"),
    "surrounding-space": ("  x ", "x.spdx3.json"),
    "trailing-dot": ("x.", "x..spdx3.json"),
    "all-dots": ("..", "...spdx3.json"),
}


def _sboms(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return [n.rsplit("/", 1)[-1] for n in zf.namelist() if "/sboms/" in n]


@pytest.mark.parametrize("value", _REFUSED.values(), ids=_REFUSED)
def test_the_checker_refuses_a_path_as_an_invalid_option(value: str) -> None:
    with pytest.raises(ValueError, match="^--sbom-basename: must be a") as caught:
        checked_embed_basename(value)
    assert code_of(caught.value) == "option-invalid"


@pytest.mark.parametrize(("value", "name"), _ACCEPTED.values(), ids=_ACCEPTED)
def test_the_checker_accepts_what_the_embed_accepts(
    tmp_path: Path, value: str, name: str
) -> None:
    """Each spelling the checker lets through is one the embed writes: a
    check that refused one the embed takes would be a new refusal."""
    base = checked_embed_basename(value)
    assert base is not None and f"{base}.spdx3.json" == name
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0")
    embed_wheel_sbom(wheel, sbom_basename=value)
    assert _sboms(wheel) == [name]


@pytest.mark.parametrize("value", [None, ""], ids=["none", "empty"])
def test_no_name_is_none_given(value: str | None) -> None:
    assert checked_embed_basename(value) == value


@pytest.mark.parametrize("value", _REFUSED.values(), ids=_REFUSED)
def test_the_library_refuses_before_it_generates_anything(
    tmp_path: Path, value: str
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0")
    before = wheel.read_bytes()
    with mock.patch("pitloom.embed._generate_embed_sbom_json") as generate:
        with pytest.raises(ValueError, match="--sbom-basename: must be a"):
            embed_wheel_sbom(wheel, sbom_basename=value)
    generate.assert_not_called()
    assert wheel.read_bytes() == before


@pytest.mark.parametrize("wheels", [1, 2], ids=["one-wheel", "two-wheels"])
def test_the_cli_refuses_once_before_any_wheel_is_touched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    wheels: int,
) -> None:
    paths = [
        _make_dummy_wheel(tmp_path / "dist", f"pkg{n}", "1.0.0") for n in range(wheels)
    ]
    before = [p.read_bytes() for p in paths]
    argv = ["loom", "embed-wheel", *map(str, paths), "--sbom-basename", "../x"]
    monkeypatch.setattr(sys, "argv", argv)
    with mock.patch(
        "pitloom.cli.commands._embed_wheel_batch.embed_wheel_sbom"
    ) as embed:
        assert __main__.main() == 1
    embed.assert_not_called()  # the refusal is the command's, not each wheel's

    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ERROR: loom embed-wheel: --sbom-basename: must be")
    assert lines[0].endswith("[option-invalid]")
    assert [p.read_bytes() for p in paths] == before


def test_the_cli_embeds_an_extension_stripped_name_with_one_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``x.spdx3.json`` is no refusal: embedded as ``x.spdx3.json``, the strip
    said once (not once for the command and once per wheel)."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo_pkg", "1.0.0")
    argv = ["loom", "embed-wheel", str(wheel), "--sbom-basename", "x.spdx3.json"]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 0
    assert _sboms(wheel) == ["x.spdx3.json"]
    stripped = [
        line
        for line in capsys.readouterr().err.splitlines()
        if "bare file name" in line
    ]
    assert len(stripped) == 1 and stripped[0].startswith("WARNING: --sbom-basename")
