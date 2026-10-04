# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared RFC 822 Core-Metadata parsing helpers, usable against either
:class:`email.message.Message` (raw ``METADATA``/``PKG-INFO`` text) or
:class:`importlib.metadata.PackageMetadata` (an installed distribution) --
both expose the same ``__contains__``/``__getitem__``/``get_all()``
interface.
"""

from __future__ import annotations

import email.message
import logging
import re
from collections.abc import Iterable, Sequence
from importlib.metadata import PackageMetadata
from typing import TYPE_CHECKING

from pitloom.extract._license import classify_license
from pitloom.extract.license_refs import classifier_expression
from pitloom.logging_config import warn_once

if TYPE_CHECKING:
    #: The two RFC 822 Core-Metadata carriers callers pass to
    #: :func:`parse_project_urls`. A structural ``Protocol`` was tried
    #: first and rejected: mypy's protocol-conformance check does not
    #: reliably match a single, non-overloaded ``Protocol`` method against
    #: these two types' real ``@overload``-ed ``get_all()`` (verified
    #: interactively -- a minimal repro still fails even with matching
    #: parameter names/kinds), so a plain union of the two concrete types
    #: is used instead. Guarded by ``TYPE_CHECKING`` since
    #: ``email.message.Message[str, str]`` is only subscriptable for a
    #: type checker, not at runtime.
    _MessageLike = email.message.Message[str, str] | PackageMetadata


def _get_str(msg: _MessageLike, name: str) -> str | None:
    """Return *msg*'s value for header *name*, or ``None`` when absent --
    guards with ``in`` before ``__getitem__`` since ``PackageMetadata``'s
    ``__getitem__`` is typed to return ``str`` (not ``str | None``), i.e.
    it may raise/misbehave on a missing key rather than returning
    ``None`` the way :meth:`email.message.Message.get` does."""
    return msg[name] if name in msg else None


def parse_project_urls(
    msg: _MessageLike,
    *,
    lowercase_labels: bool = False,
    include_homepage: bool = True,
    include_download: bool = False,
) -> dict[str, str]:
    """``Project-URL`` (``Label, URL`` -- first-comma-only split, a URL's
    own query string can legally contain commas) plus optionally legacy
    ``Home-page``/``Download-URL``. ``Project-URL`` always wins on a key
    collision with ``Home-page``, matching every existing call site's net
    behavior regardless of which order they used to achieve it.

    Parameters preserve each existing call site's own tested behavior --
    see each call site for which flags it needs; this function
    intentionally stays parametrized rather than one-size-fits-all so no
    site's behavior changes silently.

    A malformed ``Project-URL`` entry (no comma) is silently dropped --
    matches every existing call site's behavior, not a deviation worth a
    ``WARNING:``.
    """
    urls: dict[str, str] = {}
    if include_homepage:
        homepage = _get_str(msg, "Home-page")
        if homepage:
            urls["Homepage"] = homepage
    if include_download:
        download = _get_str(msg, "Download-URL")
        if download:
            urls["Download"] = download
    for entry in msg.get_all("Project-URL") or []:
        if "," in entry:
            label, url = entry.split(",", 1)
            label = label.strip()
            if lowercase_labels:
                label = label.lower()
            urls[label] = url.strip()
    return urls


#: One line per set of licence classifiers; ``%r`` escapes them.
_SEVERAL_CLASSIFIERS_MESSAGE = (
    "CLASSIFIERS=%r: several license classifiers; recorded as %r, assuming AND"
    " (they may offer a choice)"
)

_logger = logging.getLogger(__name__)

#: The fold a Core-Metadata writer puts before each continuation line of a
#: multi-line value: 8 spaces (setuptools, hatchling), 7 spaces and ``|``
#: (the older ``Description`` convention) or a tab (RFC 5322).
_FOLD_RE = re.compile(r"\n(?:        |       \||\t)")


def _unfolded(value: str | None) -> str | None:
    """*value* with each continuation line's fold removed, so a multi-line
    licence text reads as the bytes the project wrote."""
    return None if value is None else _FOLD_RE.sub("\n", value)


def _licence_classifiers(classifiers: Iterable[str]) -> list[str]:
    """The ``License ::`` classifiers in *classifiers*, sorted, no repeats."""
    return sorted({c for c in classifiers if c.startswith("License ::")})


def _classifier_names(classifiers: Iterable[str]) -> list[str]:
    """The licence names the ``License ::`` classifiers give, in classifier
    order (sorted), no repeats, blanks left out."""
    names = (c.rsplit("::", maxsplit=1)[-1].strip() for c in classifiers)
    return [n for n in dict.fromkeys(names) if n]


def license_from_classifiers(classifiers: Iterable[str]) -> str | None:
    """The licence the ``License ::`` trove classifiers state, or ``None``:
    one licence name as written; several, their ``AND``
    (:func:`~pitloom.extract.license_refs.classifier_expression`), in sorted
    classifier order so a build tool's reordering changes nothing."""
    names = _classifier_names(_licence_classifiers(classifiers))
    if not names:
        return None
    return names[0] if len(names) == 1 else classifier_expression(names)


