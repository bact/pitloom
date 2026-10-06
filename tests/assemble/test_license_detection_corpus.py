# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Licence detection on real licence files: each one ``licenseid`` alone
gets wrong or misses (a near-variant ranked first, a licence behind a
copyright notice), with and without the licence the package states.

See also: ``tests/fixtures/license-texts/README.md`` (where each file comes
from), :mod:`tests.assemble.test_license_detection` (the rules, mocked).
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from pitloom._embed_build_sbom import _add_concluded_license
from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import _family, detect_license_from_text
from pitloom.extract.project.sdist import read_sdist
from tests.fixtures.real_world import REAL_WORLD_ROOT, load_expected

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "license-texts"
_EXPECTED = json.loads((_CORPUS / "expected.json").read_text(encoding="utf-8"))

pytestmark = pytest.mark.usefixtures("licenseid_db_path")


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_a_real_licence_file_gives_its_licence_or_none(name: str) -> None:
    """Stated, the package's own licence; unstated, that licence (or its
    ``-only``/``-or-later`` sibling) or no detection (a near-tie), never
    another licence."""
    case = _EXPECTED[name]
    text = (_CORPUS / name).read_bytes().decode("utf-8")
    assert detect_license_from_text(text, stated=case["license"]) == case["stated"]
    assert detect_license_from_text(text) == case["unstated"]
    assert case["stated"] == case["license"]
    assert case["unstated"] is None or _family(case["unstated"]) == _family(
        case["license"]
    )


@pytest.mark.parametrize(
    "fixture", ["setuptools/pyyaml-6.0.3", "setuptools/requests-2.34.2"]
)
def test_an_sdist_concludes_its_own_licence(fixture: str) -> None:
    """PyYAML's MIT ``LICENSE`` starts with two notice lines (``licenseid``
    gives ``Xnet``); requests' verbatim Apache 2.0 scores just under
    ``Pixar``. Both conclude the licence the project states."""
    project = REAL_WORLD_ROOT / fixture
    expected = load_expected(project)
    metadata = read_sdist(project / expected["sdist_filename"], read_config=False)
    assert metadata.metadata.license_concluded == expected["license"]


@pytest.mark.parametrize(
    ("name", "stated", "expected"),
    [
        ("pylint-4.1.1-LICENSE", "GPL-2.0+", "GPL-2.0-or-later"),
        ("astroid-4.3.2-LICENSE", "LGPL-2.1+", "LGPL-2.1-or-later"),
    ],
)
def test_a_stated_deprecated_id_concludes_its_successor(
    name: str, stated: str, expected: str
) -> None:
    """Not the ``-only`` the text alone ranks first: that would conflict
    with the declared licence."""
    text = (_CORPUS / name).read_bytes().decode("utf-8")
    assert detect_license_from_text(text, stated=stated) == expected


@pytest.mark.parametrize(
    ("name", "stated"),
    [
        ("RapidFuzz-3.14.5-LICENSE", "JSON"),
        ("RapidFuzz-3.14.5-LICENSE", "Xnet"),
        ("RapidFuzz-3.14.5-LICENSE", "FSL-1.1-MIT"),
        ("pydantic-2.13.5-LICENSE", "JSON"),
    ],
)
def test_a_stated_near_variant_does_not_beat_a_verbatim_text(
    name: str, stated: str
) -> None:
    """A verbatim MIT text scores 1, the cap, and a near-variant within
    0.01 of it: the declared near-variant fits measurably worse, so the
    concluded licence stays MIT and the mismatch stays visible."""
    text = (_CORPUS / name).read_bytes().decode("utf-8")
    assert detect_license_from_text(text, stated=stated) == "MIT"


def test_embed_wheel_concludes_the_stated_licence(tmp_path: Path) -> None:
    """``embed-wheel --project-dir`` passes the wheel's declared licence:
    requests' verbatim Apache 2.0 concludes ``Apache-2.0``, not ``Pixar``."""
    project = REAL_WORLD_ROOT / "setuptools" / "requests-2.34.2"
    with tarfile.open(project / load_expected(project)["sdist_filename"]) as tar:
        member = tar.extractfile("requests-2.34.2/LICENSE")
        assert member is not None
        (tmp_path / "LICENSE").write_bytes(member.read())
    metadata = ProjectMetadata(name="requests", version="2.34.2")
    metadata.license_name = "Apache-2.0"
    _add_concluded_license(metadata, tmp_path)
    assert metadata.license_concluded == "Apache-2.0"
