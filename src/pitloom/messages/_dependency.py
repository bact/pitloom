# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared dependency Pitloom does not list, or lists with a doubt: one
that is not a valid declaration (``requirement-invalid``), a Poetry local
source (``requirement-unusable``), an extra gate needing several extras
together (``extra-gate-ambiguous``) or one Pitloom cannot isolate
(``extra-gate-unusable``), a direct reference not looked up on PyPI
(``dependency-name-ambiguous``), and a lock pin that disagrees with the
declaration (``dependency-pin-conflict``).

A skipped dependency is said by its cause (:data:`CAUSE_LINES`); the cause
picks the code and the line. A direct reference's URL is never printed:
its name only.

See also: :mod:`pitloom.messages._lock_say` (the helpers that say them),
:mod:`pitloom.messages.dependencies` (the public names),
:mod:`pitloom.core.requirements` (the expansion of extras).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
_SKIPPED: Final = "skipped"
#: Which runs read declared dependencies.
DECLARATION_SURFACES: Final = (
    "every run that reads a project's declared dependencies (loom project, "
    "loom generate, loom enrich --project-dir, the build hook, the library)"
)


def _dependency(text: str) -> Line:
    """A ``WARNING`` line naming the dependency and where it is declared,
    then *text*, then that it is skipped."""
    return Line(
        level="WARNING",
        template=f"dependency %(dependency)s (%(declared_in)s): {text}; {_SKIPPED}",
    )


def _extra_entry(text: str) -> Line:
    """A ``WARNING`` line naming the extra, its entry and where it is
    declared, then *text*, then that it is skipped."""
    return Line(
        level="WARNING",
        template="extra %(extra_name)s entry %(dependency)s (%(declared_in)s): "
        f"{text}; {_SKIPPED}",
    )


_NOT_PEP_508: Final = "not a PEP 508 requirement"
_MARKER: Final = "its marker does not parse: %(failure)s"

DEPENDENCY_NOT_PEP_508_LINE: Final = _dependency(_NOT_PEP_508)
#: A Poetry table poetry-core cannot convert.
DEPENDENCY_NOT_CONVERTIBLE_LINE: Final = _dependency(
    "not convertible to PEP 508: %(failure)s"
)
#: A Poetry dependency that is optional and in no extra.
DEPENDENCY_UNLISTED_OPTIONAL_LINE: Final = _dependency("optional and in no extra")
EXTRA_NOT_PEP_508_LINE: Final = _extra_entry(_NOT_PEP_508)
EXTRA_MARKER_LINE: Final = _extra_entry(_MARKER)
#: A self-reference naming an extra the project does not declare.
EXTRA_UNDECLARED_EXTRA_LINE: Final = _extra_entry(
    "names an extra the project does not declare"
)
#: A self-reference closing a cycle of extras.
EXTRA_CYCLE_LINE: Final = _extra_entry("closes a cycle of self-references")
#: A Poetry extra naming a dependency not declared.
EXTRA_UNDECLARED_DEPENDENCY_LINE: Final = _extra_entry(
    "not a declared Poetry dependency"
)
#: A dependency that is not PEP 508, met while assembling the document.
REQUIRED_LINE: Final = Line(
    level="WARNING",
    template=f"dependency %(dependency)s: {_NOT_PEP_508}; recorded as required",
)
#: A dependency that is not PEP 508, given a locked version.
LOCKED_UNCHECKED_LINE: Final = Line(
    level="WARNING",
    template=f"dependency %(dependency)s: {_NOT_PEP_508}; locked version "
    "%(version)s used unchecked",
)

