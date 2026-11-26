# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[project]`` of a ``pyproject.toml`` parsed by ``pyproject-metadata``
(:func:`parse_standard_metadata_with_retry`), with the one conflict it is
allowed to relax (a PEP 639 licence expression beside ``License ::``
classifiers) and the refusal of an overlong version number.

See also: :mod:`pitloom.extract.project.pyproject` (the caller).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyproject_metadata import ConfigurationError, StandardMetadata

from pitloom.core.internal_error import reraise_internal
from pitloom.core.pep440 import MAX_VERSION_NUMBER_DIGITS, has_overlong_number
from pitloom.extract._core_metadata import license_from_classifiers
from pitloom.extract._license import classify_license
from pitloom.messages import CodedValueError, emit
from pitloom.messages.licences import LICENSE_CONFLICT
from pitloom.messages.metadata import METADATA_INVALID, NUMBER_LINE, PROJECT_LINE

log = logging.getLogger(__name__)


def _is_license_classifier_conflict(exc: ConfigurationError) -> bool:
    """Whether *exc* is pyproject-metadata's "SPDX license expression is
    not compatible with 'License ::' classifiers" validation error --
    the one specific, narrow case :func:`read_pyproject` relaxes, not a
    stand-in for treating arbitrary ``project.license`` errors as
    recoverable.

    pyproject-metadata raises ``ConfigurationError`` with
    ``key == "project.license"`` for *two* distinct validation failures
    (this classifier conflict, and a separate pre-2.4-metadata-version
    SPDX-string error) -- ``.key`` alone can't tell them apart, so this
    also matches the full distinguishing phrase from the classifier-
    conflict message specifically. pyproject-metadata exposes no more
    stable discriminator than message text for this, so a reworded message
    stops matching."""
    return (
        exc.key == "project.license"
        and "not compatible with 'License ::' classifiers" in str(exc)
    )


def _drop_placeholder_license(data: dict[str, Any]) -> dict[str, Any] | None:
    """*data* without ``project.license`` when that is only an
    ``UNKNOWN``/``NOASSERTION`` placeholder, else ``None``. The placeholder
    is weak, so the ``License ::`` classifier it conflicts with wins anyway
    (:func:`~pitloom.extract._core_metadata.license_or_classifier`): it is
    the classifiers that carry the licence, never redundant."""
    project_data: dict[str, Any] = data.get("project", {})
    license_value = project_data.get("license")
    classified = (
        classify_license(license_value, warn=False)
        if isinstance(license_value, str)
        else None
    )
    if classified is None or classified.kind != "noassertion":
        return None
    kept = {k: v for k, v in project_data.items() if k != "license"}
    return {**data, "project": kept}


def _drop_redundant_license_classifiers(data: dict[str, Any]) -> dict[str, Any]:
    """Strip ``License ::`` trove classifiers from a parsed
    ``pyproject.toml`` mapping, leaving every other classifier and
    ``[project]`` field untouched."""
    project_data: dict[str, Any] = data.get("project", {})
    classifiers = project_data.get("classifiers", [])
    if not isinstance(classifiers, list):
        return data
    kept = [
        c
        for c in classifiers
        if not (isinstance(c, str) and c.startswith("License ::"))
    ]
    return {**data, "project": {**project_data, "classifiers": kept}}


def _refuse_overlong_numbers(project: dict[str, Any], pyproject_path: Path) -> None:
    """Fail, as on any invalid value, on a ``[project]`` ``version`` or
    ``requires-python`` with an overlong number: ``packaging`` raises a
    plain ``ValueError`` on it while parsing (``version``; 25) or later,
    printing it (``requires-python``, 26). *project* is the ``[project]``
    table (:func:`hold_deep_requirements` has read it as one) of
    *pyproject_path*."""
    for key in ("version", "requires-python"):
        value = project.get(key)
        if isinstance(value, str) and has_overlong_number(value):
            raise CodedValueError(
                METADATA_INVALID,
                line=NUMBER_LINE,
                file=pyproject_path,
                field=f"project.{key}",
                number=MAX_VERSION_NUMBER_DIGITS,
            )


def _invalid_project(pyproject_path: Path, exc: Exception) -> CodedValueError:
    """The ``metadata-invalid`` error for the ``[project]`` table of
    *pyproject_path* that *exc* (pyproject-metadata's) refuses."""
    return CodedValueError(
        METADATA_INVALID, line=PROJECT_LINE, file=pyproject_path, failure=exc
    )


def parse_standard_metadata_with_retry(
    data: dict[str, Any],
    pyproject_path: Path,
    dynamic_fields: list[str],
    *,
    quiet: bool = False,
) -> tuple[StandardMetadata, dict[str, Any]]:
    """Parse *data* via ``StandardMetadata.from_pyproject()``, retrying once
    if the failure is the PEP 639 transitional classifier conflict.

    Returns ``(std, data)`` -- *data* is returned too since the retry path
    rewrites it (:func:`_drop_redundant_license_classifiers`), and
    :func:`read_pyproject` needs that rewritten mapping for its own later
    ``data.get("project", {})``/``_try_read_poetry()`` calls, not the
    original.

    *quiet* suppresses the PEP 639 transitional-state ``WARNING:`` -- for a
    caller that already emitted it once for this same file and is re-parsing
    only to apply a different, unrelated setting (e.g.
    :func:`pitloom.extract.project.resolve_project_with_lockfile`'s
    peek-then-reread), not because anything about the license/classifier
    data changed.

    Raises:
        ValueError: The metadata is not valid, its ``version`` or
            ``requires-python`` has an overlong number too
            (:func:`pitloom.core.pep440.has_overlong_number`).
    """
    _refuse_overlong_numbers(data["project"], pyproject_path)
    try:
        return (
            StandardMetadata.from_pyproject(
                data,
                project_dir=str(pyproject_path.parent),
                dynamic_metadata=dynamic_fields or None,
                allow_extra_keys=True,
            ),
            data,
        )
    except ConfigurationError as exc:
        if not _is_license_classifier_conflict(exc):
            raise _invalid_project(pyproject_path, exc) from exc
        # Classifiers that state no licence (a category alone) lose to
        # any `license`, a placeholder too, and are dropped silently.
        classifiers = data.get("project", {}).get("classifiers")
        states_licence = isinstance(classifiers, list) and bool(
            license_from_classifiers(c for c in classifiers if isinstance(c, str))
        )
        placeholder_dropped = (
            _drop_placeholder_license(data) if states_licence else None
        )
        # PEP 639: an SPDX `license` expression together with `License ::`
        # trove classifiers is a hard error in pyproject-metadata, yet
        # projects mid-migration declare both. Retry once without the
        # classifiers; the SPDX expression stays authoritative.
        if placeholder_dropped is not None:
            data = placeholder_dropped
        else:
            if states_licence and not quiet:
                emit(log, LICENSE_CONFLICT, logging.WARNING, file=pyproject_path)
            data = _drop_redundant_license_classifiers(data)
        try:
            return (
                StandardMetadata.from_pyproject(
                    data,
                    project_dir=str(pyproject_path.parent),
                    dynamic_metadata=dynamic_fields or None,
                    allow_extra_keys=True,
                ),
                data,
            )
        # pylint: disable-next=broad-exception-caught
        except Exception as retry_exc:
            reraise_internal(retry_exc)
            raise _invalid_project(pyproject_path, retry_exc) from retry_exc
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        reraise_internal(exc)
        raise _invalid_project(pyproject_path, exc) from exc
