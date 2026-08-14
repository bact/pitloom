# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed: PEP 770 post-build SBOM wheel injection."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from installer.sources import WheelFile

from pitloom import __main__
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import (
    _apply_config_overrides,
    _build_sbom_standalone_wheel,
    _derive_wheel_sbom_filename,
    _find_dist_info_prefix,
    _resolve_project_root,
    _resolve_zip_timestamp,
    _rewrite_wheel_archive,
    _update_record_lines,
    _validate_sbom_filename,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
)
from pitloom.ids import IdRegistry

_SAMPLE_SPDX3_JSON = json.dumps(
    {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "SpdxDocument",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123",
                "name": "sample",
                "specVersion": "3.0.1",
                "profileConformance": ["core", "software"],
                "creationInfo": "_:creationInfo1",
                "rootElement": ["https://spdx.org/spdxdocs/sample-doc-123/package"],
            },
            {
                "type": "CreationInfo",
                "@id": "_:creationInfo1",
                "specVersion": "3.0.1",
                "createdBy": ["https://spdx.org/spdxdocs/sample-doc-123/agent"],
                "created": "2026-08-14T00:00:00Z",
            },
            {
                "type": "software_Package",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/package",
                "name": "demo_pkg",
                "software_packageVersion": "1.0.0",
                "software_packageUrl": "pkg:pypi/demo-pkg@1.0.0",
            },
            {
                "type": "SoftwareAgent",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/agent",
                "name": "Pitloom",
            },
        ],
    }
)


