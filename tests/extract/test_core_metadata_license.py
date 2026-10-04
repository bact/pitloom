# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract._core_metadata.core_metadata_license_with_source`,
the one licence-header rule shared by the sdist, wheel, installed-project
and installed-dependency readers.
"""

from __future__ import annotations

import email
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.deps import _finish_dependency_enrichment
from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._core_metadata import (
    core_metadata_license_with_source,
    first_license,
    license_or_classifier,
)
from pitloom.extract.project.installed import _parse_installed_metadata
from pitloom.extract.project.sdist import _parse_pkg_info, read_sdist
from pitloom.extract.wheel import _populate_metadata_from_email
from tests._license_graph import graph_of, license_targets, project_graph
from tests.assemble.conftest import _FakeMetadata, _make_ci

_BASE = "Metadata-Version: 2.4\nName: pkg\nVersion: 1.0.0\n"

#: (extra headers, licence every reader must agree on; ``None`` = absent or
#: empty), one case per boundary of the rule.
_CASES = [
    pytest.param("License-Expression: MIT\n", "MIT", id="expression-only"),
    pytest.param(
        "License-Expression: MIT\nLicense: Apache-2.0\n", "MIT", id="expression-wins"
    ),
    pytest.param("License: Apache-2.0\n", "Apache-2.0", id="legacy-only"),
    pytest.param("", None, id="neither"),
    pytest.param("License-Expression: \n", None, id="empty-expression"),
    pytest.param("License: \n", None, id="empty-legacy"),
    pytest.param(
        "License-Expression: \nLicense: Apache-2.0\n",
        "Apache-2.0",
        id="empty-then-legacy",
    ),
]


def _msg(extra: str) -> email.message.Message:
    return email.message_from_string(_BASE + extra)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("License-Expression: MIT\n", "MIT"),
        ("License-Expression: MIT\nLicense: Apache-2.0\n", "MIT"),
        ("License: Apache-2.0\n", "Apache-2.0"),
        ("", None),
        ("License-Expression: \n", ""),
        ("License: \n", ""),
        ("License-Expression: \nLicense: Apache-2.0\n", "Apache-2.0"),
        ("License: \n \n", ""),  # folded, whitespace only: blank
        ("License-Expression: \xa0\nLicense: Apache-2.0\n", "Apache-2.0"),
        # a writer's fold before each continuation line is not the text's
        ("License: a\n        b\n", "a\nb"),  # 8 spaces: setuptools, hatchling
        ("License: a\n        b\n        \n", "a\nb\n"),  # setuptools' last
        ("License: a\n       |b\n       |  c\n", "a\nb\n  c"),  # 7 and |
        ("License: a\n\tb\n", "a\nb"),  # RFC 5322
        ("License: a\n          b\n", "a\n  b"),  # inner indent kept
    ],
)
def test_core_metadata_license_is_tri_state(extra: str, expected: str | None) -> None:
    """Absent is ``None``; declared-but-empty is ``""``, not ``None``."""
    assert core_metadata_license_with_source(_msg(extra), "s")[0] == expected


@pytest.mark.parametrize(("extra", "expected"), _CASES)
def test_sdist_pkg_info_reads_license_expression(
    extra: str, expected: str | None
) -> None:
    metadata = _parse_pkg_info(_BASE + extra, "Source: PKG-INFO")
    assert metadata.license_name == expected
    assert ("license" in metadata.provenance) is bool(expected)


@pytest.mark.parametrize("suffix", [".tar.gz", ".zip"])
def test_read_sdist_reads_license_expression(tmp_path: Path, suffix: str) -> None:
    """Both archive kinds, with both headers present: the expression wins."""
    pkg_info = _BASE + "License-Expression: MIT\nLicense: Apache-2.0\n"
    sdist = tmp_path / f"pkg-1.0.0{suffix}"
    if suffix == ".zip":
        with zipfile.ZipFile(sdist, "w") as zf:
            zf.writestr("pkg-1.0.0/PKG-INFO", pkg_info)
    else:
        data = pkg_info.encode()
        with tarfile.open(sdist, "w:gz") as tf:
            info = tarfile.TarInfo("pkg-1.0.0/PKG-INFO")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    metadata = read_sdist(sdist).metadata
    assert metadata.license_name == "MIT"
    assert "license" in metadata.provenance


_MIT = "License :: OSI Approved :: MIT License"

#: Classifier cases for the end-to-end drift guard: the weak cascade and
#: exactly one relationship. (extra headers, expected licence targets)
_CLASSIFIER_CASES = [
    pytest.param(f"Classifier: {_MIT}\n", ["MIT License"], id="classifier-only"),
    pytest.param(
        f"License: UNKNOWN\nClassifier: {_MIT}\n", ["MIT License"], id="weak-license"
    ),
    pytest.param(f"License: MIT\nClassifier: {_MIT}\n", ["MIT"], id="license-wins"),
    pytest.param(f"License: NONE\nClassifier: {_MIT}\n", ["NONE"], id="none-ends"),
    pytest.param(
        f"License: \n \nClassifier: {_MIT}\n", ["MIT License"], id="folded-blank"
    ),
    pytest.param(
        f"License-Expression: \xa0\nClassifier: {_MIT}\n",
        ["MIT License"],
        id="nbsp-expression",
    ),
    pytest.param(
        "License-Expression: \xa0\nLicense: MIT\n", ["MIT"], id="nbsp-then-legacy"
    ),
    pytest.param("License: UNKNOWN\n", ["NOASSERTION"], id="weak-alone"),
    pytest.param(
        "License-Expression: UNKNOWN\nLicense: Apache-2.0\n",
        ["Apache-2.0"],
        id="weak-expression-then-legacy",
    ),
    pytest.param("License: a\n        b\n", ["a\nb"], id="folded-text"),
    pytest.param("Classifier: Topic :: Utilities\n", [], id="no-license"),
]


@pytest.mark.parametrize(
    ("primary", "expected"),
    [
        (None, ("MIT License", True)),
        ("  ", ("MIT License", True)),  # blank is absent
        ("unknown", ("MIT License", True)),  # weak
        ("NONE", ("NONE", False)),  # a statement
        ("Apache-2.0", ("Apache-2.0", False)),
    ],
)
def test_license_or_classifier(
    primary: str | None, expected: tuple[str | None, bool]
) -> None:
    assert license_or_classifier(primary, ["Topic :: Utilities", _MIT]) == expected


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (["UNKNOWN", "NOASSERTION", "MIT"], 2),  # weak gives way
        (["UNKNOWN", "NOASSERTION", None], 0),  # the first weak one
        (["", None, "NONE"], 2),  # NONE is a statement
        ([None, " "], None),  # none states any
    ],
)
def test_first_license(candidates: list[str | None], expected: int | None) -> None:
    assert first_license(candidates) == expected


def _dependency_targets(
    msg: email.message.Message, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], list[str]]:
    """The licence targets and the provenance of each licence a dependency
    records, through the real cascade (installed metadata, offline)."""
    fake = _FakeMetadata(
        {k: v for k, v in msg.items() if k != "Classifier"},
        classifiers=msg.get_all("Classifier"),
    )
    monkeypatch.setattr(deps_installed, "get_pkg_metadata", lambda _name: fake)
    sources: list[str] = []
    real = _apply_license

    def spy(license_id: str | None, provenance: str, *args: Any, **kw: Any) -> bool:
        sources.append(provenance)
        return real(license_id, provenance, *args, **kw)

    monkeypatch.setattr(deps_installed, "_apply_license", spy)
    doc_uuid = compute_doc_uuid("dep", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    package = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="pkg", creationInfo=ci
    )
    exporter.add_package(package)
    _finish_dependency_enrichment(
        "pkg", "1.0.0", package, ci, "dep", doc_uuid, exporter, offline=True
    )
    return license_targets(graph_of(exporter)), sources


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        *(
            pytest.param(c.values[0], [c.values[1]] if c.values[1] else [], id=c.id)
            for c in _CASES
        ),
        *_CLASSIFIER_CASES,
    ],
)
def test_license_readers_agree(
    extra: str, expected: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drift guard, end to end: the sdist, wheel, installed-project and
    installed-dependency readers record the same licence for one METADATA,
    through each one's own cascade, with one relationship, and name the
    classifier in provenance when one was used."""
    msg = _msg(extra)
    readers = {
        "sdist": _parse_pkg_info(_BASE + extra, "Source: sdist PKG-INFO"),
        "wheel": ProjectMetadata(name="pkg"),
        "installed": _parse_installed_metadata(msg, "Source: x.dist-info"),
    }
    _populate_metadata_from_email(
        readers["wheel"], readers["wheel"].provenance, msg, "Source: wheel METADATA"
    )
    for metadata in readers.values():
        metadata.version = "1.0.0"
    dependency, sources = _dependency_targets(msg, monkeypatch)
    assert dependency == expected
    for metadata in readers.values():
        assert license_targets(project_graph(metadata)) == expected
    from_classifier = {
        m.provenance.get("license", "").endswith("Field: Classifier")
        for m in readers.values()
    } | {sources[0].endswith("Field: Classifier")}
    assert from_classifier == {expected == ["MIT License"]}
