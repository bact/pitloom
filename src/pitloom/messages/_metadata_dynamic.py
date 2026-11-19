# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project metadata Pitloom reads but cannot complete or settle, each a
``WARNING`` the read goes on past: a dynamic field only a build computes
(``dynamic-field-needs-build``) or whose backend's resolver failed
(``dynamic-field-unusable``); installed metadata that is not the project's
(``installed-metadata-unusable``) or one of several
(``installed-metadata-ambiguous``); two sources that disagree
(``metadata-conflict``); and a table or line the backend does not read
(``metadata-no-effect``).

See also: :mod:`pitloom.messages.metadata` (the public names),
:mod:`pitloom.messages._metadata_read` (what stops the read).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: What the user does not let an agent do.
_NO_EDIT: Final = f"Do not edit the project for them; {ASK_FIRST}"
#: What a build-only field leaves.
_BUILD_ONLY: Final = (
    "A built wheel or sdist states the value: an SBOM of it (loom wheel, an "
    "sdist with PKG-INFO) records it."
)

#: A PDM version source only running project code resolves.
PDM_SOURCE_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: PDM version source %(value)s is not resolvable "
    "without running project code; version not recorded",
)
#: An sdist's dynamic fields with no PKG-INFO to state them.
SDIST_DYNAMIC_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: dynamic %(metadata_fields)s not resolved without "
    "PKG-INFO; skipped",
)

DYNAMIC_FIELD_NEEDS_BUILD: Final = Message(
    code="dynamic-field-needs-build",
    condition="needs-build",
    lines=(PDM_SOURCE_LINE, SDIST_DYNAMIC_LINE),
    summary="A [project] field is dynamic and only a build computes it: a "
    "PDM version source other than a file or SCM tag (a call into the "
    "project's code), or an sdist's dynamic fields when the archive holds no "
    "PKG-INFO to state them. Pitloom never runs project code to read "
    "metadata.",
    did="Read the project without the value: the SBOM records no version "
    "(or no such field) for it.",
    effect="thinner",
    actor="user",
    advice="Tell the user which field is not recorded and why, as the line "
    f"says. {_BUILD_ONLY} Do not build or run the project for them; "
    f"{ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: PDM's version resolver raised.
PDM_FAILED_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: PDM dynamic version not resolved; %(failure)s",
)
#: Flit's static reading of the module raised.
FLIT_FAILED_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: Flit dynamic metadata not resolved; %(failure)s",
)

DYNAMIC_FIELD_UNUSABLE: Final = Message(
    code="dynamic-field-unusable",
    condition="unusable",
    lines=(PDM_FAILED_LINE, FLIT_FAILED_LINE),
    summary="A dynamic [project] field's backend resolver failed: pdm-backend "
    "reading the version from a file or SCM tag, or flit-core reading the "
    "version and description from the module without importing it. The "
    "failure is the resolver's.",
    did="Read the project without the value: the SBOM records no version "
    "(Flit: no version and no description) from the resolver.",
    effect="thinner",
    actor="user",
    advice="Tell the user which resolver failed and its failure, as the line "
    "says. The file the backend reads is often missing or malformed (a "
    "version file, a module docstring); they fix it and generate again. "
    f"{_NO_EDIT}",
    subject_key="FILE",
    since=_SINCE,
)

#: An installed-metadata directory with no METADATA or PKG-INFO.
NO_MARKER_LINE: Final = Line(
    level="WARNING", template="DIR=%(dir)s: %(entry)s has no %(file)s; ignored"
)
#: An installed-metadata directory naming another project.
OTHER_NAME_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: %(entry)s declares name %(name)s, not the "
    "project's; ignored",
)
#: An installed-metadata directory naming no project.
INSTALLED_NO_NAME_LINE: Final = Line(
    level="WARNING", template="DIR=%(dir)s: %(entry)s declares no name; ignored"
)

INSTALLED_METADATA_UNUSABLE: Final = Message(
    code="installed-metadata-unusable",
    condition="unusable",
    lines=(NO_MARKER_LINE, OTHER_NAME_LINE, INSTALLED_NO_NAME_LINE),
    summary="A .dist-info or .egg-info directory in the project directory, "
    "read to complete the declared metadata, is not this project's: it has "
    "no METADATA (or PKG-INFO), or names no project or another one (a "
    "renamed project, a stale install). One whose file cannot be read says "
    "file-unreadable, for the project metadata.",
    did="Ignored that directory: the SBOM takes nothing from it.",
    effect="thinner",
    actor="user",
    advice="Tell the user which directory was ignored and why, as the line "
    "says. A stale one is removed, or the project reinstalled (pip install "
    "-e .), and the SBOM generated again. Do not delete or install anything "
    f"for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

#: Several installed-metadata directories name the project.
CANDIDATES_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: several installed-metadata candidates (%(files)s); "
    "used %(entry)s",
)

