# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Licence detection on real licence files: each one LicenseID alone
gets wrong or misses (a near-variant ranked first, a licence behind a
copyright notice), with and without the licence the package states.

See also: ``tests/fixtures/license-texts/README.md`` (where each file comes
from), :mod:`tests.assemble.test_license_detection` (the rules, mocked).
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from unittest.mock import create_autospec

import pytest

from pitloom._embed_overlay import add_concluded_license
from pitloom.core.project import ProjectMetadata
from pitloom.extract._license import (
    apply_in_package_license_files,
    license_from_candidates,
)
from pitloom.extract._license_text_match import (
    _family,
    detect_license_from_text,
    read_license_text,
)
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.remote._hub_files import HubFiles
from pitloom.extract.remote.huggingface_fetch import _detect_license_from_hf_files
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
    ("value", "expected"),
    [
        ("MIT", "MIT"),
        ("MIT OR Apache-2.0", "Apache-2.0 OR MIT"),
        ("MIT/Apache-2.0", None),
        ("MIT, ISC", None),
        ("Apache-2.0 / MIT", None),
    ],
    ids=["one-id", "expression", "slash", "comma", "spaced-slash"],
)
def test_a_tag_value_is_read_whole_or_not_at_all(
    value: str, expected: str | None
) -> None:
    """``SPDX-License-Identifier: MIT/Apache-2.0`` is not an expression:
    it is not detected as its first id."""
    text = f"# {'x' * 100}\nSPDX-License-Identifier: {value}\n"
    assert detect_license_from_text(text) == expected


@pytest.mark.parametrize(
    "fixture", ["setuptools/pyyaml-6.0.3", "setuptools/requests-2.34.2"]
)
def test_an_sdist_concludes_its_own_licence(fixture: str) -> None:
    """PyYAML's MIT ``LICENSE`` starts with two notice lines (LicenseID
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
        # on top of the reading with the notice, a weaker one
        ("iniconfig-2.3.0-LICENSE", "FSL-1.1-MIT"),
        ("iniconfig-2.3.0-LICENSE", "FSL-1.1-MIT OR MIT"),
        ("pytest-9.1.1-LICENSE", "FSL-1.1-MIT"),
        ("attrs-26.1.0-LICENSE", "MIT-advertising"),
    ],
)
def test_a_stated_near_variant_does_not_beat_a_verbatim_text(
    name: str, stated: str
) -> None:
    """A verbatim MIT text scores 1, the cap, and a near-variant within
    0.01 of it: the declared near-variant fits measurably worse, so the
    concluded licence stays MIT and the mismatch stays visible. A
    near-variant on top of the weaker reading (with the notice) does not
    win either."""
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
    add_concluded_license(metadata, tmp_path)
    assert metadata.license_concluded == "Apache-2.0"


@pytest.mark.parametrize(
    ("name", "stated"),
    [
        # BSD-3-Clause, BSD-3-Clause-Open-MPI and a bundled library's GPL-3.0
        ("numpy-2.5.5-LICENSE", "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"),
        # typeshed's Apache-2.0, then the MIT text of some of its parts
        ("types-setuptools-84.2.0.20261122-LICENSE", "Apache-2.0"),
    ],
)
def test_a_file_of_several_licence_texts_gives_no_licence(
    name: str, stated: str
) -> None:
    """Its top match is one of its texts (Apache-2.0 for typeshed's), or
    LicenseID gives no match (numpy's, from 0.9.4), stated or not: no
    detection, said as several texts."""
    text = (_CORPUS / name).read_bytes().decode("utf-8")
    assert read_license_text(text) == (None, True)
    assert read_license_text(text, stated=stated) == (None, True)


#: Apache-2.0 then MIT, each matched; numpy's three texts, none matched.
_SEVERAL_FILES = (
    "types-setuptools-84.2.0.20261122-LICENSE",
    "numpy-2.5.5-LICENSE",
)
_SEVERAL_IDS = ("matched", "unmatched")
_MIT_FILE = "RapidFuzz-3.14.5-LICENSE"


@pytest.mark.parametrize("several", _SEVERAL_FILES, ids=_SEVERAL_IDS)
@pytest.mark.parametrize(
    ("first", "expected"),
    [
        # a later file names only one licence of the several: not read
        (True, None),
        (False, "MIT"),  # the first decides
    ],
    ids=["several-first", "several-second"],
)
def test_a_file_of_several_licence_texts_ends_the_search(
    several: str, first: bool, expected: str | None
) -> None:
    files = (several, _MIT_FILE) if first else (_MIT_FILE, several)
    candidates = [
        ((_CORPUS / name).read_bytes().decode("utf-8"), f"Source: {name}")
        for name in files
    ]
    found = license_from_candidates(candidates, stated="Apache-2.0")
    assert (found[0] if found else None) == expected


def test_a_stated_id_before_a_file_of_several_texts_still_wins() -> None:
    """``CITATION.cff`` and ``codemeta.json`` come before the licence files."""
    text = (_CORPUS / _SEVERAL_FILES[0]).read_bytes().decode("utf-8")
    found = license_from_candidates(
        [("Apache-2.0", "Source: codemeta.json"), (text, "Source: LICENSE")]
    )
    assert found == ("Apache-2.0", "Source: codemeta.json")


def _several_then_mit(several: str) -> dict[str, str]:
    """``LICENSE`` of several texts, then a ``COPYING`` of MIT alone."""
    return {"LICENSE": several, "COPYING": _MIT_FILE}


@pytest.mark.parametrize("several", _SEVERAL_FILES, ids=_SEVERAL_IDS)
@pytest.mark.parametrize("stated", ["Apache-2.0", None])
def test_a_project_concludes_no_licence_from_a_file_after_several_texts(
    several: str, stated: str | None
) -> None:
    """``COPYING`` alone would give ``MIT``: concluded beside a stated
    licence, else declared."""
    metadata = ProjectMetadata(name="p", version="1")
    metadata.license_name = stated
    members = {
        k: (_CORPUS / v).read_bytes() for k, v in _several_then_mit(several).items()
    }
    apply_in_package_license_files(metadata, members)
    assert (metadata.license_name, metadata.license_concluded) == (stated, None)
    assert not {"license", "license_concluded"} & set(metadata.provenance)


@pytest.mark.platform  # licence files written and read back
@pytest.mark.parametrize("several", _SEVERAL_FILES, ids=_SEVERAL_IDS)
def test_a_hub_repository_gives_no_licence_from_a_file_after_several_texts(
    tmp_path: Path, several: str
) -> None:
    files = _several_then_mit(several)
    for name, fixture in files.items():
        (tmp_path / name).write_bytes((_CORPUS / fixture).read_bytes())
    hub = create_autospec(HubFiles, instance=True)
    hub.asks_hub = True
    hub.read.side_effect = lambda _model, name, **_kw: tmp_path / name
    found = _detect_license_from_hf_files(hub, "o/m", license_files=list(files))
    assert found == (None, None)
    assert hub.read.call_count == 1
