# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared fixture for exercising the ``use_lockfile``/``--no-use-lockfile``
opt-out: a small project whose direct dependency (``requests``) is also
resolvable via a sibling ``pylock.toml``, which additionally pins a
transitive-only package (``idna``) never named in
``[project.dependencies]`` -- present in a generated SBOM only when the
lock-file cascade actually ran, the clearest signal for whether it did.

Previously hand-copied, with slightly drifting content, across
``tests/assemble/test_generate_project_sbom_use_lockfile.py``,
``tests/assemble/test_model_generator_doc_identity.py``, and
``tests/cli/test_cli_project.py`` -- see AGENTS.md's "pattern hand-copied
across 3+ call sites drifts" recurring-bug-pattern note.
"""

from __future__ import annotations

from pathlib import Path

PYPROJECT_WITH_REQUESTS_DEPENDENCY = """
[project]
name = "locked-app"
version = "0.1.0"
dependencies = ["requests>=2.0"]
""".strip()

PYLOCK_WITH_TRANSITIVE_IDNA = """
lock-version = "1.0"
created-by = "test"
[[packages]]
name = "requests"
version = "2.31.0"
[[packages]]
name = "idna"
version = "3.7"
""".strip()


def write_locked_deps_project(
    project_dir: Path, *, disable_cascade_in_config: bool = False
) -> Path:
    """Write :data:`PYPROJECT_WITH_REQUESTS_DEPENDENCY` and
    :data:`PYLOCK_WITH_TRANSITIVE_IDNA` into *project_dir* (created if
    needed) and return it.

    ``disable_cascade_in_config`` appends ``[tool.pitloom] use-lockfile =
    false`` to the written ``pyproject.toml``, for a test asserting on the
    config-only (no CLI/library override) default.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    pyproject = PYPROJECT_WITH_REQUESTS_DEPENDENCY
    if disable_cascade_in_config:
        pyproject += "\n\n[tool.pitloom]\nuse-lockfile = false\n"
    (project_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (project_dir / "pylock.toml").write_text(
        PYLOCK_WITH_TRANSITIVE_IDNA, encoding="utf-8"
    )
    return project_dir
