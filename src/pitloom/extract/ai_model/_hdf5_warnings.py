# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The warnings of a Keras or HDF5 model's root attributes: one per
attribute not read whole (``model-field-unreadable``), and the raw
``model_config`` cut to its cap (``over-cap``).

See also: :mod:`pitloom.extract.ai_model.hdf5_config` (the parsing that finds
the problems).
"""

from __future__ import annotations

import logging

from pitloom.extract.ai_model.hdf5_config import (
    ATTRIBUTE_FIELDS,
    RAW_CONFIG_CHARS,
    ConfigProblem,
)
from pitloom.logging_config import one_line
from pitloom.messages import (
    ATTRIBUTE_LINE,
    CONFIG_KEPT_LINE,
    CONFIG_RAW_CUT_LINE,
    CONFIG_RAW_LINE,
    MODEL_FIELD_UNREADABLE,
    TRAINING_CONFIG_LINE,
    Cap,
    Line,
    emit,
    warn_over_cap,
)

log = logging.getLogger(__name__)

#: The raw text of a ``model_config`` that gave no class or name, as kept.
RAW_CONFIG_CAP = Cap(RAW_CONFIG_CHARS, "character", "raw-model-config")


def _warn(line: Line, problem: ConfigProblem, **values: object) -> None:
    emit(
        log,
        MODEL_FIELD_UNREADABLE,
        logging.WARNING,
        line=line,
        part=problem.part,
        error=problem.error,
        lost=problem.lost,
        **values,
    )


def log_model_config_problem(
    problem: ConfigProblem | None, raw: str, kept_raw: bool, where: str
) -> None:
    """Say, in one ``WARNING:``, what became of a ``model_config`` that could
    not be read whole: *problem* (``None`` for a valid object without a class
    or name), whether the raw text is *kept_raw* in
    ``properties.model_config_raw`` (cut to :data:`RAW_CONFIG_CHARS`, an
    ``over-cap`` naming the model *where* when that is all), or the fields
    read before it are kept and the rest skipped."""
    cut = kept_raw and len(raw) > RAW_CONFIG_CHARS
    if problem is None:
        if cut:
            warn_over_cap(
                log,
                RAW_CONFIG_CAP,
                where,
                f"the first {RAW_CONFIG_CHARS} of {len(raw)} characters kept in "
                "properties.model_config_raw",
            )
    elif cut:
        _warn(CONFIG_RAW_CUT_LINE, problem, limit=RAW_CONFIG_CHARS, number=len(raw))
    elif kept_raw:
        _warn(CONFIG_RAW_LINE, problem)
    else:
        log_config_kept(problem)


def log_config_kept(problem: ConfigProblem) -> None:
    """Say, in one ``WARNING:``, that a model config was not read whole and
    the fields read before *problem* are kept."""
    _warn(CONFIG_KEPT_LINE, problem)


def log_attribute_problem(name: str, exc: BaseException) -> None:
    """Say, in one ``WARNING:``, that root attribute *name* cannot be read."""
    _warn(ATTRIBUTE_LINE, ConfigProblem(name, one_line(exc), ATTRIBUTE_FIELDS[name]))


def log_training_config_problem(problem: ConfigProblem | None) -> None:
    """Say, in one ``WARNING:``, that a ``training_config`` was not read whole."""
    if problem is not None:
        _warn(TRAINING_CONFIG_LINE, problem)
