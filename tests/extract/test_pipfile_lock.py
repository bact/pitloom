# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``Pipfile.lock`` resolved-dependency parsing
(:mod:`pitloom.extract._pipfile_lock`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`).

See also: test_poetry_lock.py/test_pylock.py/test_uv_lock.py for the
sibling lock extractors this module's tests mirror in shape;
test_locked_dependencies.py for the cascade mechanism's own tests.
"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies
from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pipfile"
)


def _write_lock(tmp_dir: Path, data: dict[str, object]) -> None:
    (tmp_dir / "Pipfile.lock").write_text(json.dumps(data), encoding="utf-8")


def test_no_lock_file_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert not extract_pipfile_lock_dependencies(Path(tmp))


def test_malformed_json_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "Pipfile.lock").write_text("{not valid json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_default_section_not_a_dict_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, {"default": ["not-a-dict"]})

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert not result
        assert "expected a table" in caplog.text


def test_no_default_section_returns_empty_list() -> None:
    """A Pipfile.lock with no `default` key at all (unusual but not
    invalid) is treated as zero runtime dependencies, not an error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, {"develop": {"pytest": {"version": "==8.0.0"}}})

        assert not extract_pipfile_lock_dependencies(tmp_path)


def test_simple_dependency_resolved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "requests": {"version": "==2.31.0", "index": "pypi"},
                },
                "develop": {
                    "pytest": {"version": "==8.0.0"},
                },
            },
        )

        assert extract_pipfile_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_develop_section_excluded() -> None:
    """Only `default` (main/runtime) entries are included -- `develop`
    (dev-only) entries are excluded, mirroring poetry.lock's
    main-group-only policy."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {"requests": {"version": "==2.31.0"}},
                "develop": {"pytest": {"version": "==8.0.0"}},
            },
        )

        result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "pytest" not in " ".join(result)


def test_malformed_entry_not_a_dict_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "broken": "not-a-table",
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "malformed" in caplog.text.lower()


def test_missing_version_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "no-version": {"index": "pypi"},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "missing" in caplog.text.lower()


@pytest.mark.parametrize(
    "non_registry_key", ["git", "hg", "bzr", "svn", "path", "file", "editable"]
)
def test_non_registry_sourced_dependency_excluded(
    non_registry_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "local-dep": {non_registry_key: "some-value"},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "local-dep" in caplog.text


def test_invalid_specifier_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "broken-version": {"version": "not-a-specifier"},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "valid PEP 440 specifier" in caplog.text


def test_prefix_match_specifier_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: `packaging.specifiers.Specifier("==2.31.*").operator`
    is also `"=="`, so a naive `operator == "=="` check would wrongly
    accept a prefix-match specifier (pinning a *range* of versions) as
    if it were a single exact pin."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "wildcard": {"version": "==2.31.*"},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "isn't a single exact" in caplog.text


def test_non_dict_json_top_level_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: unlike TOML (whose grammar guarantees a table at the
    document root), a `Pipfile.lock` containing valid but non-object
    JSON (e.g. a bare array) used to crash extraction with
    `AttributeError` on `data.get(...)` instead of degrading gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "Pipfile.lock").write_text("[]", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert not result
        assert "expected an object" in caplog.text


@pytest.mark.parametrize("version", [">=2.31.0", "==2.31.0,!=2.31.1", "!=2.31.0"])
def test_non_exact_pin_skipped_and_warns(
    version: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A `version` that isn't a single exact `==` specifier (a range, or
    an excluded-version specifier) is skipped, not coerced -- pipenv
    lock output is expected to always resolve to an exact pin, so this
    is a defensive "don't guess" path, same policy as every other
    format's ambiguous-version skip."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "ranged": {"version": version},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "exact" in caplog.text.lower()


def test_missing_or_empty_name_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed top-level key (e.g. JSON's own coercion couldn't
    produce a non-string here in practice, but an empty string is
    possible and must not silently pass through) is skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {
                "default": {
                    "": {"version": "==1.0.0"},
                    "requests": {"version": "==2.31.0"},
                }
            },
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pipfile_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "malformed" in caplog.text.lower()


# --- read_project() cascade integration -------------------------------


def test_read_project_populates_locked_dependencies_from_setup_py_only() -> None:
    """Regression: Pipfile.lock predates PEP 621 almost entirely --
    every real project pairs it with a bare setup.py, never
    pyproject.toml. The cascade must reach it via read_project()'s
    setup.py-only dispatch path, not only the pyproject.toml one."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='demo', version='1.0.0')\n",
            encoding="utf-8",
        )
        _write_lock(tmp_path, {"default": {"requests": {"version": "==2.31.0"}}})

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: Pipfile.lock | Method: resolved_lockfile"
        )


def test_read_project_pdm_lock_takes_priority_over_pipfile_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "pdm.lock").write_text(
            '[[package]]\nname = "httpx"\nversion = "0.27.0"\ngroups = ["default"]\n',
            encoding="utf-8",
        )
        _write_lock(tmp_path, {"default": {"requests": {"version": "==2.31.0"}}})

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures -------------------------------------------------


def test_real_world_requests_html() -> None:
    """`psf/requests-html` -- real, unmodified `Pipfile.lock` from the
    matching GitHub tag, read directly via the extractor rather than
    `read_project()`: `requests-html`'s `setup.py` declares `name`/
    `version` via module-level constants (`NAME = 'requests-html'`,
    `setup(name=NAME, ...)`), which `_setuptools_py.py`'s literal-only
    AST resolution can't follow -- a known, separate, pre-existing gap
    (see the `pyyaml` entry in `real-world-projects/README.md`) that
    makes `read_setup_py()` raise `ValueError` and, with no `setup.cfg`
    fallback either, `read_project()` raise `FileNotFoundError` entirely
    for this fixture. That's this fixture's own known limitation, not
    something for the lock-cascade extractor to work around -- so this
    test exercises `extract_pipfile_lock_dependencies()` directly
    against the real fixture data instead."""
    dependencies = extract_pipfile_lock_dependencies(
        REAL_WORLD_LOCKS / "requests-html-0.10.0"
    )

    names = {dep.split("==", maxsplit=1)[0] for dep in dependencies}
    assert "requests" in names
    assert "beautifulsoup4" in names


def test_real_world_responder() -> None:
    """`kennethreitz/responder` -- also has a self-referential editable
    `path`-sourced entry (`responder` itself) in its own `default`
    section, exercising the non-registry-source skip against real data.
    Same `setup.py`-constant limitation as `requests-html` above applies
    here too, so this also calls the extractor directly."""
    from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies

    dependencies = extract_pipfile_lock_dependencies(
        REAL_WORLD_LOCKS / "responder-2.0.0"
    )

    names = {dep.split("==", maxsplit=1)[0] for dep in dependencies}
    assert "requests" in names
    assert "responder" not in names  # self-referential, editable/path-sourced
