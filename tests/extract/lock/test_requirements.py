# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pinned ``requirements.txt`` parsing
(:mod:`pitloom.extract.lock.requirements`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract.lock.cascade`).

See also: test_pipfile.py for the sibling extractor this module's
exact-pin validation is shared with (``single_exact_pin()`` in
``common.py``); test_cascade.py for the cascade
mechanism's own tests.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract.lock.requirements import (
    _join_continuation_lines,
    extract_pinned_requirements_dependencies,
)
from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "real-world-locks"
    / "requirements"
)


def _write_requirements(tmp_dir: Path, content: str) -> None:
    (tmp_dir / "requirements.txt").write_text(content, encoding="utf-8")


def test_no_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `cascade.py` relies on this distinction
    to let a lower-priority source apply when this one is truly absent."""
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pinned_requirements_dependencies(Path(tmp)) is None


def test_all_comments_and_blank_lines_returns_empty_list_not_none() -> None:
    """A `requirements.txt` with no real dependency lines at all is a
    real, valid, fully-pinned (vacuously) file -- must be `[]`, not
    `None`, so the cascade treats it as a winning (if empty) result
    rather than "not present"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "# just a comment\n\n")

        assert extract_pinned_requirements_dependencies(tmp_path) == []


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

        assert result is None
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

        assert result is None
        assert "conflicting versions" in caplog.text


def test_undecodable_file_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "requirements.txt").write_bytes(b"requests==2.31.0\n\xff\xfe\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
        assert "Failed to parse" in caplog.text


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

        assert result is None
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


def test_dangling_continuation_at_end_of_file_still_joined() -> None:
    """A file whose very last physical line ends in a backslash (no
    further line follows it at all) must still flush that buffered,
    still-unterminated logical line -- not silently drop it -- exercising
    the end-of-file flush branch distinct from the normal per-line join."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests==2.31.0 \\")

        result = extract_pinned_requirements_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_hash_annotated_continuation_still_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Joining a continuation doesn't make ``--hash=...`` tokens valid
    PEP 508 syntax -- a pip-compile ``--generate-hashes`` file stays
    unsupported, failing on the ``--hash`` token, not the raw backslash."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "requests==2.31.0 \\\n    --hash=sha256:aaaa\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
        assert "malformed requirement line" in caplog.text


def test_unpinned_bare_name_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "requests==2.31.0\nidna\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
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

        assert result is None
        assert "isn't pinned to a single exact version" in caplog.text


def test_prefix_match_specifier_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "idna==3.7\nrequests==2.31.*\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
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
    """A URL requirement that merely *looks* like a tagged release is not an
    exact version pin: PEP 508 direct references carry no normalised version.
    See the module docstring."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, f"idna==3.7\n{url_line}\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
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

        assert result is None
        assert "isn't fully pinned" in caplog.text


@pytest.mark.parametrize(
    "option_line",
    [
        "--extra-index-url https://user:secret_token@custom-pypi.org/simple",
        "--extra-index-url=https://user:secret_token@custom-pypi.org/simple",
    ],
)
def test_option_line_with_credentials_redacts_line_in_log(
    option_line: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Option lines containing credentials (e.g. basic auth in --extra-index-url)
    must only log the option token, never the URL or credentials."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            f"idna==3.7\n{option_line}\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
        assert "--extra-index-url" in caplog.text
        assert "secret_token" not in caplog.text
        assert "user" not in caplog.text


def test_malformed_url_with_credentials_redacts_credentials_in_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """URL requirements with basic auth must not leak passwords in logs."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(
            tmp_path,
            "https://user:secret_pass@example.com/pkg-1.0.whl\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
        assert "secret_pass" not in caplog.text
        assert "malformed requirement line" in caplog.text


def test_arbitrary_equality_operator_preserved_in_requirements(tmp_path: Path) -> None:
    _write_requirements(tmp_path, "custom-pkg===2021.01.01-legacy\n")
    result = extract_pinned_requirements_dependencies(tmp_path)
    assert result == ["custom-pkg===2021.01.01-legacy"]


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

        assert result is None
        assert "malformed requirement line" in caplog.text


def test_malformed_requirement_line_disqualifies_whole_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_requirements(tmp_path, "idna==3.7\n===not valid===\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pinned_requirements_dependencies(tmp_path)

        assert result is None
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


# --- read_project() cascade integration -------------------------------


def test_read_project_populates_locked_dependencies_from_setup_py_only() -> None:
    """Pinned requirements.txt, like Pipfile.lock, pairs with a bare setup.py:
    the cascade reaches it via read_project()'s setup.py-only dispatch path."""
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
            '{"_meta": {"pipfile-spec": 6}, '
            '"default": {"httpx": {"version": "==0.27.0"}}}',
            encoding="utf-8",
        )
        _write_requirements(tmp_path, "requests==2.31.0\n")

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: Pipfile.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures -------------------------------------------------


def test_real_world_home_assistant_core_rejects_partially_pinned_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`home-assistant/core`'s real root `requirements.txt` contains
    constraint-file options (`-c`) and mixed pins -- the whole-file
    all-or-nothing policy must reject it entirely."""
    with caplog.at_level(logging.WARNING):
        metadata, _config, _path = read_project(
            REAL_WORLD_LOCKS / "home-assistant-core-2026.9.0"
        )

    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance
    assert "option '-c' means this file isn't fully pinned" in caplog.text


@pytest.mark.parametrize(
    ("text", "pins"),
    [
        ("# note \\\nrequests==2.0\nidna==3.0\n", ["requests==2.0", "idna==3.0"]),
        ("  # indented \\\nrequests==2.0\n", ["requests==2.0"]),
        ("foo==1.\\\n0\n", ["foo==1.0"]),
        ("foo\\\n==\\\n1.0\nidna==3.0\n", ["foo==1.0", "idna==3.0"]),
        ("foo==1.0 \\  \n; python_version>'3'\n", ["foo==1.0"]),
        ("fo\\\no==1.0\n", ["foo==1.0"]),
        ("foo==1.0 \\\n# comment\nidna==3.0\n", ["foo==1.0", "idna==3.0"]),
        ("foo==1.0 # trailing \\\nidna==3.0\n", ["foo==1.0"]),
    ],
    ids=[
        "comment-ending-in-backslash",
        "indented-comment",
        "no-space-join",
        "three-line-chain",
        "space-after-backslash",
        "name-split",
        "comment-ends-continuation",
        "trailing-comment-still-continues",
    ],
)
def test_continuation_follows_pip(text: str, pins: list[str]) -> None:
    """pip joins pieces with nothing between them and never continues a
    comment line, so a comment ending in a backslash does not swallow the
    pin after it. (A trailing comment on a requirement still continues, so
    the next line is part of the comment, as in pip.)"""
    with tempfile.TemporaryDirectory() as tmp:
        _write_requirements(Path(tmp), text)
        assert extract_pinned_requirements_dependencies(Path(tmp)) == pins


def test_continuation_matches_pips_own_join_lines() -> None:
    """Drift guard: the logical lines are pip's (its ``join_lines`` is a
    private helper, so the test skips if it moves)."""
    try:
        # pylint: disable-next=import-outside-toplevel
        from pip._internal.req.req_file import join_lines
    except ImportError:  # pragma: no cover
        pytest.skip("pip's join_lines is not importable")
    text = (
        "# note \\\nrequests==2.0\nfoo==1.\\\n0\nfo\\\no==1.0\n"
        "a==1 \\\n# c\nb==2\n  # indented \\\nidna==3.0\nlast==1 \\"
    )
    # pylint: disable-next=protected-access
    ours = [t.strip() for _, t in _join_continuation_lines(text)]
    theirs = [t.strip() for _, t in join_lines(enumerate(text.splitlines(), start=1))]
    assert ours == theirs
