# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.py`` and ``setup.cfg`` options merged as setuptools merges them,
and the :class:`~pitloom.core.project.ProjectMetadata` built from them.

setuptools sets the ``setup()`` keywords first and applies a ``setup.cfg``
option only when the keyword's value is falsy
(``setuptools.config.setupcfg.ConfigHandler.__setitem__``): per option
(``author`` and ``author_email`` apart, ``url`` and ``project_urls`` apart),
on the raw value, a list replacing the other, never joined. Pitloom reads
``setup.py`` without running it, so a keyword it cannot use (not a
literal, blank, of a type it does not read) is not an option here and
``setup.cfg``'s is used, with a ``WARNING:``. A placeholder licence
(``UNKNOWN``) gives way to a real licence in the other file. A real
disagreement on the name, the licence, the version or ``python_requires``
is recorded as a conflict.

See also: :mod:`pitloom.extract.project.setuptools_py` and
:mod:`pitloom.extract.project.setuptools_cfg` (the option readers),
:mod:`pitloom.extract.project._field_agreement` (the conflict rule).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, NamedTuple

from pitloom.core.project import ConflictCandidate, ProjectMetadata, provenance_key_for
from pitloom.core.provenance import parse_provenance_value
from pitloom.extract._core_metadata import (
    first_license,
    license_cascade,
    license_from_classifiers,
)
from pitloom.extract.project._field_agreement import add_conflict, values_agree
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

SETUP_PY = "setup.py"
SETUP_CFG = "setup.cfg"


@dataclass(frozen=True)
class SetupOption:
    """One setuptools option as one file states it.

    *value* is parsed (stripped string, list, dict) or ``None``; *source* is
    its provenance. *given* is setuptools' own test, the truthiness of the
    raw value (``""``/``[]`` is not given), of the normalised one for
    ``version`` and ``install_requires``: a given ``setup()`` keyword
    overrides ``setup.cfg``. *declared* is whether the file itself states
    the option (``False`` for a ``setup.cfg`` value only inherited from
    ``[DEFAULT]``); it gates the provenance of a field whose empty value is
    a statement (``install_requires = ``).
    """

    value: Any
    source: str
    given: bool = True
    declared: bool = True


#: A file's options, keyed by setuptools option name.
SetupOptions = dict[str, SetupOption]


def requirement_lines(text: str) -> list[str]:
    """Requirements in *text* as setuptools reads them
    (``setuptools._reqs.parse_strings``): a line each, blank lines and
    ``#`` lines left out, a `` #`` comment dropped, a line ending in ``\\``
    joined with the next."""
    lines = (line.strip() for line in text.splitlines())
    # The comment cut is not stripped: "x \\  # c" does not continue.
    items = iter(
        line.partition(" #")[0] for line in lines if line and not line.startswith("#")
    )
    requirements: list[str] = []
    for item in items:
        parts = [item]
        while parts and parts[-1].endswith("\\"):
            following = next(items, None)
            if following is None:
                return requirements
            _cut_continuation(parts)
            parts.append(following)
        requirements.append("".join(parts).strip())
    return requirements


def _cut_continuation(parts: list[str]) -> None:
    """``"".join(parts)[:-2].strip()`` in place, in time linear in the
    parts removed: setuptools cuts two characters for the ``\\``. Each
    part starts with a non-blank character, so only the last needs a
    strip, and it never strips to nothing."""
    cut = 2
    while cut and parts:
        last = parts.pop()
        if len(last) > cut:
            parts.append(last[:-cut])
        cut = max(0, cut - len(last))
    if parts:
        parts[-1] = parts[-1].rstrip()


def merge_setup_options(cfg: SetupOptions, py: SetupOptions) -> SetupOptions:
    """*cfg* with each *py* option that setuptools keeps over it: one that is
    given, or one ``setup.cfg`` does not have."""
    merged = dict(cfg)
    for key, option in py.items():
        if option.given or key not in cfg:
            merged[key] = option
    return merged


