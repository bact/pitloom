# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helper for the model-usage tests: the accesses a script makes to a model."""

from __future__ import annotations

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_ast import find_usages
from pitloom.extract._usage_match import UsageModel
from pitloom.extract._usage_parse import parse_python


def accesses(
    source: str, name: str = "model.pkl", paths: tuple[str, ...] = ("model.pkl",)
) -> frozenset[UsageAccess]:
    """The accesses *source* makes to the model *name* at *paths*."""
    (found,) = find_usages(parse_python(source), [UsageModel(name, paths)])
    return found
