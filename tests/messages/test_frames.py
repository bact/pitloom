# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the frames: the table of :mod:`pitloom.messages` lists
exactly the strings the surfaces put before a message's text, so a line a
surface prints is trusted, and no other.

See also: tests/messages/test_messages_fields.py (a frame's own rules).
"""

from __future__ import annotations

import ast

from pitloom.messages import HANDLER_FRAMES
from tests._message_drift import SRC_ROOT, source_modules


def _handler_texts() -> set[str]:
    """The text of every ``@cli_error_handler("...")`` in the source."""
    return {
        node.args[0].value
        for _, tree in source_modules()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "cli_error_handler"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def test_the_table_holds_every_cli_handler_frame_and_no_other() -> None:
    """A frame missing from the table leaves a real line untrusted; one
    nothing prints would let a forged line through."""
    found = _handler_texts()
    assert len(found) >= 10  # the scan does find the handlers
    assert found == set(HANDLER_FRAMES)


def test_the_build_hook_frame_is_in_the_table() -> None:
    """The hook's one failure line is ``<frame>: <exception>``."""
    tree = ast.parse((SRC_ROOT / "plugins" / "hatch.py").read_bytes())
    texts = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "error"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert {t.removesuffix(": %s") for t in texts if t.endswith(": %s")} == {
        "SBOM generation failed"
    }
    assert "SBOM generation failed" in HANDLER_FRAMES
