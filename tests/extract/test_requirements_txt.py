# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pinned ``requirements.txt`` parsing
(:mod:`pitloom.extract._requirements_txt`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`).

See also: test_pipfile_lock.py for the sibling extractor this module's
exact-pin validation is shared with (``single_exact_pin()`` in
``_lock_common.py``); test_locked_dependencies.py for the cascade
mechanism's own tests.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._requirements_txt import extract_pinned_requirements_dependencies
from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "requirements"
)


def _write_requirements(tmp_dir: Path, content: str) -> None:
    (tmp_dir / "requirements.txt").write_text(content, encoding="utf-8")


def test_no_file_returns_empty_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert not extract_pinned_requirements_dependencies(Path(tmp))


def test_all_pinned_lines_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "requests==2.31.0\nidna==3.7\n",
        )

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0", "idna==3.7"]


def test_blank_lines_and_comments_ignored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "# a full-line comment\n\nrequests==2.31.0  # inline comment\n\n",
        )

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_marker_present_but_still_a_single_exact_pin_included() -> None:
    """A trailing environment marker doesn't affect whether the
    specifier itself is a single exact pin -- same "conditional
    presence, not a version conflict" simplification as every sibling
    format's marker handling."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, 'requests==2.31.0; python_version >= "3.8"\n')

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_extras_dropped_from_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests[security]==2.31.0\n")

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_duplicate_name_same_version_collapsed_to_one_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests==2.31.0\nrequests==2.31.0\n")

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_duplicate_name_conflicting_versions_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests==2.31.0\nidna==3.7\nrequests==2.32.0\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "conflicting versions" in caplog.text
        assert "requests" in caplog.text


def test_duplicate_name_different_casing_same_version_collapsed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "Flask==2.0\nflask==2.0\n")

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["Flask==2.0"]


def test_duplicate_name_different_casing_conflicting_versions_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PEP 503 says a package name is compared case-insensitively --
    ``Flask`` and ``flask`` name the same PyPI package, so pinning them
    to different versions in the same file is a real conflict, not two
    unrelated packages."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "Flask==1.0\nflask==2.0\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "conflicting versions" in caplog.text


def test_undecodable_file_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "requirements.txt").write_bytes(b"requests==2.31.0\n\xff\xfe\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "Failed to read" in caplog.text


def test_three_way_duplicate_conflicting_versions_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path, "requests==2.31.0\nrequests==2.32.0\nrequests==2.33.0\n"
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "conflicting versions" in caplog.text


def test_utf8_bom_does_not_disqualify_the_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "requirements.txt").write_bytes(
            b"\xef\xbb\xbfrequests==2.31.0\nidna==3.7\n"
        )

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0", "idna==3.7"]


def test_backslash_continuation_joined_before_parsing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            'requests==2.31.0 ; python_version >= "3.10" \\\n'
            '    and platform_system == "Linux"\n'
            "idna==3.7\n",
        )

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0", "idna==3.7"]


def test_hash_annotated_continuation_still_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Joining a continuation doesn't make ``--hash=...`` tokens valid
    PEP 508 syntax -- a pip-compile ``--generate-hashes`` file stays
    unsupported, now failing for the right reason instead of on the raw
    backslash."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "requests==2.31.0 \\\n    --hash=sha256:aaaa\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "malformed requirement line" in caplog.text


def test_unpinned_bare_name_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests==2.31.0\nidna\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "isn't pinned to a single exact version" in caplog.text


@pytest.mark.parametrize(
    "version_line", ["requests>=2.0", "requests>=2.0,<3.0", "requests~=2.31"]
)
def test_ranged_specifier_disqualifies_whole_file(
    version_line: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, f"idna==3.7\n{version_line}\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "isn't pinned to a single exact version" in caplog.text


def test_prefix_match_specifier_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "idna==3.7\nrequests==2.31.*\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "isn't pinned to a single exact version" in caplog.text


@pytest.mark.parametrize(
    "url_line",
    [
        "name @ https://github.com/org/repo/archive/refs/tags/v2.31.0.zip",
        "name @ https://github.com/org/repo/releases/download/v2.31.0/repo-2.31.0.whl",
    ],
)
def test_url_requirement_disqualifies_whole_file_even_when_tag_shaped(
    url_line: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression for the explicit design question: a URL requirement
    that merely *looks* like it points at a tagged release must not be
    treated as an exact version pin -- PEP 508 direct references carry
    no normalized version at all, and nothing guarantees a tag/filename
    round-trips to a real PEP 440 version. See the module docstring."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, f"idna==3.7\n{url_line}\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "direct URL reference" in caplog.text


@pytest.mark.parametrize(
    "option_line",
    ["-e .", "-r other-requirements.txt", "--hash=sha256:abcd", "-c constraints.txt"],
)
def test_option_line_disqualifies_whole_file(
    option_line: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, f"idna==3.7\n{option_line}\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "isn't fully pinned" in caplog.text


def test_bare_url_and_legacy_vcs_syntax_disqualify_as_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bare URL (no ``name @`` prefix) or legacy ``git+...#egg=name``
    syntax isn't valid PEP 508 -- ``packaging.requirements.Requirement``
    itself rejects both, which this extractor treats the same as any
    other malformed line: disqualifying, not silently skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "idna==3.7\ngit+https://github.com/org/repo.git@v2.31.0#egg=name\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "malformed requirement line" in caplog.text


def test_malformed_requirement_line_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "idna==3.7\n===not valid===\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "malformed requirement line" in caplog.text


def test_first_disqualifying_line_named_in_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "idna==3.7\nrequests>=2.0\nurllib3==2.0.0\n")

        with caplog.at_level(logging.WARNING):
            extract_pinned_requirements_dependencies(tmp_path)

        assert ":2:" in caplog.text
        assert "urllib3" not in caplog.text


def test_unreadable_file_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        req_dir = tmp_path / "requirements.txt"
        req_dir.mkdir()  # a directory named requirements.txt: read_text() fails

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert not result
        assert "Failed to read" in caplog.text


# --- read_project() cascade integration -------------------------------


def test_read_project_populates_locked_dependencies_from_setup_py_only() -> None:
    """Regression: pinned requirements.txt, like Pipfile.lock, predates
    PEP 621 almost entirely -- the cascade must reach it via
    read_project()'s setup.py-only dispatch path too."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='demo', version='1.0.0')\n",
            encoding="utf-8",
        )
        _write_requirements(tmp_path, "requests==2.31.0\n")

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: requirements.txt | Method: pinned_requirements"
        )


def test_read_project_pipfile_lock_takes_priority_over_requirements_txt() -> None:
    """requirements.txt is the lowest-ranked source -- every real lock
    format outranks it, including Pipfile.lock."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='demo', version='1.0.0')\n",
            encoding="utf-8",
        )
        (tmp_path / "Pipfile.lock").write_text(
            '{"default": {"httpx": {"version": "==0.27.0"}}}',
            encoding="utf-8",
        )
        _write_requirements(tmp_path, "requests==2.31.0\n")

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: Pipfile.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures -------------------------------------------------


def test_real_world_home_assistant_core_rejects_partially_pinned_file() -> None:
    """`home-assistant/core`'s real root `requirements.txt` mixes exact
    pins with range specifiers -- the whole-file all-or-nothing policy
    must reject it entirely, not partially include the pinned lines."""
    metadata, _config, _path = read_project(
        REAL_WORLD_LOCKS / "home-assistant-core-2026.9.0"
    )

    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance
