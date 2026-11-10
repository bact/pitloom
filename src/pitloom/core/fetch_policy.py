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
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pitloom.core.model_extract_limit import DEFAULT_MAX_DOWNLOAD_BYTES

__all__ = ["RemoteFetchPolicy"]


@dataclass(frozen=True)
class RemoteFetchPolicy:
    """The limits of one fetch.

    Attributes:
        max_bytes: The ``max-download-bytes`` cap: the most bytes of a file
            received, or of a checkout on disk.
        offline: Nothing is fetched; the route refuses
            (``network-unusable``).
        check_url: The caller's address policy, called with each URL it
            covers before it is requested; it raises for one that must not
            be fetched. Compared by identity.
    """

    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    offline: bool = False
    check_url: Callable[[str], None] | None = field(default=None)
