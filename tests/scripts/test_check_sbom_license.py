# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/check_sbom_license.py``, the release workflow's
licence gate on Pitloom's own SBOM."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_PKG = "urn:x#Package-1"


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("check_sbom_license")


def _rel(rel_type: str, target: str) -> dict[str, Any]:
    return {
        "type": "Relationship",
        "from": _PKG,
        "relationshipType": rel_type,
        "to": [target],
    }


def _sbom() -> dict[str, Any]:
    return {
        "@graph": [
            {"type": "software_Sbom", "spdxId": "urn:x#Sbom-1", "rootElement": [_PKG]},
            {"type": "software_Package", "spdxId": _PKG, "name": "pitloom"},
            {
                "type": "simplelicensing_SimpleLicensingText",
                "spdxId": "urn:x#License-1",
                "simplelicensing_licenseText": "Apache-2.0",
            },
            _rel("hasDeclaredLicense", "urn:x#License-1"),
            _rel("hasConcludedLicense", "urn:x#License-1"),
        ]
    }


def _graph(sbom: dict[str, Any]) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = sbom["@graph"]
    return graph


def _drop_concluded(sbom: dict[str, Any]) -> None:
    sbom["@graph"] = [
        e for e in _graph(sbom) if e.get("relationshipType") != "hasConcludedLicense"
    ]


def _concluded_mit(sbom: dict[str, Any]) -> None:
    _graph(sbom).append(
        {
            "type": "simplelicensing_LicenseExpression",
            "spdxId": "urn:x#License-2",
            "simplelicensing_licenseExpression": "MIT",
        }
    )
    _graph(sbom)[-2]["to"] = ["urn:x#License-2"]


def _second_concluded(sbom: dict[str, Any]) -> None:
    _graph(sbom).append(_rel("hasConcludedLicense", "urn:x#License-1"))


def _dangling_declared(sbom: dict[str, Any]) -> None:
    _graph(sbom)[3]["to"] = ["urn:x#Missing"]


def _two_roots(sbom: dict[str, Any]) -> None:
    _graph(sbom)[0]["rootElement"] = [_PKG, _PKG]


def _root_not_package(sbom: dict[str, Any]) -> None:
    _graph(sbom)[1]["type"] = "software_File"


def _graph_not_list(sbom: dict[str, Any]) -> None:
    sbom["@graph"] = {}


def _to_not_list(sbom: dict[str, Any]) -> None:
    _graph(sbom)[4]["to"] = 7


def _unhashable_ids(sbom: dict[str, Any]) -> None:
    _graph(sbom)[2]["spdxId"] = ["urn:x#License-1"]
    _graph(sbom)[4]["to"] = [["urn:x#License-1"]]


def test_valid_sbom_passes(module: ModuleType) -> None:
    module.check_sbom_license(_sbom(), "Apache-2.0")


def test_full_iri_relationship_type_passes(module: ModuleType) -> None:
    sbom = _sbom()
    for rel in _graph(sbom)[3:]:
        rel["relationshipType"] = (
            "https://spdx.org/rdf/3.0.1/terms/Core/RelationshipType/"
            + rel["relationshipType"]
        )
    module.check_sbom_license(sbom, "Apache-2.0")


@pytest.mark.parametrize(
    "mutate",
    [
        _drop_concluded,
        _concluded_mit,
        _second_concluded,
        _dangling_declared,
        _two_roots,
        _root_not_package,
        _graph_not_list,
        _to_not_list,
        _unhashable_ids,
    ],
)
def test_bad_sbom_fails(module: ModuleType, mutate: Callable[..., None]) -> None:
    sbom = _sbom()
    mutate(sbom)
    assert sbom != _sbom()
    with pytest.raises(module.SbomLicenseError):
        module.check_sbom_license(sbom, "Apache-2.0")


def test_wrong_expected_license_fails(module: ModuleType) -> None:
    with pytest.raises(module.SbomLicenseError, match="hasDeclaredLicense"):
        module.check_sbom_license(_sbom(), "MIT")


@pytest.mark.parametrize(
    "target",
    [
        "expandedlicensing_NoAssertionLicense",
        "https://spdx.org/rdf/3.0.1/terms/ExpandedLicensing/NoAssertionLicense",
    ],
)
def test_a_named_individual_target_is_its_licence_name(
    module: ModuleType, target: str
) -> None:
    """``NoAssertionLicense`` has no element: it reads as ``NOASSERTION``, so
    it matches that and no real licence."""
    sbom = _sbom()
    for rel in _graph(sbom)[3:]:
        rel["to"] = [target]
    module.check_sbom_license(sbom, "NOASSERTION")
    with pytest.raises(module.SbomLicenseError, match="NOASSERTION"):
        module.check_sbom_license(sbom, "Apache-2.0")