def _warn_several_classifiers(classifiers: Iterable[str], recorded: str) -> None:
    """One ``WARNING:`` per set when *recorded* is the ``AND`` of several
    licence classifiers."""
    found = _licence_classifiers(classifiers)
    if len(_classifier_names(found)) > 1:
        warn_once(
            _logger,
            "license-classifiers:" + "\x00".join(found),
            _SEVERAL_CLASSIFIERS_MESSAGE,
            found,
            recorded,
        )


def first_license(candidates: Sequence[str | None]) -> int | None:
    """The index of the licence to record from *candidates*, in priority
    order: the first that states one, except that ``NOASSERTION``/``UNKNOWN``
    is weak and gives way to any later one (``NONE`` is a statement). The
    first weak one when no other states a licence; ``None`` when none states
    any (absent, blank). The one weak-cascade rule for a package's own
    licence fields and classifiers, on every surface."""
    weak: int | None = None
    for index, value in enumerate(candidates):
        classified = classify_license(value, warn=False)
        if classified is None:
            continue
        if classified.kind != "noassertion":
            return index
        if weak is None:
            weak = index
    return weak


def license_cascade(
    fields: Sequence[str | None], classifiers: Iterable[str]
) -> tuple[int | None, str | None]:
    """``(index, licence)`` of the licence to record from *fields* (in
    priority order) and then the ``License ::`` *classifiers*, by
    :func:`first_license`; index ``len(fields)`` is the classifier. ``(None,
    None)`` when none states a licence. The one cascade for a package's own
    licence and for a dependency's record."""
    classifiers = list(classifiers)  # read twice: a generator would be spent
    candidates = [*fields, license_from_classifiers(classifiers)]
    index = first_license(candidates)
    if index is None:
        return None, None
    licence = candidates[index]
    if index == len(fields) and licence is not None:
        _warn_several_classifiers(classifiers, licence)
    return index, licence


def license_or_classifier(
    primary: str | None, classifiers: Iterable[str]
) -> tuple[str | None, bool]:
    """``(licence, from_classifier)``: *primary*, then a ``License ::``
    classifier, by :func:`license_cascade`; *primary* as given when neither
    states a licence."""
    index, licence = license_cascade([primary], classifiers)
    if index is None:
        return primary, False
    return licence, index == 1


def classifier_provenance(source: str) -> str:
    """*source* with the note that the licence came from a classifier."""
    return f"{source} | Field: Classifier"


def core_metadata_license_with_source(
    msg: _MessageLike, source: str
) -> tuple[str | None, str]:
    """``(licence, provenance)`` for a Core-Metadata carrier read from
    *source*: ``License-Expression``, ``License``, then its ``License ::``
    classifiers, by :func:`license_cascade` (so a weak
    ``License-Expression: UNKNOWN`` gives way to ``License``), each header
    unfolded; the provenance names the classifier when one was used. When
    none states a licence: ``None`` if neither header is present, ``""`` if
    one is present but blank (declared "no value", not absent).
    """
    fields = [
        _unfolded(_get_str(msg, "License-Expression")),
        _unfolded(_get_str(msg, "License")),
    ]
    index, licence = license_cascade(fields, msg.get_all("Classifier") or [])
    if index is None:
        return ("" if any(f is not None for f in fields) else None), source
    return licence, classifier_provenance(source) if index == 2 else source
