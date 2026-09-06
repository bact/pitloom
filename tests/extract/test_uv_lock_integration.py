# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock``'s overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`), and real-world
fixture coverage.

See also: test_uv_lock.py (extraction correctness this module's tests
were split from -- see that module's own docstring for the split
rationale) and test_uv_lock_root_package.py (root/workspace-member
selection unit tests).
"""

import logging
import tempfile
from pathlib import Path

import pytest

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
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
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


def test_read_project_uv_workspace_picks_matching_member_by_name() -> None:
    """Regression: a shared uv.lock listing more than one local
    workspace member must resolve the *scanned* project's own
    dependencies, identified by matching `pyproject.toml`'s declared
    name -- not whichever editable entry happens to be listed first in
    the lock file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "pkg-a"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "pkg-b"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "httpx" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n\n'
            '[[package]]\nname = "httpx"\nversion = "0.27.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]


def test_real_world_flask() -> None:
    """`pallets/flask` -- `uv.lock` ships in the PyPI sdist itself (the
    only fixture where that's true, per real-world-locks/README.md).
    Has multiple marker-conditional duplicate names (e.g. `click`),
    exercising the ambiguity-skip path against real data. Transitive
    walk adds `zipp` (a dependency of `importlib-metadata`, not a direct
    Flask dependency) beyond the root's own immediate dependency list."""
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
        "zipp",
    }
    assert "click" not in names  # ambiguous (ships two marker-conditional versions)
    assert metadata.provenance["locked_dependencies"] == (
        "Source: uv.lock | Method: resolved_lockfile"
    )


def test_real_world_fastapi_cli() -> None:
    """Transitive walk pulls in `typer`'s and `uvicorn`'s own
    dependencies (`click`, `rich`, `h11`, etc.), not just the root's four
    immediate dependencies."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "fastapi-cli-0.0.32")

    assert metadata.name == "fastapi-cli"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert names == {
        "annotated-doc",
        "anyio",
        "click",
        "colorama",
        "exceptiongroup",
        "h11",
        "httptools",
        "idna",
        "markdown-it-py",
        "mdurl",
        "pygments",
        "python-dotenv",
        "pyyaml",
        "rich",
        "rich-toolkit",
        "shellingham",
        "tomli",
        "typer",
        "typing-extensions",
        "uvicorn",
        "uvloop",
        "watchfiles",
        "websockets",
    }


def test_real_world_abi3audit() -> None:
    """Transitive walk pulls in `requests`'/`requests-cache`'s/`rich`'s
    own dependencies (`urllib3`, `certifi`, `cattrs`, etc.), not just the
    root's eight immediate dependencies."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "abi3audit-0.0.26")

    assert metadata.name == "abi3audit"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert names == {
        "abi3info",
        "attrs",
        "cattrs",
        "certifi",
        "charset-normalizer",
        "exceptiongroup",
        "idna",
        "kaitaistruct",
        "markdown-it-py",
        "mdurl",
        "packaging",
        "pefile",
        "platformdirs",
        "pyelftools",
        "pygments",
        "requests",
        "requests-cache",
        "rich",
        "typing-extensions",
        "url-normalize",
        "urllib3",
    }
