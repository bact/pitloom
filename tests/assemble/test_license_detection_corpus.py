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
from pathlib import Path

import pytest

from pitloom.extract._license import detect_license_from_text
from pitloom.extract.project.sdist import read_sdist
from tests.fixtures.real_world import REAL_WORLD_ROOT, load_expected

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "license-texts"
_EXPECTED = json.loads((_CORPUS / "expected.json").read_text(encoding="utf-8"))

pytestmark = pytest.mark.usefixtures("licenseid_db_path")


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_a_real_licence_file_gives_its_licence_or_none(name: str) -> None:
    """Stated, the package's own licence; unstated, that licence or no
    detection (a near-tie), never another licence."""
    case = _EXPECTED[name]
    text = (_CORPUS / name).read_bytes().decode("utf-8")
    assert detect_license_from_text(text, stated=case["license"]) == case["stated"]
    assert detect_license_from_text(text) == case["unstated"]
    assert case["stated"] == case["license"]
    assert case["unstated"] in (None, case["license"])


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