REQUIREMENT_INVALID: Final = Message(
    code="requirement-invalid",
    condition="invalid",
    lines=(
        DEPENDENCY_NOT_PEP_508_LINE,
        DEPENDENCY_NOT_CONVERTIBLE_LINE,
        DEPENDENCY_UNLISTED_OPTIONAL_LINE,
        EXTRA_NOT_PEP_508_LINE,
        EXTRA_MARKER_LINE,
        EXTRA_UNDECLARED_EXTRA_LINE,
        EXTRA_CYCLE_LINE,
        EXTRA_UNDECLARED_DEPENDENCY_LINE,
        REQUIRED_LINE,
        LOCKED_UNCHECKED_LINE,
    ),
    summary="A declared dependency, or an entry of an extra, is not a valid "
    "declaration: not PEP 508, an extra's marker that does not parse, a "
    "Poetry table "
    "poetry-core cannot convert, a Poetry optional dependency in no extra "
    "or an extra naming one not declared, a self-reference to an extra the "
    "project does not declare, or a self-reference closing a cycle of "
    "extras.",
    did=f"Said by {DECLARATION_SURFACES}. Left the entry out of the SBOM's "
    "dependencies (a cycle: dropped where it closes, the rest of the "
    "extras kept); one that is not PEP 508 met while assembling the "
    "document is recorded as a required dependency; one a lock file pins is "
    "recorded at the locked version, unchecked against it. The SBOM is "
    "written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which declaration is invalid and why, as the line "
    "says, and that it is not in the SBOM as declared. They fix the "
    "declaration in pyproject.toml, setup.cfg or setup.py (a build would "
    f"refuse most of these too). Do not edit the project for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A Poetry dependency on a local path or file.
DEPENDENCY_LOCAL_SOURCE_LINE: Final = _dependency(
    "a local %(source_kind)s source, not portable"
)

REQUIREMENT_UNUSABLE: Final = Message(
    code="requirement-unusable",
    condition="unusable",
    lines=(DEPENDENCY_LOCAL_SOURCE_LINE,),
    summary="A Poetry dependency comes from a local path or file: valid, "
    "but it names this machine's files, so it has no portable requirement "
    "to record.",
    did=f"Said by {DECLARATION_SURFACES}. Left the dependency out of the "
    "SBOM's dependencies. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which dependency is not in the SBOM and why, as "
    "the line says. Nothing is wrong with the project; a dependency "
    "published to a registry, or declared by version, is recorded. Do not "
    f"edit the project for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A requirement needing several extras together.
JOINED_LINE: Final = Line(
    level="WARNING",
    template="dependency %(dependency)s: needs extras %(extra_name)s together; "
    "recorded as optional for any of them",
)

EXTRA_GATE_AMBIGUOUS: Final = Message(
    code="extra-gate-ambiguous",
    condition="ambiguous",
    lines=(JOINED_LINE,),
    summary="A requirement declared in one extra carries an extra marker of "
    "its own, so it is installed only with several extras together. An SBOM "
    "relationship states one optional scope, not a set of extras that must "
    "all be asked for.",
    did="Recorded the dependency as optional, its comment naming every "
    "extra it needs. The SBOM is written.",
    effect="weaker",
    actor="none",
    advice="Nothing to do: the SBOM names the dependency as optional, with "
    "the extras it needs in its comment.",
    since=_SINCE,
)

#: A dependency whose extra marker cannot be isolated.
GATE_LINE: Final = Line(
    level="WARNING",
    template="PACKAGE=%(package)s: the extra marker of %(dependency)s cannot "
    "be isolated; recorded as required",
)
#: A self-reference whose extra marker cannot be isolated.
SELF_GATE_LINE: Final = Line(
    level="WARNING",
    template="PACKAGE=%(package)s: the extra marker of self-reference "
    "%(dependency)s cannot be isolated; the extras it requests recorded as "
    "required",
)

EXTRA_GATE_UNUSABLE: Final = Message(
    code="extra-gate-unusable",
    condition="unusable",
    lines=(GATE_LINE, SELF_GATE_LINE),
    summary="A dependency's marker tests an extra in a way Pitloom cannot "
    "isolate from its other clauses (it reads the marker's text, never "
    "evaluates it), so Pitloom cannot tell which extra installs it.",
    did="Recorded the dependency (for a self-reference, the requirements of "
    "the extras it requests) as required, not optional. The SBOM is "
    "written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which dependency is recorded as required though "
    "its marker names an extra, as the line says. A marker whose extra "
    "test is joined to its other clauses with 'and' is read as optional. "
    f"Do not edit the project for them; {ASK_FIRST}",
    subject_key="PACKAGE",
    since=_SINCE,
)

#: A direct reference (``name @ URL``) assembled online.
DIRECT_REFERENCE_LINE: Final = Line(
    level="INFO",
    template="PACKAGE=%(package)s: a direct reference; not looked up on PyPI",
)

DEPENDENCY_NAME_AMBIGUOUS: Final = Message(
    code="dependency-name-ambiguous",
    condition="ambiguous",
    lines=(DIRECT_REFERENCE_LINE,),
    summary="A dependency is a direct reference (name @ URL): its name may "
    "not be the PyPI project of that name, so PyPI's record of the name may "
    "not describe it.",
    did="Did not look the dependency up on PyPI, so nothing PyPI states "
    "about the name is recorded for it. Said once per package and "
    "document, never offline. The SBOM is written.",
    effect="thinner",
    actor="none",
    advice="Nothing to do: the SBOM lists the dependency from its "
    "declaration; its URL is its source.",
    subject_key="PACKAGE",
    since=_SINCE,
)

#: The lock pins a version other than the declared exact pin.
EXACT_PIN_KEPT_LINE: Final = Line(
    level="WARNING",
    template="PACKAGE=%(package)s: lock and declared exact pin disagree; kept "
    "the declared %(kept)s, dropped the locked %(dropped)s",
)
#: The locked version does not satisfy the declared constraint.
LOCKED_KEPT_LINE: Final = Line(
    level="WARNING",
    template="PACKAGE=%(package)s: locked version does not satisfy the "
    "declared constraint; kept the locked %(kept)s, dropped the declared "
    "%(dropped)s",
)

DEPENDENCY_PIN_CONFLICT: Final = Message(
    code="dependency-pin-conflict",
    condition="conflict",
    lines=(EXACT_PIN_KEPT_LINE, LOCKED_KEPT_LINE),
    summary="A project's lock file and its declared dependency disagree: the "
    "lock pins a version other than an exact declared pin (==), or one the "
    "declared constraint does not allow. A lock file not regenerated after "
    "the declaration changed is the usual cause.",
    did="Recorded the version the line keeps: an exact declared pin over the "
    "lock, else the locked version. The SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which dependency disagrees, what was kept and what "
    "dropped, as the line says. They regenerate the lock file (or fix the "
    "declaration) and generate again. Do not run the lock tool or edit the "
    f"project for them; {ASK_FIRST}",
    subject_key="PACKAGE",
    since=_SINCE,
)

#: The causes a skipped dependency or extra entry is said by: cause ->
#: (the line for a dependency, the line for an extra's entry), ``None``
#: where the cause does not apply. A line naming ``failure`` takes the
#: exception; ``source_kind``, the kind of local source.
CAUSE_LINES: Final[Mapping[str, tuple[Line | None, Line | None]]] = MappingProxyType(
    {
        "not-pep-508": (DEPENDENCY_NOT_PEP_508_LINE, EXTRA_NOT_PEP_508_LINE),
        "marker": (None, EXTRA_MARKER_LINE),
        "not-convertible": (DEPENDENCY_NOT_CONVERTIBLE_LINE, None),
        "local-source": (DEPENDENCY_LOCAL_SOURCE_LINE, None),
        "undeclared-extra": (None, EXTRA_UNDECLARED_EXTRA_LINE),
        "cycle": (None, EXTRA_CYCLE_LINE),
        "undeclared-dependency": (None, EXTRA_UNDECLARED_DEPENDENCY_LINE),
        "unlisted-optional": (DEPENDENCY_UNLISTED_OPTIONAL_LINE, None),
    }
)

ENTRIES: Final = (
    REQUIREMENT_INVALID,
    DEPENDENCY_PIN_CONFLICT,
    REQUIREMENT_UNUSABLE,
    EXTRA_GATE_AMBIGUOUS,
    EXTRA_GATE_UNUSABLE,
    DEPENDENCY_NAME_AMBIGUOUS,
)
