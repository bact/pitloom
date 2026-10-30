# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``RemoteSourceError`` survives a copy and a pickle (a process pool hands
an exception back pickled): its code, its message and any attribute set on
it, such as a catalogued ``pitloom_code``.

See also: tests/messages/test_messages_emit.py (``code_of``, which reads
``pitloom_code`` and never ``code``).
"""

from __future__ import annotations

import copy
import pickle  # nosec B403
from collections.abc import Callable

import pytest

from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of


def _pickled(exc: RemoteSourceError) -> RemoteSourceError:
    again: RemoteSourceError = pickle.loads(pickle.dumps(exc))  # nosec B301
    return again


_CLONE = "the repository is larger than 1 KiB; git clone was stopped"


def _set(exc: RemoteSourceError) -> RemoteSourceError:
    setattr(exc, CODE_ATTR, "lfs-pointer")
    return exc


@pytest.mark.parametrize(
    "again", [copy.copy, copy.deepcopy, _pickled], ids=["copy", "deepcopy", "pickle"]
)
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (
            RemoteSourceError("git.too-large", _CLONE, pitloom_code="over-cap"),
            "over-cap",
        ),
        (_set(RemoteSourceError("git.too-large", _CLONE)), "lfs-pointer"),
        (RemoteSourceError("git.timeout", "git clone exceeded 1s"), None),
    ],
    ids=["given", "set", "none"],
)
def test_a_remote_source_error_survives_a_copy_and_a_pickle(
    again: Callable[[RemoteSourceError], RemoteSourceError],
    exc: RemoteSourceError,
    code: str | None,
) -> None:
    """The code given to it, or set on it later, survives with the rest."""
    back = again(exc)
    assert back is not exc and isinstance(back, RemoteSourceError)
    assert (back.code, str(back), back.args) == (exc.code, str(exc), exc.args)
    assert code_of(back) == code_of(exc) == code
