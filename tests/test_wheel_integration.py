# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: build a real wheel and verify the SBOM is inside it."""

# pytest fixtures intentionally shadow the outer-scope fixture name in test params.
# pylint: disable=redefined-outer-name

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from installer.sources import WheelFile

# Skip the entire module if hatchling is not installed.
pytest.importorskip(
    "hatchling", reason="hatchling is required for wheel integration tests"
)

# Guard import after importorskip.
# pylint: disable=wrong-import-position
from hatchling.builders.wheel import WheelBuilder  # noqa: E402

from pitloom.embed import embed_wheel_sbom  # noqa: E402

# pylint: enable=wrong-import-position

FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "projects" / "sampleproject-hatchling"
)


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a wheel from the sampleproject-hatchling fixture and return its path.

    Uses ``WheelBuilder`` directly (no subprocess, no network) so the locally
    installed Pitloom is picked up.  Skipped when the fixture is absent.
    """
    if not FIXTURE_DIR.exists():
        pytest.skip("sampleproject-hatchling fixture not found")

    out_dir = tmp_path_factory.mktemp("wheel_out")
    builder = WheelBuilder(str(FIXTURE_DIR))
    wheel_filename = next(builder.build(directory=str(out_dir), versions=["standard"]))
    wheel_path = Path(wheel_filename)
    assert wheel_path.exists(), f"Expected wheel at {wheel_path}"
    return wheel_path


# ---------------------------------------------------------------------------
# Wheel structure -- SBOM placement (PEP 770)
# ---------------------------------------------------------------------------


def test_sbom_present_in_wheel(built_wheel: Path) -> None:
    """The wheel must contain exactly one file inside .dist-info/sboms/."""
    with zipfile.ZipFile(built_wheel) as zf:
        sbom_entries = [n for n in zf.namelist() if "/sboms/" in n]
    assert len(sbom_entries) == 1, f"Expected 1 SBOM entry, found: {sbom_entries}"


def test_sbom_path_matches_pep770(built_wheel: Path) -> None:
    """The SBOM must live at <dist-info>/sboms/<basename> (PEP 770)."""
    with zipfile.ZipFile(built_wheel) as zf:
        sbom_entries = [n for n in zf.namelist() if "/sboms/" in n]
    assert len(sbom_entries) == 1
    entry = sbom_entries[0]
    # Path must be: <name>-<version>.dist-info/sboms/<filename>
    assert entry.endswith(".dist-info/sboms/sbom.spdx3.json"), (
        f"Unexpected SBOM path in wheel: {entry}"
    )


def test_sbom_is_valid_json_ld(built_wheel: Path) -> None:
    """The SBOM file inside the wheel must be valid JSON-LD."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        raw = zf.read(sbom_entry)
    data = json.loads(raw)
    assert "@context" in data, "SBOM JSON-LD must have an @context key"
    assert "@graph" in data, "SBOM JSON-LD must have a @graph key"


def test_sbom_graph_contains_package(built_wheel: Path) -> None:
    """The SBOM graph must contain a software_Package element for
    sampleproject_hatchling.

    ``metadata_from_hatchling()`` uses ``core.raw_name`` (the un-normalized
    name), not Hatchling's PEP-503-normalized ``core.name``, so the package
    name in the SBOM is "sampleproject_hatchling" -- exactly the spelling
    written in the fixture's ``pyproject.toml`` ``[project] name`` -- matching
    what the CLI (``read_pyproject``) would report for the same project.
    """
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    pkg_names = [
        e.get("name") for e in data["@graph"] if e.get("type") == "software_Package"
    ]
    assert "sampleproject_hatchling" in pkg_names, (
        f"Expected 'sampleproject_hatchling' package in SBOM graph, found: {pkg_names}"
    )


def test_sbom_graph_contains_creator(built_wheel: Path) -> None:
    """The SBOM graph must contain the creator declared in the hook config."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    # sampleproject-hatchling/pyproject.toml sets creator-name = "Pitloom CI"
    person_names = [e.get("name") for e in data["@graph"] if e.get("type") == "Person"]
    assert "Pitloom CI" in person_names, (
        f"Expected creator 'Pitloom CI' in SBOM graph, found: {person_names}"
    )


def test_sbom_multiple_creators_and_tools_in_wheel(built_wheel: Path) -> None:
    """The real, built wheel's SBOM must embed all declared creators and
    creation tools, correctly linked from CreationInfo.

    Complements ``test_hook_multiple_creators_appear_in_graph`` in
    ``test_hatch_hook.py``, which asserts the same logical shape via a
    direct ``BuildHookInterface.initialize()`` call rather than a real
    ``python -m build`` / Hatchling wheel build -- this test proves the
    result also lands correctly inside an actual ``.whl`` zip (PEP 770).

    ``sampleproject-hatchling/pyproject.toml`` declares two creators
    (a Person "Pitloom CI" and an Organization "Sample Project Org") and
    two creation tools ("Pitloom" and "CI Wrapper").
    """
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    graph = data["@graph"]

    elements_by_id = {
        element["spdxId"]: element for element in graph if "spdxId" in element
    }

    creation_infos = [e for e in graph if e.get("type") == "CreationInfo"]
    assert len(creation_infos) == 1, (
        f"Expected exactly 1 CreationInfo element, found: {creation_infos}"
    )
    creation_info = creation_infos[0]

    created_by = [elements_by_id[i] for i in creation_info.get("createdBy", [])]
    assert len(created_by) == 2, f"Expected 2 createdBy agents, found: {created_by}"
    persons = [a for a in created_by if a.get("type") == "Person"]
    orgs = [a for a in created_by if a.get("type") == "Organization"]
    assert [p.get("name") for p in persons] == ["Pitloom CI"]
    assert [o.get("name") for o in orgs] == ["Sample Project Org"]

    created_using = [elements_by_id[i] for i in creation_info.get("createdUsing", [])]
    tool_names = sorted(t.get("name") for t in created_using)
    assert tool_names == ["CI Wrapper", "Pitloom"], (
        f"Expected createdUsing tools ['CI Wrapper', 'Pitloom'], found: {tool_names}"
    )


def test_sbom_is_not_empty(built_wheel: Path) -> None:
    """The SBOM file inside the wheel must have non-trivial content."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        size = zf.getinfo(sbom_entry).file_size
    assert size > 100, f"SBOM is suspiciously small ({size} bytes)"


