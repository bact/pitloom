# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``config-unsafe``: each ``INFO:`` of an untrusted project's own settings
(a Git URL's, a downloaded sdist's) reads back as its entry, at that level
only, and changes nothing in the SBOM.

See also: tests/assemble/test_generate_git_url.py (the library route) and
tests/cli/test_cli_project_git_url.py (the command line).
"""

from __future__ import annotations

from pitloom.messages import CONFIG_UNSAFE, trusted_message


def test_each_line_is_trusted_as_its_entry_and_changes_nothing() -> None:
    """The Git line and the PyPI sdist line."""
    assert len(CONFIG_UNSAFE.lines) == 2
    for line in CONFIG_UNSAFE.lines:
        text = line.render({"file": "x-1.0.tar.gz"} if line.fields else {})
        assert trusted_message(f"INFO: {text} [config-unsafe]") is CONFIG_UNSAFE
        assert trusted_message(f"WARNING: {text} [config-unsafe]") is None
    assert (CONFIG_UNSAFE.effect, CONFIG_UNSAFE.actor) == ("none", "none")
