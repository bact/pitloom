# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg``'s ``file:`` directive: several files joined as setuptools
does, and a file that cannot be read left out with one ``WARNING:`` instead
of ending the read.

See also: :mod:`tests.extract.project.test_setuptools_cfg`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project._setup_cfg_directives import _resolve_cfg_file_directive
from pitloom.extract.project.setuptools_cfg import read_setup_cfg

_MIT = "License :: OSI Approved :: MIT License"


def test_several_files_are_joined_as_setuptools_joins_them(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"one")
    (tmp_path / "b.txt").write_bytes(b"two\n")
    got = _resolve_cfg_file_directive("file: a.txt, missing.txt ,b.txt", tmp_path, "f")
    assert got == "one\ntwo\n"


def _bad_file(tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A listed file that exists but cannot be read, as *kind*."""
    if kind == "directory":
        (tmp_path / "bad").mkdir()
    elif kind == "not-utf-8":
        (tmp_path / "bad").write_bytes(b"\xff\xfe\x00bad")
    else:
        (tmp_path / "bad").write_text("x", encoding="utf-8")
        real = Path.read_text

        def denied(self: Path, *args: object, **kwargs: object) -> str:
            if self.name == "bad":
                raise PermissionError(13, "Permission denied", str(self))
            return real(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", denied)
    return "bad"


@pytest.mark.parametrize("kind", ["directory", "not-utf-8", "permission"])
def test_an_unreadable_classifiers_file_is_left_out_with_one_warning(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    name = _bad_file(tmp_path, kind, monkeypatch)
    (tmp_path / "good.txt").write_text(_MIT, encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = pkg\nversion = 1.0\n"
        f"classifiers = file: {name}, good.txt\n"
        f"long_description = file: {name}\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_setup_cfg(tmp_path)
    assert metadata.license_name == "MIT License"
    assert metadata.readme is None
    messages = sorted(r.getMessage().split(": ", 1)[1] for r in caplog.records)
    assert [m.split(" (")[0] for m in messages] == [
        "setup.cfg metadata.classifiers file bad could not be read",
        "setup.cfg metadata.long_description file bad could not be read",
    ]
