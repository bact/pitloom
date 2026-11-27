# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What stops a Git URL fetch: ``git-url-invalid`` (a URL Pitloom does not
hand to git), ``git-ref-not-found`` (no branch or tag of the name),
``git-missing`` (no git to run) and ``git-repository-unusable`` (git
failed for a reason other than the network; with ``/empty``, a repository
with no commits); and the git command echo, a summary. Each is a
:class:`~pitloom.extract.remote.errors.RemoteSourceError` whose ``.code``
(``git.url-invalid``) is unchanged; its ``pitloom_code`` is the entry's.

See also: :mod:`pitloom.messages._git_decisions` (what a fetch decided),
:mod:`pitloom.messages._remote_fetch` (``download-network-failed`` and
``download-timeout``, which a Git fetch shares) and
:mod:`pitloom.extract.remote.git` (the fetch).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._frames import GIT_PREFIX
from pitloom.messages._summary import Summary
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: A URL of a scheme git is not asked to fetch.
GIT_URL_SCHEME_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: only http and https URLs are fetched (not ssh, git, "
    "file or scp-style addresses); nothing fetched",
)
#: A URL that names no host (``https://``, ``https:///o/r``,
#: ``https://u@/o/r``, ``https://:443/o/r``).
GIT_URL_HOST_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: the URL names no host; nothing fetched"
)
#: A URL whose port is no number.
GIT_URL_PORT_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: the port is not a number; nothing fetched"
)
#: A URL with a path part that would leave the checkout or name git's own.
GIT_URL_PATH_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: a path part decodes to ., .., an empty part, a "
    "backslash, a NUL or .git; nothing fetched",
)

#: A Git URL Pitloom does not hand to git.
GIT_URL_INVALID: Final = Message(
    code="git-url-invalid",
    condition="invalid",
    lines=(
        GIT_URL_SCHEME_LINE,
        GIT_URL_HOST_LINE,
        GIT_URL_PORT_LINE,
        GIT_URL_PATH_LINE,
    ),
    summary="A Git URL is not one Pitloom fetches: its scheme is not http or "
    "https (ssh://, git://, file:// or an scp-style user@host:path), it names "
    "no host (https:///o/r, https://:443/o/r), its port is not a number, or a "
    "part of its path, once decoded, is ., .., empty, "
    "or holds a backslash, a NUL or .git, which would read outside the "
    "checkout or git's own files.",
    did="Started no git process, fetched nothing and wrote no SBOM (git.url-invalid).",
    effect="not-written",
    actor="user",
    advice="Tell the user the URL cannot be fetched, as the line says why. "
    "They give the https URL of the repository or of a page of it (the "
    "address a browser shows), or clone it themselves and run Pitloom on "
    f"the local copy. Do not rewrite the URL for them; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

#: A branch or tag the repository does not have.
GIT_REF_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: no branch or tag %(ref)s; a commit needs its full "
    "40 or 64 hex digits",
)

#: A Git URL naming a branch or tag the repository does not have.
GIT_REF_NOT_FOUND: Final = Message(
    code="git-ref-not-found",
    condition="not-found",
    lines=(GIT_REF_NOT_FOUND_LINE,),
    summary="The Git URL names a branch, tag or commit (in its path, as a "
    "page URL's tree or blob part, or as a version query) that the "
    "repository does not have as a branch or tag; a commit is fetched only "
    "by its full hash.",
    did="Fetched no checkout and wrote no SBOM (git.ref-not-found).",
    effect="not-written",
    actor="user",
    advice="Tell the user the repository has no branch or tag of that name. "
    "They check the spelling, give the full commit hash for a commit, or "
    "leave the version out for the default branch. Do not guess a ref for "
    f"them; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

#: No git to run.
GIT_MISSING_LINE: Final = Line(
    level="ERROR", template="git is not installed or not on PATH; nothing fetched"
)

#: A Git URL to fetch, and no git.
GIT_MISSING: Final = Message(
    code="git-missing",
    condition="missing",
    lines=(GIT_MISSING_LINE,),
    summary="A Git URL is fetched by running git, and no git program is on PATH.",
    did="Fetched nothing and wrote no SBOM (git.not-found).",
    effect="not-written",
    actor="user",
    advice="Tell the user git is needed to read a Git URL. They install git "
    "(or put it on PATH) and run again, or clone the repository with another "
    "tool and run Pitloom on the local copy. Do not install it for them; "
    f"{ASK_FIRST}",
    since=_SINCE,
)

#: git failed for a reason other than the network.
GIT_FAILED_LINE: Final = Line(
    level="ERROR", template="git %(command)s: %(error)s; nothing fetched"
)

#: A repository git could reach but not fetch.
GIT_REPOSITORY_UNUSABLE: Final = Message(
    code="git-repository-unusable",
    condition="unusable",
    lines=(GIT_FAILED_LINE,),
    summary="git failed for a reason other than the network: the repository "
    "does not exist or is private (an HTTP 404, or a sign-in the server "
    "asked for), the server refused the request, or the answer was not a "
    "repository. The line ends with git's own messages, the server's "
    "included.",
    did="Fetched no checkout and wrote no SBOM (git.clone-failed).",
    effect="not-written",
    actor="user",
    advice="Tell the user git could not fetch the repository, with git's "
    "reason as the line gives it. They check the URL and their access; for "
    "a private repository they clone it themselves and run Pitloom on the "
    f"local copy. Do not sign in or retry for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A repository with no commits.
GIT_EMPTY_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: an empty repository (no commits); nothing read",
)

#: A repository with nothing to read.
GIT_REPOSITORY_EMPTY: Final = Message(
    code="git-repository-unusable/empty",
    condition="unusable",
    lines=(GIT_EMPTY_LINE,),
    summary="The repository the Git URL names has no commits, so it holds no "
    "file to read.",
    did="Wrote no SBOM (git.clone-failed).",
    effect="not-written",
    actor="user",
    advice="Tell the user the repository is empty. They check the URL names "
    "the repository they meant, or push to it first. Do not pick another "
    f"repository for them; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

#: Each git command a fetch runs, as run.
GIT_COMMAND: Final = Summary(
    template=GIT_PREFIX + "$ %(command_line)s",
    meaning="Each git command a Git URL fetch runs, as it runs, the "
    "credentials of a URL in it taken out: what git was asked, in order.",
    topic="git",
)

ENTRIES: Final = (
    GIT_URL_INVALID,
    GIT_REF_NOT_FOUND,
    GIT_MISSING,
    GIT_REPOSITORY_UNUSABLE,
    GIT_REPOSITORY_EMPTY,
)

SUMMARIES: Final = (GIT_COMMAND,)