def test_sbom_graph_contains_file_hashes(built_wheel: Path) -> None:
    """The embedded SBOM must contain at least one file with a SHA-256
    verifiedUsing hash (PEP 770 wheel/CLI enrichment)."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    files = [
        e
        for e in data["@graph"]
        if e.get("type") == "software_File" and e.get("software_fileKind") == "file"
    ]
    assert files, "Expected at least one file-kind software_File in the SBOM"
    assert all(e.get("verifiedUsing") for e in files), (
        "Every packaged file must carry a verifiedUsing hash"
    )
    (hash_obj,) = files[0]["verifiedUsing"]
    assert hash_obj["algorithm"] == "sha256"


def test_sbom_graph_contains_main_package_purl(built_wheel: Path) -> None:
    """The main package must carry a pkg:pypi PURL (name normalized to
    sampleproject-hatchling per PEP 503), even though the package element's
    own ``name`` is the un-normalized "sampleproject_hatchling"."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    packages = [e for e in data["@graph"] if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "sampleproject_hatchling")
    assert main_package["software_packageUrl"] == (
        "pkg:pypi/sampleproject-hatchling@0.1.0"
    )


# ---------------------------------------------------------------------------
# 3rd-party validation: PyPA installer, check-wheel-contents, pip, spdx3-validate
# ---------------------------------------------------------------------------


def test_wheel_record_passes_pypa_installer_validation(built_wheel: Path) -> None:
    """PyPA installer strictly validates every file and RECORD hash in the wheel."""
    with WheelFile.open(built_wheel) as wf:
        wf.validate_record()


def test_wheel_passes_check_wheel_contents(built_wheel: Path) -> None:
    """check-wheel-contents validates the wheel's layout and files."""
    res = subprocess.run(
        [sys.executable, "-m", "check_wheel_contents", str(built_wheel)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"check-wheel-contents failed: {res.stderr}"


def test_wheel_passes_pip_install_dry_run(built_wheel: Path, tmp_path: Path) -> None:
    """pip install --dry-run unpacks and validates wheel without issues."""
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--target",
            str(tmp_path),
            "--no-deps",
            str(built_wheel),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"pip install --dry-run failed: {res.stderr}"


def test_wheel_sbom_passes_spdx3_validate(built_wheel: Path, tmp_path: Path) -> None:
    """Embedded SBOM in wheel conforms to SPDX 3.0.1 per spdx3-validate."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        sbom_data = zf.read(sbom_entry)

    sbom_file = tmp_path / "embedded.spdx3.json"
    sbom_file.write_bytes(sbom_data)

    res = subprocess.run(
        [sys.executable, "-m", "spdx3_validate", "--json", str(sbom_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"spdx3-validate failed: {res.stderr} {res.stdout}"


def _build_plain_fixture_wheel(tmp_path: Path) -> tuple[Path, Path]:
    """Build a plain wheel from sampleproject-hatchling without pitloom hook."""
    proj_dir = tmp_path / "plain_proj"
    shutil.copytree(FIXTURE_DIR, proj_dir)
    pyproject_file = proj_dir / "pyproject.toml"
    content = pyproject_file.read_text(encoding="utf-8").replace(
        "enabled = true", "enabled = false"
    )
    pyproject_file.write_text(content, encoding="utf-8")

    out_dir = tmp_path / "wheel_out"
    builder = WheelBuilder(str(proj_dir))
    wheel_filename = next(builder.build(directory=str(out_dir), versions=["standard"]))
    return proj_dir, Path(wheel_filename)


def test_post_build_wheel_embedding_integration(tmp_path: Path) -> None:
    """Test post-build wheel embedding (non-Hatchling / post-processing path)."""
    proj_dir, wheel_path = _build_plain_fixture_wheel(tmp_path)

    # Verify no SBOM exists before embedding
    with zipfile.ZipFile(wheel_path) as zf:
        assert not [n for n in zf.namelist() if "/sboms/" in n]

    # Post-process: embed PEP 770 SBOM via Pitloom
    res_path, arcname, sbom_json, _, _ = embed_wheel_sbom(
        wheel_path,
        project_dir=proj_dir,
    )
    assert res_path == wheel_path
    assert arcname.endswith(".dist-info/sboms/sbom.spdx3.json")

    # Authoritative 3rd-party validation suite
    with WheelFile.open(wheel_path) as wf:
        wf.validate_record()

    res = subprocess.run(
        [sys.executable, "-m", "check_wheel_contents", str(wheel_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"check-wheel-contents failed: {res.stderr}"

    install_target = tmp_path / "install_target"
    pip_res = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--target",
            str(install_target),
            "--no-deps",
            str(wheel_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert pip_res.returncode == 0, f"pip install failed: {pip_res.stderr}"

    sbom_file = tmp_path / "post_embedded.spdx3.json"
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
