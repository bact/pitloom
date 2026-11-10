# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The decisions Pitloom makes when a PyPI URL leaves the release or the
file open: no version given, a yanked release, several matching files.
``INFO`` only: the SBOM is written, from what was chosen.

See also: :mod:`pitloom.messages._pypi` (the errors) and
:mod:`pitloom.extract.remote.pypi_select` (the choice).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.0"

#: No version in the URL: the latest stable release is read.
LATEST_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s: no version given; using the "
    "latest release",
)
#: No version in the URL, and every release is a pre-release.
LATEST_PRERELEASE_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s: no version given and no "
    "stable release that is not yanked; using the newest pre-release",
)
#: No version in the URL, and every release is yanked.
LATEST_YANKED_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s: no version given and every "
    "release is yanked; using the newest (yanked: %(why)s)",
)
#: The release is yanked, and named by the URL.
YANKED_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s FILE=%(file)s: the file is "
    "yanked (%(why)s); reading it anyway",
)
#: Several wheels fit the running environment.
WHEEL_PICK_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s: %(number)s wheels match this "
    "environment; using %(file)s, the best-ranked",
)
#: The release has several sdists.
SDIST_PICK_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s VERSION=%(version)s: %(number)s sdists; using %(file)s",
)

#: ``loom generate`` read the wheel; ``loom project`` reads the sdist.
GENERATE_WHEEL_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s: loom generate reads the wheel; "
    "'loom project %(url)s' reads the sdist",
)
#: ``generate()`` read the wheel; ``generate_pypi_sbom()`` reads the sdist.
GENERATE_WHEEL_LIBRARY_LINE: Final = Line(
    level="INFO",
    template="PYPI=%(name)s: generate() reads the wheel; "
    "generate_pypi_sbom('%(url)s', kind='sdist') reads the sdist",
)
#: A redirect followed.
REDIRECT_LINE: Final = Line(
    level="INFO", template="URL=%(url)s: redirects to %(target)s; followed"
)
#: A query or fragment cut from the URL given.
QUERY_LINE: Final = Line(
    level="INFO",
    template="URL=%(url)s: the query and fragment have no effect; cut",
)

_UNPINNED_ADVICE: Final = (
    "Tell the user which release was read, as the line names it, and that "
    "the URL named no version. For a repeatable result they give the "
    "version in the URL (https://pypi.org/project/<name>/<version>/). Do not "
    "run again with another version; ask first, and with nobody to ask, "
    "report it only."
)

#: No version in the URL: the latest stable release.
RELEASE_UNPINNED: Final = Message(
    code="release-unpinned",
    condition="unpinned",
    lines=(LATEST_LINE,),
    summary="The URL names a project without a version, so Pitloom chose "
    "the latest stable release that is not yanked.",
    did="Read the latest release.",
    effect="none",
    actor="user",
    advice=_UNPINNED_ADVICE,
    subject_key="PYPI",
    since=_SINCE,
)
#: No version in the URL, no stable release.
RELEASE_UNPINNED_PRERELEASE: Final = Message(
    code="release-unpinned/prerelease",
    condition="unpinned",
    lines=(LATEST_PRERELEASE_LINE,),
    summary="The URL names a project without a version and no stable "
    "release is left that is not yanked, so Pitloom chose the newest "
    "pre-release that is not yanked.",
    did="Read the newest pre-release.",
    effect="none",
    actor="user",
    advice=_UNPINNED_ADVICE,
    subject_key="PYPI",
    since=_SINCE,
)
#: No version in the URL, every release yanked.
RELEASE_UNPINNED_YANKED: Final = Message(
    code="release-unpinned/yanked",
    condition="unpinned",
    lines=(LATEST_YANKED_LINE,),
    summary="The URL names a project without a version and every release is "
    "yanked, so Pitloom chose the newest one.",
    did="Read the newest release, which its maintainers withdrew.",
    effect="weaker",
    actor="user",
    advice="Tell the user every release of the project is yanked, so the "
    "newest was read although its maintainers withdrew it, with the reason "
    "the line gives. Whether to rely on the SBOM is their decision. Do not "
    "read another release for them; report it only.",
    subject_key="PYPI",
    since=_SINCE,
)
#: The named release is yanked.
RELEASE_YANKED: Final = Message(
    code="release-unusable",
    condition="unusable",
    lines=(YANKED_LINE,),
    summary="The file Pitloom reads is yanked: its maintainers withdrew it, "
    "with the reason shown. Either the URL names a release whose files are "
    "yanked, or every file of the kind asked for that matches this "
    "environment is yanked (the release itself still has files that are "
    "not).",
    did="Read the yanked file: a yanked file is passed over only while one "
    "that is not yanked fits.",
    effect="none",
    actor="user",
    advice="Tell the user the file is yanked and why, as the line says, and "
    "that no file of that release fitting the request is not yanked. "
    "Whether to rely on it is their decision. Do not read another release "
    "or file for them; report it only.",
    subject_key="PYPI",
    since=_SINCE,
)
#: Several files fit; one is chosen.
FILE_AMBIGUOUS: Final = Message(
    code="file-ambiguous",
    condition="ambiguous",
    lines=(
        WHEEL_PICK_LINE,
        SDIST_PICK_LINE,
        GENERATE_WHEEL_LINE,
        GENERATE_WHEEL_LIBRARY_LINE,
    ),
    summary="The release has several wheels that fit the Python and platform "
    "Pitloom runs on, or several sdists, or (loom generate, generate()) both "
    "a wheel and an sdist; Pitloom chose one.",
    did="Read the best-ranked wheel (the tag order of the running "
    "environment), the one sdist named, or, for loom generate and "
    "generate(), the wheel.",
    effect="none",
    actor="user",
    advice="Tell the user which file was read, as the line names it, and "
    "that the choice follows the running environment. A different wheel is "
    "read by running Pitloom on that platform, or on a downloaded file; the "
    "sdist by the loom project command (or generate_pypi_sbom() call) the "
    "line gives. Do not run again for another file; ask first, and with "
    "nobody to ask, report it only.",
    subject_key="PYPI",
    since=_SINCE,
)

#: A redirect of a PyPI request, followed.
URL_MOVED: Final = Message(
    code="url-moved",
    condition="moved",
    lines=(REDIRECT_LINE,),
    summary="PyPI, or the host serving a file, redirected a request to "
    "another URL on a host Pitloom reads PyPI from (a renamed project, a "
    "normalised name).",
    did="Checked the target and followed it.",
    effect="none",
    actor="none",
    advice="nothing to do: the line names where the answer came from.",
    subject_key="URL",
    since=_SINCE,
)
#: A query or fragment in a PyPI URL.
QUERY_NO_EFFECT: Final = Message(
    code="query-no-effect",
    condition="no-effect",
    lines=(QUERY_LINE,),
    summary="The PyPI URL given holds a query or a fragment (a tab of the "
    "page), which names no project or release.",
    did="Read the URL without them.",
    effect="none",
    actor="none",
    advice="nothing to do: the project and release are read from the path.",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    RELEASE_UNPINNED,
    RELEASE_UNPINNED_PRERELEASE,
    RELEASE_UNPINNED_YANKED,
    RELEASE_YANKED,
    FILE_AMBIGUOUS,
    URL_MOVED,
    QUERY_NO_EFFECT,
)
