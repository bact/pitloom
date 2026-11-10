# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a fetch from a remote source may do: one value every remote route
(a Git URL, a PyPI URL, a Hugging Face repository) takes.

See also: :func:`pitloom.core.config_cascade.resolve_fetch_policy`, the one
place a surface (a CLI command, a library call) makes it from its flag, its
explicit config and the defaults.

Each route applies all three settings; only the last step differs: a Git
clone is stopped once the checkout takes more disk than :attr:`max_bytes`
(a watcher on the directory), a PyPI or Hugging Face file once more bytes
than that are received.

A policy is checked when it is made, whoever makes it: a library caller
that builds one by hand gets the same ``ValueError`` as the resolver.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pitloom.core.internal_error import InternalError
from pitloom.core.model_extract_limit import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    require_positive_ceiling,
)

__all__ = ["RemoteFetchPolicy"]


@dataclass(frozen=True)
class RemoteFetchPolicy:
    """The limits of one fetch.

    Attributes:
        max_bytes: The ``max-download-bytes`` cap: the most bytes of a file
            received, or of a checkout on disk.
        offline: Nothing is fetched; the route refuses
            (``offline-unusable``).
        check_url: The caller's address policy, called with each URL it
            covers before it is requested; it raises for one that must not
            be fetched. Compared by identity.

    Raises:
        ValueError: *max_bytes* is not an integer of at least 1 (a ``bool``
            or a ``float`` is none); an
            :class:`~pitloom.core.internal_error.InternalError` (a
            ``ValueError``) when *offline* is not a ``bool`` or *check_url*
            is neither callable nor ``None``.
    """

    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    offline: bool = False
    check_url: Callable[[str], None] | None = field(default=None)

    def __post_init__(self) -> None:
        # Frozen: the checked value (a numpy integer made an ``int``) is set
        # through ``object``.
        object.__setattr__(
            self, "max_bytes", require_positive_ceiling(self.max_bytes, "max_bytes")
        )
        if not isinstance(self.offline, bool):
            raise InternalError(
                "offline must be a bool, got "
                f"{type(self.offline).__name__}: {self.offline!r}"
            )
        if self.check_url is not None and not callable(self.check_url):
            raise InternalError(
                "check_url must be callable or None, got "
                f"{type(self.check_url).__name__}: {self.check_url!r}"
            )