def _value(options: SetupOptions, key: str) -> Any:
    option = options.get(key)
    return None if option is None else option.value


def resolve_setuptools_licence(
    merged: SetupOptions, cfg: SetupOptions
) -> tuple[str | None, str | None]:
    """``(licence, provenance)`` as a built wheel gives it -- the ``license``
    setuptools keeps, then the ``License ::`` classifiers kept, by
    :func:`~pitloom.extract._core_metadata.license_cascade` -- except that a
    placeholder there gives way to a real ``license`` in ``setup.cfg`` that
    ``setup.py``'s overrode. ``(None, None)`` when none states a licence."""
    field, classifiers = merged.get("license"), merged.get("classifiers")
    index, licence = license_cascade(
        [None if field is None else field.value],
        [] if classifiers is None else classifiers.value,
    )
    chosen = None if index is None else classifiers if index == 1 else field
    overridden = cfg.get("license")
    # first_license([x, x]) is 0: no check that it is the same option
    if overridden is not None and first_license([licence, overridden.value]) == 1:
        return overridden.value, overridden.source
    return licence, None if chosen is None else chosen.source


def _authors(merged: SetupOptions) -> list[dict[str, str]]:
    name, email = _value(merged, "author"), _value(merged, "author_email")
    entry = {k: v for k, v in (("name", name), ("email", email)) if v}
    return [entry] if entry else []


def _urls(merged: SetupOptions) -> dict[str, str]:
    urls: dict[str, str] = {}
    if _value(merged, "url"):
        urls["Homepage"] = _value(merged, "url")
    urls.update(_value(merged, "project_urls") or {})
    return urls


#: ProjectMetadata field -> the option it is read from, its provenance set
#: when the value is non-empty.
_VALUE_GATED = {
    "version": "version",
    "description": "description",
    "readme": "long_description",
}

#: Provenance key -> the options it is read from, its provenance set when
#: either is declared, even empty. Built from both files, it names both.
_PRESENCE_GATED = {
    "requires_python": ("python_requires",),
    "keywords": ("keywords",),
    "dependencies": ("install_requires",),
    "authors": ("author", "author_email"),
    "urls": ("url", "project_urls"),
}


def _joint_source(options: list[SetupOption]) -> str:
    """The provenance of a field built from *options*: the one option's,
    or, from both files, ``Source: setup.py, setup.cfg | Field: <setup.py
    field>, <setup.cfg field>``."""
    by_file: dict[str, str] = {}
    for option in options:
        entry = parse_provenance_value(option.source)
        by_file.setdefault(entry["source"], entry["location"])
    if len(by_file) == 1:
        return options[0].source
    files = (SETUP_PY, SETUP_CFG)
    return (
        f"Source: {', '.join(files)}"
        f" | Field: {', '.join(by_file[name] for name in files)}"
    )


def _provenance(merged: SetupOptions, metadata: ProjectMetadata) -> dict[str, str]:
    prov: dict[str, str] = {}
    name = _value(merged, "name")
    if name:
        prov["name"] = merged["name"].source
    for field_name, key in _VALUE_GATED.items():
        option = merged.get(key)
        if option is not None and option.value and option.source:
            prov[field_name] = option.source
    for prov_key, keys in _PRESENCE_GATED.items():
        declared = [merged[k] for k in keys if k in merged and merged[k].declared]
        # the files the values came from, else the one declaring it empty
        stating = [o for o in declared if o.value] or declared[:1]
        if stating:
            prov[prov_key] = _joint_source(stating)
    if "authors" in prov and metadata.authors:
        prov["copyright_text"] = (
            "Source: Pitloom generator | Method: inferred_from_authors"
        )
    return prov


