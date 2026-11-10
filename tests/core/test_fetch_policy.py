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
    with pytest.raises(ValueError, match="max.download.bytes"):
        resolve_fetch_policy(None, max_download_bytes=cast(int, bad))
    with pytest.raises(ValueError, match="max.download.bytes"):
        resolve_fetch_policy(PitloomConfig(max_download_bytes=cast(int, bad)))


def test_the_policy_is_frozen() -> None:
    policy = RemoteFetchPolicy()
    with pytest.raises(AttributeError):
        policy.offline = True  # type: ignore[misc]