def _make_dummy_wheel(
    directory: Path,
    name: str = "demo_pkg",
    version: str = "1.0.0",
) -> Path:
    """Create a minimal valid wheel with a valid RECORD file."""
    directory.mkdir(parents=True, exist_ok=True)
    wheel_filename = f"{name}-{version}-py3-none-any.whl"
    wheel_path = directory / wheel_filename
    dist_info = f"{name}-{version}.dist-info"

    init_code = b"__version__ = '1.0.0'\n"
    metadata_content = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    ).encode()
    wheel_content = (
        b"Wheel-Version: 1.0\n"
        b"Generator: test\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )

    def _rec_entry(arcname: str, payload: bytes) -> str:
        d = hashlib.sha256(payload).digest()
        h = base64.urlsafe_b64encode(d).decode("ascii").rstrip("=")
        return f"{arcname},sha256={h},{len(payload)}"

    records = [
        _rec_entry(f"{name}/__init__.py", init_code),
        _rec_entry(f"{dist_info}/METADATA", metadata_content),
        _rec_entry(f"{dist_info}/WHEEL", wheel_content),
        f"{dist_info}/RECORD,,",
    ]
    record_content = "\n".join(records).encode("utf-8") + b"\n"

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{name}/__init__.py", init_code)
        zf.writestr(f"{dist_info}/METADATA", metadata_content)
        zf.writestr(f"{dist_info}/WHEEL", wheel_content)
        zf.writestr(f"{dist_info}/RECORD", record_content)

    return wheel_path


def test_embed_sbom_in_wheel_minimal(tmp_path: Path) -> None:
    """Test embedding an SBOM into a minimal wheel."""
    wheel_path = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0")

    res_path, arcname, _ = embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
    assert res_path == wheel_path
    assert arcname == "demo_pkg-1.0.0.dist-info/sboms/demo_pkg-1.0.0.spdx3.json"

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert arcname in zf.namelist()
        raw = zf.read(arcname).decode("utf-8")
        assert raw == _SAMPLE_SPDX3_JSON

    # 1. Authoritative PyPA installer RECORD validation
    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()

    # 2. check-wheel-contents validation
    result = subprocess.run(
        [sys.executable, "-m", "check_wheel_contents", str(wheel_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"check-wheel-contents failed: {result.stderr}"

    # 3. pip install --dry-run validation
    with tempfile.TemporaryDirectory() as td:
        pip_res = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--target",
                td,
                "--no-deps",
                str(wheel_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert pip_res.returncode == 0, f"pip install failed: {pip_res.stderr}"


def test_embed_sbom_in_wheel_custom_filename(tmp_path: Path) -> None:
    """Test embedding with custom sbom_filename."""
    wheel_path = _make_dummy_wheel(tmp_path, "my_app", "2.1.0")

    _, arcname, _ = embed_sbom_in_wheel(
        wheel_path,
        _SAMPLE_SPDX3_JSON,
        sbom_filename="custom_sbom.spdx3.json",
    )
    assert arcname == "my_app-2.1.0.dist-info/sboms/custom_sbom.spdx3.json"

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_embed_sbom_in_wheel_idempotency(tmp_path: Path) -> None:
    """Test re-embedding updates RECORD cleanly without duplicate entries."""
    wheel_path = _make_dummy_wheel(tmp_path, "demo_pkg", "1.0.0")

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
    updated_sbom = _SAMPLE_SPDX3_JSON.replace("demo_pkg", "demo_pkg_v2")
    embed_sbom_in_wheel(wheel_path, updated_sbom)

    with zipfile.ZipFile(wheel_path, "r") as zf:
        sbom_entries = [n for n in zf.namelist() if "/sboms/" in n]
        assert len(sbom_entries) == 1
        assert zf.read(sbom_entries[0]).decode("utf-8") == updated_sbom

        record_text = zf.read("demo_pkg-1.0.0.dist-info/RECORD").decode("utf-8")
        sbom_record_lines = [
            line for line in record_text.splitlines() if "/sboms/" in line
        ]
        assert len(sbom_record_lines) == 1

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_embed_sbom_source_date_epoch_reproducibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test SOURCE_DATE_EPOCH reproducibility produces byte-identical wheels."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

    wheel_1 = _make_dummy_wheel(tmp_path / "w1", "repro", "1.0.0")
    wheel_2 = _make_dummy_wheel(tmp_path / "w2", "repro", "1.0.0")

    embed_sbom_in_wheel(wheel_1, _SAMPLE_SPDX3_JSON)
    embed_sbom_in_wheel(wheel_2, _SAMPLE_SPDX3_JSON)

    assert wheel_1.read_bytes() == wheel_2.read_bytes()


def test_embed_sbom_missing_dist_info_raises(tmp_path: Path) -> None:
    """Test ValueError raised if no .dist-info directory is found."""
    bad_wheel = tmp_path / "bad-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(bad_wheel, "w") as zf:
        zf.writestr("pkg/__init__.py", b"")

    with pytest.raises(ValueError, match="no .dist-info directory found"):
        embed_sbom_in_wheel(bad_wheel, _SAMPLE_SPDX3_JSON)


def test_embed_wheel_sbom_with_pregenerated_sbom(tmp_path: Path) -> None:
    """Test embed_wheel_sbom with a pre-generated SBOM path."""
    wheel_path = _make_dummy_wheel(tmp_path, "pregen_pkg", "0.5.0")
    sbom_file = tmp_path / "custom.spdx3.json"
    sbom_file.write_text(_SAMPLE_SPDX3_JSON, encoding="utf-8")
    out_file = tmp_path / "extracted_sbom.json"

    res_path, arcname, sbom_json, _ = embed_wheel_sbom(
        wheel_path,
        sbom_path=sbom_file,
        output_path=out_file,
    )
    assert res_path == wheel_path
    assert arcname.endswith(".dist-info/sboms/pregen_pkg-0.5.0.spdx3.json")
    assert sbom_json == _SAMPLE_SPDX3_JSON
    assert out_file.read_text(encoding="utf-8") == _SAMPLE_SPDX3_JSON

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_embed_wheel_sbom_with_project_fixture(tmp_path: Path) -> None:
    """Test embed_wheel_sbom using a project fixture directory."""
    fixture_dir = (
        Path(__file__).parent / "fixtures" / "projects" / "sampleproject-hatchling"
    )
    if not fixture_dir.exists():
        pytest.skip("sampleproject-hatchling fixture not found")

    wheel_path = _make_dummy_wheel(tmp_path, "sampleproject_hatchling", "0.1.0")

    res_path, arcname, sbom_json, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=fixture_dir,
    )
    assert res_path == wheel_path
    assert arcname.endswith(".dist-info/sboms/sbom.spdx3.json")

    sbom_data = json.loads(sbom_json)
    assert "@context" in sbom_data
    assert "@graph" in sbom_data

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()

    # 4. spdx3-validate validation
    sbom_file = tmp_path / "fixture_sbom.spdx3.json"
    sbom_file.write_text(sbom_json, encoding="utf-8")
    val_res = subprocess.run(
        [sys.executable, "-m", "spdx3_validate", "--json", str(sbom_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert val_res.returncode == 0, (
        f"spdx3-validate failed: {val_res.stderr} {val_res.stdout}"
    )


def test_cli_embed_wheel_single(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel_path = _make_dummy_wheel(tmp_path, "clipkg", "1.0.0")
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(wheel_path)])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out
    assert "clipkg-1.0.0-py3-none-any.whl" in captured.out

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_cli_embed_wheel_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dist_dir = tmp_path / "dist"
    w1 = _make_dummy_wheel(dist_dir, "multi_a", "1.0.0")
    w2 = _make_dummy_wheel(dist_dir, "multi_b", "1.0.0")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", "dist/*.whl"])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "multi_a-1.0.0-py3-none-any.whl" in captured.out
    assert "multi_b-1.0.0-py3-none-any.whl" in captured.out

    with WheelFile.open(w1) as wf:
        wf.validate_record()
    with WheelFile.open(w2) as wf:
        wf.validate_record()


def test_cli_wheel_embed_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom wheel <wheel> --embed` CLI command."""
    wheel_path = _make_dummy_wheel(tmp_path, "flagpkg", "1.0.0")
    monkeypatch.setattr(sys, "argv", ["loom", "wheel", str(wheel_path), "--embed"])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "pitloom: embedded" in captured.out

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_validate_sbom_filename_edge_cases() -> None:
    """Test _validate_sbom_filename rejects null bytes, traversal, and whitespace."""
    for bad in ("", "   ", "\x00", "a/b", "a\\b", "..", "."):
        with pytest.raises(ValueError, match="Invalid SBOM filename"):
            _validate_sbom_filename(bad)


def test_embed_wheel_sbom_basename_with_extension_normalized(tmp_path: Path) -> None:
    """Test custom basename already ending with .spdx3.json avoids double extension."""
    wheel_path = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    _, arcname, _, _ = embed_wheel_sbom(
        wheel_path,
        sbom_basename="custom.spdx3.json",
    )
    assert arcname.endswith(".dist-info/sboms/custom.spdx3.json")
    assert not arcname.endswith(".spdx3.json.spdx3.json")

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_cli_embed_wheel_absolute_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom embed-wheel <abs_path>/*.whl` with absolute glob patterns."""
    dist_dir = tmp_path / "abs_dist"
    w1 = _make_dummy_wheel(dist_dir, "abs_pkg", "1.0.0")

    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(dist_dir / "*.whl")])
    assert __main__.main() == 0

    captured = capsys.readouterr()
    assert "abs_pkg-1.0.0-py3-none-any.whl" in captured.out

    with WheelFile.open(w1) as wf:
        wf.validate_record()


def test_cli_embed_wheel_multiple_with_output_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom embed-wheel` fails when multiple wheels match with -o."""
    dist_dir = tmp_path / "dist"
    _make_dummy_wheel(dist_dir, "m1", "1.0.0")
    _make_dummy_wheel(dist_dir, "m2", "1.0.0")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", "dist/*.whl", "-o", "out.spdx3.json"],
    )
    assert __main__.main() == 1

    captured = capsys.readouterr()
    assert "--output cannot be used when embedding multiple wheels" in captured.err


def test_embed_sbom_empty_content_raises(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel raises ValueError on empty or whitespace SBOM."""
    wheel_path = _make_dummy_wheel(tmp_path, "empty_sbom", "1.0.0")
    with pytest.raises(ValueError, match="SBOM content cannot be empty"):
        embed_sbom_in_wheel(wheel_path, "")

    with pytest.raises(ValueError, match="SBOM content cannot be empty"):
        embed_sbom_in_wheel(wheel_path, "   \n\t  ")


def test_embed_sbom_preserves_file_permissions(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel preserves original filesystem permissions."""
    wheel_path = _make_dummy_wheel(tmp_path, "perm_pkg", "1.0.0")
    target_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH  # 0o644
    os.chmod(wheel_path, target_mode)

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
    current_mode = stat.S_IMODE(wheel_path.stat().st_mode)
    assert current_mode == target_mode


def test_cli_and_api_produce_identical_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify CLI and Python API produce bit-for-bit identical wheels and SBOMs."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    monkeypatch.chdir(tmp_path)

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "identpkg"
version = "1.0.0"

[tool.pitloom]
creation-comment = "shared-comment"
creation-datetime = "2026-08-14T12:00:00Z"

[[tool.pitloom.creator]]
name = "Test Author"
type = "person"
""",
        encoding="utf-8",
    )

    dir_cli = tmp_path / "cli"
    dir_api = tmp_path / "api"
    w_cli = _make_dummy_wheel(dir_cli, "identpkg", "1.0.0")
    w_api = _make_dummy_wheel(dir_api, "identpkg", "1.0.0")

    # Run via CLI
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(w_cli)])
    assert __main__.main() == 0

    # Run via Python API
    _, arcname_api, sbom_json_api, _ = embed_wheel_sbom(w_api)

    # Compare embedded SBOM contents
    with zipfile.ZipFile(w_cli, "r") as z_cli, zipfile.ZipFile(w_api, "r") as z_api:
        assert z_cli.namelist() == z_api.namelist()
        cli_sbom_bytes = z_cli.read(arcname_api)
        api_sbom_bytes = z_api.read(arcname_api)
        assert cli_sbom_bytes == api_sbom_bytes
        assert cli_sbom_bytes.decode("utf-8") == sbom_json_api

        # Compare RECORD contents
        cli_record = z_cli.read("identpkg-1.0.0.dist-info/RECORD")
        api_record = z_api.read("identpkg-1.0.0.dist-info/RECORD")
        assert cli_record == api_record

    # Compare entire wheel binary bytes
    assert w_cli.read_bytes() == w_api.read_bytes()


def test_find_dist_info_prefix_edge_cases(tmp_path: Path) -> None:
    """Test _find_dist_info_prefix with single, matching, and ambiguous dist-infos."""
    # 1. No dist-info
    p1 = tmp_path / "nodist-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p1, "w") as zf:
        zf.writestr("nodist/module.py", "# code")
    with zipfile.ZipFile(p1, "r") as zf:
        with pytest.raises(ValueError, match="no .dist-info directory found"):
            _find_dist_info_prefix(zf, p1)

    # 2. Multiple dist-info where one matches stem prefix
    p2 = tmp_path / "mypkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p2, "w") as zf:
        zf.writestr("mypkg-1.0.0.dist-info/METADATA", "Name: mypkg\nVersion: 1.0.0\n")
        zf.writestr("other-1.0.0.dist-info/METADATA", "Name: other\nVersion: 1.0.0\n")
    with zipfile.ZipFile(p2, "r") as zf:
        assert _find_dist_info_prefix(zf, p2) == "mypkg-1.0.0.dist-info/"

    # 3. Multiple dist-info where none or multiple match stem prefix
    p3 = tmp_path / "unmatched-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p3, "w") as zf:
        zf.writestr("pkg1-1.0.0.dist-info/METADATA", "Name: pkg1\n")
        zf.writestr("pkg2-1.0.0.dist-info/METADATA", "Name: pkg2\n")
    with zipfile.ZipFile(p3, "r") as zf:
        with pytest.raises(ValueError, match="multiple .dist-info directories found"):
            _find_dist_info_prefix(zf, p3)


def test_resolve_zip_timestamp_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _resolve_zip_timestamp under various invalid/fallback conditions."""
    # Invalid string in SOURCE_DATE_EPOCH
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-number")
    ts = _resolve_zip_timestamp(fallback=(1990, 5, 1, 12, 0, 0))
    assert ts == (1990, 5, 1, 12, 0, 0)

    # Overflow in SOURCE_DATE_EPOCH
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999999999999999999999999")
    ts_overflow = _resolve_zip_timestamp(fallback=(1995, 1, 1, 0, 0, 0))
    assert ts_overflow == (1995, 1, 1, 0, 0, 0)

    # Fallback with year < 1980 clamped to 1980
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    ts_clamped = _resolve_zip_timestamp(fallback=(1970, 1, 1, 0, 0, 0))
    assert ts_clamped == (1980, 1, 1, 0, 0, 0)

    # Fallback None uses current time
    ts_now = _resolve_zip_timestamp(fallback=None)
    assert ts_now[0] >= 2026


def test_update_record_lines_empty_rows() -> None:
    """Test _update_record_lines skips empty rows in RECORD string."""
    raw_record = "pkg/__init__.py,sha256=abc,10\n\n\npkg-1.0.dist-info/RECORD,,\n"
    updated = _update_record_lines(
        raw_record,
        "pkg-1.0.dist-info/sboms/pkg.spdx3.json",
        "hash123",
        100,
        "pkg-1.0.dist-info/",
    )
    assert "pkg-1.0.dist-info/sboms/pkg.spdx3.json,sha256=hash123,100" in updated
    assert "pkg-1.0.dist-info/RECORD,," in updated


def test_embed_sbom_file_not_found(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel raises FileNotFoundError for missing wheel."""
    missing_wheel = tmp_path / "does_not_exist.whl"
    with pytest.raises(FileNotFoundError, match="Wheel file not found"):
        embed_sbom_in_wheel(missing_wheel, "{}")


def test_embed_sbom_without_existing_record(tmp_path: Path) -> None:
    """Test embed_sbom_in_wheel handles a wheel archive with no RECORD entry."""
    wheel_path = tmp_path / "norec-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "norec-1.0.0.dist-info/METADATA",
            "Name: norec\nVersion: 1.0.0\n",
        )
        zf.writestr("norec/__init__.py", "# empty\n")

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert "norec-1.0.0.dist-info/sboms/norec-1.0.0.spdx3.json" in zf.namelist()
        assert "norec-1.0.0.dist-info/RECORD" in zf.namelist()
        rec_text = zf.read("norec-1.0.0.dist-info/RECORD").decode("utf-8")
        assert "norec-1.0.0.dist-info/sboms/norec-1.0.0.spdx3.json" in rec_text
        assert "norec-1.0.0.dist-info/RECORD,," in rec_text


def test_derive_wheel_sbom_filename_fallbacks(tmp_path: Path) -> None:
    """Test _derive_wheel_sbom_filename metadata missing/empty header fallbacks."""
    # 1. No METADATA in archive -> fall back to dist-info name prefix
    p1 = tmp_path / "nometa-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p1, "w") as zf:
        zf.writestr("nometa-1.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\n")
    with zipfile.ZipFile(p1, "r") as zf:
        fn1 = _derive_wheel_sbom_filename(zf, "nometa-1.0.0.dist-info/")
        assert fn1 == "nometa-1.0.0.spdx3.json"

    # 2. METADATA with no Name or Version headers -> fall back to dist-info prefix
    p2 = tmp_path / "emptyheaders-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p2, "w") as zf:
        zf.writestr(
            "emptyheaders-1.0.0.dist-info/METADATA",
            "Summary: A summary\nAuthor: Author\n",
        )
    with zipfile.ZipFile(p2, "r") as zf:
        fn2 = _derive_wheel_sbom_filename(zf, "emptyheaders-1.0.0.dist-info/")
        assert fn2 == "emptyheaders-1.0.0.spdx3.json"

    # 3. METADATA with blank line after Name (stops header scan)
    p3 = tmp_path / "blankheader-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(p3, "w") as zf:
        zf.writestr(
            "blankheader-1.0.0.dist-info/METADATA",
            "Name: myname\n\nVersion: 2.0.0 in description body\n",
        )
    with zipfile.ZipFile(p3, "r") as zf:
        fn3 = _derive_wheel_sbom_filename(zf, "blankheader-1.0.0.dist-info/")
        assert fn3 == "blankheader-1.0.0.spdx3.json"

    # 4. Empty prefix fallback
    with zipfile.ZipFile(p1, "r") as zf:
        fn4 = _derive_wheel_sbom_filename(zf, ".dist-info/")
        assert fn4 == "sbom.spdx3.json"


def test_rewrite_wheel_archive_chmod_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test _rewrite_wheel_archive gracefully ignores OSError on os.chmod."""
    wheel_path = _make_dummy_wheel(tmp_path, "chmodpkg", "1.0.0")

    def _failing_chmod(path: Any, mode: int) -> None:
        raise OSError("Permission denied simulation")

    monkeypatch.setattr("pitloom.embed.os.chmod", _failing_chmod)
    # Should complete without error
    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)


def test_rewrite_wheel_archive_temp_file_cleanup_on_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test temporary file is cleaned up if archive write fails midway."""
    wheel_path = _make_dummy_wheel(tmp_path, "cleanuppkg", "1.0.0")

    def _failing_writestr(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Disk write simulation failed")

    monkeypatch.setattr("zipfile.ZipFile.writestr", _failing_writestr)
    with pytest.raises(RuntimeError, match="Disk write simulation failed"):
        embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)

    # Verify no .tmp files remain in parent dir
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert not tmp_files


def test_resolve_project_root_non_existent(tmp_path: Path) -> None:
    """Test _resolve_project_root when non-existent path or empty directory."""
    # Non-existent explicit project_dir falls back to checking cwd
    res = _resolve_project_root(tmp_path / "does_not_exist")
    assert res is None or res.exists()


def test_apply_config_overrides_full() -> None:
    """Test _apply_config_overrides applies all CLI override parameters."""
    cfg = PitloomConfig()
    prov = ProvenanceConfig(
        format="fields",
        schema="https://example.com/schema",
        detail="full",
        preserve_source_metadata="always",
    )
    overridden = _apply_config_overrides(
        cfg,
        provenance=prov,
        enrich=True,
        extract_file_header=False,
        content_type=True,
        content_type_method="extension",
        offline=True,
    )
    assert overridden.provenance_format == "fields"
    assert overridden.provenance_schema == "https://example.com/schema"
    assert overridden.provenance_detail == "full"
    assert overridden.provenance_preserve_source_metadata == "always"
    assert overridden.enrich_local is True
    assert overridden.extract_file_header is False
    assert overridden.content_type.enabled is True
    assert overridden.content_type.method == "extension"
    assert overridden.offline is True

    with pytest.raises(ValueError, match="content_type_method must be one of"):
        _apply_config_overrides(
            cfg,
            provenance=None,
            enrich=None,
            extract_file_header=None,
            content_type=None,
            content_type_method="invalid_method",
            offline=None,
        )


def test_build_sbom_standalone_wheel_registry_options(tmp_path: Path) -> None:
    """Test _build_sbom_standalone_wheel with various registry options."""
    meta = ProjectMetadata(name="standalonereg", version="1.0.0", files=[])

    # 1. IdRegistry instance with namespace
    reg = IdRegistry(namespace="https://example.com/spdx")
    sbom_1 = _build_sbom_standalone_wheel(meta, None, reg, None, False)
    assert "standalonereg" in sbom_1

    # 2. Path string to registry file
    reg_file = tmp_path / "custom_ids.json"
    reg.save(reg_file)
    sbom_2 = _build_sbom_standalone_wheel(meta, None, str(reg_file), None, True)
    assert "standalonereg" in sbom_2


def test_embed_sbom_drops_stale_sboms_from_archive(tmp_path: Path) -> None:
    """Test re-embedding drops prior SBOM from archive & RECORD."""
    wheel_path = _make_dummy_wheel(tmp_path, "stalepkg", "1.0.0")

    # 1. Embed initial SBOM under custom name 'first.spdx3.json'
    embed_sbom_in_wheel(
        wheel_path,
        _SAMPLE_SPDX3_JSON,
        sbom_filename="first.spdx3.json",
    )
    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" in zf.namelist()

    # 2. Embed second SBOM under custom name 'second.spdx3.json'
    embed_sbom_in_wheel(
        wheel_path,
        _SAMPLE_SPDX3_JSON,
        sbom_filename="second.spdx3.json",
    )
    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()
        assert "stalepkg-1.0.0.dist-info/sboms/second.spdx3.json" in namelist
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" not in namelist

        record_text = zf.read("stalepkg-1.0.0.dist-info/RECORD").decode("utf-8")
        assert "stalepkg-1.0.0.dist-info/sboms/second.spdx3.json" in record_text
        assert "stalepkg-1.0.0.dist-info/sboms/first.spdx3.json" not in record_text

    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()


def test_rewrite_wheel_archive_orig_mode_none(tmp_path: Path) -> None:
    """Test _rewrite_wheel_archive handles non-existent wheel path without error."""

    source_wheel = _make_dummy_wheel(tmp_path, "orig_mode_pkg", "1.0.0")
    target_wheel = tmp_path / "new_target.whl"

    with zipfile.ZipFile(source_wheel, "r") as original_zf:
        _rewrite_wheel_archive(
            target_wheel,
            original_zf,
            "orig_mode_pkg-1.0.0.dist-info/sboms/sbom.spdx3.json",
            b"{}",
            "orig_mode_pkg-1.0.0.dist-info/RECORD",
            b"",
            (2026, 1, 1, 0, 0, 0),
        )
    assert target_wheel.exists()


def test_cli_collect_wheel_paths_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI error handling for non-existent and non-whl paths."""
    not_a_whl = tmp_path / "test.txt"
    not_a_whl.write_text("hello", encoding="utf-8")
    non_existent = tmp_path / "missing.whl"

    # 1. Non-existent literal file
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(non_existent)])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel file not found" in err

    # 2. Not a .whl file
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(not_a_whl)])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: not a .whl file" in err

    # 3. Glob matching no wheels
    monkeypatch.setattr(
        sys, "argv", ["loom", "embed-wheel", str(tmp_path / "empty_dir/*.whl")]
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: no wheel files matched" in err


def test_cli_embed_wheel_multiple_with_output_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test multiple wheels with -o option returns error."""
    w1 = _make_dummy_wheel(tmp_path, "pkg_one", "1.0.0")
    w2 = _make_dummy_wheel(tmp_path, "pkg_two", "1.0.0")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(w1), str(w2), "-o", str(tmp_path / "out.json")],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: --output cannot be used when embedding multiple wheels" in err


def test_cli_embed_wheel_project_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI with explicit --project-dir."""
    wheel_path = _make_dummy_wheel(tmp_path, "projdirpkg", "1.0.0")
    fixture_dir = (
        Path(__file__).parent / "fixtures" / "projects" / "sampleproject-hatchling"
    )

    # 1. Non-existent project directory
    missing_dir = tmp_path / "no_such_proj_dir"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(missing_dir)],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: project directory not found" in err

    # 2. Valid project directory
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(fixture_dir)],
    )
    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "pitloom: embedded" in out


def test_cli_embed_wheel_pregenerated_sbom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI embedding a pregenerated SBOM file with --sbom."""
    wheel_path = _make_dummy_wheel(tmp_path, "pregenpkg", "1.0.0")
    sbom_file = tmp_path / "custom_sbom.spdx3.json"
    sbom_file.write_text(_SAMPLE_SPDX3_JSON, encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(wheel_path),
            "--sbom",
            str(sbom_file),
            "--sbom-basename",
            "embedded_pregen.spdx3.json",
        ],
    )
    assert __main__.main() == 0
    out = capsys.readouterr().out
    assert "embedded_pregen.spdx3.json" in out

    with zipfile.ZipFile(wheel_path, "r") as zf:
        assert (
            "pregenpkg-1.0.0.dist-info/sboms/embedded_pregen.spdx3.json"
            in zf.namelist()
        )


def test_cli_wheel_embed_verbose_and_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom wheel --embed` with --verbose and explicit -o."""
    wheel_path = _make_dummy_wheel(tmp_path, "verbosepkg", "1.0.0")
    out_file = tmp_path / "standalone.spdx3.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "wheel",
            str(wheel_path),
            "--embed",
            "-v",
            "-o",
            str(out_file),
        ],
    )
    assert __main__.main() == 0
    captured = capsys.readouterr()
    assert "Output path" in captured.out
    assert out_file.exists()


def test_cli_embed_wheel_error_verbose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI error logging and traceback on failure with --verbose."""
    bad_wheel = tmp_path / "corrupt.whl"
    bad_wheel.write_bytes(b"not a zip file")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(bad_wheel), "-v"],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel SBOM embedding failed" in err


def test_cli_wheel_embed_error_verbose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test `loom wheel --embed` failure with --verbose."""
    bad_wheel = tmp_path / "corrupt.whl"
    bad_wheel.write_bytes(b"not a zip file")

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "wheel", str(bad_wheel), "--embed", "-v"],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "ERROR: wheel SBOM generation failed" in err


def test_cli_embed_wheel_project_dir_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI fallback when project directory exists but has no pyproject.toml."""
    wheel_path = _make_dummy_wheel(tmp_path, "nometa_pkg", "1.0.0")
    empty_dir = tmp_path / "empty_project_dir"
    empty_dir.mkdir()

    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "embed-wheel", str(wheel_path), "--project-dir", str(empty_dir)],
    )
    assert __main__.main() == 1
    err = capsys.readouterr().err
    assert "No pyproject.toml" in err
