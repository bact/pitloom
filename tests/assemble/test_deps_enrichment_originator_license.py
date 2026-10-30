# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency originator/license resolution and the PyPI
JSON API extraction helpers used by ``pitloom.assemble.spdx3.deps``.

See also: test_deps_enrichment_names_versions.py,
test_deps_enrichment_pypi_fallback.py, test_deps_enrichment_prefetch.py --
the sibling modules for the rest of dependency enrichment.

Covers a multi-address ``Maintainer-email`` field (a naive parser drops it
entirely) and ``License-File`` matching, where a same-named file outside
``.dist-info`` must not be misattributed.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3 import deps_originator
from pitloom.assemble.spdx3.deps import _enrich_from_installed
from pitloom.assemble.spdx3.deps_originator import (
    _find_license_copyright,
    _resolve_author_or_maintainer,
    _resolve_remote_authors_file,
)
from pitloom.assemble.spdx3.deps_pypi import (
    _extract_pypi_license,
    _extract_pypi_originator,
    _extract_release_hash,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES
from tests._symlink import CAN_SYMLINK, case_sensitive

from .conftest import _FakeMetadata, _make_ci

_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="cannot create a symlink")

# ---------------------------------------------------------------------------
# _resolve_author_or_maintainer -- single address, Maintainer fallback, multi-address
# ---------------------------------------------------------------------------


def test_resolve_author_or_maintainer_from_author_email() -> None:
    meta = _FakeMetadata({"Author-email": "Trail of Bits <opensource@trailofbits.com>"})
    assert _resolve_author_or_maintainer(meta, "p") == [
        ("Trail of Bits", "opensource@trailofbits.com")
    ]


def test_resolve_author_or_maintainer_falls_back_to_maintainer() -> None:
    meta = _FakeMetadata(
        {"Maintainer-email": "Taneli Hukkinen <hukkin@users.noreply.github.com>"}
    )
    assert _resolve_author_or_maintainer(meta, "p") == [
        (
            "Taneli Hukkinen",
            "hukkin@users.noreply.github.com",
        )
    ]


def test_resolve_author_or_maintainer_handles_multiple_maintainer_addresses() -> None:
    """A comma-separated multi-maintainer ``Maintainer-email`` (common in
    PyPI metadata) yields a supplier: ``email.utils.getaddresses`` parses the
    list (``parseaddr`` expects one address and returns ``('', '')``); only
    the first entry is used.
    """
    meta = _FakeMetadata(
        {
            "Maintainer-email": (
                "Bernát Gábor <gaborjbernat@gmail.com>, "
                "Kemal Zebari <kemalzebra@gmail.com>, "
                "Vineet Naik <naikvin@gmail.com>"
            )
        }
    )
    assert _resolve_author_or_maintainer(meta, "p") == [
        ("Bernát Gábor", "gaborjbernat@gmail.com"),
        ("Kemal Zebari", "kemalzebra@gmail.com"),
        ("Vineet Naik", "naikvin@gmail.com"),
    ]


def test_resolve_author_or_maintainer_plain_name_no_email() -> None:
    meta = _FakeMetadata({"Author": "Some Org"})
    assert _resolve_author_or_maintainer(meta, "p") == [("Some Org", None)]


def test_resolve_author_or_maintainer_absent_returns_none() -> None:
    assert not _resolve_author_or_maintainer(_FakeMetadata({}), "p")


