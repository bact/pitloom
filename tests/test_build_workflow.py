# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``.github/workflows/build.yml``'s SBOM validation reporting.

A validation step records ``failure=network`` or ``failure=invalid`` (from
``scripts/retry_network.py``'s exit status); a step stopped before it records
one (``timeout-minutes``, cancellation) leaves it empty. Only ``invalid`` may
be reported as non-conformance, in every place that reports it.

See also: tests/scripts/test_retry_network.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_ARM = re.compile(r"^\s*([\w*]+)\) (.*)$", re.MULTILINE)

#: Step id -> wording that states a non-conformance verdict.
_VERDICTS = {
    "validate": ("does not conform", "Review the SBOM content for SPDX compliance"),
    "validate_wheel_sbom": ("embedded SBOM content (schema/SHACL)",),
}


@pytest.mark.parametrize(("step_id", "phrases"), sorted(_VERDICTS.items()))
def test_only_invalid_reported_as_nonconformance(
    step_id: str, phrases: tuple[str, ...]
) -> None:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build-wheel"]["steps"]
    output = f"steps.{step_id}.outputs.failure"

    def verdict(text: str) -> bool:
        return any(phrase in text for phrase in phrases)

    # The step maps retry_network.py's exit status 75 to network, others invalid.
    [run] = [s["run"] for s in steps if s.get("id") == step_id]
    arms = dict(_ARM.findall(run))
    assert arms["75"] == "failure=network ;;" and arms["*"] == "failure=invalid ;;"
    assert 'echo "failure=${failure}" >> "$GITHUB_OUTPUT"' in run

    # The ::error:: step: one arm per failure value, the verdict in one only.
    [run] = [s["run"] for s in steps if output in s.get("env", {}).get("FAILURE", "")]
    arms = dict(_ARM.findall(run))
    assert {label: verdict(text) for label, text in arms.items()} == {
        "network": False,
        "invalid": True,
        "*": False,
    }

    # Summary wording: every ||-alternative stating the verdict needs invalid.
    terms = [
        term
        for s in steps
        for expression in _EXPRESSION.findall(s.get("run", ""))
        for term in expression.split("||")
        if verdict(term)
    ]
    assert terms
    assert all(f"{output} == 'invalid'" in term for term in terms), terms
