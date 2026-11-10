# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The errors of reading a PyPI project or release page URL: an invalid URL,
a project, release or file PyPI does not hold, a digest that does not match,
an answer that is not valid. ``ERROR`` (and one ``WARNING``): each stops the
read.

See also: :mod:`pitloom.messages._remote_fetch` (a refused redirect or host,
a failed or timed out download, offline mode: shared with the Git and
Hugging Face routes), :mod:`pitloom.messages._pypi_info` (the decisions
about which release and file to read), :mod:`pitloom.extract.remote.pypi_url` (the URL),
:mod:`pitloom.extract.remote.pypi` (the resolver) and
:mod:`pitloom.extract.remote.pypi_select` (the choice of file).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.0"

#: The URL is not a PyPI project or release page.
PYPI_URL_FORM_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: not a PyPI project or release page; give "
    "https://pypi.org/project/<name>/ or .../<name>/<version>/",
)
#: The URL is not https.
PYPI_URL_SCHEME_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: PyPI is read over https only; give the https:// URL",
)
#: The URL holds user information.
PYPI_URL_CREDENTIALS_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: holds user information; a PyPI URL is read "
    "without credentials",
)
#: The project name in the URL is not a valid name.
PYPI_NAME_INVALID_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: %(name)s is not a valid project name"
)
#: The URL is on another index of the PyPI family (``test.pypi.org``).
PYPI_INDEX_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: only pypi.org is read; another index is not supported yet",
)
#: The URL is on PyPI's old host.
PYPI_OLD_HOST_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: pypi.python.org is PyPI's old address; give "
    "https://pypi.org/project/<name>/",
)
#: The URL is a direct link to a file on PyPI's file host.
PYPI_FILE_LINK_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: a file link is not read yet; give the project or "
    "release page https://pypi.org/project/<name>/<version>/",
)
#: The version in the URL is not a PEP 440 version.
PYPI_VERSION_INVALID_LINE: Final = Line(
    level="ERROR", template="URL=%(url)s: %(version)s is not a PEP 440 version"
)

#: A URL that is not a PyPI project or release page Pitloom reads.
PYPI_URL_INVALID: Final = Message(
    code="pypi-url-invalid",
    condition="invalid",
    lines=(
        PYPI_URL_FORM_LINE,
        PYPI_URL_SCHEME_LINE,
        PYPI_URL_CREDENTIALS_LINE,
        PYPI_INDEX_LINE,
        PYPI_OLD_HOST_LINE,
        PYPI_FILE_LINK_LINE,
        PYPI_NAME_INVALID_LINE,
        PYPI_VERSION_INVALID_LINE,
    ),
    summary="A URL on a PyPI host is not one Pitloom reads: it is not a "
    "project or release page (https://pypi.org/project/<name>/ or "
    ".../<name>/<version>/), is not https, holds a user name or password, is "
    "on another index (test.pypi.org) or PyPI's old address "
    "(pypi.python.org), is a link to a file (files.pythonhosted.org), or "
    "names a project or version that is not valid.",
    did="Wrote no SBOM, and sent no request.",
    effect="not-written",
    actor="user",
    advice="Tell the user which part of the URL was refused, as the line "
    "says, and that Pitloom reads https://pypi.org/project/<name>/ or "
    "https://pypi.org/project/<name>/<version>/ only. They correct the URL "
    "and run again; a release on another index is read by downloading the "
    "file and running Pitloom on it. Do not guess another URL; ask first, "
    "and with nobody to ask, report it only.",
    subject_key="URL",
    since=_SINCE,
)

#: The project is not on PyPI.
PYPI_PROJECT_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="PYPI=%(name)s: no such project on PyPI"
)
#: The release is not on PyPI.
VERSION_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s VERSION=%(version)s: no such release on PyPI",
)
#: No release of the project has a file Pitloom can read.
NO_USABLE_RELEASE_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s: no release has a wheel or sdist with a SHA-256 digest",
)