def test_enrich_from_installed_sets_originated_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps_mod,
        "get_pkg_metadata",
        lambda name: _FakeMetadata(
            {"Author-email": "Taneli Hukkinen <hukkin@users.noreply.github.com>"}
        ),
    )

    doc_uuid = compute_doc_uuid("supptest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="supptest", doc_uuid=doc_uuid),
        name="tomli",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "2.4.1"
    exporter.add_package(dep_package)

    _enrich_from_installed("tomli", dep_package, ci, "supptest", doc_uuid, exporter)

    assert len(dep_package.originatedBy) > 0
    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 1
    assert agents[0].name == "Taneli Hukkinen"
    assert dep_package.originatedBy == [require_spdx_id(agents[0])]


def test_enrich_from_installed_dedupes_shared_supplier_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two dependencies with the same author must share one Agent element,
    not mint a duplicate for each."""
    monkeypatch.setattr(
        deps_mod,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author-email": "Same Author <same@example.com>"}),
    )

    doc_uuid = compute_doc_uuid("deduptest", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    for dep_name in ("pkg-a", "pkg-b"):
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name="deduptest", doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=ci,
        )
        dep_package.software_packageVersion = "1.0.0"
        exporter.add_package(dep_package)
        _enrich_from_installed(
            dep_name, dep_package, ci, "deduptest", doc_uuid, exporter
        )

    agents = [o for o in exporter.object_set.objects if isinstance(o, spdx3.Person)]
    assert len(agents) == 1


# ---------------------------------------------------------------------------
# _find_license_copyright -- License-File under .dist-info, every notice
# ---------------------------------------------------------------------------


class _FakePackagePath:
    """Minimal stand-in for ``importlib.metadata.PackagePath``: *path* in
    the installed tree, its content written under *root*."""

    def __init__(self, root: Path, path: str, content: str | None):
        self._path = path
        self._file = root / path
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if content is None:  # a directory: present, but no file to read
            self._file.mkdir()
        else:
            self._file.write_bytes(content.encode("utf-8"))

    @property
    def name(self) -> str:
        return self._path.rsplit("/", maxsplit=1)[-1]

    def __str__(self) -> str:
        return self._path

    def locate(self) -> Path:
        return self._file


# pylint: disable-next=too-few-public-methods
class _FakeDistribution:
    def __init__(self, root: Path, files: list[_FakePackagePath]):
        self._root = root
        self.files = files

    def locate_file(self, path: str) -> Path:
        return self._root / path


_LIC = "mypkg-1.0.dist-info/licenses/"
_OVER_CAP = "Copyright (c) 2026 Big\n" + "x" * LICENSE_FILE_MAX_BYTES


@pytest.mark.parametrize(
    ("files", "license_files", "expected"),
    [
        # A same-named file outside .dist-info (vendored), listed first so a
        # basename-only match would pick it, is not the dependency's.
        (
            [
                ("mypkg/vendor/otherlib/LICENSE", "Copyright (c) 2015 Vendored\n"),
                (f"{_LIC}LICENSE", "Copyright (c) 2026 Real Author\n"),
            ],
            ["LICENSE"],
            "Copyright (c) 2026 Real Author",
        ),
        (
            [("mypkg-1.0.dist-info/LICENSE.txt", "Copyright (c) 2026 Root\n")],
            ["LICENSE.txt"],
            "Copyright (c) 2026 Root",
        ),
        # Every notice of every License-File in order, a repeat left out,
        # one past the first 500 characters too.
        (
            [
                (
                    f"{_LIC}LICENSE",
                    "Copyright (c) 2026 A\n" + "x\n" * 300 + "(C) 2027 B\n",
                ),
                (f"{_LIC}NOTICE", "Copyright (c) 2026 A\nCopyright 2028 C\n"),
            ],
            ["LICENSE", "NOTICE"],
            "Copyright (c) 2026 A\n(C) 2027 B\nCopyright 2028 C",
        ),
        ([(f"{_LIC}LICENSE", "No notice at all.\n")], ["LICENSE"], None),
        ([(f"{_LIC}LICENSE", _OVER_CAP)], ["LICENSE"], None),
        ([(f"{_LIC}LICENSE", None)], ["LICENSE"], None),
    ],
    ids=["vendored", "dist-info-root", "several", "none", "over-cap", "unreadable"],
)
# pylint: disable-next=too-many-arguments
def test_find_license_copyright(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    files: list[tuple[str, str | None]],
    license_files: list[str],
    expected: str | None,
) -> None:
    fake_dist = _FakeDistribution(
        tmp_path, [_FakePackagePath(tmp_path, path, text) for path, text in files]
    )
    monkeypatch.setattr(deps_originator, "get_pkg_distribution", lambda name: fake_dist)

    meta = _FakeMetadata({}, license_files=license_files)
    with caplog.at_level(logging.WARNING):
        assert _find_license_copyright("mypkg", meta) == expected
    failed = [(p, text) for p, text in files if text is None or text == _OVER_CAP]
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == len(failed)
    for message, (path, _) in zip(messages, failed, strict=True):
        # Unreadable or over the cap: named by its RECORD entry, no
        # directory of this machine.
        assert message.startswith(f"FILE={path}: ")
        assert str(tmp_path) not in message


_SECRET = "Copyright (c) 2026 Secret\n"


@pytest.mark.parametrize(
    ("entry", "expected", "warned"),
    [
        ("mypkg-1.0.dist-info/../../secret/LICENSE", None, True),
        ("{secret}", None, False),
        pytest.param("mypkg-1.0.dist-info/LICENSE", None, True, marks=_SYMLINK),
        ("mypkg-1.0.dist-info/licenses/LICENSE", "Copyright (c) 2026 Real", False),
        ("MYPKG-1.0.dist-info/licenses/LICENSE", "Copyright (c) 2026 Real", False),
    ],
    ids=["dotdot", "absolute", "symlink", "inside", "case-insensitive"],
)
# pylint: disable-next=too-many-arguments
def test_find_license_copyright_record_entry_confined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    entry: str,
    expected: str | None,
    warned: bool,
) -> None:
    """A ``RECORD`` entry is read only inside the ``.dist-info`` it names,
    as the installed file system resolves it: ``..``, an absolute path or a
    symlink out is never read; a case-insensitive spelling still is."""
    if entry.startswith("MYPKG") and case_sensitive(tmp_path):
        pytest.skip("needs a case-insensitive file system")
    site, secret = tmp_path / "site", tmp_path / "secret" / "LICENSE"
    dist_info = site / "mypkg-1.0.dist-info"
    (dist_info / "licenses").mkdir(parents=True)
    secret.parent.mkdir()
    secret.write_text(_SECRET, encoding="utf-8")
    (dist_info / "licenses" / "LICENSE").write_text(
        "Copyright (c) 2026 Real\n", encoding="utf-8"
    )
    if entry == "mypkg-1.0.dist-info/LICENSE":
        (dist_info / "LICENSE").symlink_to(secret)
    record = entry.format(secret=secret.as_posix())
    (dist_info / "RECORD").write_text(f"{record},,\n", encoding="utf-8")
    dist = PathDistribution(dist_info)
    monkeypatch.setattr(deps_originator, "get_pkg_distribution", lambda name: dist)

    meta = _FakeMetadata({}, license_files=["LICENSE"])
    with caplog.at_level(logging.WARNING):
        assert _find_license_copyright("mypkg", meta) == expected
    messages = [r.getMessage() for r in caplog.records]
    assert messages == (
        [
            f"FILE={record}: could not read for license files; "
            "outside the project directory"
        ]
        if warned
        else []
    )


# ---------------------------------------------------------------------------
# PyPI JSON API extraction helpers (pure functions, no network)
# ---------------------------------------------------------------------------


def test_extract_pypi_originator_from_author() -> None:
    info = {"author": "Trail of Bits", "author_email": "opensource@trailofbits.com"}
    assert _extract_pypi_originator(info, "p") == [
        ("Trail of Bits", "opensource@trailofbits.com")
    ]


def test_extract_pypi_originator_falls_back_to_maintainer() -> None:
    info = {
        "maintainer": "Taneli Hukkinen",
        "maintainer_email": "hukkin@users.noreply.github.com",
    }
    assert _extract_pypi_originator(info, "p") == [
        ("Taneli Hukkinen", "hukkin@users.noreply.github.com")
    ]


def test_extract_pypi_originator_absent_returns_none() -> None:
    assert not _extract_pypi_originator({}, "p")


_PYPI = "Source: PyPI JSON API | Package: p"
_PYPI_CLASSIFIER = f"{_PYPI} | Field: Classifier"


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        pytest.param(
            {"license_expression": "MIT", "license": "some legacy free text"},
            ("MIT", _PYPI),
            id="expression-first",
        ),
        pytest.param({"license": "Apache-2.0"}, ("Apache-2.0", _PYPI), id="legacy"),
        # A whole LICENSE file pasted into the free-text field is no licence id.
        pytest.param({"license": "A" * 500}, (None, _PYPI), id="legacy-too-long"),
        # License-Expression has no length cap: a long one is still recorded.
        pytest.param(
            {"license_expression": "A" * 201}, ("A" * 201, _PYPI), id="long-expression"
        ),
        pytest.param(
            {
                "classifiers": [
                    "Programming Language :: Python :: 3",
                    "License :: OSI Approved :: MIT License",
                ]
            },
            ("MIT License", _PYPI_CLASSIFIER),
            id="classifier",
        ),
        pytest.param({}, (None, _PYPI), id="absent"),
    ],
)
def test_extract_pypi_license(
    info: dict[str, Any], expected: tuple[str | None, str]
) -> None:
    assert _extract_pypi_license(info, _PYPI) == expected


def test_extract_release_hash_prefers_wheel() -> None:
    sdist_hash = "a" * 64
    wheel_hash = "b" * 64
    release_info = {
        "urls": [
            {"packagetype": "sdist", "digests": {"sha256": sdist_hash}},
            {"packagetype": "bdist_wheel", "digests": {"sha256": wheel_hash}},
        ]
    }
    assert _extract_release_hash(release_info) == wheel_hash


def test_extract_release_hash_multiple_wheels_deterministic_by_filename() -> None:
    """A release with several platform wheels must always pick the same
    one (sorted by filename), regardless of the PyPI JSON API's own
    array order -- required for bit-for-bit-identical SBOMs across builds."""
    macos_hash = "a" * 64
    linux_hash = "b" * 64
    windows_hash = "c" * 64
    forward_order = {
        "urls": [
            {
                "packagetype": "bdist_wheel",
                "filename": "pkg-1.0-cp310-cp310-macosx_10_9_x86_64.whl",
                "digests": {"sha256": macos_hash},
            },
            {
                "packagetype": "bdist_wheel",
                "filename": "pkg-1.0-cp310-cp310-manylinux_2_17_x86_64.whl",
                "digests": {"sha256": linux_hash},
            },
            {
                "packagetype": "bdist_wheel",
                "filename": "pkg-1.0-cp310-cp310-win_amd64.whl",
                "digests": {"sha256": windows_hash},
            },
        ]
    }
    reversed_order = {"urls": list(reversed(forward_order["urls"]))}

    result_forward = _extract_release_hash(forward_order)
    result_reversed = _extract_release_hash(reversed_order)

    assert result_forward == result_reversed == macos_hash


def test_extract_release_hash_falls_back_to_sdist() -> None:
    sdist_hash = "a" * 64
    release_info = {
        "urls": [{"packagetype": "sdist", "digests": {"sha256": sdist_hash}}]
    }
    assert _extract_release_hash(release_info) == sdist_hash


def test_extract_release_hash_prefers_sdist_over_legacy_binary() -> None:
    """With no wheel present, sdist outranks a legacy binary format (e.g.
    bdist_egg) rather than sharing one "other" tier tie-broken by filename."""
    sdist_hash = "a" * 64
    egg_hash = "c" * 64
    release_info = {
        "urls": [
            # Filename sort would otherwise put the egg first.
            {"packagetype": "bdist_egg", "digests": {"sha256": egg_hash}},
            {"packagetype": "sdist", "digests": {"sha256": sdist_hash}},
        ]
    }
    assert _extract_release_hash(release_info) == sdist_hash


def test_extract_release_hash_falls_back_to_first_url() -> None:
    egg_hash = "c" * 64
    release_info = {
        "urls": [{"packagetype": "bdist_egg", "digests": {"sha256": egg_hash}}]
    }
    assert _extract_release_hash(release_info) == egg_hash


def test_extract_release_hash_no_urls_returns_none() -> None:
    assert _extract_release_hash({"urls": []}) is None
    assert _extract_release_hash({}) is None


def test_extract_release_hash_validates_hex_sha256() -> None:
    # Non-dict digests
    assert _extract_release_hash({"urls": [{"digests": "not-a-dict"}]}) is None
    assert _extract_release_hash({"urls": [{"digests": [1, 2, 3]}]}) is None
    assert _extract_release_hash({"urls": [{"digests": 123}]}) is None
    # Invalid length or characters
    assert (
        _extract_release_hash({"urls": [{"digests": {"sha256": "too-short"}}]}) is None
    )
    assert _extract_release_hash({"urls": [{"digests": {"sha256": "g" * 64}}]}) is None
    # Uppercase normalized to lowercase
    upper_hash = ("A" * 32) + ("B" * 32)
    assert (
        _extract_release_hash({"urls": [{"digests": {"sha256": upper_hash}}]})
        == upper_hash.lower()
    )
    # No "sha256" key at all, and a non-string "sha256" value
    assert _extract_release_hash({"urls": [{"digests": {"md5": "x"}}]}) is None
    assert _extract_release_hash({"urls": [{"digests": {"sha256": 12345}}]}) is None


# ---------------------------------------------------------------------------
# _resolve_remote_authors_file -- disallowed-scheme defensive raise
# ---------------------------------------------------------------------------


def test_resolve_remote_authors_file_disallowed_scheme_falls_back() -> None:
    """A gitlab.com repo URL with a non-http(s) scheme produces a
    ``raw_url`` that fails the scheme allowlist -- the defensive
    ``ValueError`` raise inside the fetch's ``try`` block is caught by the
    same ``except`` clause as a genuine network failure, so no real
    network I/O happens."""
    loc, ctype, text = _resolve_remote_authors_file(
        "ftp://gitlab.com/group/disallowed-scheme-project",
        "AUTHORS",
        False,
        "auto",
    )
    assert loc == "ftp://gitlab.com/group/disallowed-scheme-project/-/blob/HEAD/AUTHORS"
    assert text is None
    # No real network call is made -- guess_content_type falls back to
    # extension-based sniffing, which returns None for an extensionless
    # filename like "AUTHORS".
    assert ctype is None
