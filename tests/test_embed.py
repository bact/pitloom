# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.embed: PEP 770 post-build SBOM wheel injection."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

from pitloom import __main__
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom

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

    res_path, arcname = embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
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

    _, arcname = embed_sbom_in_wheel(
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

    res_path, arcname, sbom_json = embed_wheel_sbom(
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

    res_path, arcname, sbom_json = embed_wheel_sbom(
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


def test_validate_sbom_filename_edge_cases(tmp_path: Path) -> None:
    """Test _validate_sbom_filename rejects null bytes, traversal, and whitespace."""
    from pitloom.embed import _validate_sbom_filename

    for bad in ("", "   ", "\x00", "a/b", "a\\b", "..", "."):
        with pytest.raises(ValueError, match="Invalid SBOM filename"):
            _validate_sbom_filename(bad)


def test_embed_wheel_sbom_basename_with_extension_normalized(tmp_path: Path) -> None:
    """Test custom basename already ending with .spdx3.json avoids double extension."""
    wheel_path = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    _, arcname, _ = embed_wheel_sbom(
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
    import os
    import stat

    wheel_path = _make_dummy_wheel(tmp_path, "perm_pkg", "1.0.0")
    target_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH  # 0o644
    os.chmod(wheel_path, target_mode)

    embed_sbom_in_wheel(wheel_path, _SAMPLE_SPDX3_JSON)
    current_mode = stat.S_IMODE(wheel_path.stat().st_mode)
    assert current_mode == target_mode