INSTALLED_METADATA_AMBIGUOUS: Final = Message(
    code="installed-metadata-ambiguous",
    condition="ambiguous",
    lines=(CANDIDATES_LINE,),
    summary="More than one .dist-info or .egg-info directory in the project "
    "directory names the project (an old install left beside a new one).",
    did="Used the one the line names: a .dist-info before an .egg-info, "
    "then by name, so the same directories give the same choice.",
    effect="weaker",
    actor="user",
    advice="Tell the user which directories were found and which was used, "
    "as the line says. They remove the stale ones and generate again. Do not "
    f"delete anything for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

#: setup.py and setup.cfg give one field two values; setup.py wins.
SETUP_PY_KEPT_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: %(field)s: setup.py and setup.cfg disagree; kept "
    "setup.py's %(kept)s, dropped setup.cfg's %(dropped)s",
)
#: The same; setup.cfg wins.
SETUP_CFG_KEPT_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: %(field)s: setup.py and setup.cfg disagree; kept "
    "setup.cfg's %(kept)s, dropped setup.py's %(dropped)s",
)
#: The declared metadata and the installed one give one field two values.
INSTALLED_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: %(field)s: declared and installed metadata "
    "disagree; kept the declared %(kept)s, dropped the installed %(dropped)s",
)

METADATA_CONFLICT: Final = Message(
    code="metadata-conflict",
    condition="conflict",
    lines=(SETUP_PY_KEPT_LINE, SETUP_CFG_KEPT_LINE, INSTALLED_LINE),
    summary="Two sources of the project's metadata give one field two real "
    "values: setup.py and setup.cfg (a setup() keyword overrides the "
    "setup.cfg option, as setuptools does), or the declared metadata and an "
    "installed .dist-info or .egg-info (a stale install).",
    did="Recorded the value the line keeps and both values as a conflict in "
    "the field's provenance.",
    effect="weaker",
    actor="user",
    advice="Tell the user which field disagrees, what was kept and what "
    "dropped, as the line says. They make the sources agree (or reinstall "
    f"the project) and generate again. {_NO_EDIT}",
    subject_key="DIR",
    since=_SINCE,
)

#: [tool.poetry.extras] beside a [project] Poetry reads instead.
POETRY_EXTRAS_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: [tool.poetry.extras] not read: [project] declares "
    "dependencies or optional-dependencies, which Poetry reads instead; ignored",
)
#: [tool.poetry.dependencies] beside [project] optional-dependencies.
POETRY_DEPENDENCIES_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: [tool.poetry.dependencies] not read: [project] "
    "declares optional-dependencies and no dependencies, which Poetry reads "
    "instead; ignored",
)
#: [tool.poetry] keys a backend other than Poetry's does not read.
POETRY_BACKEND_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: [tool.poetry] %(entries)s not read: build-backend "
    "%(backend)s does not read them; ignored",
)
#: pip option lines in a requirements file setuptools reads.
PIP_OPTIONS_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: %(field)s: pip option lines %(entries)s, which "
    "setuptools does not accept; skipped",
)

METADATA_NO_EFFECT: Final = Message(
    code="metadata-no-effect",
    condition="no-effect",
    lines=(
        POETRY_EXTRAS_LINE,
        POETRY_DEPENDENCIES_LINE,
        POETRY_BACKEND_LINE,
        PIP_OPTIONS_LINE,
    ),
    summary="A project declares something its build backend does not read: a "
    "[tool.poetry] table or keys Poetry ignores because [project] declares "
    "the same, [tool.poetry] keys under another build backend, or pip option "
    "lines (-r, --index-url) in a requirements file setuptools reads for "
    "tool.setuptools.dynamic.",
    did="Read the project as its build backend does, without them.",
    effect="none",
    actor="user",
    advice="Tell the user which declaration has no effect and why, as the "
    "line says; the SBOM states what a build would. They move or remove it "
    f"if it was meant to apply. {_NO_EDIT}",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (
    DYNAMIC_FIELD_NEEDS_BUILD,
    DYNAMIC_FIELD_UNUSABLE,
    INSTALLED_METADATA_UNUSABLE,
    INSTALLED_METADATA_AMBIGUOUS,
    METADATA_CONFLICT,
    METADATA_NO_EFFECT,
)
