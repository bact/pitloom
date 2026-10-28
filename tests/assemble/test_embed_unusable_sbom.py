# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``embed-wheel --sbom FILE`` refuses a file it cannot read as what it is
named, before a byte of the wheel is written: on the library and the CLI.

See also: test_embed_external_sbom.py (what a good file embeds as).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.embed import embed_wheel_sbom

from .conftest import _make_dummy_wheel, _spdx3_json_with_subject

_CYCLONEDX = json.dumps(
    {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []}
)
#: file name, content (``None``: a directory, ``False``: absent), message part
_BAD: dict[str, tuple[str, bytes | None | bool, str]] = {
    "malformed": ("a.spdx3.json", b'{"@graph": [', "is not valid JSON"),
    "empty": ("a.spdx3.json", b"", "is not valid JSON"),
    "array": ("a.spdx3.json", b"[1, 2]", "is not a JSON object"),
    "cyclonedx": ("a.spdx3.json", _CYCLONEDX.encode(), "not SPDX 3 JSON-LD"),
    "malformed-other-name": ("a.json", b"{oops", "is not valid JSON"),
    "non-utf8": ("a.spdx3.json", b'{"@graph": "\xff"}', "not valid UTF-8"),
}


def _bad_file(tmp_path: Path, kind: str) -> Path:
    name, content, _ = _BAD[kind]
    path = tmp_path / name
    assert isinstance(content, bytes)
    path.write_bytes(content)
    return path


def _leftovers(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".tmp")


@pytest.mark.parametrize("kind", list(_BAD))
def test_the_library_refuses_a_bad_file_and_leaves_the_wheel(
    tmp_path: Path, kind: str
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    before = wheel.read_bytes()
    sbom = _bad_file(tmp_path, kind)

    with pytest.raises(ValueError, match=_BAD[kind][2]):
        embed_wheel_sbom(wheel, sbom_path=sbom)

    assert wheel.read_bytes() == before
    assert _leftovers(tmp_path) == []


@pytest.mark.parametrize("kind", list(_BAD))
def test_the_cli_refuses_a_bad_file_with_one_error_line(
    tmp_path: Path,
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    before = wheel.read_bytes()
    sbom = _bad_file(tmp_path, kind)
    monkeypatch.setattr(
        sys, "argv", ["loom", "embed-wheel", str(wheel), "--sbom", str(sbom)]
    )

    assert __main__.main() == 1

    errors = [
        ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("ERROR:")
    ]
    assert len(errors) == 1 and _BAD[kind][2] in errors[0]
    assert wheel.read_bytes() == before


def test_a_valid_json_object_in_another_format_keeps_the_skip_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A CycloneDX file named for what it is is still embedded (not SPDX 3, no
    cross-check): only a file named ``.spdx3.json`` claims SPDX 3."""
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    sbom = tmp_path / "bom.cdx.json"
    sbom.write_text(_CYCLONEDX, encoding="utf-8")

    with caplog.at_level("WARNING"):
        embed_wheel_sbom(wheel, sbom_path=sbom)

    assert any("cannot cross-check" in m for m in caplog.messages)


def test_a_valid_spdx3_file_still_embeds(tmp_path: Path) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    sbom = tmp_path / "ok.spdx3.json"
    sbom.write_text(_spdx3_json_with_subject("extpkg", "1.0.0"), encoding="utf-8")

    _, arcname, _, _, _ = embed_wheel_sbom(wheel, sbom_path=sbom)

    assert arcname.endswith(".spdx3.json")


@pytest.mark.parametrize("kind", ["directory", "missing"])
def test_a_directory_or_missing_file_is_an_os_error(tmp_path: Path, kind: str) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    before = wheel.read_bytes()
    target = tmp_path / "x.spdx3.json"
    if kind == "directory":
        target.mkdir()

    with pytest.raises(OSError):
        embed_wheel_sbom(wheel, sbom_path=target)

    assert wheel.read_bytes() == before
