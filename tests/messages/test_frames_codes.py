# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A frame of a ``WARNING`` or ``INFO`` line names the exact codes it comes
before: a model scan's (``FORMAT=... FILE=...: ``) the codes a model reader
says, a Git URL fetch's (``Git source: ``) the codes the fetch says after
it, never a sibling variant of one (``url-moved/hf-endpoint``). A line of
another code after the frame is not trusted, the reference does not say the
frame comes before it, and :func:`~pitloom.messages.emit` refuses to put
the frame before it.

See also: tests/messages/test_frames.py (the table and the ``ERROR``
frames), tests/messages/test_drift_sources.py (each line read back after
each frame).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.internal_error import InternalError
from pitloom.extract import scanner
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import (
    FRAMES,
    GIT_FRAME,
    GIT_PREFIX,
    MESSAGES,
    RELAY_FRAME,
    Frame,
    Message,
    emit,
    trusted_message,
)
from pitloom.messages.files import OVER_CAP, TEXT_MALFORMED
from pitloom.messages.git import GIT_COMMAND, GIT_FILTER_UNUSABLE, GIT_URL_INVALID
from pitloom.messages.targets import CONFIG_UNSAFE, CONFIG_UNSAFE_REMOTE_LINE
from tests._message_drift import SAMPLES, source_modules

_LOG = logging.getLogger("pitloom.test_frames_codes")

#: The model readers' package: the scan relays its loggers' records.
_READERS = "pitloom.extract.ai_model"

#: Each helper outside the readers' package a reader calls, to the codes
#: it says on a logger the scan relays. ``warn_over_cap``: the scan says
#: ``over-cap`` again itself, naming the model; ``warn_unless_expression``
#: logs on its own logger, which the scan does not relay.
_HELPERS: dict[str, frozenset[str]] = {
    "warn_lone_surrogates": frozenset({"text-malformed"}),
    "warn_over_cap": frozenset(),
    "warn_unless_expression": frozenset(),
}


#: The codes a Git URL fetch says after its frame. A drift test holds the
#: frame's set and the ``emit(..., frame=GIT_FRAME)`` sites together.
_GIT_FRAMED = frozenset(
    {
        "config-unsafe",
        "git-filter-unusable",
        "git-link-unsafe",
        "git-redirect-unusable",
        "query-no-effect",
        "target-ambiguous/git-page",
        "temp-dir-unwritable",
        "url-moved",
        "url-unsafe",
    }
)
#: The ``frame=`` arguments of an ``emit`` that hands on a frame its caller
#: passed, checked where it is passed (tests/messages/test_frames_build.py).
PASS_THROUGH = frozenset(
    {("core/temp_dirs.py", "frame"), ("core/build_signals.py", "activity.frame")}
)
#: Siblings of those codes that Git never says framed.
_NOT_GIT_FRAMED = (
    "config-unsafe/build-code",
    "target-ambiguous",
    "url-moved/hf-endpoint",
    "url-unsafe/hf-endpoint",
)


def test_every_frame_code_is_catalogued() -> None:
    for frame in FRAMES:
        for code in frame.codes or ():
            assert code in MESSAGES, (frame.template, code)
    assert GIT_FRAME.codes == _GIT_FRAMED


@pytest.mark.parametrize("codes", [None, frozenset()], ids=["none", "empty"])
def test_a_warning_or_info_frame_must_name_its_codes(
    codes: frozenset[str] | None,
) -> None:
    with pytest.raises(ValueError, match="codes"):
        Frame(levels=frozenset({"INFO"}), template="X: ", surface="s", codes=codes)


def test_an_error_frame_names_every_code_or_some() -> None:
    Frame(levels=frozenset({"ERROR"}), template="X: ", surface="s")
    with pytest.raises(ValueError, match="empty"):
        Frame(
            levels=frozenset({"ERROR"}), template="X: ", surface="s", codes=frozenset()
        )


def test_a_frame_allows_its_codes_at_its_levels_only() -> None:
    assert GIT_FRAME.allows("url-moved", "INFO")
    assert not GIT_FRAME.allows("url-moved", "ERROR")
    assert not GIT_FRAME.allows("over-cap", "INFO")
    assert RELAY_FRAME.allows("text-malformed", "WARNING")
    assert not RELAY_FRAME.allows("text-malformed/registry", "WARNING")
    assert not RELAY_FRAME.allows("lfs-pointer-malformed", "WARNING")
    for code in _NOT_GIT_FRAMED:
        assert not any(GIT_FRAME.allows(code, lv) for lv in ("WARNING", "INFO"))


def test_a_sibling_variant_is_not_trusted_after_the_git_frame() -> None:
    """``url-moved/hf-endpoint``'s line after ``Git source: `` is not one
    Pitloom prints."""
    moved = MESSAGES["url-moved/hf-endpoint"]
    (line,) = moved.lines
    text = line.render({"url": "https://hub.example"})
    code = moved.code
    assert trusted_message(f"INFO: {text} [{code}]") is moved
    assert trusted_message(f"INFO: {GIT_PREFIX}{text} [{code}]") is None