#: A project or release PyPI does not hold.
RELEASE_NOT_FOUND: Final = Message(
    code="release-not-found",
    condition="not-found",
    lines=(
        PYPI_PROJECT_NOT_FOUND_LINE,
        VERSION_NOT_FOUND_LINE,
        NO_USABLE_RELEASE_LINE,
    ),
    summary="PyPI does not hold the project or the release the URL names, or "
    "(for a URL without a version) no release of the project has a wheel or "
    "sdist with a SHA-256 digest to read.",
    did="Wrote no SBOM. The error code is pypi.project-not-found or "
    "pypi.release-not-found.",
    effect="not-written",
    actor="user",
    advice="Tell the user which project or release PyPI does not hold. They "
    "check the spelling of the name and the version, and that the project is "
    "not deleted, and run again. Do not guess another name or version; ask "
    "first, and with nobody to ask, report it only.",
    subject_key="PYPI",
    since=_SINCE,
)

#: The release has no wheel.
NO_WHEEL_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s VERSION=%(version)s: the release has no wheel; "
    "'loom project %(url)s' reads its sdist",
)
#: The release has no wheel for this Python and platform.
NO_COMPATIBLE_WHEEL_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s VERSION=%(version)s: no wheel matches this Python "
    "and platform (wheels: %(files)s); 'loom project %(url)s' reads its sdist",
)
#: The release has no sdist.
NO_SDIST_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s VERSION=%(version)s: the release has no sdist; "
    "'loom wheel %(url)s' reads a wheel",
)

#: The release has no wheel at all.
RELEASE_FILE_NOT_FOUND: Final = Message(
    code="release-file-not-found",
    condition="not-found",
    lines=(NO_WHEEL_LINE,),
    summary="The release the URL names has no wheel for 'loom wheel' to read.",
    did="Wrote no SBOM. The error code is pypi.no-wheel.",
    effect="not-written",
    actor="user",
    advice="Tell the user the release has no wheel, and that the command in "
    "the line reads its sdist. Offer it. Do not run it for them; with "
    "nobody to ask, report it only.",
    subject_key="PYPI",
    since=_SINCE,
)
#: The release has wheels, none for this Python and platform.
RELEASE_FILE_NOT_FOUND_COMPATIBLE: Final = Message(
    code="release-file-not-found/compatible-wheel",
    condition="not-found",
    lines=(NO_COMPATIBLE_WHEEL_LINE,),
    summary="The release the URL names has wheels, but none whose tags this "
    "Python and platform accept.",
    did="Wrote no SBOM. The error code is pypi.no-compatible-wheel.",
    effect="not-written",
    actor="user",
    advice="Tell the user no wheel of the release matches the Python and "
    "platform Pitloom runs on, naming the wheels the line lists, and that the "
    "command in the line reads the sdist instead. They may also run Pitloom "
    "on the platform of the wheel they want. Offer the sdist command. Do not "
    "run it for them. With nobody to ask, report it only.",
    subject_key="PYPI",
    since=_SINCE,
)
#: The release has no sdist.
RELEASE_FILE_NOT_FOUND_SDIST: Final = Message(
    code="release-file-not-found/sdist",
    condition="not-found",
    lines=(NO_SDIST_LINE,),
    summary="The release the URL names has no sdist for 'loom project' to read.",
    did="Wrote no SBOM. The error code is pypi.no-sdist.",
    effect="not-written",
    actor="user",
    advice="Tell the user the release has no sdist, and that the command in "
    "the line reads a wheel. Offer it. Do not run it for them; with "
    "nobody to ask, report it only.",
    subject_key="PYPI",
    since=_SINCE,
)

#: The downloaded bytes do not match the digest PyPI declares.
DIGEST_MISMATCH_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: SHA-256 %(measured)s does not match %(declared)s "
    "declared by %(source)s; not read",
)

#: A downloaded file whose SHA-256 differs from the one declared.
DIGEST_MISMATCH: Final = Message(
    code="digest-invalid",
    condition="invalid",
    lines=(DIGEST_MISMATCH_LINE,),
    summary="The SHA-256 of the file Pitloom downloaded differs from the one "
    "PyPI declares for it: the download is corrupt or was altered on the way.",
    did="Did not read the file, and wrote no SBOM. The error code is "
    "pypi.digest-mismatch.",
    effect="not-written",
    actor="user",
    advice="Tell the user the downloaded file does not match the digest PyPI "
    "declares, so Pitloom did not read it, and that the file may have been "
    "altered. They may run again; if it repeats, report it to PyPI. Do not "
    "read the file by other means; ask first, and with nobody to ask, report "
    "it only.",
    subject_key="FILE",
    since=_SINCE,
)

