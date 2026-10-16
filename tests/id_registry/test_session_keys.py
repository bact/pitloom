# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :meth:`~pitloom.id_registry.IdRegistrySession.lookup_key`,
``record_key`` and ``recorded_keys``, and the hash-less pin of
:meth:`~pitloom.id_registry.IdRegistry.lookup`.

See also: test_session.py (``lookup_id`` and the claim rule),
test_session_alias.py (the alias's real-file, tie and count rules),
test_keys_alias.py (:func:`~pitloom.id_registry.alias_candidates`).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    Alias,
    IdRegistry,
    IdRegistrySession,
    LookupKey,
)
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_A, _B = "a" * 64, "b" * 64
_RLO = "\u202e"
_NFC = unicodedata.normalize("NFC", "\u00e9")
_NFD = unicodedata.normalize("NFD", _NFC)
_NONE, _CANON, _LAYOUT = Alias.NONE, Alias.CANONICAL, Alias.LAYOUT


@pytest.fixture(autouse=True)
def _empty_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The registries' root (the current directory) holds none of the keys,
    so an alias is never refused for a real file at its shorter key."""
    monkeypatch.chdir(tmp_path)


def _registry() -> IdRegistry:
    rows = {
        "src/demo/x.py": ("File-1", _A),  # canonical; demo/x.py is its alias
        "demo/y.py": ("File-2", _A),  # alias of src/demo/y.py
        "evil\\u202ex.py": ("File-3", _A),  # imported, escaped
        "plain.py": ("File-4", _A),
        "lib/demo/z.py": ("File-5", _A),  # with the next: a tie for demo/z.py
        "src/demo/z.py": ("File-6", _A),
        "src/demo/v.py": ("File-7", _B),  # other content
        "demo/e\\u202e.py": ("File-8", _A),  # imported alias, escaped
        "src/demo/f\\u202e.py": ("File-9", _A),  # imported canonical, escaped
        f"src/demo/{_NFC}.py": ("File-10", _A),
    }
    entries = {(FILE_TYPE, k): (f"{_NS}#{i}", s) for k, (i, s) in rows.items()}
    entries[(AI_PACKAGE_TYPE, "src/demo/w.py")] = (f"{_NS}#AIPackage-1", _A)
    return make_registry(entries)


def _lookup(
    session: IdRegistrySession,
    alias: Alias,
    key: str,
    sha: str | None,
    claimant: str = "c",
) -> tuple[str | None, int]:
    calls: list[None] = []
    found = session.lookup_key(
        claimant,
        FILE_TYPE,
        LookupKey(key, alias),
        sha256=sha,
        on_miss=lambda: calls.append(None),
    )
    return found, len(calls)


_HIT_CASES = [
    # exact raw: every mode, gated or not; exact is tried before the alias
    (_NONE, "plain.py", _A, "File-4", "plain.py"),
    (_NONE, "plain.py", None, "File-4", "plain.py"),
    (_LAYOUT, "plain.py", _A.upper(), "File-4", "plain.py"),
    (_CANON, "plain.py", None, "File-4", "plain.py"),
    (_LAYOUT, "src/demo/x.py", _A, "File-1", "src/demo/x.py"),
    # exact display-escaped: the raw key is recorded
    (_NONE, f"evil{_RLO}x.py", _A, "File-3", f"evil{_RLO}x.py"),
    (_NONE, f"evil{_RLO}x.py", None, "File-3", f"evil{_RLO}x.py"),
    # canonical alias: the lookup key is recorded (harvest promotes it)
    (_CANON, "src/demo/y.py", _A, "File-2", "src/demo/y.py"),
    (_CANON, f"src/demo/e{_RLO}.py", _A, "File-8", f"src/demo/e{_RLO}.py"),
    # layout alias: the held key is recorded
    (_LAYOUT, "demo/x.py", _A, "File-1", "src/demo/x.py"),
    (_LAYOUT, f"demo/f{_RLO}.py", _A, "File-9", "src/demo/f\\u202e.py"),
    (_LAYOUT, f"demo/{_NFD}.py", _A, "File-10", f"src/demo/{_NFC}.py"),
]

_MISS_CASES = [
    (_NONE, "plain.py", _B),  # gated, other content
    (_NONE, "demo/x.py", _A),  # no alias mode: no alias
    (_NONE, "src/demo/y.py", _A),
    (_NONE, "demo/x.py", None),
    (_CANON, "src/demo/y.py", None),  # ungated: no alias
    (_LAYOUT, "demo/x.py", None),
    (_CANON, "demo/x.py", _A),  # wrong direction
    (_LAYOUT, "src/demo/y.py", _A),
    (_NONE, "nothere/a.py", _A),
    (_CANON, "src/nothere/a.py", _A),
    (_LAYOUT, "nothere/a.py", _A),
    (_LAYOUT, "demo/w.py", _A),  # held only for another type
    (_LAYOUT, "demo/v.py", _A),  # held with other content
    (_LAYOUT, "demo/z.py", _A),  # two candidates: a tie
]


@pytest.mark.parametrize(
    ("alias", "key", "sha", "spdx_id", "recorded"),
    _HIT_CASES,
    ids=[f"hit{n}" for n in range(len(_HIT_CASES))],
)
def test_lookup_key_hit(
    alias: Alias, key: str, sha: str | None, spdx_id: str, recorded: str
) -> None:
    session = IdRegistrySession(_registry())

    found, misses = _lookup(session, alias, key, sha)

    assert (found, misses) == (f"{_NS}#{spdx_id}", 0)
    assert dict(session.recorded_keys()) == {found: (FILE_TYPE, recorded)}
    assert session.claimed_ids() == [found]


@pytest.mark.parametrize(
    ("alias", "key", "sha"),
    _MISS_CASES,
    ids=[f"miss{n}" for n in range(len(_MISS_CASES))],
)
def test_lookup_key_miss(alias: Alias, key: str, sha: str | None) -> None:
    session = IdRegistrySession(_registry())

    assert _lookup(session, alias, key, sha) == (None, 1)
    assert not session.recorded_keys()
    assert not session.claimed_ids()


def test_alias_tie_is_a_miss_with_one_info(caplog: pytest.LogCaptureFixture) -> None:
    session = IdRegistrySession(_registry())

    with caplog.at_level("INFO", logger="pitloom"):
        assert _lookup(session, _LAYOUT, "demo/z.py", _A) == (None, 1)

    infos = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert len(infos) == 1
    assert "ID registry:" in infos[0]
    assert "demo/z.py" in infos[0]


@pytest.mark.parametrize(
    ("first", "second", "held"),
    [
        ((_NONE, "src/demo/x.py"), (_LAYOUT, "demo/x.py"), "src/demo/x.py"),
        ((_LAYOUT, "demo/x.py"), (_LAYOUT, "demo/x.py"), "src/demo/x.py"),
        ((_CANON, "src/demo/y.py"), (_NONE, "demo/y.py"), "demo/y.py"),
    ],
    ids=["exact-alias", "alias-alias", "canon-exact"],
)
def test_claim_collision_as_lookup_id(
    first: tuple[Alias, str],
    second: tuple[Alias, str],
    held: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = IdRegistrySession(_registry())
    claimed, _ = _lookup(session, *first, _A, claimant="first")
    recorded = dict(session.recorded_keys())

    with caplog.at_level("WARNING", logger="pitloom"):
        assert _lookup(session, *second, _A, claimant="second") == (None, 0)

    assert claimed is not None
    assert dict(session.recorded_keys()) == recorded == {claimed: recorded[claimed]}
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "registered for both" in warnings[0]
    # one claim rule for both APIs: a lookup_id claim rejects lookup_key
    other = IdRegistrySession(_registry())
    assert other.lookup_id("first", FILE_TYPE, [held], sha256=_A) == claimed
    assert _lookup(other, *second, _A, claimant="second") == (None, 0)
    assert not other.recorded_keys()


def test_alias_sees_an_id_registered_after_a_miss() -> None:
    registry = _registry()
    session = IdRegistrySession(registry)
    layout = LookupKey("demo/n.py", _LAYOUT)
    assert session.lookup_key("c", FILE_TYPE, layout, sha256=_A) is None

    registered = registry.register(FILE_TYPE, "src/demo/n.py", sha256=_A)
    assert _lookup(session, _LAYOUT, "demo/n.py", _A) == (registered, 0)

    session.register_id("r", FILE_TYPE, "src/demo/m.py", sha256=_A)
    assert _lookup(session, _LAYOUT, "demo/m.py", _A) == (None, 0)  # claimed


def test_record_key_setdefault_hit_wins() -> None:
    session = IdRegistrySession(_registry())
    hit = f"{_NS}#File-1"
    session.record_key(hit, FILE_TYPE, "minted/first.py")
    _lookup(session, _LAYOUT, "demo/x.py", _A)  # a hit replaces it
    session.record_key(hit, FILE_TYPE, "late.py")  # and is kept
    session.record_key(f"{_NS}#File-99", FILE_TYPE, f"new{_RLO}.py")
    session.record_key(f"{_NS}#File-99", FILE_TYPE, "again.py")

    assert dict(session.recorded_keys()) == {
        hit: (FILE_TYPE, "src/demo/x.py"),
        f"{_NS}#File-99": (FILE_TYPE, f"new{_RLO}.py"),
    }


def test_recorded_keys_read_only_and_absent_for_unrecorded() -> None:
    registry = _registry()
    session = IdRegistrySession(registry)
    registered = session.register_id("r", FILE_TYPE, "new.py", sha256=_A)
    view = session.recorded_keys()

    assert registered is not None
    assert registered not in view and not view
    with pytest.raises(TypeError):
        view[registered] = (FILE_TYPE, "new.py")  # type: ignore[index]
    session.record_key(registered, FILE_TYPE, "new.py")
    assert view == {registered: (FILE_TYPE, "new.py")}  # a live view


def test_no_registry_records_nothing() -> None:
    session = IdRegistrySession(None)

    assert _lookup(session, _LAYOUT, "demo/x.py", _A) == (None, 0)
    session.record_key(f"{_NS}#File-1", FILE_TYPE, "x.py")
    assert not session.recorded_keys()
    assert not session.claimed_ids()


@pytest.mark.parametrize(
    ("held", "sha256", "pin", "hit"),
    [
        (None, _A, True, True),
        (None, _A, False, False),
        (_A, _A.upper(), True, True),
        (_B, _A, True, False),
        (_B, None, True, True),
        ("absent", _A, True, False),
    ],
    ids=["hashless-pin", "hashless-gated", "equal", "other", "ungated", "absent"],
)
def test_pin_without_hash(
    held: str | None, sha256: str | None, pin: bool, hit: bool
) -> None:
    """With *pin_without_hash* a hash-less entry also hits a gated lookup;
    only an entry recording another hash misses. Both the registry and
    the session agree."""
    entries = (
        {}
        if held == "absent"
        else {(DATASET_PACKAGE_TYPE, "d"): (f"{_NS}#DatasetPackage-1", held)}
    )
    registry = make_registry(entries)
    want = f"{_NS}#DatasetPackage-1" if hit else None
    missed: list[bool] = []

    found = registry.lookup(
        DATASET_PACKAGE_TYPE, ["d"], sha256=sha256, pin_without_hash=pin
    )
    claimed = IdRegistrySession(registry).lookup_key(
        "c",
        DATASET_PACKAGE_TYPE,
        LookupKey("d"),
        sha256=sha256,
        pin_without_hash=pin,
        on_miss=lambda: missed.append(True),
    )

    assert (found, claimed, missed) == (want, want, [] if hit else [True])
