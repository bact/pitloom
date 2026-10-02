# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which ``.dist-info`` is a wheel's own, the bounded member read and the
Zstandard error probe.

See also: tests/extract/test_wheel_identity.py (``read_wheel``),
tests/test_wheel_identity_surfaces.py (every surface) and
tests/assemble/test_embed_internals.py (``_find_dist_info_prefix``).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from pitloom.core import wheel_dist_info
from pitloom.core.wheel_dist_info import (
    own_dist_info,
    read_member_bounded,
    resolve_own_dist_info,
)

WHEEL = "demo-1.0-py3-none-any.whl"


def _members(*dist_infos: str) -> list[str]:
    return [f"{d}/METADATA" for d in dist_infos] + ["demo/__init__.py"]


@pytest.mark.parametrize(
    ("wheel", "dirs", "prefix", "problem"),
    [
        (WHEEL, ["demo-1.0.dist-info"], "demo-1.0.dist-info/", None),
        # PEP 503 name and PEP 440 version equivalence: not a disagreement.
        (
            "My.Pkg-1.0-py3-none-any.whl",
            ["my_pkg-1.0.0.dist-info"],
            "my_pkg-1.0.0.dist-info/",
            None,
        ),
        # The file name picks among several; the foreign one is ignored.
        (
            WHEEL,
            ["demo-1.0.dist-info", "evil-9.9.dist-info"],
            "demo-1.0.dist-info/",
            None,
        ),
        (
            WHEEL,
            ["evil-9.9.dist-info", "demo-1.0.dist-info"],
            "demo-1.0.dist-info/",
            None,
        ),
        # Not a wheel file name: the only one, silently.
        ("pkg.whl", ["demo-1.0.dist-info"], "demo-1.0.dist-info/", None),
        # A wheel file name that names another directory: the only one, said.
        (WHEEL, ["evil-9.9.dist-info"], "evil-9.9.dist-info/", "names no"),
        # Zero, or several none of which the file name names.
        (WHEEL, [], None, "no top-level"),
        (WHEEL, ["a-1.dist-info", "b-1.dist-info"], None, "several"),
        ("pkg.whl", ["a-1.dist-info", "b-1.dist-info"], None, "several"),
        # Two directories spelling the one name: ambiguous, not "first".
        (WHEEL, ["demo-1.0.dist-info", "Demo-1.0.dist-info"], None, "several"),
    ],
    ids=[
        "plain",
        "pep503-pep440",
        "foreign-after",
        "foreign-before",
        "renamed-file",
        "disagreement",
        "none",
        "several",
        "renamed-several",
        "same-name-twice",
    ],
)
def test_the_own_dist_info_and_what_is_said(
    wheel: str, dirs: list[str], prefix: str | None, problem: str | None
) -> None:
    choice = resolve_own_dist_info(wheel, _members(*dirs))

    assert choice.prefix == prefix
    assert own_dist_info(wheel, _members(*dirs)) == prefix
    if problem is None:
        assert choice.problem is None
    else:
        assert choice.problem is not None and problem in choice.problem


@pytest.mark.parametrize(
    "members",
    [
        # Nested, vendored: never the wheel's own, wherever it sorts.
        ["demo/_vendor/evil-9.9.dist-info/METADATA"],
        ["demo/_vendor/demo-1.0.dist-info/METADATA"],
        # A file, not a directory.
        ["demo-1.0.dist-info"],
    ],
)
def test_only_a_top_level_directory_is_the_wheels_own(members: list[str]) -> None:
    assert own_dist_info(WHEEL, members) is None
    assert own_dist_info(WHEEL, [*members, "demo-1.0.dist-info/METADATA"]) == (
        "demo-1.0.dist-info/"
    )


def test_the_choice_does_not_depend_on_member_order() -> None:
    names = _members("demo-1.0.dist-info", "evil-9.9.dist-info", "x-1.dist-info")
    assert own_dist_info(WHEEL, names) == own_dist_info(WHEEL, names[::-1])


def _zip_with(data: bytes, compression: int) -> tuple[zipfile.ZipFile, zipfile.ZipInfo]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zf:
        zf.writestr("m", data)
    zf = zipfile.ZipFile(buffer)
    return zf, zf.getinfo("m")


@pytest.mark.parametrize(
    ("size", "limit", "expected"),
    [(10, 10, True), (11, 10, False), (0, 10, True), (20000, 8192, False)],
)
def test_the_bounded_read_returns_up_to_the_limit(
    size: int, limit: int, expected: bool
) -> None:
    data = b"x" * size
    zf, info = _zip_with(data, zipfile.ZIP_DEFLATED)
    with zf:
        assert read_member_bounded(zf, info, limit) == (data if expected else None)


class _Endless(io.RawIOBase):
    """A member that never ends; counts what it hands out."""

    def __init__(self) -> None:
        self.served = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        size = 8192 if size < 0 else size
        self.served += size
        if self.served > 64 * 1024 * 1024:
            raise AssertionError("read past the cap without stopping")
        return b"x" * size


def test_the_bounded_read_stops_at_the_cap_whatever_the_declared_size() -> None:
    stream = _Endless()
    zf = Mock(spec=zipfile.ZipFile)
    zf.open.return_value = stream
    info = zipfile.ZipInfo("m")
    info.file_size = 1  # a lie

    assert read_member_bounded(zf, info, 1000) is None
    assert stream.served <= 1000 + 8192


class _ZstdError(Exception):
    pass


def _importer(result: object) -> Any:
    def import_module(_name: str) -> object:
        if isinstance(result, Exception):
            raise result
        return result

    return import_module


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (SimpleNamespace(ZstdError=_ZstdError), (_ZstdError,)),
        (SimpleNamespace(ZstdError="not a class"), ()),
        (SimpleNamespace(), ()),
        (ImportError("no compression.zstd"), ()),
    ],
    ids=["present", "not-a-class", "absent-name", "no-module"],
)
def test_the_zstd_error_is_used_only_when_the_module_defines_one(
    monkeypatch: pytest.MonkeyPatch, module: object, expected: tuple[type, ...]
) -> None:
    monkeypatch.setattr(
        wheel_dist_info, "importlib", SimpleNamespace(import_module=_importer(module))
    )
    assert wheel_dist_info._zstd_errors() == expected
