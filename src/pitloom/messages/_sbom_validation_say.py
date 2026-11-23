# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Printing what ``spdx3-validate`` found, for ``loom validate-wheel``,
``loom fragment validate`` and ``embed-wheel --sbom --validate``: its own
text relayed one ``ERROR:`` line per text line after
:data:`~pitloom.messages._sbom_input.VALIDATOR_PREFIX`, with no code (the
words are the validator's), then one coded ``sbom-invalid`` line per
document.

A relayed line has its white space collapsed (a SHACL finding's tabs), a
URL's credentials masked, is cut to :data:`VALIDATOR_LINE_CHARS`
characters and escaped (:func:`~pitloom.logging_config.one_line`); a blank
line is dropped, and a finding the validator gives twice, word for word,
is said once. A path of *names* (a temporary copy) is shown as its name
wherever the validator's text names it; a coded line cuts it as every
name is (:func:`~pitloom.messages._field_writers.cut_name`).

See also: :mod:`pitloom.messages._sbom_input` (the entry),
:mod:`pitloom.cli.commands.utils` (the caller).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Final

from pitloom.logging_config import one_line, print_error
from pitloom.messages._field_writers import cut_name
from pitloom.messages._sbom_input import (
    DOCUMENT_INVALID_LINE,
    MERGED_INVALID_LINE,
    NONE_VALIDATED_LINE,
    NOT_VALIDATED_LINE,
    SBOM_INVALID,
    VALIDATOR_PREFIX,
)

#: The most characters of one relayed line of the validator's text.
VALIDATOR_LINE_CHARS: Final = 1000
#: The source ``spdx3-validate`` gives the findings of the documents merged.
MERGED_SOURCE: Final = "(merged)"


def _shown(text: str, names: Mapping[str, str] | None) -> str:
    """*text* with each path of *names* replaced by its name."""
    for path, name in (names or {}).items():
        text = text.replace(path, name)
    return text


def relay_validator_text(text: str, *, names: Mapping[str, str] | None = None) -> int:
    """Print each line of *text*, ``spdx3-validate``'s own words, as one
    ``ERROR: spdx3-validate: <line>`` line (the command frame before it),
    no code; a blank line is dropped. Returns how many lines it printed."""
    printed = 0
    for line in _shown(text, names).splitlines():
        shown = one_line(line, VALIDATOR_LINE_CHARS, ellipsis=True)
        if shown:
            print_error(VALIDATOR_PREFIX + shown)
            printed += 1
    return printed


def say_validation_findings(
    findings: Iterable[tuple[str, str, str]],
    *,
    names: Mapping[str, str] | None = None,
    per_document: bool = True,
) -> int:
    """Print *findings*, each ``(source, kind, message)`` of
    ``spdx3-validate``'s result in the order given (a repeat of an earlier
    one dropped), as ``<source>: [<kind>] <message>`` relayed by
    :func:`relay_validator_text`, grouped by source in the order each is
    first found; after each source's findings, with *per_document*, its
    one ``sbom-invalid`` line: ``FILE=<name>: not valid SPDX 3 (N
    finding(s) above)``, or, for :data:`MERGED_SOURCE`, the documents
    merged. A source is shown as *names* names it, else as given. Returns
    the number of findings said."""
    by_source: dict[str, list[tuple[str, str]]] = {}
    for source, kind, message in dict.fromkeys(findings):
        by_source.setdefault(source, []).append((kind, message))
    said = 0
    for source, found in by_source.items():
        name = _shown(source, names)
        for kind, message in found:
            relay_validator_text(f"{name}: [{kind}] {message}", names=names)
        said += len(found)
        if not per_document:
            continue
        if source == MERGED_SOURCE:
            text = MERGED_INVALID_LINE.render({"number": len(found)})
        else:
            shown = {"file": cut_name(name), "number": len(found)}
            text = DOCUMENT_INVALID_LINE.render(shown)
        print_error(text, code=SBOM_INVALID.code)
    return said


def say_validator_failure(
    exc: BaseException,
    *,
    file: str | os.PathLike[str] | None = None,
    names: Mapping[str, str] | None = None,
) -> None:
    """Print why ``spdx3-validate`` could not validate: *exc*'s text (its
    class name when it has none) relayed by :func:`relay_validator_text`,
    then one ``sbom-invalid`` line naming the document *file* (as *names*
    names it), or, with ``None`` (several documents), the documents."""
    relay_validator_text(str(exc) or type(exc).__name__, names=names)
    if file is None:
        text = NONE_VALIDATED_LINE.render({})
    else:
        shown = cut_name(_shown(os.fspath(file), names))
        text = NOT_VALIDATED_LINE.render({"file": shown})
    print_error(text, code=SBOM_INVALID.code)
