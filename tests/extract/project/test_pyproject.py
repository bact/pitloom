# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for read_pyproject()'s [project]-focused parsing paths and its
private helpers (readme/author extraction, provenance building).

See also: test_pyproject_license.py for license-classifier-conflict
recovery and license-hint-resolution tests, split out to keep this file
under this repo's file-size soft limit; test_pyproject_dynamic.py for
PEP 621 ``dynamic`` field resolution
(:mod:`pitloom.extract.project.pyproject_dynamic`); test_poetry_pyproject.py
for the [tool.poetry] fallback/override behaviour; test_hatch_hook_metadata.py
for the Hatchling build-hook path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from pyproject_metadata import StandardMetadata

from pitloom.core._config_types import PitloomConfig
from pitloom.extract._license_text_match import LicenseTextReading
from pitloom.extract.project._poetry_fields import _FIELD_SHAPES
from pitloom.extract.project._pyproject_fields import (
    build_provenance,
    extract_authors,
    extract_readme,
)
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject import (
    _read_pyproject_fallback,
    _try_read_poetry,
    read_pyproject,
)
from pitloom.messages import code_of

# ---------------------------------------------------------------------------
# read_pyproject -- no [project] section, no [tool.poetry] fallback
# ---------------------------------------------------------------------------


def test_read_pyproject_no_project_no_poetry_detects_license_from_dir() -> None:
    """No ``[project]``/``[tool.poetry]``: falls through to an empty
    ``ProjectMetadata`` whose licence is detected independently from the
    project directory (line 85's ``license_prov`` truthy branch)."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.read_license_text",
            return_value=LicenseTextReading("MIT"),
        ):
            metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == ""
    assert metadata.license_name == "MIT"
    assert "license" in metadata.provenance


def test_read_pyproject_explicit_empty_requires_python_gets_provenance() -> None:
    """An explicit `requires-python = ""` (PEP 621's equivalent of Poetry's
    `python = "*"`) resolves to None but must still record provenance --
    merge_project_metadata() relies on that presence to treat the None as
    an authoritative "no constraint", not absent."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\nrequires-python = ""\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None
    assert metadata.provenance["requires_python"] == (
        "Source: pyproject.toml | Field: project.requires-python"
    )


def test_read_pyproject_explicit_empty_requires_python_survives_poetry_gap_fill() -> (
    None
):
    """The [project] table's explicit `requires-python = ""` wins over
    [tool.poetry]'s real constraint through the actual read_pyproject()
    merge, not only a synthetic unit-level scenario."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "pkg"\n'
            'version = "1.0.0"\n'
            'requires-python = ""\n'
            "\n"
            "[tool.poetry]\n"
            'name = "pkg"\n'
            'version = "1.0.0"\n'
            "\n"
            "[tool.poetry.dependencies]\n"
            'python = ">=3.8"\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None


def test_read_pyproject_no_requires_python_declared() -> None:
    """No `[project.requires-python]` key: resolves to None, and no
    provenance is recorded -- distinct from an explicit empty string."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.requires_python is None
    assert "requires_python" not in metadata.provenance


def test_read_pyproject_no_project_no_poetry_no_license_found() -> None:
    """No ``[project]``, no ``[tool.poetry]``, and nothing in the directory
    that looks like a license: ``license_prov`` stays falsy."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == ""
    assert metadata.license_name is None


# ---------------------------------------------------------------------------
# read_pyproject -- dynamic version present but unresolvable
# ---------------------------------------------------------------------------


def test_read_pyproject_fallback_records_name_provenance() -> None:
    """``_read_pyproject_fallback`` records ``prov["name"]`` when a non-empty
    *name* is supplied even though there is no usable ``[project]`` section
    (e.g. a caller reusing a name resolved from elsewhere)."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text("[build-system]\n")
        metadata, _config = _read_pyproject_fallback(
            {},
            pyproject_path,
            "mypkg",
            PitloomConfig(),
            include_locked_dependencies=True,
        )
    assert metadata.name == "mypkg"
    assert metadata.provenance["name"] == "Source: pyproject.toml | Field: project.name"


def test_read_pyproject_dynamic_version_unresolvable() -> None:
    """``dynamic = ["version"]`` but no Hatchling path/``__about__.py`` found:
    the dynamic-version block is skipped (line 96->107) and
    ``pyproject-metadata`` is left to raise (dynamic version) or the field
    is simply absent from the parsed metadata."""
    content = """
[project]
name = "no-resolvable-version"
dynamic = ["version"]
"""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(content)
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.name == "no-resolvable-version"
    assert metadata.version is None


