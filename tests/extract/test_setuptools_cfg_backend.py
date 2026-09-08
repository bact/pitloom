# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for detect_build_backend() -- split out of test_setuptools_cfg.py
to keep that file under this repo's file-size soft limit.

See also: :mod:`tests.extract.test_setuptools_cfg` for setup.cfg field
parsing tests.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._setuptools import detect_build_backend


def test_detect_backend_hatchling() -> None:
    """Detects hatchling backend from pyproject.toml build-backend key."""
    content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "hatchling"


def test_detect_backend_setuptools_in_pyproject() -> None:
    """Detects setuptools backend when pyproject.toml declares setuptools.build_meta."""
    content = """
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "mypackage"
version = "1.0.0"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_pyproject_with_setup_cfg() -> None:
    """Infers setuptools backend when only setup.cfg exists."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_pyproject_with_setup_py() -> None:
    """Infers setuptools backend when only setup.py exists."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(
            'from setuptools import setup\nsetup(name="pkg")\n'
        )
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_config_files() -> None:
    """Returns None when no build configuration files are present."""
    with tempfile.TemporaryDirectory() as d:
        assert detect_build_backend(Path(d)) is None


def test_detect_backend_malformed_pyproject_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A pyproject.toml that fails to parse is caught, logged, and returns None."""
    content = "[build-system\nbroken toml"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._setuptools"):
            result = detect_build_backend(Path(d))
    assert result is None
    assert any("pyproject.toml" in r.message for r in caplog.records)


def test_detect_backend_explicit_none_pyproject_data_skips_reread() -> None:
    """Regression: a caller that already parsed ``pyproject.toml`` itself
    and got ``None`` (missing/unparseable) should be able to pass that
    ``None`` straight through -- ``detect_build_backend`` must not
    re-open and re-parse the same file a second time for the same
    answer, distinguishing this from simply omitting the argument
    (which does mean "please read it for me")."""
    content = "[build-system\nbroken toml"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        with patch("pitloom.extract._setuptools.read_pyproject_toml") as mock_read:
            result = detect_build_backend(Path(d), pyproject_data=None)
    mock_read.assert_not_called()
    assert result is None


def test_detect_backend_unknown_backend() -> None:
    """Returns the raw backend string for unrecognised build backends."""
    content = """
[build-system]
requires = ["meson-python"]
build-backend = "mesonpy"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "mesonpy"


def test_detect_build_backend_custom_backend() -> None:
    """detect_build_backend returns prefix for unknown custom build backend."""
    content = (
        "[build-system]\n"
        'requires = ["custom-build"]\n'
        'build-backend = "my_builder.api"\n'
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "my_builder"


def test_detect_build_backend_empty_string() -> None:
    """detect_build_backend returns None when build-backend is empty string."""
    content = '[build-system]\nrequires = ["custom-build"]\nbuild-backend = ""\n'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) is None


def test_detect_build_backend_pep518_only_falls_back_to_setuptools() -> None:
    """A pyproject.toml with [build-system] but no build-backend key (a
    legacy PEP 518-only declaration) is still detected as setuptools
    when setup.cfg/setup.py back it up -- same fallback as when
    pyproject.toml is absent entirely, not a silent None."""
    content = '[build-system]\nrequires = ["setuptools"]\n'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_build_backend_unparseable_pyproject_falls_back_to_setuptools() -> None:
    """Regression: a ``pyproject.toml`` that exists but is unparseable
    (malformed TOML) must fall back to the same setup.cfg/setup.py check
    as the file-absent and no-build-backend-key branches -- not return
    ``None`` outright just because the file happens to exist."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text("this is not [valid toml\n")
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_build_backend_unparseable_pyproject_no_fallback_is_none() -> None:
    """Same malformed-TOML case, but with no setup.cfg/setup.py to back
    it up -- there is genuinely nothing to detect a backend from."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text("this is not [valid toml\n")
        assert detect_build_backend(Path(d)) is None


def test_detect_build_backend_non_dict_build_system_falls_back() -> None:
    """Regression: a ``build-system`` key that isn't a table (e.g. a
    stray top-level ``build-system = "..."`` scalar instead of a
    ``[build-system]`` section -- valid TOML, just the wrong shape) must
    not crash ``.get()`` on it -- treated the same as no build-backend
    resolvable, falling back to the setup.cfg/setup.py check."""
    content = 'build-system = "not-a-table"\n'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_build_backend_non_string_build_backend_falls_back() -> None:
    """Regression: a ``build-backend`` value that isn't a string (e.g. a
    stray integer -- valid TOML, just the wrong type) must not crash on
    string operations -- treated the same as no build-backend
    resolvable, falling back to the setup.cfg/setup.py check."""
    content = '[build-system]\nrequires = ["setuptools"]\nbuild-backend = 123\n'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_build_backend_rejects_substring_lookalike() -> None:
    """Regression: a build-backend whose top-level module merely
    *contains* "setuptools" as a substring (but isn't setuptools) must
    not be misdetected -- matching is on the top-level module name, not
    substring containment."""
    content = (
        "[build-system]\n"
        'requires = ["my-setuptools-shim"]\n'
        'build-backend = "my_setuptools_shim.api"\n'
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "my_setuptools_shim"


def test_detect_build_backend_flit_core_alias() -> None:
    """flit's actual top-level module is flit_core, not flit -- still
    detected as the canonical "flit" identifier pitloom uses elsewhere."""
    content = (
        "[build-system]\n"
        'requires = ["flit_core"]\n'
        'build-backend = "flit_core.buildapi"\n'
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "flit"


def test_detect_build_backend_legacy_colon_suffix() -> None:
    """A build-backend with a PEP 517 object-reference suffix
    (``module:obj``) is still matched on its top-level module, ignoring
    everything from the colon onward."""
    content = (
        "[build-system]\n"
        'requires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta:__legacy__"\n'
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "setuptools"