def build_setuptools_metadata(cfg: SetupOptions, py: SetupOptions) -> ProjectMetadata:
    """:class:`~pitloom.core.project.ProjectMetadata` from *cfg* and *py*
    merged by :func:`merge_setup_options`; name ``""`` when neither file
    names the project."""
    merged = merge_setup_options(cfg, py)
    metadata = ProjectMetadata(
        name=_value(merged, "name") or "",
        version=_value(merged, "version"),
        description=_value(merged, "description"),
        readme=_value(merged, "long_description"),
        requires_python=_value(merged, "python_requires"),
        keywords=list(_value(merged, "keywords") or []),
        authors=_authors(merged),
        urls=_urls(merged),
        dependencies=list(_value(merged, "install_requires") or []),
    )
    metadata.provenance = _provenance(merged, metadata)
    licence, source = resolve_setuptools_licence(merged, cfg)
    metadata.license_name = licence
    if licence and source:  # a stated licence always has a source
        metadata.provenance["license"] = source
    return metadata


class ConflictReport(NamedTuple):
    """Where a ``setup.py``/``setup.cfg`` disagreement is reported."""

    subject: str
    quiet: bool


def _record(
    metadata: ProjectMetadata,
    field_name: str,
    sides: tuple[tuple[Any, str], tuple[Any, str]],
    py_wins: bool,
    report: ConflictReport,
) -> None:
    """Record the ``(value, source)`` *sides* (``setup.py``'s first) as a
    conflict on *field_name*, the winner first, with one ``WARNING:``."""
    py_side, cfg_side = sides
    ordered = (py_side, cfg_side) if py_wins else (cfg_side, py_side)
    candidates: list[ConflictCandidate] = [
        {"value": value, "role": "declared", "source": source}
        for value, source in ordered
    ]
    key = provenance_key_for(field_name)
    add_conflict(metadata, key, candidates)
    if not report.quiet:
        log.warning(
            "%s: setup.py and setup.cfg disagree on %s"
            " (setup.py %r, setup.cfg %r) -- keeping %s's",
            loggable(report.subject),
            key,
            py_side[0],
            cfg_side[0],
            SETUP_PY if py_wins else SETUP_CFG,
        )


def own_licence(options: SetupOptions) -> tuple[str | None, str]:
    """``(licence, provenance)`` one file states on its own: its
    ``license``, else its ``License ::`` classifier, a placeholder giving
    way. Never warns, unlike the cascade the metadata is built with."""
    field, classifiers = options.get("license"), options.get("classifiers")
    candidates = [
        None if field is None else field.value,
        license_from_classifiers([] if classifiers is None else classifiers.value),
    ]
    index = first_license(candidates)
    if index is None:
        return None, ""
    chosen = field if index == 0 else classifiers
    return candidates[index], "" if chosen is None else chosen.source


#: ProjectMetadata field -> option, checked for a real value overridden.
_OVERRIDE_CHECKED = (
    ("name", "name"),
    ("version", "version"),
    ("requires_python", "python_requires"),
)


def record_setuptools_conflicts(
    metadata: ProjectMetadata,
    cfg: SetupOptions,
    py: SetupOptions,
    report: ConflictReport,
) -> None:
    """Record where the two files state different real values: the name,
    version and ``python_requires`` ``setup.py`` overrides, and the licence each
    file states on its own (:func:`own_licence`), whichever file's is kept
    (a ``license`` field beats a classifier)."""
    for field_name, key in _OVERRIDE_CHECKED:
        py_option, cfg_option = py.get(key), cfg.get(key)
        if not (py_option and cfg_option and py_option.given):
            continue
        if not (py_option.value and cfg_option.value):
            continue
        if values_agree(field_name, py_option.value, cfg_option.value):
            continue
        sides = (
            (py_option.value, py_option.source),
            (cfg_option.value, cfg_option.source),
        )
        _record(metadata, field_name, sides, True, report)
    py_licence, cfg_licence = own_licence(py), own_licence(cfg)
    # A placeholder agrees with anything (values_agree).
    if not (py_licence[0] and cfg_licence[0]) or values_agree(
        "license_name", py_licence[0], cfg_licence[0]
    ):
        return
    py_wins = metadata.provenance.get("license") == py_licence[1]
    _record(metadata, "license_name", (py_licence, cfg_licence), py_wins, report)
