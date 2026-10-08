# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Put ``os.environ`` back after a test.

``monkeypatch.delenv`` on an absent name records no restore, so a direct
write that follows (``--debug`` sets ``PITLOOM_DEBUG``) leaks, as does a
third-party import that sets a variable. Left in place, a later test on the
same xdist worker sees it, depending on which tests share the worker.
``tests/conftest.py`` wraps every test in :func:`environ_restored`.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def environ_restored() -> Iterator[None]:
    """Restore ``os.environ`` to its state on entry: drop added names, put
    back changed and removed ones."""
    saved = os.environ.copy()
    try:
        yield
    finally:
        for name in os.environ.keys() - saved.keys():
            del os.environ[name]
        for name, value in saved.items():
            if os.environ.get(name) != value:
                os.environ[name] = value
