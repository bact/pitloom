# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared licence value that is not an SPDX license expression as
written: ``license-expression-malformed`` (LicenseID cannot parse it),
``license-expression-invalid`` (it names no licence LicenseID knows) and
``license-expression-invalid/resolved`` (LicenseID reads one in it); and
the licence the classifiers state: ``license-ambiguous`` (several
classifiers) and ``license-conflict`` (classifiers beside an SPDX
``license``).

See also: :mod:`pitloom.messages._license_say` (the helpers),
:mod:`pitloom.extract._license_classify` and
:mod:`pitloom.extract._license_resolve` (the reading).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: Where a value read as an SPDX license expression only comes from.
_SPDX_ONLY_FIELDS: Final = (
    "PEP 639 project.license, Core Metadata License-Expression, a file's "
    "SPDX-License-Identifier tag, GGUF general.license, a PyPI record's "
    "license_expression"
)
#: What a value of each refusal looks like, for the summaries.
_LOOKS_LIKE: Final = (
    "A licence value that looks like an SPDX license expression (an operator "
    "or a parenthesis, and a word LicenseID reads as a licence id), or any "
    f"value in a field that holds an expression only ({_SPDX_ONLY_FIELDS}), "
)
#: What every refusal does.
_RECORDED_AS_TEXT: Final = (
    "Recorded the value as licence text, not as an expression, and went on; "
    "said once per value per process."
)
#: What the user does not let an agent do.
_NO_EDIT: Final = f"Do not edit the project for them; {ASK_FIRST}"

#: The value, read where a licence text may also stand.
MALFORMED_LINE: Final = Line(
    level="WARNING",
    template="LICENSE=%(license)s: malformed SPDX license expression "
    "(%(license_reason)s); recorded as licence text",
)
#: The value, read from a field that holds an expression only.
MALFORMED_FIELD_LINE: Final = Line(
    level="WARNING",
    template=f"FIELD=%(field)s {MALFORMED_LINE.template}",
)

LICENSE_EXPRESSION_MALFORMED: Final = Message(
    code="license-expression-malformed",
    condition="malformed",
    lines=(MALFORMED_LINE, MALFORMED_FIELD_LINE),
    summary=f"{_LOOKS_LIKE}has a syntax LicenseID cannot parse: an operator "
    "with no operand on one side (MIT OR), a parenthesis without its match. "
    "The reason in brackets is LicenseID's.",
    did=_RECORDED_AS_TEXT,
    effect="weaker",
    actor="user",
    advice="Tell the user which value, as the line shows it, is not a "
    "well-formed SPDX license expression, and that the SBOM holds it as "
    "licence text. They fix the operator syntax in the source (an operand on "
    "each side of AND, OR and WITH, matched parentheses) and generate "
    f"again. {_NO_EDIT}",
    subject_key="LICENSE",
    since=_SINCE,
)

#: The value, read where a licence text may also stand.
INVALID_LINE: Final = Line(
    level="WARNING",
    template="LICENSE=%(license)s: not a valid SPDX license expression "
    "(%(license_reason)s); recorded as licence text",
)
#: The value, read from a field that holds an expression only.
INVALID_FIELD_LINE: Final = Line(
    level="WARNING",
    template="FIELD=%(field)s LICENSE=%(license)s: not read as an SPDX license "
    "expression (%(license_reason)s); recorded as licence text",
)

LICENSE_EXPRESSION_INVALID: Final = Message(
    code="license-expression-invalid",
    condition="invalid",
    lines=(INVALID_LINE, INVALID_FIELD_LINE),
    summary=f"{_LOOKS_LIKE}names no licence LicenseID knows: an operand not "
    "on the SPDX License List (Acme-Terms, MIT OR Foo, Apache-2.0 WITH Bar, a "
    "WITH with no exception after it, read as a name), "
    "or, in a field that holds an expression only, a value on more than one "
    "line or longer than 200 characters (a licence text). The reason in "
    "brackets says which.",
    did=_RECORDED_AS_TEXT,
    effect="weaker",
    actor="user",
    advice="Tell the user which value, as the line shows it, names no SPDX "
    "licence, and that the SBOM holds it as licence text. They write an id on "
    "the SPDX License List, or a LicenseRef- for a licence that is not on "
    "it, and move a licence text to a licence file (PEP 639 license-files), "
    f"then generate again. {_NO_EDIT}",
    subject_key="LICENSE",
    since=_SINCE,
)

