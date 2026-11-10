# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which release and file of a PyPI answer are read
(:mod:`pitloom.extract.remote.pypi_select`): pure, the environment's tag
order patched, every pick the same for the answer in any order.

See also: tests/extract/remote/test_pypi_fetch.py (the resolver around it).
"""

from __future__ import annotations

from typing import Any

import pytest
from packaging.tags import Tag
from packaging.version import Version

from pitloom.extract.remote import pypi_select
from pitloom.extract.remote.pypi_select import (
    PRERELEASE,
    SDIST,
    STABLE,
    WHEEL,
    YANKED,
    ReleaseChoice,
    file_name_problem,
    pick_sdist,
    pick_wheel,
    read_files,
    select_release,
    versions_equal_to,
)

_SHA = "ab" * 32
_V1 = Version("1.0")


def _entry(filename: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "filename": filename,
        "packagetype": "bdist_wheel" if filename.endswith(".whl") else "sdist",
        "url": f"https://files.pythonhosted.org/p/{filename}",
        "digests": {"sha256": _SHA},
        "yanked": False,
        "yanked_reason": None,
    }
    entry.update(extra)
    return entry


@pytest.mark.parametrize(
    "filename",
    [
        "../x-1.0.tar.gz",
        "a/x-1.0-py3-none-any.whl",
        "a\\x-1.0-py3-none-any.whl",
        "x-1.0.tar.gz\x00.whl",
        "x-1.0\n.tar.gz",
        "x-1.0\u202e.tar.gz",
        ".x-1.0.tar.gz",
        "x-1.0.tar.gz.",
        "x-1.0.tar.gz ",
        "C:x-1.0.tar.gz",
        "x-1..0.tar.gz",
        "nul.foo-1.0-py3-none-any.whl",
        "aux.x-1.0.tar.gz",
        "com1.x-1.0.zip",
        "LPT9 .x-1.0.zip",
        "CONOUT$.x-1.0.zip",
        "com\u00b9.x-1.0.zip",
        "\u212aeras-1.0.tar.gz",
        "x" * 250 + "-1.0.tar.gz",
        "",
    ],
    ids=[
        "dotdot",
        "slash",
        "backslash",
        "nul",
        "newline",
        "bidi",
        "leading-dot",
        "trailing-dot",
        "trailing-space",
        "drive",
        "inner-dotdot",
        "nul",
        "aux",
        "com1",
        "lpt-space",
        "conout",
        "com-superscript",
        "kelvin",
        "too-long",
        "empty",
    ],
)
def test_a_hostile_file_name_is_refused(filename: str) -> None:
    assert file_name_problem(filename) is not None
    _files, refused = read_files([_entry(filename)], "x", _V1)
    assert [name for name, _why in refused] == [filename]


@pytest.mark.parametrize(
    ("filename", "accepted"),
    [
        ("x-1.0-py3-none-any.whl", True),
        ("X_-1.0.0-py3-none-any.whl", False),  # name x_ is not x
        ("x-1.0.0-py3-none-any.whl", True),  # 1.0.0 == 1.0
        ("x-1.1-py3-none-any.whl", False),
        ("y-1.0-py3-none-any.whl", False),
        ("x-1.0-bad.whl", False),
        ("x-1.0.tar.gz", True),
        ("X-1.0.zip", True),
        ("x-1.0.tar.bz2", False),
        ("x-2.0.tar.gz", False),
    ],
    ids=[
        "wheel",
        "other-name",
        "pep440-equal",
        "other-version",
        "other-project",
        "bad-wheel",
        "sdist",
        "zip",
        "bz2",
        "sdist-other-version",
    ],
)
def test_a_file_is_a_candidate_only_of_its_own_release(
    filename: str, accepted: bool
) -> None:
    files, refused = read_files([_entry(filename)], "x", _V1)
    assert ([f.filename for f in files] == [filename]) is accepted
    assert bool(refused) is not accepted


@pytest.mark.parametrize(
    ("extra", "sha256", "yanked", "reason"),
    [
        ({"digests": {"sha256": _SHA.upper()}}, _SHA, False, None),
        ({"digests": {"sha256": "ab" * 31}}, None, False, None),
        ({"digests": {"md5": "x"}}, None, False, None),
        ({"digests": ["x"]}, None, False, None),
        ({"yanked": "true", "yanked_reason": 7}, _SHA, False, None),
        ({"yanked": True, "yanked_reason": "  "}, _SHA, True, None),
        ({"yanked": True, "yanked_reason": "bad build"}, _SHA, True, "bad build"),
    ],
    ids=[
        "upper-digest",
        "short-digest",
        "no-sha256",
        "digests-list",
        "wrong-types",
        "blank-reason",
        "yanked",
    ],
)
def test_each_value_of_an_entry_is_type_checked(
    extra: dict[str, Any], sha256: str | None, yanked: bool, reason: str | None
) -> None:
    files, _refused = read_files([_entry("x-1.0.tar.gz", **extra)], "x", _V1)
    assert (files[0].sha256, files[0].yanked, files[0].yanked_reason) == (
        sha256,
        yanked,
        reason,
    )


@pytest.mark.parametrize(
    "entries",
    [
        [_entry("x-1.0-py2.4.egg", packagetype="bdist_egg")],
        ["x-1.0.tar.gz", None, 3],
        {"filename": "x-1.0.tar.gz"},
        [{**_entry("x-1.0.tar.gz"), "filename": 3}],
        [_entry("x-1.0.tar.gz", packagetype=None)],
    ],
    ids=["egg", "not-dicts", "not-a-list", "name-not-text", "no-type"],
)
def test_what_is_no_wheel_or_sdist_is_left_out_quietly(entries: object) -> None:
    assert read_files(entries, "x", _V1) == ([], [])


@pytest.mark.parametrize(
    "filename",
    ["console-1.0.tar.gz", "nul-1.0.tar.gz", "com10-1.0.tar.gz", "aux_x-1.0.zip"],
    ids=["console", "nul-version", "com10", "aux-underscore"],
)
def test_a_name_that_only_starts_like_a_device_is_read(filename: str) -> None:
    assert file_name_problem(filename) is None


def test_a_file_name_listed_twice_is_refused_once() -> None:
    """Either entry could be the file PyPI serves: neither is read, the name
    is refused once, and the order of the answer changes nothing."""
    entries = [
        _entry("x-1.0.tar.gz"),
        _entry("x-1.0.tar.gz", url="https://files.pythonhosted.org/p/other"),
        _entry("x-1.0.tar.gz", url=None),
        _entry("x-1.0.zip"),
    ]
    for order in (entries, entries[::-1]):
        files, refused = read_files(order, "x", _V1)
        assert [f.filename for f in files] == ["x-1.0.zip"]
        assert refused == [
            ("x-1.0.tar.gz", "the answer lists the file name more than once")
        ]


def test_an_entry_without_a_url_is_refused() -> None:
    _files, refused = read_files([_entry("x-1.0.tar.gz", url=None)], "x", _V1)
    assert refused == [("x-1.0.tar.gz", "the answer gives no download URL")]


def _release(*names: str, **extra: Any) -> list[dict[str, Any]]:
    return [_entry(name, **extra) for name in names]


@pytest.mark.parametrize(
    ("releases", "expected"),
    [
        (
            {
                "1.0": _release("x-1.0.tar.gz"),
                "2.0b1": _release("x-2.0b1.tar.gz"),
                "1.5": _release("x-1.5.tar.gz", yanked=True),
            },
            ReleaseChoice("1.0", STABLE),
        ),
        (
            {"9.0": _release("x-9.0.tar.gz"), "10.0": _release("x-10.0.tar.gz")},
            ReleaseChoice("10.0", STABLE),
        ),
        (
            {
                "1.0rc1": _release("x-1.0rc1.tar.gz"),
                "0.9": _release("x-0.9.tar.gz", yanked=True),
            },
            ReleaseChoice("1.0rc1", PRERELEASE),
        ),
        (
            {
                "1.0": _release("x-1.0.tar.gz", yanked=True),
                "2.0.dev1": _release("x-2.0.dev1.tar.gz", yanked=True),
            },
            ReleaseChoice("2.0.dev1", YANKED),
        ),
        (
            {
                "1.0": [*_release("x-1.0.tar.gz", yanked=True), _entry("x-1.0.zip")],
                "0.9": _release("x-0.9.tar.gz"),
            },
            ReleaseChoice("1.0", STABLE),
        ),
        (
            {
                "2.0": _release("x-2.0.tar.gz", digests={}),
                "3.0": [],
                "4.0": _release("y-4.0.tar.gz"),
                "latest": _release("x-latest.tar.gz"),
                "1.0": _release("x-1.0.tar.gz"),
            },
            ReleaseChoice("1.0", STABLE),
        ),
        (
            {"1.0": _release("x-1.0.tar.gz"), "1.0.0": _release("x-1.0.0.tar.gz")},
            ReleaseChoice("1.0.0", STABLE),
        ),
        (
            {"2.0": _release("x-2.0.tar.gz", digests={}), "3.0": "x"},
            None,
        ),
    ],
    ids=[
        "stable-first",
        "pep440-order",
        "prerelease-only",
        "yanked-only",
        "partly-yanked",
        "unusable-skipped",
        "tie-on-key",
        "none-usable",
    ],
)
def test_the_release_cascade(
    releases: dict[str, Any], expected: ReleaseChoice | None
) -> None:
    """The pick is the same for the answer in reverse order."""
    assert select_release(releases, "x") == expected
    reverse = dict(reversed(list(releases.items())))
    assert list(reverse) != list(releases)
    assert select_release(reverse, "x") == expected


_LONG = "1." + "9" * 5000


def test_an_overlong_version_is_no_release() -> None:
    """A number past Python's int conversion limit is no version: left out,
    never a crash (a bare ``ValueError`` from ``int()``)."""
    releases: dict[str, object] = {
        _LONG: _release(f"x-{_LONG}.tar.gz"),
        "1.0": _release("x-1.0.tar.gz"),
    }
    assert select_release(releases, "x") == ReleaseChoice("1.0", STABLE)
    assert versions_equal_to(releases, Version("1.0")) == ["1.0"]
    _files, refused = read_files([_entry(f"x-{_LONG}-py3-none-any.whl")], "x", _V1)
    assert len(refused) == 1


def test_versions_equal_to() -> None:
    releases: dict[str, object] = {"1.0.0": [], "1.0": [], "1.0.1": [], "bad": []}
    assert versions_equal_to(releases, Version("1")) == ["1.0", "1.0.0"]


_TAGS = [
    Tag("cp313", "cp313", "linux"),
    Tag("py3", "none", "linux"),
    Tag("py3", "none", "any"),
]


@pytest.fixture(name="tags")
def _tags(monkeypatch: pytest.MonkeyPatch) -> list[Tag]:
    """The environment's tags, best first, patched."""
    monkeypatch.setattr(pypi_select, "_environment_tags", lambda: list(_TAGS))
    return _TAGS


