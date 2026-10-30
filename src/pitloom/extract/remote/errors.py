# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The error every remote source raises, with a stable code.

No Pitloom imports.
"""

from __future__ import annotations

__all__ = ["RemoteSourceError"]


class RemoteSourceError(Exception):
    """A remote source could not be read.

    ``code`` names the failure for a caller that maps it to its own
    vocabulary (``git.clone-failed``, ``git.timeout``, ``git.not-found``,
    ``git.offline``, ``git.url-invalid``, ``git.ref-not-found``,
    ``git.path-not-found``, ``git.too-many-redirects``,
    ``git.output-too-large``, ``git.too-large``, ``git.no-project``, and any
    code a caller's own URL check raises through :class:`RemoteSourceError`);
    the message is for the user. *pitloom_code* is the catalogued code of
    the condition when it has one (``over-cap`` for ``git.too-large`` and
    ``git.output-too-large``), read by :func:`pitloom.messages.code_of`.
    """

    def __init__(
        self, code: str, message: str, *, pitloom_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        #: The catalogued code of the condition, or ``None``.
        self.pitloom_code = pitloom_code

    def __reduce__(
        self,
    ) -> tuple[type[RemoteSourceError], tuple[str, str], dict[str, object]]:
        """Copied and pickled by its code and message, and every attribute
        set on it: ``args`` holds the message only, so the default would call
        ``__init__`` without the code."""
        return (type(self), (self.code, str(self)), dict(self.__dict__))
