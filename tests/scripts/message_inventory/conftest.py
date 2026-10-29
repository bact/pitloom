# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A tiny ``src/pitloom`` tree to inventory, and the loaded tool.

See also: ``scripts/message_inventory/`` (the tool).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from tests._message_inventory import load, load_main

MODULES = {
    # The catalogue's own emit(): its body is the mechanism, out of scope.
    "messages/_emit.py": """\
def emit(log, message, level, fmt, *args):
    log.log(level, fmt, *args, extra=code_extra(message))
""",
    # Three coded sites: emit(), extra=code_extra(), CodedValueError().
    "coded.py": """\
import logging

from pitloom.messages import CodedValueError, MSG, code_extra, emit

_log = logging.getLogger(__name__)


def check(path, message):
    emit(_log, message, logging.WARNING, "FILE=%s: held", path)
    _log.warning("FILE=%s: held again", path, extra=code_extra(MSG))
    raise CodedValueError(MSG, "FILE: refused")
""",
    # In-scope uncoded sites, one DEBUG (out of scope), a print_error with
    # a literal None code, one that forwards an exception's code.
    "uncoded.py": """\
import logging

from pitloom.logging_config import print_error
from pitloom.messages import code_of

_log = logging.getLogger(__name__)


def check(path, exc):
    _log.warning("FILE=%s: odd", path)
    _log.info("FILE=%s: fine", path)
    _log.debug("FILE=%s: detail", path)
    print_error("boom", code=None)
    print_error("boom again", code=code_of(exc))
""",
    # Two helpers whose body logs: one codes its line, one does not.
    "helpers.py": """\
import logging

from pitloom.messages import MSG, CodedValueError, code_extra

_log = logging.getLogger(__name__)


def refuse(path):
    return CodedValueError(MSG, path)


def warn_coded(path):
    _log.warning("FILE=%s: held", path, extra=code_extra(MSG))


def warn_plain(path):
    _log.warning("FILE=%s: odd", path)
""",
    # A call of each helper, and a raise with text.
    "callers.py": """\
from pitloom.helpers import refuse, warn_coded, warn_plain


def run(path):
    warn_coded(path)
    warn_plain(path)
    raise ValueError("bad value: %s" % path)


def run_via_object(self, path):
    self.out.warn_coded(path)


def run_refuse(path):
    raise refuse(path)
""",
}


@pytest.fixture(name="mi", scope="session")
def mi_fixture() -> ModuleType:
    """The loaded ``message_inventory`` package."""
    return load()


@pytest.fixture(name="mi_main", scope="session")
def mi_main_fixture() -> ModuleType:
    """The package's ``__main__`` module."""
    return load_main()


@pytest.fixture(name="tree")
def tree_fixture(tmp_path: Path) -> Path:
    """A repository root holding the four modules under ``src/pitloom``."""
    package = tmp_path / "src" / "pitloom"
    (package / "messages").mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in MODULES.items():
        (package / name).write_bytes(source.encode("utf-8"))
    return tmp_path
