# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``uv.lock`` warning shapes: which message a given malformed lock gets,
and that it gets it once.

See also: test_uv.py (extraction correctness), test_uv_root_package.py
(root-package selection).
"""

import logging
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock.cascade import apply_locked_dependencies
from pitloom.extract.lock.uv import extract_uv_lock_dependencies
from tests._code_records import coded, has_parts
from tests.extract.lock.lock_lines_shared import matching, said, said_once

pytestmark = pytest.mark.platform

_APP = '[[package]]\nname = "app"\nversion = "0.1"\nsource = {editable = "."}\n'
_FOO = '[[package]]\nname = "foo"\nversion = "1.0"\n'


def _write(project_dir: Path, text: str) -> None:
    (project_dir / "uv.lock").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("expected", ["pkg-c", None])
def test_workspace_without_a_matching_member_gets_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, expected: str | None
) -> None:
    """The multi-candidate warning is the only one: not also a second,
    false "no 'editable'/'virtual' source entry"."""
    other = '[[package]]\nname = "other"\nversion = "0.1"\nsource = {virtual = "."}\n'
    _write(tmp_path, "version = 1\n" + _APP + other)

    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, expected) is None

    [(code, message)] = coded(caplog)
    assert code == "lock-file-unusable"
    assert has_parts(message, "FILE=uv.lock", "workspace entries: 2")


def test_the_sole_member_of_another_name_is_not_this_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write(
        tmp_path,
        "version = 1\n" + _APP.replace('"app"', '"other"') + _FOO,
    )
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") is None
    assert [code for code, _text in coded(caplog)] == ["lock-file-unusable"]


@pytest.mark.parametrize("version", ["true", "false"])
def test_a_boolean_version_is_no_uv_lock_version(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, version: str
) -> None:
    _write(tmp_path, f"version = {version}\n" + _APP)
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") is None
    said(caplog, "lock-file-wrong-format", "FILE=uv.lock", "format marker version")


@pytest.mark.parametrize(
    ("malformed", "wording"),
    [
        ('[[package]]\nname = "x y"\nversion = "1"\n', "name 'x y'"),
        ("[[package]]\nname = 5\n", "name 5"),
    ],
    ids=["invalid-name", "name-not-a-string"],
)
def test_each_malformed_entry_is_warned_of_once_across_the_cascade(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, malformed: str, wording: str
) -> None:
    """The pin pass and the extras pass both read the root package; only the
    first reports a malformed ``[[package]]`` entry."""
    _write(
        tmp_path,
        "version = 1\n"
        + malformed
        + _APP
        + '[package.optional-dependencies]\nextra = [{name = "foo"}]\n'
        + _FOO,
    )
    metadata = ProjectMetadata(
        name="app", version="1", dependencies=["foo; extra == 'extra'"]
    )
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies == ["foo==1.0"]
    [(code, message)] = coded(caplog)
    assert code == "lock-entry-malformed"
    assert has_parts(message, "FILE=uv.lock", wording)


def test_a_non_table_entry_is_warned_of_once_across_the_cascade(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write(
        tmp_path,
        "version = 1\npackage = [1, "
        '{name = "app", version = "0.1", source = {editable = "."}, '
        'optional-dependencies = {extra = [{name = "foo"}]}}, '
        '{name = "foo", version = "1.0"}]\n',
    )
    metadata = ProjectMetadata(
        name="app", version="1", dependencies=["foo; extra == 'extra'"]
    )
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, tmp_path)

    assert metadata.locked_dependencies == ["foo==1.0"]
    [(code, message)] = coded(caplog)
    assert code == "lock-entry-malformed"
    assert has_parts(message, "FILE=uv.lock", "package is int", "expected a table")


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ('optional-dependencies = "x"\n', "optional-dependencies is str"),
        ("[package.optional-dependencies]\nx = 5\n", "extra 'x' is int"),
    ],
    ids=["table", "list"],
)
def test_a_malformed_extras_table_of_a_requested_extra_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, tail: str, expected: str
) -> None:
    _write(
        tmp_path,
        "version = 1\n"
        + _APP
        + '[[package.dependencies]]\nname = "foo"\nextra = ["x", 5]\n'
        + _FOO
        + tail,
    )
    with caplog.at_level(logging.WARNING):
        extract_uv_lock_dependencies(tmp_path, "app")

    said(caplog, "lock-entry-malformed", "PACKAGE=foo", expected)
    said(caplog, "lock-entry-malformed", "PACKAGE=foo", "not a string")


_DIAMOND_TOP = (
    "version = 1\n"
    + _APP.replace('source = {editable = "."}', 'source = {editable = "."}\n')
    + 'dependencies = [{name = "a"}, {name = "b"}]\n'
)


def _diamond(left: str, right: str, tail: str = "") -> str:
    """``app`` depends on ``a`` and ``b``, which each depend on one spelling
    of a package (*left*, *right*)."""
    member = (
        '[[package]]\nname = "{}"\nversion = "1"\ndependencies = [{{name = "{}"}}]\n'
    )
    return _DIAMOND_TOP + member.format("a", left) + member.format("b", right) + tail


@pytest.mark.parametrize(
    "spellings", [("ghost", "ghost"), ("ghost", "Ghost")], ids=["same", "other-case"]
)
def test_a_package_missing_from_the_table_is_warned_of_once_per_walk(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, spellings: tuple[str, str]
) -> None:
    """Two packages depend on one package the lock's table lacks: each
    reference fails to resolve, and the walk says so once."""
    _write(tmp_path, _diamond(*spellings))
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") == ["a==1", "b==1"]
    ghost = [text for code, text in coded(caplog) if "ghost" in text.lower()]
    assert len(ghost) == 1, caplog.messages
    assert has_parts(ghost[0], "FILE=uv.lock", "not in the lock's package table")
    assert [code for code, _text in coded(caplog)] == ["lock-entry-malformed"]


def test_a_package_at_several_versions_is_warned_of_once_per_walk(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    twice = '[[package]]\nname = "dup"\nversion = "{}"\n'
    _write(tmp_path, _diamond("dup", "dup", twice.format("1") + twice.format("2")))
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") == ["a==1", "b==1"]
    dup = [text for text in caplog.messages if "dup" in text]
    assert len(dup) == 1, caplog.messages


def test_a_lock_only_package_is_normal_and_a_clean_lock_prints_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``foo`` is in the table and no project entry names it; ``1.0`` and
    ``1.0.0`` are one version: no line."""
    _write(
        tmp_path,
        _diamond(
            "foo",
            "foo",
            '[[package]]\nname = "foo"\nversion = "1.0"\n'
            '[[package]]\nname = "foo"\nversion = "1.0.0"\n',
        )
        + _FOO.replace("foo", "unused"),
    )
    with caplog.at_level(logging.WARNING):
        result = extract_uv_lock_dependencies(tmp_path, "app")
    assert result is not None and "unused==1.0" not in result
    assert not caplog.records