def _wheels(*names: str, yanked: tuple[str, ...] = ()) -> list[pypi_select.ReleaseFile]:
    entries = [_entry(n, yanked=n in yanked) for n in names]
    return read_files(entries, "x", _V1)[0]


@pytest.mark.usefixtures("tags")
@pytest.mark.parametrize(
    ("names", "yanked", "expected", "compatible"),
    [
        (
            ("x-1.0-py3-none-any.whl", "x-1.0-cp313-cp313-linux.whl"),
            (),
            "x-1.0-cp313-cp313-linux.whl",
            2,
        ),
        (
            ("x-1.0-py3-none-any.whl", "x-1.0-cp313-cp313-win_amd64.whl"),
            (),
            "x-1.0-py3-none-any.whl",
            1,
        ),
        (
            ("x-1.0-1b-py3-none-any.whl", "x-1.0-1a-py3-none-any.whl"),
            (),
            "x-1.0-1a-py3-none-any.whl",
            2,
        ),
        (
            ("x-1.0-py3-none-any.whl", "x-1.0-cp313-cp313-linux.whl"),
            ("x-1.0-cp313-cp313-linux.whl",),
            "x-1.0-py3-none-any.whl",
            2,
        ),
        (
            ("x-1.0-cp313-cp313-linux.whl", "x-1.0-py3-none-any.whl"),
            ("x-1.0-cp313-cp313-linux.whl", "x-1.0-py3-none-any.whl"),
            "x-1.0-cp313-cp313-linux.whl",
            2,
        ),
        (("x-1.0-py2.py3-none-linux.whl",), (), "x-1.0-py2.py3-none-linux.whl", 1),
    ],
    ids=[
        "best-rank",
        "one-matches",
        "tie-on-name",
        "yanked-last",
        "all-yanked",
        "tag-set",
    ],
)
def test_the_wheel_pick(
    names: tuple[str, ...], yanked: tuple[str, ...], expected: str, compatible: int
) -> None:
    files = _wheels(*names, yanked=yanked)
    # Both orders of the candidates themselves: read_files sorts by name.
    for order in (files, files[::-1]):
        pick = pick_wheel(order)
        assert pick is not None
        assert (pick.file.filename, pick.compatible) == (expected, compatible)


