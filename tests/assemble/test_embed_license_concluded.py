# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Concluded licence in an embed-wheel SBOM: wheel ``METADATA`` carries only
the declared licence, so the project directory supplies the concluded one.

See also: test_embed_core.py (the embed API end to end).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.embed import embed_wheel_sbom
from pitloom.extract import _license

from .conftest import _make_dummy_wheel

_NAME = "demo_pkg"


def _root_licenses(sbom_json: str, relationship_type: str) -> list[str]:
    """Licence values the SBOM's root package has for *relationship_type*."""
    graph: list[dict[str, Any]] = json.loads(sbom_json)["@graph"]
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    (sbom,) = [e for e in graph if e["type"] == "software_Sbom"]
    (root,) = sbom["rootElement"]
    return sorted(
        by_id[target].get("simplelicensing_licenseExpression")
        or by_id[target]["simplelicensing_licenseText"]
        for rel in graph
        if rel["type"] == "Relationship"
        and rel["from"] == root
        and rel["relationshipType"] == relationship_type
        for target in rel["to"]
    )


def _project(
    directory: Path, codemeta_license: str | None, license_text: str | None = None
) -> Path:
    directory.mkdir()
    (directory / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\n"
        f'name = "{_NAME}"\n'
        'version = "1.0.0"\n'
        'license = "Apache-2.0"\n',
        encoding="utf-8",
    )
    codemeta: dict[str, str] = {"name": _NAME}
    if codemeta_license is not None:
        codemeta["license"] = codemeta_license
    (directory / "codemeta.json").write_text(json.dumps(codemeta), encoding="utf-8")
    if license_text is not None:
        (directory / "LICENSE").write_text(license_text, encoding="utf-8")
    (directory / _NAME).mkdir()
    (directory / _NAME / "__init__.py").write_text("", encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("codemeta_license", "expected"),
    [
        ("https://spdx.org/licenses/Apache-2.0", ["Apache-2.0"]),
        # A second opinion that disagrees is still reported, not the
        # declared value echoed back.
        ("https://spdx.org/licenses/MIT", ["MIT"]),
    ],
)
def test_embed_concludes_license_from_project_dir(
    tmp_path: Path, codemeta_license: str, expected: list[str]
) -> None:
    project = _project(tmp_path / "proj", codemeta_license)
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(wheel, project_dir=project)

    assert _root_licenses(sbom_json, "hasDeclaredLicense") == ["Apache-2.0"]
    assert _root_licenses(sbom_json, "hasConcludedLicense") == expected


def test_embed_concluded_license_matches_project_sbom(tmp_path: Path) -> None:
    """Drift guard: embed-wheel and ``loom project`` conclude the same licence."""
    project = _project(tmp_path / "proj", "https://spdx.org/licenses/Apache-2.0")
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    _, _, embed_json, _, _ = embed_wheel_sbom(wheel, project_dir=project)
    project_json = generate_project_sbom(project, offline=True)

    concluded = _root_licenses(embed_json, "hasConcludedLicense")
    assert concluded == ["Apache-2.0"]
    assert concluded == _root_licenses(project_json, "hasConcludedLicense")


def test_embed_no_project_license_source_concludes_nothing(tmp_path: Path) -> None:
    """No licence source in the project: absent, not an error."""
    project = _project(tmp_path / "proj", None)
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(wheel, project_dir=project)

    assert _root_licenses(sbom_json, "hasDeclaredLicense") == ["Apache-2.0"]
    assert not _root_licenses(sbom_json, "hasConcludedLicense")


def test_embed_undeclared_wheel_license_gets_no_second_opinion(
    tmp_path: Path,
) -> None:
    """Same gate as ``loom project``: no declared licence, no G2 candidate."""
    project = _project(tmp_path / "proj", "https://spdx.org/licenses/MIT")
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME)

    _, _, sbom_json, _, _ = embed_wheel_sbom(wheel, project_dir=project)

    assert not _root_licenses(sbom_json, "hasConcludedLicense")


def test_embed_standalone_concludes_nothing(tmp_path: Path) -> None:
    """No project directory: the wheel alone has no second opinion."""
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(wheel)

    assert _root_licenses(sbom_json, "hasDeclaredLicense") == ["Apache-2.0"]
    assert not _root_licenses(sbom_json, "hasConcludedLicense")


def test_embed_explicit_config_still_concludes_license(tmp_path: Path) -> None:
    """An explicit config skips the project read; the resolver fills in."""
    project = _project(tmp_path / "proj", "https://spdx.org/licenses/MIT")
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    _, _, sbom_json, _, _ = embed_wheel_sbom(
        wheel, project_dir=project, pitloom_config=PitloomConfig()
    )

    assert _root_licenses(sbom_json, "hasConcludedLicense") == ["MIT"]


# pylint: disable-next=too-few-public-methods
class _EmptyMatcher:
    """A licenseid matcher over an empty database."""

    def match(self, *_args: object, **_kwargs: object) -> list[object]:
        return []


@pytest.fixture(name="fresh_empty_db_warning")
def fresh_empty_db_warning_fixture() -> Iterator[None]:
    """Reset the process-wide warn-once state around the test."""
    # pylint: disable-next=protected-access
    _license._warn_empty_database.cache_clear()
    yield
    # pylint: disable-next=protected-access
    _license._warn_empty_database.cache_clear()


@pytest.mark.usefixtures("fresh_empty_db_warning")
@pytest.mark.parametrize("explicit_config", [False, True])
def test_embed_empty_license_db_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    explicit_config: bool,
) -> None:
    """Text detection on an empty database warns once, though the project
    is read more than once, and the concluded licence is then absent -- the
    release gate's failure mode."""
    monkeypatch.setattr(_license, "_get_matcher", _EmptyMatcher)
    project = _project(tmp_path / "proj", None, license_text="Apache License\n" * 20)
    wheel = _make_dummy_wheel(tmp_path / "dist", _NAME, license_expression="Apache-2.0")

    with caplog.at_level(logging.WARNING):
        _, _, sbom_json, _, _ = embed_wheel_sbom(
            wheel,
            project_dir=project,
            pitloom_config=PitloomConfig() if explicit_config else None,
        )

    warnings = [r for r in caplog.records if "database appears empty" in r.message]
    assert len(warnings) == 1
    assert not _root_licenses(sbom_json, "hasConcludedLicense")
