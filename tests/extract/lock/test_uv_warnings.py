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

    (message,) = caplog.messages
    assert "2 candidate" in message


def test_the_sole_member_of_another_name_is_not_this_project(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write(
        tmp_path,
        "version = 1\n" + _APP.replace('"app"', '"other"') + _FOO,
    )
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") is None
    assert len(caplog.messages) == 1


@pytest.mark.parametrize("version", ["true", "false"])
def test_a_boolean_version_is_no_uv_lock_version(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, version: str
) -> None:
    _write(tmp_path, f"version = {version}\n" + _APP)
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(tmp_path, "app") is None
    assert "doesn't look like a genuine uv.lock" in caplog.text


@pytest.mark.parametrize(
    ("malformed", "wording"),
    [
        ('[[package]]\nname = "x y"\nversion = "1"\n', "invalid 'name'"),
        ("[[package]]\nname = 5\n", "missing or non-string 'name'"),
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
    (message,) = caplog.messages
    assert wording in message


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
    (message,) = caplog.messages
    assert "expected a table, got int" in message


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ('optional-dependencies = "x"\n', "'optional-dependencies': expected a table"),
        ("[package.optional-dependencies]\nx = 5\n", "expected a list, got int"),
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

    assert expected in caplog.text
    assert "not strings" in caplog.text