def test_the_workspace_line_names_the_lock_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Named by its file name, never its directory, and once in the line."""
    other = '[[package]]\nname = "other"\nversion = "0.1"\nsource = {virtual = "."}\n'
    _write(tmp_path, "version = 1\n" + _APP + other)
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "pkg-c") is None
    [(_code, text)] = coded(caplog)
    assert text.count("uv.lock") == 1 and text.count("FILE=") == 1
    assert str(tmp_path) not in text


def _referrers(reference: str, tail: str = "") -> str:
    """``app`` depends on ``a`` and ``b``, which each carry *reference* (a
    dependency reference) to ``c``, a package the table holds."""
    member = '[[package]]\nname = "{}"\nversion = "1"\ndependencies = [{}]\n'
    return (
        _DIAMOND_TOP
        + member.format("a", reference)
        + member.format("b", reference)
        + '[[package]]\nname = "c"\nversion = "1"\n'
        + tail
    )


_C_ENTRY = '[[package]]\nname = "c"\nversion = "1"\n'


@pytest.mark.parametrize(
    ("reference", "c_entry", "code", "parts"),
    [
        (
            '{name = "c", version = "1"}',
            _C_ENTRY,
            "lock-entry-unusable",
            ("PACKAGE=c", "version per marker"),
        ),
        (
            '{name = "c", extra = 5}',
            _C_ENTRY,
            "lock-entry-malformed",
            ("PACKAGE=c", "extra is int"),
        ),
        (
            '{name = "c", extra = ["x", 5]}',
            _C_ENTRY,
            "lock-entry-malformed",
            ("PACKAGE=c", "not a string"),
        ),
        (
            '{name = "c", extra = "x"}',
            _C_ENTRY + 'optional-dependencies = "x"\n',
            "lock-entry-malformed",
            ("PACKAGE=c", "optional-dependencies is str"),
        ),
    ],
    ids=["marker-version", "scalar-extra", "extra-items", "extras-table"],
)
def test_a_reference_problem_is_said_once_however_many_entries_refer(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    reference: str,
    c_entry: str,
    code: str,
    parts: tuple[str, ...],
) -> None:
    _write(tmp_path, _referrers(reference).replace(_C_ENTRY, c_entry))
    with caplog.at_level(logging.WARNING):
        extract_uv_lock_dependencies(tmp_path, "app")
    said_once(caplog, code, *parts)


def test_the_runtime_walk_and_the_extras_pass_say_a_line_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``ghost`` is missing from the table, referenced by ``a`` and by the
    root's extra ``x``: one run, one line."""
    _write(
        tmp_path,
        "version = 1\n"
        + _APP.replace(
            'source = {editable = "."}',
            'source = {editable = "."}\ndependencies = [{name = "a"}]\n'
            "[package.optional-dependencies]\n"
            'x = [{name = "ghost"}]\n',
        )
        + '[[package]]\nname = "a"\nversion = "1"\ndependencies = [{name = "ghost"}]\n',
    )
    metadata = ProjectMetadata(
        name="app", version="1", dependencies=["a", "ghost; extra == 'x'"]
    )
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, tmp_path)
    assert metadata.locked_dependencies == ["a==1"]
    said_once(caplog, "lock-entry-malformed", "PACKAGE=ghost")
    # A later run (another project) says it again: the memo is per run.
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(
            ProjectMetadata(
                name="app", version="1", dependencies=["a", "ghost; extra == 'x'"]
            ),
            tmp_path,
        )
    assert len(matching(caplog, "lock-entry-malformed", "PACKAGE=ghost")) == 2


def test_a_duplicate_without_a_version_is_listed_as_no_version(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write(
        tmp_path,
        _diamond(
            "dup",
            "dup",
            '[[package]]\nname = "dup"\n[[package]]\nname = "dup"\nversion = "2"\n',
        ),
    )
    with caplog.at_level(logging.WARNING):
        extract_uv_lock_dependencies(tmp_path, "app")
    [line] = matching(caplog, "lock-entry-conflict", "PACKAGE=dup")
    assert has_parts(line, "'2'", "'no version'")
    assert "None" not in line


def test_a_reference_without_a_usable_name_names_its_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "uv.lock").write_text(
        'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
        + _APP
        + 'dependencies = [{ name = "-bad-" }]\n',
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") == []
    said(caplog, "lock-entry-malformed", "FILE=uv.lock", "an entry of dependencies")