@pytest.mark.parametrize(
    "target", ["urn:x#Foo_NoneLicense", "urn:x#Foo/NoAssertionLicense"]
)
def test_a_lookalike_of_an_individual_is_not_one(
    module: ModuleType, target: str
) -> None:
    sbom = _sbom()
    for rel in _graph(sbom)[3:]:
        rel["to"] = [target]
    with pytest.raises(module.SbomLicenseError, match="no licence text"):
        module.check_sbom_license(sbom, "NOASSERTION")


def _write_wheel(path: Path, sboms: dict[str, bytes]) -> Path:
    """A wheel with a ``.dist-info`` that ``find_embedded_sbom`` accepts."""
    members = {
        "p/__init__.py": b"",
        "p-1.dist-info/METADATA": b"Metadata-Version: 2.4\nName: p\nVersion: 1\n",
        "p-1.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
    }
    members.update({f"p-1.dist-info/sboms/{k}": v for k, v in sboms.items()})
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in members.items():
            wheel.writestr(name, data)
    return path


def test_load_sbom_reads_wheel_member(module: ModuleType, tmp_path: Path) -> None:
    wheel = _write_wheel(
        tmp_path / "p-1-py3-none-any.whl",
        {"p-1.spdx3.json": json.dumps(_sbom()).encode()},
    )
    assert module.load_sbom(wheel) == _sbom()


@pytest.mark.parametrize(
    ("sboms", "pattern"),
    [
        ({}, "no SBOM"),
        ({"s0.spdx3.json": b"{}", "s1.spdx3.json": b"{}"}, "Multiple SBOMs"),
        ({"sub/s.spdx3.json": b"{}"}, "no SBOM"),
    ],
)
def test_load_sbom_wheel_needs_one_sbom(
    module: ModuleType, tmp_path: Path, sboms: dict[str, bytes], pattern: str
) -> None:
    wheel = _write_wheel(tmp_path / "p-1-py3-none-any.whl", sboms)
    with pytest.raises(module.SbomLicenseError, match=pattern):
        module.load_sbom(wheel)


def test_load_sbom_not_a_wheel(module: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "p-1-py3-none-any.whl"
    bad.write_bytes(b"not a zip")
    with pytest.raises(module.SbomLicenseError, match="cannot read"):
        module.load_sbom(bad)


@pytest.mark.parametrize(
    "payload", [b"\xff\xfe not json", b"{", b'\xef\xbb\xbf{"@graph": []}']
)
def test_load_sbom_bad_or_bom_json(
    module: ModuleType, tmp_path: Path, payload: bytes
) -> None:
    """Malformed bytes raise the script's own error; a UTF-8 BOM is accepted."""
    path = tmp_path / "s.json"
    path.write_bytes(payload)
    if payload.startswith(b"\xef\xbb\xbf"):
        assert module.load_sbom(path) == {"@graph": []}
    else:
        with pytest.raises(module.SbomLicenseError, match="cannot read"):
            module.load_sbom(path)


def test_cli_reports_each_path(scripts_dir: Path, tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_sbom()), encoding="utf-8")
    bad_sbom = copy.deepcopy(_sbom())
    _drop_concluded(bad_sbom)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_sbom), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "check_sbom_license.py"),
            "--license",
            "Apache-2.0",
            str(good),
            str(bad),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    stdout = result.stdout.decode()
    stderr = result.stderr.decode()
    assert f"FILE={good} LICENSE=Apache-2.0" in stdout
    assert stderr.startswith(f"ERROR: FILE={bad}:")
    assert "hasConcludedLicense" in stderr
    assert str(good) not in stderr


def test_load_sbom_uppercase_wheel_extension_is_refused(
    module: ModuleType, tmp_path: Path
) -> None:
    """``x.WHL`` is routed as a wheel, then refused as ``pip`` would."""
    wheel = _write_wheel(tmp_path / "p-1-py3-none-any.WHL", {})
    with pytest.raises(module.SbomLicenseError, match="not a .whl file"):
        module.load_sbom(wheel)