def test_a_framed_line_is_trusted_only_for_an_allowed_code() -> None:
    url = "https://example.org/r.git"
    text = f"{GIT_PREFIX}URL={url}: the server rejected the blob filter; "
    text += "fetching without it"
    assert trusted_message(f"INFO: {text} [git-filter-unusable]") is (
        GIT_FILTER_UNUSABLE
    )
    over = OVER_CAP.lines[0]
    printed = over.render({n: SAMPLES[n] for n in over.fields})
    line = f"{over.level}: {GIT_PREFIX}{printed} [over-cap]"
    assert trusted_message(line) is None
    assert trusted_message(f"{over.level}: {printed} [over-cap]") is OVER_CAP


def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().err.splitlines()


def test_emit_puts_the_frame_before_the_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No values (the config line) and values with a ``%`` in the frame."""
    configure_logging()
    emit(
        _LOG,
        CONFIG_UNSAFE,
        logging.INFO,
        line=CONFIG_UNSAFE_REMOTE_LINE,
        frame=GIT_FRAME,
    )
    framed = {"format": "gguf", "file": "d/a%s%%.gguf"}
    emit(
        _LOG,
        TEXT_MALFORMED,
        logging.WARNING,
        frame=RELAY_FRAME,
        frame_values=framed,
        file="m%d",
    )
    config, relayed = _lines(capsys)
    assert config == (
        f"INFO: {GIT_PREFIX}{CONFIG_UNSAFE_REMOTE_LINE.template} [config-unsafe]"
    )
    assert relayed.startswith("WARNING: FORMAT=gguf FILE=d/a%s%%.gguf: FILE=m%d: ")
    assert trusted_message(config) is CONFIG_UNSAFE
    assert trusted_message(relayed) is TEXT_MALFORMED


def test_a_frame_value_with_a_percent_is_not_doubled_on_a_line_with_no_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Logging leaves a record with no arguments as it is, so a ``%`` in the
    frame stays one (every code a real frame precedes with values has them:
    a frame of the test's own, before the config line)."""
    configure_logging()
    frame = Frame(
        levels=frozenset({"INFO"}),
        template="FILE=%(file)s: ",
        surface="a test",
        codes=frozenset({CONFIG_UNSAFE.code}),
    )
    emit(
        _LOG,
        CONFIG_UNSAFE,
        logging.INFO,
        line=CONFIG_UNSAFE_REMOTE_LINE,
        frame=frame,
        frame_values={"file": "a%b"},
    )
    assert _lines(capsys) == [
        f"INFO: FILE=a%b: {CONFIG_UNSAFE_REMOTE_LINE.template} [config-unsafe]"
    ]


def test_emit_refuses_a_frame_that_does_not_allow_the_line() -> None:
    """A code the frame does not name, a level it does not frame, and
    frame values with no frame: each a programming error."""
    over = OVER_CAP.lines[0]
    values = {n: SAMPLES[n] for n in over.fields}
    level = {"WARNING": logging.WARNING, "INFO": logging.INFO}[over.level]
    with pytest.raises(InternalError):
        emit(
            _LOG,
            OVER_CAP,
            level,
            line=over,
            once=None,
            extra=None,
            frame=GIT_FRAME,
            frame_values=None,
            **values,
        )
    with pytest.raises(InternalError):
        emit(
            _LOG,
            GIT_URL_INVALID,
            logging.ERROR,
            line=GIT_URL_INVALID.lines[0],
            frame=GIT_FRAME,
            url="ssh://h/r",
        )
    with pytest.raises(InternalError):
        emit(
            _LOG,
            CONFIG_UNSAFE,
            logging.INFO,
            line=CONFIG_UNSAFE_REMOTE_LINE,
            frame_values={},
        )


def test_the_git_echo_is_built_from_the_frame() -> None:
    assert GIT_COMMAND.template.startswith(GIT_PREFIX)
    assert GIT_FRAME.render({}) == GIT_PREFIX


def _module_of(rel: str) -> ModuleType:
    """The module at *rel*, a path under ``src/pitloom``."""
    dotted = "pitloom." + rel.removesuffix(".py").replace("/", ".")
    return importlib.import_module(dotted.removesuffix(".__init__"))


def _resolve(node: ast.expr, module: ModuleType) -> object:
    """The object a name or a dotted name of *module* stands for.

    Raises:
        LookupError: *node* is neither, or names nothing.
    """
    if isinstance(node, ast.Name):
        return vars(module)[node.id]
    if isinstance(node, ast.Attribute):
        return getattr(_resolve(node.value, module), node.attr)
    raise LookupError(ast.unparse(node))


def _calls(tree: ast.AST, name: str) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = getattr(func, "id", getattr(func, "attr", None))
            if called == name:
                yield node


def _emitted(node: ast.Call, module: ModuleType) -> tuple[Message, int]:
    """The message and level of a call ``emit(log, MESSAGE, LEVEL, ...)``."""
    message = _resolve(node.args[1], module)
    level = _resolve(node.args[2], module)
    assert isinstance(message, Message) and isinstance(level, int), ast.dump(node)
    return message, level


