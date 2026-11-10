# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The acquisition record of a PyPI URL target's SBOM
(:mod:`pitloom.assemble.spdx3.provenance_acquisition`): one provenance
record on the main package, with the file's URL, the SHA-256 measured and
the one declared, the release and its status, and a wheel's tags and pick.

The JSON API and the file host are a local server (``loopback``).

See also: tests/assemble/test_generate_pypi.py (the surfaces),
tests/assemble/_pypi_dists.py (the builders).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom.assemble import generate_pypi_sbom
from pitloom.assemble.spdx3.provenance_acquisition import acquisition_provenance
from pitloom.core.acquisition import Acquisition
from pitloom.core.provenance import ProvenanceConfig, parse_provenance_value
from pitloom.extract.remote.pypi import SDIST
from tests._fake_pypi_server import Dist, FakePypi, sha256_of
from tests.assemble._pypi_dists import (
    CP_WHEEL_NAME,
    CREATION,
    NAME,
    PAGE,
    RECORD_FIELD,
    SDIST_NAME,
    URL,
    VERSION,
    WHEEL_NAME,
    fake_pypi,
    graph,
    publish_demo,
    record_fields,
    sdist_bytes,
    the_record,
    wheel_bytes,
)

_JSON_API = "PyPI JSON API"


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        yield fake


def _digests(filename: str, data: bytes) -> dict[str, dict[str, str]]:
    digest = sha256_of(data)
    return {
        "sha256": {
            "source": "downloaded file",
            "file": filename,
            "value": digest,
            "evidence": "measured_read",
        },
        "sha256_declared": {
            "source": _JSON_API,
            "file": filename,
            "value": digest,
            "evidence": "declared",
        },
    }


def _located(fake: FakePypi, filename: str) -> dict[str, dict[str, str]]:
    return {
        "project_url": {"source": "PyPI", "value": URL},
        "download_location": {
            "source": "PyPI",
            "file": filename,
            "value": fake.url(f"/files/{filename}"),
        },
    }


@pytest.mark.loopback
def test_a_pinned_wheels_record(fake: FakePypi) -> None:
    publish_demo(fake)
    fields = the_record(generate_pypi_sbom(URL, creation_metadata=CREATION))
    assert fields == {
        **_located(fake, WHEEL_NAME),
        **_digests(WHEEL_NAME, wheel_bytes()),
        "release_version": {"source": _JSON_API, "value": VERSION},
        "wheel_tags": {
            "source": "wheel filename",
            "file": WHEEL_NAME,
            "value": "py3-none-any",
        },
        "compatible_wheels_skipped": {
            "source": _JSON_API,
            "method": "running-environment",
            "value": "0",
        },
    }


@pytest.mark.loopback
def test_a_pinned_sdists_record(fake: FakePypi) -> None:
    """An sdist is no choice between wheels: no tags, no skipped count."""
    publish_demo(fake)
    sbom = generate_pypi_sbom(URL, kind=SDIST, creation_metadata=CREATION)
    fields = the_record(sbom)
    assert fields == {
        **_located(fake, SDIST_NAME),
        **_digests(SDIST_NAME, sdist_bytes()),
        "release_version": {"source": _JSON_API, "value": VERSION},
    }


@pytest.mark.loopback
def test_a_url_spelling_of_the_release_is_kept(fake: FakePypi) -> None:
    """The URL names ``1.0``, PyPI lists ``1.0.0``: the version is PyPI's,
    the URL's spelling kept beside it; the page is the listed release's."""
    publish_demo(fake)
    short = f"{PAGE}{NAME}/1.0/"
    assert short != URL  # the spelling differs
    fields = the_record(generate_pypi_sbom(short, creation_metadata=CREATION))
    assert fields["release_version"] == {
        "source": _JSON_API,
        "value": VERSION,
        "normalized-from": "1.0",
    }
    assert fields["project_url"]["value"] == URL


@pytest.mark.loopback
def test_the_skipped_wheels_are_counted(fake: FakePypi) -> None:
    """Two wheels match the environment: the best-ranked is read, the other
    counted."""
    data = wheel_bytes()
    publish_demo(fake, {VERSION: [Dist(WHEEL_NAME, data), Dist(CP_WHEEL_NAME, data)]})
    fields = the_record(generate_pypi_sbom(URL, creation_metadata=CREATION))
    assert fields["wheel_tags"]["value"] == "cp313-cp313-linux_x86_64"
    assert fields["download_location"]["file"] == CP_WHEEL_NAME
    assert fields["compatible_wheels_skipped"]["value"] == "1"


#: A yank reason that would forge a segment and a line if written raw.
_HOSTILE = "broken | Evidence: not_measured | Reason: over-cap\nSource: x"