@pytest.mark.usefixtures("tags")
def test_no_wheel_for_this_environment() -> None:
    assert pick_wheel(_wheels("x-1.0-cp27-cp27m-win32.whl")) is None
    assert pick_wheel(read_files([_entry("x-1.0.tar.gz")], "x", _V1)[0]) is None


def test_the_tag_order_is_the_running_environments() -> None:
    assert pypi_select._environment_tags()  # pylint: disable=protected-access


@pytest.mark.parametrize(
    ("names", "yanked", "expected"),
    [
        (("x-1.0.zip", "x-1.0.tar.gz"), (), "x-1.0.tar.gz"),
        (("X-1.0.zip", "x-1.0.tar.gz"), (), "x-1.0.tar.gz"),
        (("x-1.0.zip", "X-1.0.zip"), (), "X-1.0.zip"),
        (("x-1.0.zip", "x-1.0.tar.gz"), ("x-1.0.tar.gz",), "x-1.0.zip"),
        (("x-1.0.tar.gz",), (), "x-1.0.tar.gz"),
    ],
    ids=["tar-gz-first", "tar-gz-before-name", "name-tie", "yanked-last", "one"],
)
def test_the_sdist_pick(
    names: tuple[str, ...], yanked: tuple[str, ...], expected: str
) -> None:
    files = read_files([_entry(n, yanked=n in yanked) for n in names], "x", _V1)[0]
    for order in (files, files[::-1]):
        pick = pick_sdist(order)
        assert pick is not None and pick.file.kind == SDIST
        assert (pick.file.filename, pick.count) == (expected, len(names))


def test_no_sdist() -> None:
    files = read_files([_entry("x-1.0-py3-none-any.whl")], "x", _V1)[0]
    assert files[0].kind == WHEEL
    assert pick_sdist(files) is None
