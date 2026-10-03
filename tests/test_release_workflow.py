# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release SBOM's path through ``.github/workflows``: the SBOM
the build hook embedded is checked, extracted, attached and signed as is.

``pypi-publish.yml`` runs only on a release, so its structure is pinned
here; ``build.yml`` runs the same extraction on every push and PR.

See also: tests/test_build_workflow.py, tests/scripts/test_extract_wheel_sbom.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"
_PUBLISH_BUILD = ("pypi-publish.yml", "build")
_PR_BUILD = ("build.yml", "build-wheel")


def _job(workflow: str, job: str) -> dict[str, Any]:
    text = (_WORKFLOWS / workflow).read_text(encoding="utf-8")
    jobs: dict[str, dict[str, Any]] = yaml.safe_load(text)["jobs"]
    return jobs[job]


def _steps(workflow: str, job: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _job(workflow, job)["steps"]
    return steps


def _uses(steps: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [s for s in steps if str(s.get("uses", "")).startswith(action)]


@pytest.mark.parametrize(("workflow", "job"), [_PUBLISH_BUILD, _PR_BUILD])
def test_extract_script_requires_magika(workflow: str, job: str) -> None:
    runs = [s.get("run", "") for s in _steps(workflow, job)]
    [run] = [r for r in runs if "scripts/extract_wheel_sbom.py" in r]
    assert "--require-magika" in run


@pytest.mark.parametrize(("workflow", "job"), [_PUBLISH_BUILD, _PR_BUILD])
def test_content_type_extra_installed(workflow: str, job: str) -> None:
    installs = _uses(_steps(workflow, job), "./.github/actions/install-pitloom")
    assert installs
    assert all("content-type" in s["with"]["package-spec"] for s in installs)


def test_publish_build_exposes_extracted_name() -> None:
    [step] = [
        s
        for s in _steps(*_PUBLISH_BUILD)
        if "scripts/extract_wheel_sbom.py" in s.get("run", "")
    ]
    assert step["id"] == "sbom"
    assert '--github-output "$GITHUB_OUTPUT"' in step["run"]
    assert _job(*_PUBLISH_BUILD)["outputs"]["sbom-name"] == (
        "${{ steps.sbom.outputs.sbom-name }}"
    )


def test_publish_build_does_not_re_embed() -> None:
    steps = _steps(*_PUBLISH_BUILD)
    assert not [s for s in steps if s.get("uses") == "./"]
    assert not [s for s in steps if "embed-wheel" in str(s)]


def test_publish_build_uploads_extracted_sbom() -> None:
    steps = _steps(*_PUBLISH_BUILD)
    [upload] = [
        s
        for s in _uses(steps, "actions/upload-artifact")
        if s["with"]["name"] == "sbom"
    ]
    assert upload["with"]["path"] == "sbom/"
    assert upload["with"]["if-no-files-found"] == "error"
    # After every check, so a failed one leaves no artifact to attach.
    after = steps[steps.index(upload) + 1 :]
    assert not [s for s in after if "run" in s]
    assert _job(*_PUBLISH_BUILD)["outputs"] == {
        "sbom-name": "${{ steps.sbom.outputs.sbom-name }}"
    }


def test_sign_and_attest_covers_the_sbom() -> None:
    steps = _steps("pypi-publish.yml", "sign-and-attest")
    downloads = _uses(steps, "actions/download-artifact")
    assert {s["with"]["name"]: s["with"]["path"] for s in downloads} == {
        "dist": "dist/",
        "sbom": "sbom/",
    }
    [sign] = _uses(steps, "sigstore/gh-action-sigstore-python")
    [attest] = _uses(steps, "actions/attest-build-provenance")
    sbom = "sbom/${{ needs.build.outputs.sbom-name }}"
    assert sbom in sign["with"]["inputs"]
    assert sbom in attest["with"]["subject-path"]
    [upload] = [s for s in steps if "gh release upload" in s.get("run", "")]
    assert 'sbom/${SBOM_NAME}.sigstore.json"' in upload["run"]
    assert upload["env"]["SBOM_NAME"] == "${{ needs.build.outputs.sbom-name }}"


def test_attach_release_sbom_keeps_both_success_gates() -> None:
    gate = _job("pypi-publish.yml", "attach-release-sbom")["if"]
    assert "needs.build.result == 'success'" in gate
    assert "needs.publish.result == 'success'" in gate
    assert "needs.build.outputs.sbom-name != ''" in gate
