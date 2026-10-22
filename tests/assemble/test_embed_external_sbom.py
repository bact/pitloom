# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An external SBOM given to ``embed-wheel --sbom`` is embedded as its bytes.

See also: test_embed_core.py (``--sbom`` through the library) and
test_embed_stale_sboms.py (what a re-embed removes).
"""

from __future__ import annotations

import codecs
import zipfile
from pathlib import Path

import pytest

from pitloom.embed import embed_wheel_sbom

from .conftest import _make_dummy_wheel, _spdx3_json_with_subject

_JSON = _spdx3_json_with_subject("extpkg", "1.0.0")
_CRLF = _JSON.replace(",", ",\r\n").encode("utf-8")


def _embed(tmp_path: Path, raw: bytes) -> tuple[bytes, bytes]:
    """Embed *raw* with ``-o``: the bytes in the wheel and in the copy."""
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    sbom = tmp_path / "given.spdx3.json"
    sbom.write_bytes(raw)
    copy = tmp_path / "copy.json"
    _, arcname, _, _, _ = embed_wheel_sbom(wheel, sbom_path=sbom, output_path=copy)
    with zipfile.ZipFile(wheel) as zf:
        return zf.read(arcname), copy.read_bytes()


def test_line_endings_are_kept(tmp_path: Path) -> None:
    assert b"\r\n" in _CRLF and _CRLF != _JSON.encode()
    embedded, copy = _embed(tmp_path, _CRLF)
    assert embedded == copy == _CRLF


def test_a_byte_order_mark_is_dropped_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        embedded, copy = _embed(tmp_path, codecs.BOM_UTF8 + _CRLF)
    assert embedded == copy == _CRLF
    assert len(caplog.messages) == 1
    assert "given.spdx3.json" in caplog.messages[0]
    assert "byte order mark" in caplog.messages[0]


def test_invalid_utf8_is_refused(tmp_path: Path) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    sbom = tmp_path / "given.spdx3.json"
    sbom.write_bytes(b'{"@graph": "\xff"}')
    with pytest.raises(ValueError, match="not valid UTF-8"):
        embed_wheel_sbom(wheel, sbom_path=sbom)
    with zipfile.ZipFile(wheel) as zf:
        assert not [n for n in zf.namelist() if "/sboms/" in n]
