# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom id import`` and ``IdRegistry.import_sbom`` read an SBOM that starts
with a UTF-8 byte order mark without it and say so with one coded
``WARNING:`` (``json-malformed/bom``), as ``embed-wheel --sbom`` does.

See also: test_registry_import.py (the import itself).
"""

from __future__ import annotations

import codecs
import logging
from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry
from pitloom.logging_config import CODE_ATTR
from tests.id_registry.shared import _write_sample_sbom
from tests.id_registry.surfaces_base import _run_cli

pytestmark = pytest.mark.platform

_CODE = "json-malformed/bom"


def _bom_sbom(tmp_path: Path, *, bom: bool) -> Path:
    """The sample SBOM at ``sample.spdx3.json``, with a byte order mark or not."""
    path = tmp_path / "sample.spdx3.json"
    _write_sample_sbom(path)
    if bom:
        path.write_bytes(codecs.BOM_UTF8 + path.read_bytes())
    return path


def _said(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, CODE_ATTR, None) == _CODE]


@pytest.mark.parametrize("bom", [True, False], ids=["bom", "no-bom"])
def test_the_library_import_says_a_byte_order_mark_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bom: bool
) -> None:
    sbom = _bom_sbom(tmp_path, bom=bom)
    registry = IdRegistry.new("proj")
    with caplog.at_level(logging.WARNING):
        registry.import_sbom(sbom)
    assert registry.elements  # read the same either way
    said = _said(caplog.records)
    assert len(said) == (1 if bom else 0)
    if bom:
        assert said[0].levelno == logging.WARNING
        assert said[0].getMessage().startswith("FILE=")
        assert "sample.spdx3.json" in said[0].getMessage()


@pytest.mark.parametrize("bom", [True, False], ids=["bom", "no-bom"])
def test_the_cli_import_says_a_byte_order_mark_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bom: bool,
) -> None:
    sbom = _bom_sbom(tmp_path, bom=bom)
    registry = tmp_path / "reg.json"
    assert _run_cli(monkeypatch, ["id", "import", str(sbom), "-o", str(registry)]) == 0
    assert registry.is_file()
    said = [
        line
        for line in capsys.readouterr().err.splitlines()
        if line.endswith(f"[{_CODE}]")
    ]
    assert len(said) == (1 if bom else 0)
    if bom:
        assert said[0].startswith("WARNING: FILE=")
        assert "byte order mark" in said[0]