#: PyPI declares no SHA-256 digest for the file.
NO_DIGEST_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: PyPI declares no SHA-256 digest; not downloaded",
)
#: PyPI answered for another project.
NAME_MISMATCH_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s: PyPI answered for project %(answered)s; not read",
)
#: The JSON API answer lacks a field Pitloom needs.
RESPONSE_SHAPE_LINE: Final = Line(
    level="ERROR",
    template="PYPI=%(name)s: the PyPI JSON API answer has no valid %(field)s; not read",
)
#: A file of the release is left out of the choice.
FILE_SKIPPED_LINE: Final = Line(
    level="WARNING", template="PYPI=%(name)s FILE=%(file)s: %(why)s; skipped"
)

#: A PyPI answer that does not hold what Pitloom needs.
PYPI_RESPONSE_INVALID: Final = Message(
    code="pypi-response-invalid",
    condition="invalid",
    lines=(NO_DIGEST_LINE, NAME_MISMATCH_LINE, RESPONSE_SHAPE_LINE, FILE_SKIPPED_LINE),
    summary="The answer of the PyPI JSON API is not one Pitloom reads: it is "
    "for another project, lacks a field it needs, or declares no SHA-256 "
    "digest for the file. A file of a release whose entry is not valid is "
    "left out of the choice, with a warning.",
    did="Did not download the file and wrote no SBOM (an error), or left the "
    "file out and chose among the rest (the warning). The error code is "
    "pypi.response-invalid.",
    effect="not-written",
    actor="user",
    advice="Tell the user PyPI's answer was not usable, as the line says. "
    "Without a digest Pitloom cannot check the download, so it reads nothing. "
    "They may run again later; if it repeats, the project's release is "
    "malformed on PyPI. A skipped file only narrows the choice; report it "
    "only. Do not read the file by other means; ask first, and with nobody "
    "to ask, report it only.",
    since=_SINCE,
)

#: ``--embed`` was given with a PyPI URL.
EMBED_URL_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: --embed writes into a wheel file, and a PyPI URL "
    "has none to keep; nothing fetched",
)
#: ``loom model`` was given a PyPI URL.
MODEL_URL_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: a PyPI page is not a model; 'loom wheel' reads "
    "its wheel, 'loom project' its sdist; nothing fetched",
)

#: The Git route (``generate_git_sbom()``) was given a PyPI URL.
GIT_PYPI_URL_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: a PyPI page is not a Git repository; "
    "generate_pypi_sbom(), 'loom wheel' or 'loom project' reads it; "
    "nothing fetched",
)

#: A command that cannot take a PyPI URL was given one.
PYPI_URL_UNUSABLE: Final = Message(
    code="pypi-url-unusable",
    condition="unusable",
    lines=(EMBED_URL_LINE, MODEL_URL_LINE, GIT_PYPI_URL_LINE),
    summary="A PyPI URL was given to a command or option that cannot use it: "
    "loom wheel --embed (it would write into a temporary copy of the wheel), "
    "loom model or generate_model_sbom() (a release is not a model), or a "
    "library call that fetches a Git repository (generate_git_sbom(), "
    "generate_git_project_sbom(), fetch_git_project()).",
    did="Fetched nothing and wrote no SBOM.",
    effect="not-written",
    actor="user",
    advice="Tell the user which command or option cannot take the URL. For "
    "--embed they download the wheel and run 'loom wheel FILE --embed'; for "
    "a model they use 'loom wheel URL' or 'loom project URL'; from Python, "
    "generate_pypi_sbom() (or generate()) instead of the Git or model call. "
    "Do not "
    "download or embed for them; ask first, and with nobody to ask, report "
    "it only.",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    PYPI_URL_INVALID,
    RELEASE_NOT_FOUND,
    RELEASE_FILE_NOT_FOUND,
    RELEASE_FILE_NOT_FOUND_COMPATIBLE,
    RELEASE_FILE_NOT_FOUND_SDIST,
    DIGEST_MISMATCH,
    PYPI_RESPONSE_INVALID,
    PYPI_URL_UNUSABLE,
)
