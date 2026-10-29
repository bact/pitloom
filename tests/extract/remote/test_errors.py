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


@pytest.mark.parametrize(
    "again", [copy.copy, copy.deepcopy, _pickled], ids=["copy", "deepcopy", "pickle"]
)
def test_a_remote_source_error_survives_a_copy_and_a_pickle(
    again: Callable[[RemoteSourceError], RemoteSourceError],
) -> None:
    exc = RemoteSourceError("git.too-large", "the repository is larger than 1 KiB")
    setattr(exc, CODE_ATTR, "lfs-pointer")
    back = again(exc)
    assert back is not exc and type(back) is RemoteSourceError
    assert (back.code, str(back), back.args) == (exc.code, str(exc), exc.args)
    assert code_of(back) == "lfs-pointer"
