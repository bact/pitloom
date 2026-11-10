# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The conditions every remote route shares (a Git URL, a PyPI URL, a
Hugging Face repository): a request that failed, timed out, was sent
somewhere Pitloom does not fetch from or could not be saved, and offline
mode, which forbids the fetch. One family per condition; each route keeps
its own line where its subject or action differs. ``ERROR`` stops the read
(Git, PyPI); ``WARNING`` leaves one Hugging Face file out.

See also: :mod:`pitloom.messages._pypi` (the PyPI route's own conditions),
:mod:`pitloom.messages._over_cap` (``over-cap``, the download cap's family),
:mod:`pitloom.extract.remote._http_errors` (the HTTP client's errors) and
:mod:`pitloom.extract.remote._git_run` (git's).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.0"

#: A redirect that is not followed.
REDIRECT_REFUSED_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: redirects to %(target)s; not followed (%(why)s)",
)
#: A redirect of a Hugging Face file that is not followed.
REDIRECT_REFUSED_WARNING_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: redirects to %(target)s; not followed (%(why)s); "
    "%(outcome)s",
)
#: More redirects than Pitloom follows.
TOO_MANY_REDIRECTS_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: more than %(number)s redirects; not followed"
)
#: More redirects of a Hugging Face file than Pitloom follows.
TOO_MANY_REDIRECTS_WARNING_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: more than %(number)s redirects; %(outcome)s",
)
#: A file's download URL is on a host Pitloom does not fetch from.
FILE_HOST_REFUSED_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: download URL %(target)s is not on %(hosts)s; not fetched",
)

#: A redirect or download URL Pitloom does not follow or fetch.
URL_REFUSED: Final = Message(
    code="url-unsafe",
    condition="unsafe",
    lines=(
        REDIRECT_REFUSED_LINE,
        TOO_MANY_REDIRECTS_LINE,
        FILE_HOST_REFUSED_LINE,
        REDIRECT_REFUSED_WARNING_LINE,
        TOO_MANY_REDIRECTS_WARNING_LINE,
    ),
    summary="Pitloom would have to send a request somewhere it does not: a "
    "redirect to a URL that is not https or not on a host it reads PyPI or "
    "a Hugging Face file from, more redirects than it follows, or a file "
    "whose download URL PyPI gives on another host.",
    did="Did not follow the redirect or fetch the file, and wrote no SBOM "
    "(the error); for a Hugging Face file, left that file out and read the "
    "rest (the warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user which URL was not followed and why, as the line "
    "says. A mirror or proxy that redirects is not supported; they may "
    "download the file themselves and run Pitloom on it. Do not fetch the "
    "target for them; ask first, and with nobody to ask, report it only.",
    since=_SINCE,
)

#: A request that failed.
DOWNLOAD_FAILED_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: %(failure)s; not read"
)
#: A request for a Hugging Face file that failed.
DOWNLOAD_FAILED_WARNING_LINE: Final = Line(
    level="WARNING", template="URL=%(url)s: %(failure)s; %(outcome)s"
)
#: git could not reach the repository.
GIT_NETWORK_FAILED_LINE: Final = Line(
    level="ERROR", template="git %(command)s failed: %(error)s; nothing fetched"
)

#: A request to a remote source that failed.
DOWNLOAD_FAILED: Final = Message(
    code="download-network-failed",
    condition="network-failed",
    lines=(DOWNLOAD_FAILED_LINE, GIT_NETWORK_FAILED_LINE, DOWNLOAD_FAILED_WARNING_LINE),
    summary="A request to a remote source failed. PyPI or Hugging Face: an "
    "HTTP status other than 404 (a 401 or 403 for a private or gated "
    "repository read without access), a refused or reset connection, a name "
    "that did not resolve, or an answer cut short. Git: git could not reach "
    "the repository (a name that did not resolve, a refused, reset or "
    "timed-out connection, a TLS failure, an HTTP 5xx answer); a git failure "
    "with any other cause carries no code.",
    did="Wrote no SBOM (the error: pypi.download-failed, git.clone-failed); "
    "for a Hugging Face file, left that file out and read the rest (the "
    "warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user the request failed, with the reason the line gives. "
    "They check the network and run again; for a private or gated Hugging "
    "Face repository (HTTP 401 or 403) they sign in with an account that has "
    "access (HF_TOKEN, or 'hf auth login'). Do not retry in a loop or sign "
    "in for them; ask first, and with nobody to ask, report it only.",
    subject_key="URL",
    since=_SINCE,
)

