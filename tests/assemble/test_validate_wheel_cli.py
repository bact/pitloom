# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for `loom validate-wheel` (schema/SHACL content validation --
no location/extension check, see `verify-wheel` for that).

See also: :mod:`tests.assemble.test_verify_wheel_cli` for the structural
counterpart these tests intentionally don't duplicate.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from tests.kv_helpers import kv_stdout, statuses

from .conftest import _SAMPLE_SPDX3_JSON, _embed_sbom_entry, _make_dummy_wheel

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
# _SAMPLE_SPDX3_JSON (below) is well-formed but not fully SHACL-valid
# (missing creationInfo on some elements) -- fine for embed-wheel tests
# that never inspect content, but the happy-path validate test needs a
# document that's actually valid end-to-end. Same fixture
# test_cli_fragment.py's own network-dependent success test uses.
VALID_FRAGMENT = FIXTURE_DIR / "fragments" / "dataset-fragment.spdx3.json"


@pytest.mark.usefixtures("offline_spdx3_validate")
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
    _embed_sbom_entry(
        wheel_path,
        "validpkg-1.0.0.spdx3.json",
        VALID_FRAGMENT.read_text(encoding="utf-8"),
    )

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    result = __main__.main()
    captured = capsys.readouterr()
    assert result == 0

    assert statuses(captured.out) == ["valid"]
    assert "INFO: validate-wheel: 1 wheel(s) valid" in captured.err.splitlines()


@pytest.mark.usefixtures("offline_spdx3_validate")
def test_validate_wheel_invalid_sbom_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A schema-invalid embedded document -> ERROR lines, exit 1.

    Corrupts a known-good document's node type so it still has a valid
    @context; the vendored model keeps the run offline."""
    doc = json.loads(_SAMPLE_SPDX3_JSON)
    doc["@graph"][0]["type"] = "NotARealType"
    wheel_path = _make_dummy_wheel(tmp_path, "badpkg", "1.0.0")
    _embed_sbom_entry(wheel_path, "badpkg-1.0.0.spdx3.json", json.dumps(doc))

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    lines = captured.err.splitlines()
    assert lines
    for line in lines:
        assert line.startswith("ERROR: loom validate-wheel: ")
    # The validator's own words after its prefix, none blank, then the one
    # coded line of the document.
    relayed = [ln for ln in lines if "validate-wheel: spdx3-validate: " in ln]
    assert relayed and lines[-1].endswith(" [sbom-invalid]")
    assert len(relayed) == len(lines) - 1
    # The messages name the wheel's member, not the temporary copy checked.
    assert f"FILE={wheel_path.name}/" in lines[-1]
    assert ".dist-info/sboms/badpkg-1.0.0.spdx3.json: not valid SPDX 3" in lines[-1]
    found = len([ln for ln in relayed if re.search(r": \[(schema|shacl)\] ", ln)])
    assert f"({found} finding(s) above)" in lines[-1]
    assert tempfile.gettempdir() not in captured.err


def test_validate_wheel_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reports a clear ERROR when 'spdx3-validate' isn't installed."""
    wheel_path = _make_dummy_wheel(tmp_path, "nodeppkg", "1.0.0")
    _embed_sbom_entry(wheel_path, "nodeppkg-1.0.0.spdx3.json", _SAMPLE_SPDX3_JSON)

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    with patch.dict("sys.modules", {"spdx3_validate": None}):
        result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert captured.err == (
        "ERROR: loom validate-wheel: required library not installed: "
        "spdx3_validate; "
        "install pitloom[validate] [library-missing]\n"
    )


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
    assert (
        "ERROR: loom validate-wheel: ARCHIVE='nosbompkg-1.0.0-py3-none-any.whl': "
        "no SBOM under .dist-info/sboms/ [wheel-sbom-missing]" in captured.err
    )
    assert statuses(captured.out) == ["failed"]


def test_validate_wheel_batch_reports_one_status_per_wheel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A skipped and a failing wheel: one STATUS line each, in order, and
    no success summary."""
    skipped = _make_dummy_wheel(tmp_path, "cdxpkg", "1.0.0")
    _embed_sbom_entry(skipped, "cdxpkg-1.0.0.cdx.json", '{"bomFormat": "CycloneDX"}')
    missing = _make_dummy_wheel(tmp_path, "nosbom", "1.0.0")

    argv = ["loom", "validate-wheel", str(skipped), str(missing)]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert kv_stdout(captured.out) == [
        {"WHEEL": skipped.name, "STATUS": "skipped"},
        {"WHEEL": missing.name, "STATUS": "failed"},
    ]
    assert "wheel(s) valid" not in captured.err


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
    assert captured.err.startswith("ERROR: ")
    assert "no top-level .dist-info directory" in captured.err
    assert "[dist-info-missing]" in captured.err


def test_validate_wheel_corrupt_zip_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file that isn't even a valid ZIP archive -> ERROR, exit 1.

    Exercises find_embedded_sbom's BadZipFile -> refusal normalisation
    directly (distinct from a well-formed ZIP that's merely missing
    .dist-info, covered by the malformed-wheel test). OSError is
    deliberately NOT normalised (see open_wheel_zip) -- not this test's
    concern."""
    wheel_path = tmp_path / "notazip-1.0.0-py3-none-any.whl"
    wheel_path.write_bytes(b"not a zip file at all")

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "; wheel refused [wheel-unreadable]" in captured.err


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
    assert "ERROR: loom validate-wheel: wheel file not found" in captured.err


def test_validate_wheel_unrecognized_format_warns_not_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-SPDX3-shaped embedded file has no registered validator ->
    WARNING, not ERROR -- unsupported is not the same as invalid."""
    wheel_path = _make_dummy_wheel(tmp_path, "otherpkg", "1.0.0")
    _embed_sbom_entry(
        wheel_path, "otherpkg-1.0.0.cdx.json", '{"bomFormat": "CycloneDX"}'
    )

    monkeypatch.setattr(sys, "argv", ["loom", "validate-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "WARNING: " in captured.err
    assert "no validator for the SBOM's format; not validated" in captured.err
    assert "[wheel-sbom-unusable]" in captured.err
    assert statuses(captured.out) == ["skipped"]
    assert (
        "INFO: validate-wheel: 0 wheel(s) valid, 1 skipped "
        "(no validator for their format)" in captured.err.splitlines()
    )
