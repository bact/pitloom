# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The main package's ``License ::`` classifier as a licence source on every
surface that reads core metadata, and a licence text kept as written.

See also: :mod:`tests.assemble.test_license_elements_surfaces`.
"""

from __future__ import annotations

import email
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.plugin.manager import PluginManager

from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project import read_project
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.project.installed import _parse_installed_metadata
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import _populate_metadata_from_email
from tests._license_graph import (
    graph_of,
    license_elements,
    license_targets,
    license_value,
    provenance_fields,
    two_packages,
)
from tests.assemble.conftest import _make_sdist

_BSD = "License :: OSI Approved :: BSD License"
_MIT = "License :: OSI Approved :: MIT License"
#: Several classifiers, in any order: the AND of their names, sorted.
_BOTH = (
    "LicenseRef-pitloom-classifier-BSD-License"
    " AND LicenseRef-pitloom-classifier-MIT-License"
)
_HEAD = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\n"


def _metadata_text(license_name: str | None, classifiers: list[str]) -> str:
    lines = [f"License: {license_name}"] if license_name else []
    return _HEAD + "".join(
        f"{line}\n" for line in lines + [f"Classifier: {c}" for c in classifiers]
    )


def _from_wheel(
    license_name: str | None, classifiers: list[str], _tmp: Path
) -> ProjectMetadata:
    metadata = ProjectMetadata(name="demo")
    _populate_metadata_from_email(
        metadata,
        metadata.provenance,
        email.message_from_string(_metadata_text(license_name, classifiers)),
        "Source: wheel METADATA | File: demo.whl",
    )
    return metadata


def _from_sdist(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    text = _metadata_text(license_name, classifiers)
    sdist = _make_sdist(tmp, members={"PKG-INFO": text.encode()})
    return read_sdist(sdist, read_config=False).metadata


def _from_installed(
    license_name: str | None, classifiers: list[str], _tmp: Path
) -> ProjectMetadata:
    return _parse_installed_metadata(
        email.message_from_string(_metadata_text(license_name, classifiers)),
        "Source: demo-1.0.0.dist-info | File: METADATA",
    )


def _from_pyproject(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    licence = (
        f"license = {{text = {json.dumps(license_name)}}}\n" if license_name else ""
    )
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n'
        f"{licence}classifiers = {json.dumps(classifiers)}\n",
        encoding="utf-8",
    )
    return read_project(tmp, include_installed_metadata=False)[0]


def _from_setup_cfg(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    licence = f"license = {license_name}\n" if license_name else ""
    listed = "".join(f"\n    {c}" for c in classifiers)
    (tmp / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0.0\n{licence}classifiers ={listed}\n",
        encoding="utf-8",
    )
    return read_project(tmp, include_installed_metadata=False)[0]


def _from_pyproject_string(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    """The PEP 639 string form: ``license = "UNKNOWN"`` beside a classifier
    is a conflict for ``pyproject-metadata``, recovered without a drop."""
    licence = f"license = {json.dumps(license_name)}\n" if license_name else ""
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n'
        f"{licence}classifiers = {json.dumps(classifiers)}\n",
        encoding="utf-8",
    )
    return read_project(tmp, include_installed_metadata=False)[0]


def _from_hook(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    """The Hatchling build hook's reader, on the same ``pyproject.toml``."""
    _from_pyproject(license_name, classifiers, tmp)
    core = hatchling_metadata_core.ProjectMetadata(str(tmp), PluginManager())
    return metadata_from_hatchling(core, tmp)


def _from_setup_py(
    license_name: str | None, classifiers: list[str], tmp: Path
) -> ProjectMetadata:
    licence = f"    license={license_name!r},\n" if license_name else ""
    (tmp / "setup.py").write_text(
        "from setuptools import setup\n"
        f"setup(\n    name='demo',\n    version='1.0.0',\n{licence}"
        f"    classifiers={classifiers!r},\n)\n",
        encoding="utf-8",
    )
    return read_project(tmp, include_installed_metadata=False)[0]


_READERS: dict[str, Callable[[str | None, list[str], Path], ProjectMetadata]] = {
    "wheel": _from_wheel,
    "sdist": _from_sdist,
    "installed": _from_installed,
    "pyproject": _from_pyproject,
    "pyproject-string": _from_pyproject_string,
    "hook": _from_hook,
    "setup.cfg": _from_setup_cfg,
    "setup.py": _from_setup_py,
}


def _graph(metadata: ProjectMetadata) -> list[dict[str, Any]]:
    return graph_of(
        build(DocumentModel(project=metadata, creation_metadata=CreationMetadata()))
    )


