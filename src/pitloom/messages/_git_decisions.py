# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a Git URL fetch decided and went on from, each said after
:data:`~pitloom.messages.GIT_FRAME` (``Git source: ``):
``git-redirect-unusable`` (the URL could not be checked for a redirect),
``git-filter-unusable`` (the server refused the blob filter) and
``git-link-unsafe`` (symbolic links removed from the checkout).

See also: :mod:`pitloom.messages._git` (what stops a fetch) and
:mod:`pitloom.extract.remote.git` (the fetch).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"

#: A redirect probe that got no usable answer.
GIT_REDIRECT_UNUSABLE: Final = Message(
    code="git-redirect-unusable",
    condition="unusable",
    lines=(
        Line(
            level="INFO",
            template="URL=%(url)s: could not be checked for a redirect "
            "(%(why)s); git asked directly",
        ),
    ),
    summary="Before git is run, Pitloom asks the URL itself whether it "
    "redirects, so a redirect is checked before git follows it. That request "
    "got no usable answer: an HTTP error, a redirect without a Location, no "
    "answer in time, or a failed connection.",
    did="Ran git on the URL as given, which follows no redirect.",
    effect="none",
    actor="none",
    advice="nothing to do: if git cannot fetch the URL either, its own error follows.",
    subject_key="URL",
    since=_SINCE,
)

#: A server that refused the blob filter.
GIT_FILTER_UNUSABLE: Final = Message(
    code="git-filter-unusable",
    condition="unusable",
    lines=(
        Line(
            level="INFO",
            template="URL=%(url)s: the server rejected the blob filter; "
            "fetching without it",
        ),
    ),
    summary="Pitloom fetches with a filter that leaves out large files the "
    "checkout does not need; the server answered it with an error (Azure "
    "DevOps: HTTP 400).",
    did="Fetched again without the filter; the download cap still bounds "
    "what is fetched.",
    effect="none",
    actor="none",
    advice="nothing to do: the fetch went on without the filter.",
    subject_key="URL",
    since=_SINCE,
)

#: Symbolic links of a checkout removed.
GIT_LINK_UNSAFE: Final = Message(
    code="git-link-unsafe",
    condition="unsafe",
    lines=(
        Line(
            level="INFO",
            template="URL=%(url)s: %(number)s symbolic link(s) leading out of "
            "the repository, into its .git directory or to a directory; removed, "
            "not followed",
        ),
    ),
    summary="The checkout holds symbolic links that lead outside the "
    "repository, into its .git directory, or to a directory. The repository is "
    "untrusted: following them would read files it does not hold, or walk "
    "a directory twice.",
    did="Removed the links before reading: the SBOM lists neither them nor "
    "what they point to.",
    effect="thinner",
    actor="none",
    advice="nothing to do: the SBOM describes the repository's own files; "
    "a link's target is read from a local copy only.",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (GIT_REDIRECT_UNUSABLE, GIT_FILTER_UNUSABLE, GIT_LINK_UNSAFE)
