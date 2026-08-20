# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from setup.py.

See also:
- :mod:`tests.extract.test_setuptools_cfg` for setup.cfg field-level tests.
- :mod:`tests.extract.test_setuptools_integration` for merge, license, and
  fixture tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from pitloom.extract._setuptools import read_setup_py

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SETUPTOOLS_FIXTURE = FIXTURE_DIR / "projects" / "sampleproject-setuptools"


def test_read_setup_py_basic() -> None:
    """Extracts core metadata from a fully-populated setup() call."""
    content = """
from setuptools import setup

setup(
    name="mypackage",
    version="1.0.0",
    description="A cool package",
    author="Bob",
    author_email="bob@example.com",
    license="Apache-2.0",
    url="https://example.com",
    python_requires=">=3.8",
    install_requires=["requests>=2.0", "click"],
    keywords=["foo", "bar"],
)
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))

    assert metadata.name == "mypackage"
    assert metadata.version == "1.0.0"
    assert metadata.description == "A cool package"
    assert metadata.authors == [{"name": "Bob", "email": "bob@example.com"}]
    assert metadata.license_name == "Apache-2.0"
    assert metadata.urls == {"Homepage": "https://example.com"}
    assert metadata.requires_python == ">=3.8"
    assert "requests>=2.0" in metadata.dependencies
    assert "click" in metadata.dependencies
    assert "foo" in metadata.keywords


def test_read_setup_py_setuptools_dot_setup() -> None:
    """Recognise setuptools.setup() as well as bare setup()."""
    content = """
import setuptools
setuptools.setup(name="mypkg", version="0.1")
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.name == "mypkg"
    assert metadata.version == "0.1"


def test_read_setup_py_missing_file() -> None:
    """Raises FileNotFoundError when setup.py does not exist."""
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            read_setup_py(Path(d))


def test_read_setup_py_no_name_literal() -> None:
    """When name is a variable (not a literal), parsing should raise."""
    content = """
from setuptools import setup
pkg_name = "mypackage"
setup(name=pkg_name, version="1.0")
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        with pytest.raises(ValueError, match="project name"):
            read_setup_py(Path(d))


def test_read_setup_py_dynamic_version_skipped() -> None:
    """Dynamic version (function call) is silently skipped -- version is None."""
    content = """
from setuptools import setup
setup(name="mypkg", version=get_version())
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.name == "mypkg"
    assert metadata.version is None


def test_read_setup_py_project_urls() -> None:
    """Reads project_urls dict literal from setup()."""
    content = """
from setuptools import setup
setup(
    name="mypkg",
    version="1.0",
    project_urls={
        "Homepage": "https://example.com",
        "Source": "https://github.com/example/mypkg",
    },
)
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.urls["Homepage"] == "https://example.com"
    assert metadata.urls["Source"] == "https://github.com/example/mypkg"


def test_read_setup_py_keywords_string() -> None:
    """Splits space-separated keywords string into a list."""
    content = (
        "from setuptools import setup\n"
        "setup(name='pkg', version='1.0', keywords='a b c')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.keywords == ["a", "b", "c"]


def test_read_setup_py_provenance() -> None:
    """Each extracted field records setup.py as its source in provenance."""
    content = (
        "from setuptools import setup\nsetup(name='pkg', version='1.0', author='X')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert "setup.py" in metadata.provenance["name"]
    assert "setup.py" in metadata.provenance["version"]
    assert "setup.py" in metadata.provenance["authors"]


def test_read_setup_py_returns_default_pitloom_config() -> None:
    """setup.py provides no pitloom config -- defaults are returned."""
    content = "from setuptools import setup\nsetup(name='pkg', version='1.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        _, config = read_setup_py(Path(d))
    assert config.pretty is False
    assert config.sbom_basename is None


def test_fixture_read_setup_py_bare_setup() -> None:
    """setup.py with bare setup() call extracts no metadata (all in setup.cfg)."""
    with pytest.raises(ValueError, match="project name"):
        read_setup_py(SETUPTOOLS_FIXTURE)


def test_read_setup_py_syntax_error() -> None:
    """read_setup_py raises ValueError on invalid Python syntax."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text("def unclosed_syntax(")
        with pytest.raises(ValueError, match="Could not parse setup.py"):
            read_setup_py(Path(d))


def test_read_setup_py_long_description_and_tuples() -> None:
    """read_setup_py handles long_description and tuple arguments."""
    content = (
        "import setuptools\n"
        "setuptools.setup(\n"
        "    name='full-pkg',\n"
        "    version='2.0.0',\n"
        "    long_description='A detailed description',\n"
        "    keywords=123,\n"
        "    install_requires=('dep1', 'dep2'),\n"
        ")\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.readme == "A detailed description"
    assert metadata.dependencies == ["dep1", "dep2"]
    assert "readme" in metadata.provenance


def test_ast_literal_dict_unpacking_and_calls() -> None:
    """_extract_setup_kwargs handles dict unpacking and non-setup calls."""
    import ast  # pylint: disable=import-outside-toplevel

    from pitloom.extract._setuptools_py import (
        _ast_literal,
        _extract_setup_kwargs,
        _parse_setup_urls,
    )

    code = (
        "print('hello')\n"
        "extra = {'a': 1}\n"
        "setup(name='pkg', version='1.0', "
        "project_urls={'Docs': 'https://doc', 1: 'num', **extra}, "
        "**extra)\n"
    )
    tree = ast.parse(code)
    kwargs = _extract_setup_kwargs(tree)
    assert kwargs.get("name") == "pkg"
    assert kwargs.get("project_urls") == {"Docs": "https://doc"}

    # No setup call in AST returns empty dict
    no_setup_tree = ast.parse("x = 1\ny = 2\n")
    assert _extract_setup_kwargs(no_setup_tree) == {}

    # Non-string dict key ignored by _ast_literal
    expr_stmt = ast.parse("{1: 'val', 'k': 'v'}").body[0]
    dict_node = expr_stmt.value  # type: ignore[attr-defined]
    assert _ast_literal(dict_node) == {"k": "v"}

    # Non-dict project_urls and non-string values
    assert _parse_setup_urls({"project_urls": "https://invalid"}) == {}
    urls_dict = {"Docs": 123, "Home": "https://h"}
    assert _parse_setup_urls({"project_urls": urls_dict}) == {"Home": "https://h"}
