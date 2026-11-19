# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` variants of a Git URL's user information:
``credentials-unsafe/git-line-break``, credentials holding a line break are
not handed to ``git`` (the fetch is anonymous), and
``credentials-unsafe/http-clear``, credentials of a plain ``http://`` URL go
to the server in clear (the fetch goes on). Both ``WARNING``; the
``credentials-unsafe/git-userinfo`` variant (a URL whose user information
cannot be taken out) is an ``ERROR``, said by the git reader.

See also: :mod:`pitloom.messages._url_credentials` (the family's other
entries), :mod:`pitloom.messages.url_credentials_git` (the helpers that say
them) and :mod:`pitloom.extract.remote._git_credentials` (which calls them).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: What to give ``git`` a credential through instead of a URL.
_INSTEAD: Final = (
    "a credential belongs in a .netrc file, a keyring (a git credential "
    "helper) or an environment variable, never in a URL"
)

#: A Git URL's credentials hold a line break.
GIT_LINE_BREAK_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: credentials holding a line break are not sent to git",
)
#: A plain ``http://`` Git URL holds credentials.
HTTP_CLEAR_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: credentials are sent in clear over http; use https",
)

#: A Git URL holds user information that cannot be taken out of the command
#: line.
GIT_USERINFO_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: user information cannot be taken out of the git "
    "command line; not fetched",
)

CREDENTIALS_UNSAFE_GIT_LINE_BREAK: Final = Message(
    code="credentials-unsafe/git-line-break",
    condition="unsafe",
    lines=(GIT_LINE_BREAK_LINE,),
    summary="The user name or password of a Git URL holds a line break "
    "(an encoded %0A or %0D). A line break would add a line to what the "
    "credential helper hands git, so git could be told another value.",
    did="Fetched the URL without its credentials (a private repository "
    "then fails); said once per URL, shown masked.",
    effect="thinner",
    actor="user",
    advice="Tell the user which URL, as the line shows it, and that its "
    f"credentials were not used; {_INSTEAD}. A credential typed into a "
    "command line is exposed in the shell history: they should consider it "
    f"exposed and rotate it. Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_HTTP_CLEAR: Final = Message(
    code="credentials-unsafe/http-clear",
    condition="unsafe",
    lines=(HTTP_CLEAR_LINE,),
    summary="A plain http:// Git URL holds a user name or password: git "
    "sends it to the server unencrypted, readable by anyone on the path.",
    did="Fetched the URL with its credentials, as asked; said once per URL, "
    "shown masked.",
    effect="none",
    actor="user",
    advice="Tell the user which URL, as the line shows it, and that its "
    "credentials crossed the network in clear: they should use the https:// "
    f"address and consider the credential exposed; {_INSTEAD}. Do not edit "
    f"their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_GIT_USERINFO: Final = Message(
    code="credentials-unsafe/git-userinfo",
    condition="unsafe",
    lines=(GIT_USERINFO_LINE,),
    summary="A Git URL holds user information (an @ before the first /) that "
    "Pitloom cannot split off the command line the way git reads it: a bracket "
    "or port that is not valid, an empty host, or "
    "an @ git reads as a password where the URL parser sees a query. Or the "
    "user name or password holds a NUL (an encoded %00), which cannot be "
    "handed to git at all.",
    did="Did not run git for the URL, and sent no request; the URL is shown masked.",
    effect="not-written",
    actor="user",
    advice="Tell the user which URL, as the line shows it, and that it was "
    f"not fetched; {_INSTEAD}. They give the address without user "
    f"information and run again. Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    CREDENTIALS_UNSAFE_GIT_LINE_BREAK,
    CREDENTIALS_UNSAFE_GIT_USERINFO,
    CREDENTIALS_UNSAFE_HTTP_CLEAR,
)
