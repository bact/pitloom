# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.given_path`: a path keeps the spelling the
user gave, through a copy, a pickle and a configuration's ``asdict``.

See also: tests/cli/test_cli_typed_spelling.py (every command naming its
target as typed).
"""

from __future__ import annotations

import copy
import dataclasses
import os
import pickle  # nosec B403 # round-trips its own value
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.config_cascade import load_config_file
from pitloom.core.given_path import GivenPath, TypedPath, given_spelling

pytestmark = pytest.mark.platform

_REBUILDS = [
    copy.copy,
    copy.deepcopy,
    *(
        lambda p, n=n: pickle.loads(pickle.dumps(p, protocol=n))  # nosec B301
        for n in range(pickle.HIGHEST_PROTOCOL + 1)
    ),
]
_REBUILD_IDS = [
    "copy",
    "deepcopy",
    *(f"pickle-{n}" for n in range(pickle.HIGHEST_PROTOCOL + 1)),
]
_URL = "https://h//x/../y.whl"


@pytest.mark.parametrize("rebuild", _REBUILDS, ids=_REBUILD_IDS)
def test_a_given_path_survives_copy_and_pickle(
    rebuild: Callable[[GivenPath], object],
) -> None:
    """With its spelling, and still equal to (and hashed as) the path."""
    path = GivenPath("/abs/reg.json", "reg.json")
    again = rebuild(path)
    assert isinstance(again, GivenPath)
    assert (again, again.given, repr(again)) == (path, "reg.json", "'/abs/reg.json'")
    assert hash(again) == hash("/abs/reg.json")


def test_a_config_holding_a_given_path_converts_to_a_dict(tmp_path: Path) -> None:
    """``load_config_file`` keeps the spelling of a relative ``id-registry``;
    ``dataclasses.asdict`` deep-copies it."""
    config = tmp_path / "c.toml"
    config.write_text('[tool.pitloom]\nid-registry = "sub/r.json"\n', "utf-8")
    loaded = load_config_file(config)
    assert isinstance(loaded.id_registry, GivenPath)
    said = dataclasses.asdict(loaded)["id_registry"]
    assert (said, said.given) == (str(tmp_path / "sub/r.json"), "sub/r.json")


def test_a_typed_path_is_the_path_and_keeps_the_text() -> None:
    """Equal to, hashed and read as ``Path(text)``, which collapses ``//``."""
    typed = TypedPath(_URL)
    assert str(typed) != _URL  # the spelling Path loses
    assert (typed.given, typed, os.fspath(typed)) == (_URL, Path(_URL), str(Path(_URL)))
    assert hash(typed) == hash(Path(_URL))
    assert isinstance(typed, Path)


@pytest.mark.parametrize("rebuild", _REBUILDS, ids=_REBUILD_IDS)
def test_a_typed_path_survives_copy_and_pickle(
    rebuild: Callable[[TypedPath], object],
) -> None:
    again = rebuild(TypedPath(_URL))
    assert isinstance(again, TypedPath)
    assert (again.given, again) == (_URL, Path(_URL))


@dataclasses.dataclass
class _Holder:
    path: TypedPath


@pytest.mark.parametrize(
    "rebuild",
    [*_REBUILDS, lambda p: dataclasses.asdict(_Holder(p))["path"]],
    ids=[*_REBUILD_IDS, "asdict"],
)
def test_a_typed_path_of_a_resolved_path_stays_that_file(
    rebuild: Callable[[TypedPath], object],
) -> None:
    """Rebuilt from the path, not from the text typed for it: ``x.whl``
    typed, ``/abs/dir/x.whl`` read, the rebuilt path still that file."""
    resolved = str(Path("/abs/dir/x.whl").absolute())
    again = rebuild(TypedPath(GivenPath(resolved, "x.whl")))
    assert isinstance(again, TypedPath)
    assert (str(again), again.given, given_spelling(again)) == (
        resolved,
        "x.whl",
        "x.whl",
    )


@pytest.mark.parametrize(
    "derive",
    [
        lambda p: p.absolute(),
        lambda p: p.parent,
        lambda p: p / "z",
        lambda p: TypedPath(Path("a//b")),
        lambda p: TypedPath("a", "b"),
    ],
    ids=["absolute", "parent", "joined", "from-path", "two-parts"],
)
def test_a_derived_typed_path_names_itself(
    derive: Callable[[TypedPath], TypedPath],
) -> None:
    """A new path, not the text typed for another."""
    derived = derive(TypedPath(_URL))
    assert derived.given == str(derived)


def test_an_empty_typed_path_keeps_the_empty_text() -> None:
    assert (str(TypedPath("")), TypedPath("").given) == (".", "")


@pytest.mark.parametrize(
    ("path", "spelling"),
    [
        (TypedPath(_URL), _URL),
        (GivenPath("/abs/r.json", "r.json"), "r.json"),
        (GivenPath("/abs/r.json", TypedPath("a//r.json")), "a//r.json"),
        ("a//b", "a//b"),
        (Path("a//b"), Path("a/b")),
    ],
    ids=["typed", "given", "given-of-typed", "str", "path"],
)
def test_given_spelling(path: str | os.PathLike[str], spelling: object) -> None:
    assert given_spelling(path) == spelling