#: A request that did not finish in time.
DOWNLOAD_TIMEOUT_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: no complete answer within %(seconds)s seconds; not read",
)
#: A request for a Hugging Face file that did not finish in time.
DOWNLOAD_TIMEOUT_WARNING_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: no complete answer within %(seconds)s seconds; %(outcome)s",
)
#: A git call that did not finish in time.
GIT_TIMEOUT_LINE: Final = Line(
    level="ERROR",
    template="git %(command)s did not finish within %(seconds)s seconds; stopped",
)

#: A request to a remote source that did not finish in time.
DOWNLOAD_TIMEOUT: Final = Message(
    code="download-timeout",
    condition="timeout",
    lines=(DOWNLOAD_TIMEOUT_LINE, GIT_TIMEOUT_LINE, DOWNLOAD_TIMEOUT_WARNING_LINE),
    summary="A request to PyPI, to the host that serves a file or to the "
    "Hugging Face Hub, or the git calls that fetch a repository, did not "
    "finish within the time Pitloom allows.",
    did="Stopped the request and wrote no SBOM (the error: "
    "pypi.download-timeout, git.timeout); for a Hugging Face file, left that "
    "file out and read the rest (the warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user the request timed out. They check the network and "
    "run again, or fetch the file or repository themselves and run Pitloom on "
    "the local copy. Do not retry in a loop; ask first, and with nobody to "
    "ask, report it only.",
    subject_key="URL",
    since=_SINCE,
)

#: A downloaded file that could not be saved in the temporary directory.
SAVE_FAILED_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: could not be saved in the temporary directory "
    "(%(failure)s); not downloaded",
)
#: A Hugging Face file that could not be saved in the temporary directory.
SAVE_FAILED_WARNING_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: could not be saved in the temporary directory "
    "(%(failure)s); %(outcome)s",
)

#: The temporary directory cannot take a downloaded file.
TEMP_DIR_UNUSABLE: Final = Message(
    code="temp-dir-unusable",
    condition="unusable",
    lines=(SAVE_FAILED_LINE, SAVE_FAILED_WARNING_LINE),
    summary="A file downloaded from PyPI or a Hugging Face repository could "
    "not be written to the temporary directory: the disk is full, the path "
    "is too long (Windows), or the directory cannot be written to.",
    did="Stopped the download and wrote no SBOM (the error: "
    "pypi.save-failed); for a Hugging Face file, left that file out and read "
    "the rest (the warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user the download could not be saved locally, with the "
    "reason the line gives; the network is not the cause. They free disk "
    "space, or set TMPDIR (TEMP on Windows) to a writable directory with a "
    "short path, and run again. Do not change their temporary directory for "
    "them; ask first, and with nobody to ask, report it only.",
    subject_key="FILE",
    since=_SINCE,
)

#: Offline mode forbids the fetch a target needs.
OFFLINE_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: network access is forbidden (offline mode); nothing fetched",
)
#: Offline mode forbids fetching a Hugging Face file.
OFFLINE_WARNING_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: network access is forbidden (offline mode); %(outcome)s",
)

#: A target that must be fetched, in offline mode.
NETWORK_UNUSABLE: Final = Message(
    code="network-unusable",
    condition="unusable",
    lines=(OFFLINE_LINE, OFFLINE_WARNING_LINE),
    summary="Offline mode is on and the target must be fetched: a Git URL, "
    "a PyPI URL or a Hugging Face repository. Offline mode is --offline, "
    "the offline key of --config, or offline=True; for a file of a Hugging "
    "Face repository also huggingface_hub's own HF_HUB_OFFLINE.",
    did="Fetched nothing and wrote no SBOM (the error: git.offline, "
    "pypi.offline, huggingface.offline); for a Hugging Face file under "
    "HF_HUB_OFFLINE, left that file out and read the rest (the warning).",
    effect="not-written",
    actor="user",
    advice="Tell the user the target must be fetched and offline mode forbids "
    "it. They run again without offline mode (no --offline, offline = false "
    "in the config, HF_HUB_OFFLINE unset), or fetch the repository or file "
    "themselves and run Pitloom on the local copy. Do not turn offline mode "
    "off for them; ask first, and with nobody to ask, report it only.",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    URL_REFUSED,
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    TEMP_DIR_UNUSABLE,
    NETWORK_UNUSABLE,
)
