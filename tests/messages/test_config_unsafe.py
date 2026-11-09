# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``config-unsafe``: the one ``INFO:`` of a Git URL's own settings reads
back as its entry, at that level only, and changes nothing in the SBOM.

See also: tests/assemble/test_generate_git_url.py (the library route) and
tests/cli/test_cli_project_git_url.py (the command line).
"""

from __future__ import annotations

from pitloom.messages import CONFIG_UNSAFE, trusted_message


def test_the_line_is_trusted_as_its_entry_and_changes_nothing() -> None:
    (line,) = CONFIG_UNSAFE.lines
    assert trusted_message(f"INFO: {line.template} [config-unsafe]") is CONFIG_UNSAFE
    assert trusted_message(f"WARNING: {line.template} [config-unsafe]") is None
    assert (CONFIG_UNSAFE.effect, CONFIG_UNSAFE.actor) == ("none", "none")
