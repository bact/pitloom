# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``software_Package`` key holds the package's version (Q-D): each
release of a package is its own registry entry, so a release keeps its id
and another release gets its own.

The key is ``<PEP 503 name>[@<canonical PEP 440 version>]``; a package
that states no version has a bare key, which never matches a versioned one.

See also: :mod:`tests.id_registry.test_package_ids` (two versions of one
dependency in one document), :mod:`tests.id_registry.test_surfaces_same_ids`
(every route, both orders), ``tests/cli/test_cli_id_entity_key.py`` (``-e``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import dataclasses
import itertools
import unicodedata
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble.spdx3._document_deployed import build_deployed
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.lock.common import is_same_version
from pitloom.id_registry import (
    PACKAGE_TYPE,
    IdRegistry,
    RegistryEntry,
    package_key,
    package_version_key,
)
from pitloom.id_registry._ambiguous import _element_key_of
from pitloom.id_registry._types import _element_key
from tests.id_registry.package_ids_base import (
    build_doc,
    claim_warnings,
    make_doc,
    packages,
    phantom,
)

_NFD = unicodedata.normalize("NFD", "café")
_OVERLONG = "1." + "9" * 700

#: (version text, the key's version part): one row per PEP 440 boundary.
_PARTS = [
    ("1.0", "1"),
    ("1.0.0", "1"),
    ("v1.0", "1"),
    ("01.00", "1"),
    ("1!1.0", "1!1"),
    ("1.0rc1", "1rc1"),
    ("1.0c1", "1rc1"),
    ("1.0.post1", "1.post1"),
    ("1.0-1", "1.post1"),
    ("1.0.dev0", "1.dev0"),
    ("1.0+cu121", "1+cu121"),
    ("1.0+CU-121", "1+cu.121"),
    ("1.0+cpu", "1+cpu"),
    ("foobar", "foobar"),  # a ``===foobar`` pin: no PEP 440 version, as given
    ("1.0 beta", "1.0 beta"),
    (_OVERLONG, _OVERLONG),  # an overlong number is never parsed
    (_NFD, unicodedata.normalize("NFC", _NFD)),
    (None, None),
    ("", None),
    (" ", None),
    ("unknown", None),
    ("UNKNOWN", None),
    ("NOASSERTION", None),
]
_PART_IDS = [
    *("1.0", "1.0.0", "v1.0", "01.00", "epoch", "rc", "c", "post", "post-n"),
    *("dev", "local", "local-spelt", "local-cpu", "arbitrary", "unparsable"),
    *("overlong", "nfd", "none", "empty", "blank", "unknown", "UNKNOWN"),
    "noassertion",
]


@pytest.mark.parametrize(("version", "part"), _PARTS, ids=_PART_IDS)
def test_package_version_key(version: str | None, part: str | None) -> None:
    assert package_version_key(version) == part


#: (name, version, key): PEP 503 names, the separator, the bare key.
_KEYS = [
    ("Requests", "2.31.0", "requests@2.31"),
    ("Foo_Bar.baz", "1.0", "foo-bar-baz@1"),
    ("foo-bar-baz", "1", "foo-bar-baz@1"),
    ("@scope/pkg", "1.0.0", "%40scope/pkg@1"),
    ("a%40b", None, "a%2540b"),
    ("foo", "unknown", "foo"),
    ("foo", "1.0\nINFO: x", "foo@1.0\nINFO: x"),
]


@pytest.mark.parametrize(("name", "version", "key"), _KEYS)
def test_package_key_and_its_normalisation_is_idempotent(
    name: str, version: str | None, key: str
) -> None:
    """The key, and every normalisation of it (load, ``-e``, ``get``,
    ``register``), is one fixed point: the first ``@`` is the separator."""
    assert package_key(name, version) == key
    assert _element_key(type_name=PACKAGE_TYPE, name=key) == (PACKAGE_TYPE, key)


def test_a_bare_key_never_matches_a_versioned_one() -> None:
    registry = IdRegistry.new("r")
    bare = registry.register(PACKAGE_TYPE, "foo")
    versioned = registry.register(PACKAGE_TYPE, "foo@1.0")

    assert bare != versioned
    assert registry.lookup(PACKAGE_TYPE, ["foo"]) == bare
    assert registry.lookup(PACKAGE_TYPE, ["Foo@1.0.0"]) == versioned
    assert registry.lookup(PACKAGE_TYPE, ["foo@2"]) is None


#: Stated versions only: a placeholder (``unknown``) is no version, and an
#: NFC/NFD pair of one unparsable text is one key (every key is NFC) but
#: two texts to ``is_same_version``.
_STATED = [
    *(v for v, part in _PARTS if v is not None and part and v is not _NFD),
    *("2.31.0", "2.31", f"{_OVERLONG}.0"),
]


def test_version_key_agrees_with_is_same_version() -> None:
    """Drift guard: two versions share a key part exactly when the
    dependency grouping calls them one release."""
    disagree = [
        (a[:20], b[:20])
        for a, b in itertools.combinations(_STATED, 2)
        if is_same_version(a, b) != (package_version_key(a) == package_version_key(b))
    ]
    assert not disagree


def test_a_key_with_an_at_sign_in_the_name_survives_a_file_round_trip(
    tmp_path: Path,
) -> None:
    registry = IdRegistry.new("r")
    spdx_id = registry.register(PACKAGE_TYPE, package_key("@scope/pkg", "1.0"))
    registry.save(tmp_path / "r.json")
    element = spdx3.software_Package(
        spdxId=spdx_id, name="@scope/pkg", creationInfo=_creation()
    )
    element.software_packageVersion = "1.0.0"

    loaded = IdRegistry.load(tmp_path / "r.json")

    assert loaded.get(PACKAGE_TYPE, "%40scope/pkg@1") == RegistryEntry(spdx_id)
    assert _element_key_of(element) == (PACKAGE_TYPE, "%40scope/pkg@1")


# --- a document's packages, run after run ----------------------------------


def _doc(version: str, *dependencies: str) -> DocumentModel:
    doc = make_doc(dependencies=dependencies)
    project = dataclasses.replace(doc.project, version=version)
    return dataclasses.replace(doc, project=project)


def _run(registry: IdRegistry, doc: DocumentModel) -> dict[str, str]:
    """One build and its auto-harvest; name -> spdxId of each package."""
    exporter = build_doc(doc, registry)
    _sync_registry(exporter, registry, True)
    return {p.name: p.spdx_id for p in packages(exporter)}


@pytest.mark.usefixtures("fixed_epoch")
def test_each_release_gets_its_own_id_and_going_back_gets_the_first(
    tmp_path: Path,
) -> None:
    """``demo`` and its ``foo`` pin go 1.0, 2.0, 1.0: the second release
    gets new ids, the third the first's (on ``main`` all three shared)."""
    registry = IdRegistry.new("r", tmp_path / "r.json")

    ids = [_run(registry, _doc(v, f"foo=={v}")) for v in ("1.0", "2.0", "1.0")]

    for name in ("demo", "foo"):
        assert ids[1][name] != ids[0][name], name
        assert ids[2][name] == ids[0][name], name
    keys = {name for type_name, name in registry.elements if type_name == PACKAGE_TYPE}
    assert keys == {"demo@1", "demo@2", "foo@1", "foo@2"}


@pytest.mark.parametrize("installed_first", [False, True], ids=["unknown", "installed"])
def test_unknown_and_installed_versions_are_two_keys_in_either_order(
    tmp_path: Path, installed_first: bool
) -> None:
    """An unpinned dependency is ``unknown`` when not installed (a bare key)
    and its installed version when installed: two packages, two ids, each
    kept when it comes back."""
    registry = IdRegistry.new("r", tmp_path / "r.json")
    states = [installed_first, not installed_first, installed_first]

    def run(installed: bool) -> str:
        found = patch(
            "pitloom.assemble.spdx3.deps_installed.get_package_version",
            return_value="1.0",
            side_effect=None if installed else PackageNotFoundError("foo"),
        )
        with found:
            return _run(registry, _doc("1.0.0", "foo"))["foo"]

    ids = [run(installed) for installed in states]

    assert ids[0] != ids[1]
    assert ids[2] == ids[0]
    assert registry.get(PACKAGE_TYPE, "foo") is not None
    assert registry.get(PACKAGE_TYPE, "foo@1") is not None


def test_a_hand_edited_registry_sharing_one_id_across_releases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``foo@1`` and ``foo@2`` hold one id: the first claimant takes it,
    the other gets the claim WARNING and its own id; the harvest leaves one
    key per id, so the next run is silent."""
    registry = IdRegistry.new("r", tmp_path / "r.json")
    shared = registry.register(PACKAGE_TYPE, "foo@1.0")
    registry.elements[(PACKAGE_TYPE, "foo@2")] = RegistryEntry(shared)
    doc = make_doc(dependencies=["foo==1.0; os_name=='a'", "foo==2.0; os_name=='b'"])

    with caplog.at_level("WARNING"):
        first = build_doc(doc, registry)
        _sync_registry(first, registry, True)
        warnings = claim_warnings(caplog)
        second = build_doc(doc, registry)

    ids = {p.version: p.spdx_id for p in packages(first) if p.name == "foo"}
    assert ids["1.0"] == shared and ids["2.0"] != shared
    assert len(warnings) == 1
    assert "dependency foo 1.0 and dependency foo 2.0" in warnings[0]
    assert len(claim_warnings(caplog)) == 1  # the second build said nothing
    assert registry.lookup(PACKAGE_TYPE, ["foo@2"]) == ids["2.0"]
    assert {p.version: p.spdx_id for p in packages(second) if p.name == "foo"} == ids


def test_a_newline_in_a_version_is_one_escaped_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A version is text an archive or an SBOM states: in the claim WARNING
    it is escaped, so it cannot forge a second line."""
    version = "1\nINFO: forged"
    registry = IdRegistry.new("r")
    registry.register(PACKAGE_TYPE, package_key("libz", version))

    with caplog.at_level("WARNING"):
        build_doc(make_doc(phantom=[phantom("libz", version)] * 2), registry)

    (warning,) = claim_warnings(caplog)
    assert "\n" not in warning
    assert "libz 1\\nINFO: forged" in warning


def test_recorded_package_keys_are_the_keys_harvest_derives() -> None:
    """Drift guard: the key a lookup records for a package (what a run's
    harvest writes) is the key derived from its name and version (what
    ``id import`` and a merged fragment write)."""
    registry = IdRegistry.new("r")
    doc = make_doc(
        dependencies=["Foo_Bar==1.0.0", "baz===foobar", "local==1.0+CU-121", "bare"],
        locked=["locked-lib==3.0"],
        phantom=[phantom("libz", "1.2"), phantom("libq")],
    )
    for found in packages(build_doc(doc, None)):  # pin every package's key
        registry.register(PACKAGE_TYPE, package_key(found.name, found.version))
    registry.register(PACKAGE_TYPE, "req@2.0.0")
    deployed = DocumentModel(
        project=ProjectMetadata(name="deployed-environment", version="0.0.0"),
        creation_metadata=doc.creation_metadata,
    )
    tree = [{"package": {"key": "req", "installed_version": "2.0.0"}}]

    exporters = [
        build_doc(doc, registry),
        build_deployed(deployed, tree, registry=registry, offline=True),
    ]

    checked = 0
    for exporter in exporters:
        for obj in exporter.object_set.objects:
            recorded = exporter.registry_keys.get(str(getattr(obj, "spdxId", "")))
            if isinstance(obj, spdx3.software_Package) and recorded is not None:
                assert recorded == _element_key_of(obj), obj.name
                checked += 1
    assert checked == 9  # main, five dependencies, two phantoms, req


# --- id import and loom env -------------------------------------------------


def _creation() -> spdx3.CreationInfo:
    info = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    info.createdBy = ["https://spdx.org/spdxdocs/import-1#SoftwareAgent-1"]
    return info


@pytest.mark.parametrize(
    ("version", "key"),
    [("2.31.0", "requests@2.31"), (None, "requests"), ("NOASSERTION", "requests")],
    ids=["versioned", "none", "noassertion"],
)
def test_id_import_keys_a_package_by_the_version_it_states(
    tmp_path: Path, version: str | None, key: str
) -> None:
    namespace = "https://spdx.org/spdxdocs/import-1"
    info = _creation()
    element = spdx3.software_Package(
        spdxId=f"{namespace}#Package-1", name="Requests", creationInfo=info
    )
    if version is not None:
        element.software_packageVersion = version
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(info)
    exporter.add_agent(
        spdx3.SoftwareAgent(
            spdxId=f"{namespace}#SoftwareAgent-1", name="Pitloom", creationInfo=info
        )
    )
    exporter.add_package(element)
    sbom = tmp_path / "in.spdx3.json"
    sbom.write_text(exporter.to_json(), encoding="utf-8")
    registry = IdRegistry.new("r")

    registry.import_sbom(sbom)

    assert [k for k in registry.elements if k[0] == PACKAGE_TYPE] == [
        (PACKAGE_TYPE, key)
    ]


def _env(registry: IdRegistry, versions: dict[str, str]) -> dict[str, str]:
    doc = DocumentModel(
        project=ProjectMetadata(name="deployed-environment", version="0.0.0"),
        creation_metadata=make_doc().creation_metadata,
    )
    tree = [
        {"package": {"key": name, "installed_version": version}}
        for name, version in versions.items()
    ]
    exporter = build_deployed(doc, tree, registry=registry, offline=True)
    _sync_registry(exporter, registry, True)
    return {p.name: p.spdx_id for p in packages(exporter)}


def test_env_upgrade_gives_only_the_upgraded_package_a_new_id(
    tmp_path: Path,
) -> None:
    """``loom env`` before and after ``foo`` is upgraded: ``foo`` gets a new
    id, ``bar`` and the synthetic root (``deployed-environment@0``, never
    looked up) keep theirs."""
    registry = IdRegistry.new("r", tmp_path / "r.json")

    before = _env(registry, {"foo": "1.0", "bar": "2.0"})
    after = _env(registry, {"foo": "1.1", "bar": "2.0"})

    assert after["foo"] != before["foo"]
    assert after["bar"] == before["bar"]
    assert after["deployed-environment"] == before["deployed-environment"]
    assert registry.get(PACKAGE_TYPE, "deployed-environment@0.0.0") is not None