#: LicenseID's reading of the value.
RESOLVED_LINE: Final = Line(
    level="INFO",
    template="LICENSE=%(license)s: read as %(expression)s (%(steps)s)",
)
#: The same, for a value read from a named field.
RESOLVED_FIELD_LINE: Final = Line(
    level="INFO", template=f"FIELD=%(field)s {RESOLVED_LINE.template}"
)

LICENSE_EXPRESSION_RESOLVED: Final = Message(
    code="license-expression-invalid/resolved",
    condition="invalid",
    lines=(RESOLVED_LINE, RESOLVED_FIELD_LINE),
    summary="A declared licence value is not an SPDX license expression as "
    "written, and LicenseID reads one in it beyond a change of form: a "
    "re-spelt id (Apache2), a listed licence name (MIT License), a licence "
    'URL, a separator (MIT/Apache-2.0), a stated "or later", a deprecated '
    "id reached by a re-spelling (GPLv3). The steps in brackets are "
    "LicenseID's. A change of form only (case, spacing, a + written as "
    "-or-later) is said at DEBUG, with no code.",
    did="Read the value as that expression. When it is the licence the "
    "package states (not a classifier set that an earlier field beats), the "
    "SBOM records the expression and its provenance keeps the value as "
    "written and the steps (Method: licenseid_resolution, Resolution-1). "
    "Said once per value per process.",
    effect="none",
    actor="none",
    advice="Nothing to do: the SBOM records LicenseID's reading and its "
    "provenance keeps the value as written. If the reading is not what the "
    "author meant, they write the SPDX expression in the source.",
    subject_key="LICENSE",
    since=_SINCE,
)

#: The classifiers, and the expression recorded for them.
AMBIGUOUS_LINE: Final = Line(
    level="WARNING",
    template="CLASSIFIERS=%(classifiers)s: several licence classifiers; recorded "
    "as %(expression)s, assuming AND (they may offer a choice)",
)

LICENSE_AMBIGUOUS: Final = Message(
    code="license-ambiguous",
    condition="ambiguous",
    lines=(AMBIGUOUS_LINE,),
    summary="A package's licence comes from its License :: trove classifiers "
    "(no license or License-Expression field states one), and they name "
    "several licences. Classifiers cannot say whether every licence applies "
    "(AND) or the licences offer a choice (OR).",
    did="Recorded the AND of the licences, a name LicenseID reads as one id "
    "as that id, in sorted classifier order; said once per set of "
    "classifiers per process.",
    effect="weaker",
    actor="user",
    advice="Tell the user that the SBOM assumes every licence the classifiers "
    "name applies (AND), which is wrong when they offer a choice. The "
    "project states its licence as an SPDX license expression in "
    "project.license (PEP 639) and generates again; for a dependency, its "
    f"maintainers do. {_NO_EDIT}",
    subject_key="CLASSIFIERS",
    since=_SINCE,
)

#: The pyproject.toml declaring both.
CONFLICT_LINE: Final = Line(
    level="WARNING",
    template="FILE=%(file)s: an SPDX license expression and License :: "
    "classifiers both state a licence; kept the expression, dropped the "
    "classifiers (PEP 639 transitional state)",
)

LICENSE_CONFLICT: Final = Message(
    code="license-conflict",
    condition="conflict",
    lines=(CONFLICT_LINE,),
    summary="A pyproject.toml declares project.license as an SPDX license "
    "expression (PEP 639) and also License :: trove classifiers that state "
    "a licence, which PEP 639 forbids and pyproject-metadata refuses. A "
    "project moving to PEP 639 often declares both.",
    did="Read the project metadata again without the License :: "
    "classifiers; the SBOM states the expression.",
    effect="none",
    actor="user",
    advice="Tell the user that the SBOM states project.license and leaves "
    "out the License :: classifiers, as PEP 639 asks; the line goes once "
    f"they remove the classifiers from pyproject.toml. {_NO_EDIT}",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (
    LICENSE_EXPRESSION_MALFORMED,
    LICENSE_EXPRESSION_INVALID,
    LICENSE_EXPRESSION_RESOLVED,
    LICENSE_AMBIGUOUS,
    LICENSE_CONFLICT,
)
