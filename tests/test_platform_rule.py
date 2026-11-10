# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``platform`` marker rule (tests/_platform.py) picks the right files."""

from pathlib import Path

import pytest

from tests._platform import is_platform_file


@pytest.mark.parametrize(
    ("relative", "text", "expected"),
    [
        ("cli/test_a.py", "x = 1\n", True),
        ("scripts/test_a.py", "x = 1\n", True),
        ("core/test_a.py", "x = 1\n", False),
        ("core/test_b.py", "import subprocess\n", True),
        ("extract/test_c.py", "path.chmod(0o000)\n", True),
        ("test_d.py", "if sys.platform == 'win32': pass\n", True),
        ("test_e.py", "assert 1 + 1 == 2\n", False),
    ],
    ids=["cli", "scripts", "pure", "subprocess", "chmod", "platform", "plain"],
)
def test_rule(tmp_path: Path, relative: str, text: str, expected: bool) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    assert is_platform_file(path, tmp_path) is expected
