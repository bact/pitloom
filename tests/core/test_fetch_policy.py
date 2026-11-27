# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one resolver of a remote fetch's policy
(:func:`pitloom.core.config_cascade.resolve_fetch_policy`): the argument,
else the explicit config, else the default, for ``offline`` and
``max-download-bytes``; the caller's ``check_url`` as given.

See also: tests/test_fetch_policy_surfaces.py (every surface resolves it
alike).
"""

from __future__ import annotations

from typing import cast

import pytest

from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import resolve_fetch_policy
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES
from pitloom.messages import code_of
from tests.argument_errors import integer_refusal

_CONFIG = PitloomConfig(offline=True, max_download_bytes=1000)


@pytest.mark.parametrize(
    ("config", "offline", "cap", "expected"),
    [
        (None, None, None, RemoteFetchPolicy(DEFAULT_MAX_DOWNLOAD_BYTES, False)),
        (_CONFIG, None, None, RemoteFetchPolicy(1000, True)),
        (_CONFIG, False, 2000, RemoteFetchPolicy(2000, False)),
        (None, True, 1, RemoteFetchPolicy(1, True)),
        (PitloomConfig(), False, None, RemoteFetchPolicy(DEFAULT_MAX_DOWNLOAD_BYTES)),
    ],
    ids=["defaults", "config", "arguments-beat-config", "arguments", "explicit-off"],
)
def test_the_argument_beats_the_config_beats_the_default(
    config: PitloomConfig | None,
    offline: bool | None,
    cap: int | None,
    expected: RemoteFetchPolicy,
) -> None:
    got = resolve_fetch_policy(config, offline=offline, max_download_bytes=cap)
    assert got == expected


def test_the_check_is_kept_as_given() -> None:
    checked: list[str] = []
    check = checked.append
    assert resolve_fetch_policy(None, check_url=check).check_url is check
    assert resolve_fetch_policy(None).check_url is None


@pytest.mark.parametrize("bad", [0, -1, True, 1.5], ids=repr)
def test_an_invalid_cap_is_refused_from_either_source(bad: object) -> None:
    with pytest.raises(integer_refusal(bad), match="max.download.bytes"):
        resolve_fetch_policy(None, max_download_bytes=cast(int, bad))
    with pytest.raises(integer_refusal(bad), match="max.download.bytes"):
        resolve_fetch_policy(PitloomConfig(max_download_bytes=cast(int, bad)))


def test_the_policy_is_frozen() -> None:
    policy = RemoteFetchPolicy()
    with pytest.raises(AttributeError):
        policy.offline = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {"max_bytes": 0},
            "max_bytes: must be an integer of at least 1, got an integer 0",
        ),
        ({"max_bytes": -1}, "of at least 1, got an integer -1"),
        ({"max_bytes": True}, "max_bytes: must be an integer, got a boolean true"),
        ({"max_bytes": 1.5}, "max_bytes: must be an integer, got a float 1.5"),
        ({"max_bytes": "5"}, "max_bytes: must be an integer, got a string '5'"),
        ({"offline": 1}, "^RemoteFetchPolicy.offline: must be True or False"),
        ({"offline": None}, "^RemoteFetchPolicy.offline: must be True or False"),
        ({"check_url": "https://h/"}, "check_url must be callable or None"),
    ],
    ids=["zero", "negative", "bool", "float", "str", "offline-int",
         "offline-none", "check-str"],
)  # fmt: skip
def test_a_policy_made_by_hand_is_checked(
    kwargs: dict[str, object], match: str
) -> None:
    """Direct construction (a library caller's) is checked as the resolver's
    value is, never later in a route: a byte ceiling or ``offline`` of the
    wrong type is a ``TypeError``, any other refusal a ``ValueError`` (an
    ``InternalError`` for ``check_url``, which only Pitloom builds)."""
    if "max_bytes" in kwargs:
        error = integer_refusal(kwargs["max_bytes"])
    else:
        error = TypeError if "offline" in kwargs else ValueError
    with pytest.raises(error, match=match) as exc:
        RemoteFetchPolicy(**kwargs)  # type: ignore[arg-type]
    # A library parameter here, not a file setting.
    assert code_of(exc.value) == (None if "check_url" in kwargs else "option-invalid")


def test_a_valid_policy_made_by_hand_is_kept() -> None:
    # pylint: disable-next=too-few-public-methods
    class Index:
        """An integer that is no ``int`` (a ``numpy.int64``)."""

        def __index__(self) -> int:
            return 7

    def check(_url: str) -> None:
        return None

    policy = RemoteFetchPolicy(Index(), True, check)  # type: ignore[arg-type]
    assert isinstance(policy.max_bytes, int) and policy.max_bytes == 7
    assert policy.offline is True and policy.check_url is check
    assert RemoteFetchPolicy(1).max_bytes == 1
