# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for `pitloom validate-wheel` (schema/SHACL content validation --
no location/extension check, see `verify-wheel` for that).

See also: :mod:`tests.assemble.test_verify_wheel_cli` for the structural
counterpart these tests intentionally don't duplicate.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__

from .conftest import _SAMPLE_SPDX3_JSON, _make_dummy_wheel

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
# _SAMPLE_SPDX3_JSON (below) is well-formed but not fully SHACL-valid
# (missing creationInfo on some elements) -- fine for embed-wheel tests
# that never inspect content, but the happy-path validate test needs a
# document that's actually valid end-to-end. Same fixture
# test_cli_fragment.py's own network-dependent success test uses.
VALID_FRAGMENT = FIXTURE_DIR / "fragments" / "dataset-fragment.spdx3.json"


def _embed_raw(wheel_path: Path, sbom_basename: str, content: str) -> None:
    """Add a `sboms/` entry with arbitrary *content*, any basename."""
    with zipfile.ZipFile(wheel_path) as zf:
        dist_info = next(
            n.split("/")[0] for n in zf.namelist() if n.endswith(".dist-info/METADATA")
        )
    with zipfile.ZipFile(wheel_path, "a") as zf:
        zf.writestr(f"{dist_info}/sboms/{sbom_basename}", content)


@pytest.mark.pypi_network
def test_validate_wheel_valid_sbom_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A valid embedded SPDX3 document exits 0 and reports success.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled (see test_cli_fragment.py's
    equivalent note).
    """
    wheel_path = _make_dummy_wheel(tmp_path, "validpkg", "1.0.0")
    _embed_raw(
        wheel_path,
        "validpkg-1.0.0.spdx3.json",
        VALID_FRAGMENT.read_text(encoding="utf-8"),
    )

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom validate-wheel: 1 wheel(s) valid" in captured.out


def test_validate_wheel_invalid_sbom_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A schema-invalid embedded document -> ERROR lines, exit 1.

    Corrupts a known-good document's node type so it still has a valid
    @context (no network-dependent schema fetch needed to reach the
    UnknownVersionError path -- this exercises the ValidationResult.errors
    path instead, offline, mirroring test_cli_fragment.py's local case)."""
    doc = json.loads(_SAMPLE_SPDX3_JSON)
    doc["@graph"][0]["type"] = "NotARealType"
    wheel_path = _make_dummy_wheel(tmp_path, "badpkg", "1.0.0")
    _embed_raw(wheel_path, "badpkg-1.0.0.spdx3.json", json.dumps(doc))

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    for line in captured.err.splitlines():
        assert line.startswith("ERROR: ")


def test_validate_wheel_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reports a clear ERROR when 'spdx3-validate' isn't installed."""
    wheel_path = _make_dummy_wheel(tmp_path, "nodeppkg", "1.0.0")
    _embed_raw(wheel_path, "nodeppkg-1.0.0.spdx3.json", _SAMPLE_SPDX3_JSON)

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    with patch.dict("sys.modules", {"spdx3_validate": None}):
        result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert "ERROR: the 'spdx3-validate' package is required" in captured.err
    assert 'pip install "pitloom[validate]"' in captured.err


def test_validate_wheel_missing_sbom_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No embedded SBOM at all -> ERROR, exit 1 (same as verify-wheel)."""
    wheel_path = _make_dummy_wheel(tmp_path, "nosbompkg", "1.0.0")

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: no SBOM found under .dist-info/sboms/" in captured.err


def test_validate_wheel_malformed_wheel_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wheel with no .dist-info directory at all -> ERROR, exit 1."""
    wheel_path = tmp_path / "malformed-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("not_a_dist_info/file.txt", "content")

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: Invalid wheel archive" in captured.err
    assert "no .dist-info directory found" in captured.err


def test_validate_wheel_corrupt_zip_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file that isn't even a valid ZIP archive -> ERROR, exit 1.

    Exercises find_embedded_sbom's BadZipFile -> ValueError normalization
    directly (distinct from a well-formed ZIP that's merely missing
    .dist-info, covered by the malformed-wheel test). OSError is
    deliberately NOT normalized (see _open_wheel_zip) -- not this test's
    concern."""
    wheel_path = tmp_path / "notazip-1.0.0-py3-none-any.whl"
    wheel_path.write_bytes(b"not a zip file at all")

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: Invalid wheel archive" in captured.err


def test_validate_wheel_no_wheel_files_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No wheel file matches the given path -> ERROR, exit 1, before any check."""
    monkeypatch.setattr(
        sys, "argv", ["loom", "validate-wheel", str(tmp_path / "nope.whl")]
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "ERROR: wheel file not found" in captured.err


def test_validate_wheel_unrecognized_format_warns_not_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-SPDX3-shaped embedded file has no registered validator ->
    WARNING, not ERROR -- unsupported is not the same as invalid."""
    wheel_path = _make_dummy_wheel(tmp_path, "otherpkg", "1.0.0")
    _embed_raw(wheel_path, "otherpkg-1.0.0.cdx.json", '{"bomFormat": "CycloneDX"}')

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "WARNING: " in captured.err
    assert "no validator registered" in captured.err
    assert (
        "pitloom validate-wheel: 0 wheel(s) valid, 1 skipped "
        "(no validator for their format)" in captured.out
    )
