# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock`` resolved-dependency parsing
(:mod:`pitloom.extract._uv_lock`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`).

See also: test_pylock.py/test_poetry_lock.py for the sibling lock
extractors this module's tests mirror in shape;
test_locked_dependencies.py for the cascade mechanism's own tests.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._uv_lock import (
    _find_root_package,
    _pinned_dep_for_package,
    extract_uv_lock_dependencies,
)
from pitloom.extract.project import read_project

_LOCK_HEADER = 'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'

#: A minimal root/project package entry -- every test that needs one
#: root dependency composes this with its own `dependencies` block.
_ROOT_HEADER = (
    '[[package]]\nname = "demo"\nversion = "1.0.0"\nsource = { editable = "." }\n'
)

REAL_WORLD_LOCKS = Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "uv"


def _write_lock(tmp_dir: Path, body: str = "") -> None:
    (tmp_dir / "uv.lock").write_text(_LOCK_HEADER + body, encoding="utf-8")


def test_no_lock_file_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert not extract_uv_lock_dependencies(Path(tmp))


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "uv.lock").write_text("this is not [ valid toml", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_package_key_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_no_root_package_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A uv.lock with no `editable`/`virtual`-sourced entry has no
    identifiable project package -- nothing to resolve dependencies
    for."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "no project package found" in caplog.text


def test_root_dependencies_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { editable = "." }\ndependencies = "not-a-list"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_root_with_no_dependencies_key_returns_empty_list() -> None:
    """A project with zero runtime dependencies is valid, not an error."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER)

        assert not extract_uv_lock_dependencies(tmp_path)


def test_simple_dependency_resolved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_dependency_with_marker_but_no_inline_version_still_resolved() -> None:
    """A `marker` field alone (conditional presence, not a version
    conflict) doesn't block resolution -- same "no marker evaluation,
    include regardless" simplification as poetry.lock/pylock.toml."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests", '
            "marker = \"python_full_version < '3.11'\" }]\n\n"
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_malformed_dependency_reference_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER + 'dependencies = ["not-a-table"]\n')

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "malformed" in caplog.text.lower()


def test_dependency_reference_missing_name_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER + "dependencies = [{ extra = ['x'] }]\n")

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "malformed" in caplog.text.lower()


def test_marker_conditional_root_dependency_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An inline `version` directly on the root's own dependency
    reference means the resolved version differs per environment marker
    -- ambiguous without evaluating markers, so it's skipped, not
    guessed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "click", version = "8.1.8", '
            'source = { registry = "https://pypi.org/simple" }, '
            "marker = \"python_full_version < '3.10'\" }]\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "marker-conditional" in caplog.text


def test_dependency_not_found_in_package_table_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path, _ROOT_HEADER + 'dependencies = [{ name = "ghost-pkg" }]\n'
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "not found" in caplog.text


def test_ambiguous_multi_version_dependency_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The same package name resolved at two different versions (e.g.
    one per Python-version marker branch) can't be picked between
    without marker evaluation -- skip both, don't guess."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "click" }]\n\n'
            '[[package]]\nname = "click"\nversion = "8.1.8"\n'
            'source = { registry = "https://pypi.org/simple" }\n\n'
            '[[package]]\nname = "click"\nversion = "8.3.1"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "2 resolved versions" in caplog.text


@pytest.mark.parametrize(
    "source_key", ["git", "path", "directory", "editable", "virtual"]
)
def test_non_registry_sourced_dependency_excluded(
    source_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "local-dep" }]\n\n'
            f'[[package]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'source = {{ {source_key} = "some-value" }}\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_dependency_missing_version_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "no-version" }]\n\n'
            '[[package]]\nname = "no-version"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "missing" in caplog.text.lower()


def test_dependency_with_no_source_table_still_included() -> None:
    """A package entry with no `source` key at all (unusual but not
    invalid) is treated the same as a registry source -- only an
    explicit non-registry key excludes it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "no-source" }]\n\n'
            '[[package]]\nname = "no-source"\nversion = "1.2.3"\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["no-source==1.2.3"]


def test_find_root_package_returns_none_for_empty_list() -> None:
    assert _find_root_package([]) is None


def test_find_root_package_ignores_malformed_entries() -> None:
    """A malformed top-level `[[package]]` entry (not a table) is
    silently skipped while searching for the root package -- see
    test_lock_common.py for the equivalent `index_packages_by_name()`
    coverage this and `_uv_lock.py`'s own extraction share."""
    packages: list[object] = [
        "not-a-dict",
        {"version": "1.0.0"},  # missing name, still not editable/virtual
        {"name": "requests", "version": "2.31.0"},
    ]

    assert _find_root_package(packages) is None


def test_pinned_dep_for_package_returns_none_when_source_not_a_dict() -> None:
    """Defensive: a `source` value that isn't a table (malformed) is
    skipped by the source-key check, not a crash -- version resolution
    still proceeds normally."""
    assert (
        _pinned_dep_for_package(
            {"name": "odd-pkg", "version": "1.0.0", "source": "not-a-table"}
        )
        == "odd-pkg==1.0.0"
    )


# --- read_project() cascade integration -----------------------------------


def test_read_project_populates_locked_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: uv.lock | Method: resolved_lockfile"
        )


def test_read_project_uv_lock_takes_priority_over_poetry_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "httpx" }]\n\n'
            '[[package]]\nname = "httpx"\nversion = "0.27.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: uv.lock | Method: resolved_lockfile | Note: supersedes poetry.lock"
        )


def test_read_project_pylock_takes_priority_over_uv_lock() -> None:
    """pylock.toml (PEP 751) outranks uv.lock in the cascade."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "1.0"\ncreated-by = "test"\n'
            '[[packages]]\nname = "httpx"\nversion = "0.27.0"\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


# --- real-world fixtures ---------------------------------------------------


def test_real_world_flask() -> None:
    """`pallets/flask` -- `uv.lock` ships in the PyPI sdist itself (the
    only fixture where that's true, per real-world-locks/README.md).
    Has multiple marker-conditional duplicate names (e.g. `click`),
    exercising the ambiguity-skip path against real data."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "flask-3.1.3")

    assert metadata.name == "Flask"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert names == {
        "blinker",
        "importlib-metadata",
        "itsdangerous",
        "jinja2",
        "markupsafe",
        "werkzeug",
    }
    assert "click" not in names  # ambiguous (ships two marker-conditional versions)
    assert metadata.provenance["locked_dependencies"] == (
        "Source: uv.lock | Method: resolved_lockfile"
    )


def test_real_world_fastapi_cli() -> None:
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "fastapi-cli-0.0.32")

    assert metadata.name == "fastapi-cli"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert names == {"rich-toolkit", "tomli", "typer", "uvicorn"}


def test_real_world_abi3audit() -> None:
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "abi3audit-0.0.26")

    assert metadata.name == "abi3audit"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert names == {
        "abi3info",
        "kaitaistruct",
        "packaging",
        "pefile",
        "pyelftools",
        "requests",
        "requests-cache",
        "rich",
    }