def _reader_modules() -> Iterator[tuple[str, ast.Module, ModuleType]]:
    for rel, tree in source_modules():
        if rel.startswith("extract/ai_model/"):
            yield rel, tree, _module_of(rel)


def _helper_codes(node: ast.Call, module: ModuleType, where: str) -> set[str]:
    """The codes a call of a function from outside the readers' package
    says on a relayed logger: :data:`_HELPERS`; a ``warn_*`` helper, or any
    function handed a logger, not in the table fails."""
    try:
        func = _resolve(node.func, module)
    except LookupError:
        return set()  # a method of a local value
    home = getattr(func, "__module__", None) or ""
    if home.startswith(_READERS) or func is emit:
        return set()
    name = getattr(func, "__name__", "")
    handed = [a for a in node.args if isinstance(a, ast.Name) and a.id in vars(module)]
    logs = [a for a in handed if isinstance(vars(module)[a.id], logging.Logger)]
    if name.startswith("warn_") or logs:
        assert name in _HELPERS, f"{where}:{node.lineno}: {name} not in _HELPERS"
        return set(_HELPERS[name])
    return set()


def test_the_relay_frame_names_every_code_a_reader_says() -> None:
    """Each ``emit`` of a reader at ``WARNING`` or above, and each helper of
    :data:`_HELPERS` it calls: the scan keeps their codes after the frame,
    and no other code (``lfs-pointer-malformed``, which the scan says
    itself)."""
    said: set[str] = set()
    modules = list(_reader_modules())
    assert len(modules) >= 10, "the walk finds the readers"
    for rel, tree, module in modules:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) == "emit":
                message, level = _emitted(node, module)
                if level >= logging.WARNING:
                    said.add(message.code)
            else:
                said |= _helper_codes(node, module, rel)
    assert RELAY_FRAME.codes is not None
    assert said == set(RELAY_FRAME.codes)


def test_every_framed_emit_says_a_code_its_frame_allows() -> None:
    """Each ``emit(..., frame=X)`` outside the catalogue: X allows the
    message's code at the call's level (``emit`` would raise at run time,
    on a path a test may not reach), or X is a frame the caller passed
    (:data:`PASS_THROUGH`). Every code a frame allows is said after it
    somewhere: tests/messages/test_frames_build.py."""
    sites = 0
    for rel, tree in source_modules():
        framed = [
            node
            for node in _calls(tree, "emit")
            if any(
                kw.arg == "frame"
                and not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
                for kw in node.keywords
            )
        ]
        if not framed:
            continue
        module = _module_of(rel)
        for node in framed:
            message, level = _emitted(node, module)
            frame = next(kw.value for kw in node.keywords if kw.arg == "frame")
            if (rel, ast.unparse(frame)) in PASS_THROUGH:
                continue
            found = _resolve(frame, module)
            name = logging.getLevelName(level)
            assert isinstance(found, Frame), f"{rel}:{node.lineno}"
            assert found.allows(message.code, name), f"{rel}:{node.lineno}"
            sites += 1
    assert sites >= 2  # the scan finds the config-unsafe lines


def test_a_scanner_relay_keeps_a_relayed_code_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A reader's ``text-malformed`` record keeps its code after the frame;
    an ``lfs-pointer`` one does not (no reader says it)."""
    lines = {
        "text-malformed": "FILE=m.gguf: lone surrogates written as \\uXXXX",
        "lfs-pointer": "FILE=m.gguf: Git LFS pointer, content not read; run "
        "'git lfs pull' for the content",
    }
    records = []
    for code, text in lines.items():
        record = logging.LogRecord("x", logging.WARNING, "x", 1, text, None, None)
        setattr(record, CODE_ATTR, code)
        records.append(record)
    model: Any = SimpleNamespace(
        distribution_path="demo/m.gguf", physical_path="demo/m.gguf"
    )
    # pylint: disable-next=protected-access
    relog = scanner._relog_reader_records
    with caplog.at_level(logging.WARNING, logger=scanner.log.name):
        relog(records, AiModelFormat.GGUF, model, tmp_path / "m.gguf")
    codes = [getattr(r, CODE_ATTR, None) for r in caplog.records]
    assert codes == ["text-malformed", None]
    first = caplog.records[0].getMessage()
    assert first.startswith("FORMAT=gguf FILE=demo/m.gguf: FILE=m.gguf: ")


def _generator() -> ModuleType:
    """The reference generator, loaded from its file."""
    path = Path(__file__).resolve().parents[2] / "scripts"
    spec = importlib.util.spec_from_file_location(
        "generate_message_reference", path / "generate_message_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("code", sorted(_GIT_FRAMED | set(_NOT_GIT_FRAMED)), ids=str)
def test_the_reference_says_the_git_frame_only_where_git_says_it(code: str) -> None:
    """The section of a code Git says framed names the prefix; a sibling's
    does not."""
    gen = _generator()
    page = gen.render_page(gen.SITES[0], gen.topic_of(code))
    section = page.split(f"### `{code}`\n", 1)[1].split("\n### ", 1)[0]
    noted = f"`{GIT_PREFIX}<text>`" in section
    assert noted is (code in _GIT_FRAMED), section