# ---------------------------------------------------------------------------
# read_pyproject -- StandardMetadata.from_pyproject() failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ('project = "x"\n', "[project] is a string 'x', expected a table"),
        ("project = []\n", "[project] is an array, expected a table"),
        ("[project]\nname = 5\n", "project.name is an integer 5, expected a string"),
        ("[project]\nname = 0\n", "project.name is an integer 0, expected a string"),
        ("[project]\nname = []\n", "project.name is an array, expected a string"),
    ],
    ids=["table-is-str", "table-is-array", "name-int", "name-falsy-int", "name-array"],
)
def test_read_pyproject_project_of_the_wrong_type_is_a_coded_error(
    tmp_path: Path, toml: str, message: str
) -> None:
    """A ``[project]`` that is no table, or a ``name`` that is no string (a
    falsy one too: present is not absent), is refused as ``metadata-invalid``,
    not an ``AttributeError``."""
    path = tmp_path / "pyproject.toml"
    path.write_text(toml, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        read_pyproject(path)
    assert str(caught.value) == f"FILE={path}: {message}"
    assert code_of(caught.value) == "metadata-invalid"


@pytest.mark.parametrize("key", ["version", "requires-python"])
def test_read_pyproject_overlong_number_is_a_coded_error(
    tmp_path: Path, key: str
) -> None:
    """A number packaging cannot parse is refused like any invalid value."""
    value = "1." + "9" * 700 if key == "version" else ">=3." + "9" * 700
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "p"\n{key} = "{value}"\n', encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        read_pyproject(path)
    assert str(caught.value) == (
        f"FILE={path}: project.{key} has a number over 640 digits"
    )
    assert code_of(caught.value) == "metadata-invalid"


def test_read_pyproject_invalid_metadata_raises_value_error() -> None:
    """A ``[project]`` section that ``pyproject-metadata`` cannot parse (here:
    an invalid PEP 440 version string) surfaces as ``ValueError``, not the
    raw underlying exception."""
    content = """
[project]
name = "bad-version-pkg"
version = "not-a-valid-version!!"
"""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(content)
        with pytest.raises(ValueError, match=r"not valid \[project\] metadata"):
            read_pyproject(tmp_path / "pyproject.toml")


# ---------------------------------------------------------------------------
# build_provenance -- direct unit tests for branches unreachable/awkward
# to reach purely through read_pyproject()
# ---------------------------------------------------------------------------


def testbuild_provenance_no_version_source_no_version_field() -> None:
    """Neither a resolved dynamic-version source nor a declared
    ``project.version`` field: the ``version`` key is omitted entirely
    (line 185->188)."""
    prov = build_provenance({"name": "pkg"}, version_source=None)
    assert "version" not in prov


def testbuild_provenance_license_override_without_declared_field() -> None:
    """``license_prov_override`` is set but ``project.license`` was never
    declared: the override still lands in ``prov["license"]`` via the
    fallback branch at the end of the function (line 198)."""
    prov = build_provenance(
        {"name": "pkg"},
        version_source=None,
        license_prov_override="Source: LICENSE | Method: licenseid_detection",
    )
    assert prov["license"] == "Source: LICENSE | Method: licenseid_detection"


# ---------------------------------------------------------------------------
# extract_readme -- inline readme text (PEP 621 {text = ...} table)
# ---------------------------------------------------------------------------


def testextract_readme_inline_text() -> None:
    """A readme object exposing ``.text`` (no usable ``.file``) returns the
    inline text directly (lines 238-239)."""
    fake_readme = SimpleNamespace(file=None, text="Hello from inline readme.")
    std = SimpleNamespace(readme=fake_readme)
    result = extract_readme(cast(StandardMetadata, std), override=None)
    assert result == "Hello from inline readme."


def testextract_readme_no_file_no_text() -> None:
    """A readme object with neither a usable ``.file`` nor ``.text``
    resolves to ``None``."""
    fake_readme = SimpleNamespace(file=None, text=None)
    std = SimpleNamespace(readme=fake_readme)
    result = extract_readme(cast(StandardMetadata, std), override=None)
    assert result is None


# ---------------------------------------------------------------------------
# extract_authors -- entries that resolve to nothing get skipped
# ---------------------------------------------------------------------------


def testextract_authors_skips_empty_entries() -> None:
    """An ``(name, email)`` pair that is entirely empty is dropped rather
    than appended as an empty dict (line 318->314)."""
    std = SimpleNamespace(authors=[("", ""), ("Bob", ""), ("", "carol@example.com")])
    raw = [{"name": "x"}, {"name": "Bob"}, {"email": "carol@example.com"}]
    result = extract_authors(cast(StandardMetadata, std), {"authors": raw})
    assert result == [{"name": "Bob"}, {"email": "carol@example.com"}]


# ---------------------------------------------------------------------------
# _try_read_poetry -- extract_poetry_metadata failure paths
# ---------------------------------------------------------------------------


def test_try_read_poetry_value_error_returns_none() -> None:
    """``extract_poetry_metadata`` raising ``ValueError`` is swallowed and
    reported as "no poetry metadata available" (lines 391-392)."""
    data = {"tool": {"poetry": {"name": "pkg"}}}
    with tempfile.TemporaryDirectory() as d:
        with patch(
            "pitloom.extract.project.pyproject.extract_poetry_metadata",
            side_effect=ValueError("boom"),
        ):
            result = _try_read_poetry(data, Path(d))
    assert result is None


_WRONG_TYPES: list[object] = [0, "", [], [1], {}, {"k": 1}, "x", True, {"a": 1}]


def test_poetry_extraction_raises_only_coded_value_errors() -> None:
    """``_try_read_poetry`` catches ``ValueError`` only, and says it through
    ``relay_coded_warning``, which refuses an uncoded one: every
    ``[tool.poetry]`` key given a value of every wrong type either reads or
    raises a coded error -- no ``KeyError``, no bare ``ValueError``."""
    keys = [*_FIELD_SHAPES, "group", "packages", "include", "scripts"]
    with tempfile.TemporaryDirectory() as d:
        for key in keys:
            for value in _WRONG_TYPES:
                poetry = {"name": "p", "dependencies": {"a": "*"}, key: value}
                try:
                    extract_poetry_metadata({"tool": {"poetry": poetry}}, Path(d))
                except ValueError as exc:
                    assert code_of(exc) is not None, (key, value)


def test_read_pyproject_records_readme_provenance() -> None:
    """Declared readme in [project] must record its field provenance."""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\nreadme = "README.md"\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
    expected_prov = "Source: pyproject.toml | Field: project.readme"
    assert metadata.provenance.get("readme") == expected_prov


def test_pyproject_author_with_comma_is_one_author(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``[project].authors`` is structured: ``pyproject-metadata`` keeps a
    comma inside a name, and Pitloom never splits it (no warning)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1"\n'
        'authors = [{name = "Doe, Jane", email = "j@example.com"},'
        ' {name = "Roe and Rex"}]\n',
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        metadata, _ = read_pyproject(tmp_path / "pyproject.toml")
    assert metadata.authors == [
        {"name": "Doe, Jane", "email": "j@example.com"},
        {"name": "Roe and Rex"},
    ]
    assert caplog.messages == []


@pytest.mark.parametrize(
    ("readme", "read", "field"),
    [('"R.md"', True, None), ('"s/../R.md"', True, None),
     ('"../out.md"', False, "project.readme"), ('"{out}"', False, "project.readme"),
     ('"link.md"', False, "project.readme"),
     ('{{file = "R.md", content-type = "text/plain"}}', True, None),
     ('{{file = "../out.md", content-type = "text/plain"}}', False,
      "project.readme.file"),
     ('{{file = "../out.md", content-type = ""}}', False, None)],
    ids=["inside", "dotdot-inside", "dotdot-out", "absolute", "symlink-out",
         "table-inside", "table-out", "table-no-type"],
)  # fmt: skip
def test_a_readme_outside_the_project_is_not_read(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    readme: str,
    read: bool,
    field: str | None,
) -> None:
    """``pyproject-metadata`` reads ``project.readme`` wherever it points; the
    field is dropped with one ``WARNING:``, worded as for a licence file; a
    shape it reads no file for is left to it."""
    project = tmp_path / "p"
    (project / "s").mkdir(parents=True)
    (project / "R.md").write_text("Inside", encoding="utf-8")
    (tmp_path / "out.md").write_text("Leaked", encoding="utf-8")
    if "link" in readme:
        try:
            (project / "link.md").symlink_to(tmp_path / "out.md")
        except OSError:  # Windows without the symlink privilege
            pytest.skip("cannot create a symlink here")
    readme = readme.format(out=(tmp_path / "out.md").as_posix())
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "pkg"\nversion = "1"\nreadme = {readme}\n',
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        metadata, _ = read_pyproject(project / "pyproject.toml")
        read_pyproject(project / "pyproject.toml", quiet=True)
    assert (metadata.readme is not None) == read
    name = readme.split('"')[1]
    assert caplog.messages == (
        [f"FILE={name}: could not read for {field}; outside the project directory"]
        if field
        else []
    )


@pytest.mark.parametrize(
    "readme",
    ['{file = "gone.md", content-type = "text/plain"}', '"../out.txt"',
     '{file = "../out.md"}'],
    ids=["missing", "no-suffix-out", "no-type-key-out"],
)  # fmt: skip
def test_a_readme_pyproject_metadata_rejects_still_fails_the_parse(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, readme: str
) -> None:
    """Only a file ``pyproject-metadata`` would read is confined: a missing
    one, or a readme it rejects first, still fails the parse unwarned."""
    project = tmp_path / "p"
    project.mkdir()
    for name in ("out.txt", "out.md"):
        (tmp_path / name).write_text("Leaked", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "pkg"\nversion = "1"\nreadme = {readme}\n',
        encoding="utf-8",
    )
    with (
        caplog.at_level("WARNING"),
        pytest.raises(ValueError, match=r"not valid \[project\] metadata"),
    ):
        read_pyproject(project / "pyproject.toml")
    assert not caplog.messages
