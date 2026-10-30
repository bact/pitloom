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
def emit(log, message, level, *, line=None, once=None, **values):
    log.log(level, line.template, values, extra={"pitloom_code": message.code})
""",
    # Three coded sites: emit(), extra={CODE_ATTR: ...}, CodedValueError().
    "coded.py": """\
import logging

from pitloom.messages import CODE_ATTR, MSG, CodedValueError, emit

_log = logging.getLogger(__name__)


def check(path, message):
    emit(_log, message, logging.WARNING, file=path)
    _log.warning("FILE=%s: held again", path, extra={CODE_ATTR: MSG.code})
    raise CodedValueError(MSG, path=path)
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
    # A programming error, by its class (also imported under another name),
    # is out of scope; the same text as a ValueError is a message.
    "internal.py": """\
from pitloom.core.internal_error import InternalError
from pitloom.core.internal_error import InternalError as Bug


def check(level):
    raise InternalError(f"unknown level: {level}")


def check_again(level):
    raise Bug(f"unknown level: {level}")


def check_user(level):
    raise ValueError(f"unknown level: {level}")
""",
    # A relay that says another record again with its code: it forwards.
    "relay.py": """\
import logging

from pitloom.messages import relay_extra

_log = logging.getLogger(__name__)


def relay(record, text):
    _log.warning("FORMAT=x %s", text, extra=relay_extra(record, "WARNING", text))
""",
    # Two helpers whose body logs: one codes its line, one does not.
    "helpers.py": """\
import logging

from pitloom.messages import MSG, CodedValueError

_log = logging.getLogger(__name__)


def refuse(path):
    return CodedValueError(MSG, path=path)


def warn_coded(path):
    _log.warning("FILE=%s: held", path, extra={"pitloom_code": MSG.code})


def warn_plain(path):
    _log.warning("FILE=%s: odd", path)
""",
    # The catalogue's over-cap helper: its body is the mechanism too.
    "messages/_over_cap_warning.py": """\
from pitloom.messages._emit import emit


def warn_over_cap(log, cap, where, outcome="skipped", *, once=False, key=None):
    emit(log, cap, 30, name=where, outcome=outcome)
""",
    # The helper's call and a wrapper's call (coded, in scope; the wrapper's
    # own call is counted at its callers), and a raise naming the code by its
    # pitloom_code keyword (coded).
    "caps.py": """\
import logging

from pitloom.messages import OVER_CAP, Cap
from pitloom.messages._over_cap_warning import warn_over_cap
from pitloom.remote_errors import RemoteSourceError

_log = logging.getLogger(__name__)
NAME_CAP = Cap(9, "character", "name")


def warn_field_cap(field, key, cap, read):
    warn_over_cap(_log, cap, key, read)


def check(path, cap):
    warn_over_cap(_log, cap, path)
    warn_field_cap("a b", "authors", cap, None)
    warn_over_cap(_log, model_cap(NAME_CAP, "gguf"), path, "cut")
    raise RemoteSourceError("git.too-large", "too large", pitloom_code=OVER_CAP.code)
""",
    # A catalogue helper saying its message through emit (the mechanism),
    # and its calls: each a coded site in scope.
    "messages/_file_warning.py": """\
from pitloom.messages._emit import emit


def warn_file_unreadable(log, exc, *, file, use=None):
    emit(log, UNREAD, 30, file=file, use=use, failure=exc)
""",
    "reads.py": """\
import logging

from pitloom.messages._file_warning import warn_file_unreadable

_log = logging.getLogger(__name__)


def read(path, exc):
    warn_file_unreadable(_log, exc, file=path, use="for file scanning")
""",
    # A model reader's raise is the detail of the scanner's line, by where
    # it is; its dispatch's own refusal is a message, and a CodedImportError
    # is coded by its class, whatever message it is given.
    "extract/ai_model/gguf.py": """\
def read_gguf(path, exc):
    raise ValueError(f"Failed to read GGUF file {path}: {exc}")
""",
    "extract/ai_model/reader.py": """\
from pitloom.messages import CodedImportError


def read_ai_model(path):
    raise ValueError(f"{path}: not a model")


def need(message, module):
    raise CodedImportError(message, module=module, requirement="pitloom[x]")
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
        (package / name).parent.mkdir(parents=True, exist_ok=True)
        (package / name).write_bytes(source.encode("utf-8"))
    return tmp_path