@pytest.mark.parametrize("surface", list(_READERS))
@pytest.mark.parametrize(
    ("license_name", "classifiers", "expected"),
    [
        pytest.param(None, [_BSD], "BSD License", id="classifier-only"),
        pytest.param("UNKNOWN", [_BSD], "BSD License", id="weak-license"),
        pytest.param("MIT", [_BSD], "MIT", id="license-wins"),
        pytest.param("NONE", [_BSD], "NONE", id="none-is-a-statement"),
        pytest.param("UNKNOWN", [], "NOASSERTION", id="weak-alone"),
        pytest.param(None, ["Topic :: Utilities"], None, id="no-license-class"),
        pytest.param(None, [_MIT, _BSD, _MIT], _BOTH, id="several"),
        # a stated licence wins: the classifiers are not recorded, no WARNING
        pytest.param("MIT", [_MIT, _BSD, _MIT], "MIT", id="license-and-several"),
        # a trove parent is a category: the licence is its child alone
        pytest.param(
            None, ["License :: OSI Approved", _MIT], "MIT License", id="trove-parent"
        ),
    ],
)
def test_main_package_classifier_is_the_same_on_every_surface(
    surface: str,
    license_name: str | None,
    classifiers: list[str],
    expected: str | None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Directory (``pyproject.toml``, ``setup.cfg``, ``setup.py``) == build
    hook == sdist == wheel == installed: the same licence, declared (each is
    the package's own metadata), and the classifier named in provenance when
    it was used. A placeholder licence is no reason to drop a classifier as
    redundant, so no WARNING."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata = _READERS[surface](license_name, classifiers, tmp_path)
    # Only a real SPDX string beside a classifier is the PEP 639 transitional
    # state, whose redundant classifiers are dropped with one WARNING.
    transitional = surface == "pyproject-string" and license_name in ("MIT", "NONE")
    # Several licence classifiers: one WARNING that AND was assumed.
    assert len(caplog.records) == int(transitional) + int(expected == _BOTH)
    graph = _graph(metadata)
    assert license_targets(graph) == ([] if expected is None else [expected])
    relationships = {
        r["relationshipType"]
        for r in graph
        if r.get("relationshipType") in ("hasDeclaredLicense", "hasConcludedLicense")
    }
    assert relationships == (set() if expected is None else {"hasDeclaredLicense"})
    from_classifier = metadata.provenance.get("license", "").endswith(
        ("Field: Classifier", "classifiers", "setup(classifiers=...)")
    )
    assert from_classifier is (expected in ("BSD License", "MIT License", _BOTH))


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("MIT License\n", "MIT License"),  # final line breaks dropped
        ("MIT License\r\n\r\n", "MIT License"),  # all of them
        ("MIT License\r", "MIT License"),
        ("a\n\nb\n\n", "a\n\nb"),  # inner ones kept
        ("  indented\n\ttext \n", "indented\n\ttext "),  # the rest verbatim
        ("\n\n\tText\n  more", "Text\n  more"),  # leading blank space dropped
    ],
)
def test_licence_text_is_kept_as_written_less_its_final_line_breaks(
    text: str, kept: str
) -> None:
    metadata = ProjectMetadata(name="p", version="1.0", license_name=text)
    (element,) = license_elements(_graph(metadata))
    assert license_value(element) == kept


def test_texts_equal_when_stripped_share_the_first_seen_element() -> None:
    """The dedup key is the stripped text; the text kept is the first seen."""
    metadata = ProjectMetadata(
        name="p", version="1.0", license_name="Foo ", license_concluded="Foo"
    )
    (element,) = license_elements(_graph(metadata))
    assert license_value(element) == "Foo "


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("MIT OR Apache-2.0", "Apache-2.0 OR MIT"),  # operands reordered
        ("MIT OR MIT", "MIT"),  # a repeat collapsed
        ("MIT OR ISC OR MIT", "ISC OR MIT"),
        ("Apache-2.0+  OR  MIT", "MIT OR Apache-2.0+"),
    ],
)
def test_a_rewritten_expression_records_what_it_was(raw: str, value: str) -> None:
    graph = two_packages([raw])
    (element,) = license_elements(graph)
    assert license_value(element) == value
    notes = [
        f
        for subject in [element["spdxId"], *(r["spdxId"] for r in graph if "from" in r)]
        for f in provenance_fields(graph, subject)
    ]
    assert any(json.loads(f).get("normalized-from") == raw for f in notes)


def test_a_lone_surrogate_in_a_licence_still_serialises() -> None:
    metadata = ProjectMetadata(name="p", version="1.0", license_name="Foo\ud800")
    (element,) = license_elements(_graph(metadata))
    assert license_value(element) == "Foo�"