@pytest.mark.loopback
def test_an_unpinned_yanked_pre_release(fake: FakePypi) -> None:
    """No version in the URL and every release yanked: the record says the
    latest release was read, that it is a pre-release and yanked, and why,
    the reason unable to add a segment."""
    version = "2.0rc1"
    wheel = f"{NAME}-{version}-py3-none-any.whl"
    publish_demo(
        fake,
        {
            version: [
                Dist(
                    wheel,
                    wheel_bytes(version=version),
                    yanked=True,
                    reason=_HOSTILE,
                )
            ]
        },
    )
    sbom = generate_pypi_sbom(f"{PAGE}{NAME}/", creation_metadata=CREATION)
    fields = the_record(sbom)
    assert fields["release_version"] == {
        "source": _JSON_API,
        "method": "latest-release",
        "value": version,
    }
    assert fields["release_status"] == {
        "source": _JSON_API,
        "value": "prerelease, yanked",
        "note": _HOSTILE.replace("|", "/"),
    }
    assert fields["project_url"]["value"] == f"{PAGE}{NAME}/{version}/"


@pytest.mark.loopback
def test_a_pre_release_alone_has_no_note(fake: FakePypi) -> None:
    version = "2.0rc1"
    wheel = f"{NAME}-{version}-py3-none-any.whl"
    publish_demo(fake, {version: [Dist(wheel, wheel_bytes(version=version))]})
    fields = the_record(
        generate_pypi_sbom(f"{PAGE}{NAME}/{version}/", creation_metadata=CREATION)
    )
    assert fields["release_status"] == {"source": _JSON_API, "value": "prerelease"}
    assert fields["release_version"] == {"source": _JSON_API, "value": version}


@pytest.mark.loopback
@pytest.mark.parametrize(
    ("form", "annotations", "comments"),
    [("annotation", 1, 0), ("comment", 0, 1), ("both", 1, 1)],
)
def test_the_record_follows_the_provenance_format(
    fake: FakePypi, form: str, annotations: int, comments: int
) -> None:
    publish_demo(fake)
    sbom = generate_pypi_sbom(
        URL, creation_metadata=CREATION, provenance=ProvenanceConfig(format=form)
    )
    assert len(record_fields(sbom)) == annotations
    lines = [
        line
        for element in graph(sbom)
        for line in str(element.get("comment", "")).split("\n")
        if f"{RECORD_FIELD}: Source: {_JSON_API}" in line
    ]
    assert len(lines) == comments


@pytest.mark.loopback
def test_minimal_and_full_detail_keep_the_whole_record(fake: FakePypi) -> None:
    publish_demo(fake)
    records = [
        record_fields(
            generate_pypi_sbom(
                URL,
                creation_metadata=CREATION,
                provenance=ProvenanceConfig(detail=detail),
            )
        )
        for detail in ("minimal", "full")
    ]
    assert records[0] == records[1] and len(records[0][0]) == 7


def _acquisition(**changes: object) -> Acquisition:
    values: dict[str, object] = {
        "index": "PyPI",
        "project_url": URL,
        "file_url": "https://files.pythonhosted.org/x/demo-1.0.0.tar.gz",
        "filename": SDIST_NAME,
        "version": VERSION,
        "sha256": "a" * 64,
        "declared_sha256": "a" * 64,
        "declared_by": _JSON_API,
        **changes,
    }
    return Acquisition(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    [
        "filename",
        "file_url",
        "project_url",
        "version",
        "yanked_reason",
        "chosen_by",
        "requested_version",
    ],
)
def test_text_from_the_index_cannot_add_a_segment(field: str) -> None:
    """Every entry has the keys of a benign record, whatever the index sent."""
    base: dict[str, object] = {
        "status": ("yanked",),
        "compatible_skipped": 0,
        "yanked_reason": "r",
        "chosen_by": "c",
        "requested_version": "1.0",
    }
    benign = acquisition_provenance(_acquisition(**base))
    hostile = acquisition_provenance(_acquisition(**{**base, field: _HOSTILE}))
    assert set(benign) == set(hostile)
    for name, entry in hostile.items():
        assert set(parse_provenance_value(entry)) == set(
            parse_provenance_value(benign[name])
        ), name


def test_a_record_without_a_choice_says_none() -> None:
    """No skipped count without one, no method without a pick, and no
    status for a stable release."""
    record = acquisition_provenance(_acquisition())
    assert list(record) == [
        "project_url",
        "download_location",
        "sha256",
        "sha256_declared",
        "release_version",
    ]
    stray = acquisition_provenance(
        _acquisition(status=("prerelease",), yanked_reason="not yanked")
    )
    assert "note" not in parse_provenance_value(stray["release_status"])
    picked = acquisition_provenance(_acquisition(compatible_skipped=3))
    assert parse_provenance_value(picked["compatible_wheels_skipped"]) == {
        "source": _JSON_API,
        "value": "3",
    }
