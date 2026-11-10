# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run ``git`` for a remote source: no redirect followed, no credential
prompt, no LFS download, a time and an output limit."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess  # nosec B404
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from subprocess import run as _run_command  # nosec B404
from typing import IO, cast

from pitloom.core.model_extract_limit import MAX_DOWNLOAD_BYTES_KEY
from pitloom.core.url_masking import (
    mask_checkout,
    sanitize_url,
    sanitize_url_credentials,
)
from pitloom.extract.remote import git_url
from pitloom.extract.remote._git_size import SizeCap, tree_bytes
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable
from pitloom.messages import (
    CLONE_LINE,
    DOWNLOAD_FAILED,
    DOWNLOAD_TIMEOUT,
    GIT_NETWORK_FAILED_LINE,
    GIT_OUTPUT_LINE,
    GIT_TIMEOUT_LINE,
    OVER_CAP,
    Cap,
)

log = logging.getLogger(__name__)

__all__ = [
    "GIT_TIMEOUT_SECONDS",
    "MAX_OUTPUT_BYTES",
    "GitRunner",
    "is_network_failure",
]

#: Seconds one ``git`` call may take; the calls of one fetch share a deadline.
GIT_TIMEOUT_SECONDS = 600.0

#: Bytes of output one call may produce (a server listing a million refs).
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_READ_CHUNK = 64 * 1024

#: Seconds between looks at how much a running call has written.
_SIZE_POLL_SECONDS = 0.25

#: Whether a call runs in its own process group, killed as one; elsewhere
#: (Windows) ``taskkill`` ends the process tree.
_POSIX = os.name == "posix"

#: Seconds ``taskkill`` may take to end a process tree.
_TASKKILL_SECONDS = 10.0

#: Settings every call runs with. A redirect is followed by hand (each hop
#: checked), and git-lfs, which would fetch from an address the repository's
#: own ``.lfsconfig`` names, is switched off.
_SAFE_CONFIG = (
    "http.followRedirects=false",
    "filter.lfs.smudge=",
    "filter.lfs.process=",
    "filter.lfs.required=false",
)

#: Environment variables that point git at another repository or add
#: settings; one set by the caller (a git hook) must not reach the fetch.
_SCRUBBED_ENV = re.compile(
    r"GIT_(DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|NAMESPACE|COMMON_DIR|"
    r"ALTERNATE_OBJECT_DIRECTORIES|CONFIG_COUNT|CONFIG_PARAMETERS|"
    r"CONFIG_KEY_\d+|CONFIG_VALUE_\d+)"
)

#: Lines of git's standard error that say what went wrong.
_ERROR_LINE = re.compile(r"(fatal|error|remote): ")

#: The lines of those that git (or curl through it) writes itself; a
#: ``remote:`` line is the server's own text.
_OWN_ERROR_LINE = re.compile(r"(fatal|error): ")

#: What a line of git's says that is not git's own words: a quoted span (a
#: URL, a path, a repository name; a quote after a letter is an apostrophe,
#: ``Couldn't``), a URL and what follows ``remote error:`` (the server's
#: text).
_NOT_GITS_WORDS = re.compile(
    r"(?<![A-Za-z])'[^']*'|[A-Za-z][A-Za-z0-9+.-]*://\S*|remote error:.*",
    re.IGNORECASE,
)

#: What git (through curl) says when the server could not be reached or the
#: transfer broke: a ``download-network-failed``. Any other failure (a
#: repository, ref or sign-in the server refused, an HTTP 4xx answer) is no
#: network failure and carries no code. Each is a phrase of curl's, its TLS
#: library's or git's own (a ref name holds no space): a single word such as
#: ``SSL`` would match a repository or branch named for it.
_NETWORK_FAILURE = re.compile(
    r"Could(n't| not) resolve (host|proxy)|Failed to connect|Couldn't connect"
    r"|Connection (refused|reset|timed out)|Operation timed out"
    r"|Network is unreachable|No route to host"
    r"|SSL certificate problem|SSL peer certificate|(SSL|TLS) connect error"
    r"|(Open|Libre|Boring)SSL SSL_|SSL routines|SSL: (no alternative|certificate)"
    r"|gnutls_handshake\(\) failed|server certificate verification failed"
    r"|schannel: |error setting certificate"
    r"|Empty reply from server|transfer closed|Recv failure|Send failure"
    r"|early EOF|unexpected disconnect|Proxy CONNECT aborted"
    r"|RPC failed; curl \d+|RPC failed; HTTP 5\d\d"
    r"|The requested URL returned error: 5\d\d"
    r"|Received HTTP code 5\d\d from proxy",
    re.IGNORECASE,
)

#: The locale every call runs in: git translates its messages (Git for
#: Windows into the display language), and :func:`is_network_failure` and
#: the callers that read a failure's text read git's English.
_LOCALE = "C"

#: Variables that would choose another language over :data:`_LOCALE`.
_LOCALE_ENV = ("LANGUAGE", "LC_MESSAGES", "LANG")


@dataclass
class GitRunner:
    """Runs ``git`` calls that share one deadline.

    Every call runs with ``http.followRedirects=false`` (redirects are followed
    by hand, each hop checked), git-lfs off (it fetches from an address the
    repository names), no credential prompt (a private repository fails fast)
    and only the allowed transports.
    """

    seconds: float = field(default_factory=lambda: GIT_TIMEOUT_SECONDS)
    started: float = field(default_factory=time.monotonic)
    #: The most bytes a call that fetches may write below its *watch*
    #: directory; ``None`` for no limit.
    max_bytes: int | None = None

    def remaining(self) -> float:
        """Seconds left of the shared deadline."""
        return self.seconds - (time.monotonic() - self.started)

    def run(
        self,
        args: list[str],
        what: str,
        *,
        echo: bool = True,
        watch: str | None = None,
    ) -> str:
        """Run ``git`` with *args*; return its standard output. With *watch*
        (a directory the call writes to) and :attr:`max_bytes`, the call is
        stopped once that directory holds more.

        Raises:
            RemoteSourceError: ``git.not-found`` (no ``git``),
                ``git.timeout`` (the deadline passed), ``git.too-large``
                (the cap was passed), ``git.output-too-large`` or
                ``git.clone-failed`` (git failed; the message is its own).
        """
        git = shutil.which("git")
        if git is None:
            raise RemoteSourceError(
                "git.not-found", "git is not installed or not on PATH."
            )
        command = [git]
        for setting in _SAFE_CONFIG:
            command += ["-c", setting]
        command += args
        if echo:
            log.info(
                "Git source: $ %s",
                loggable(
                    sanitize_url_credentials(shlex.join(map(sanitize_url, command)))
                ),
            )
        left = self.remaining()
        if left <= 0:
            raise self._timeout(what)
        cap = None
        if watch is not None and self.max_bytes is not None:
            cap = SizeCap(watch, self.max_bytes)
        status, out, err = _capture(command, left, cap)
        if cap is not None and (cap.exceeded or tree_bytes(watch or "") > cap.limit):
            reason = Cap(cap.limit, "byte", MAX_DOWNLOAD_BYTES_KEY).reason_values()
            raise RemoteSourceError(
                "git.too-large",
                CLONE_LINE.render({**reason, "command": what}),
                pitloom_code=OVER_CAP.code,
            )
        if status is None:
            raise self._timeout(what)
        if out is None:
            raise RemoteSourceError(
                "git.output-too-large",
                GIT_OUTPUT_LINE.render({"command": what, "size": MAX_OUTPUT_BYTES}),
                pitloom_code=OVER_CAP.code,
            )
        if status != 0:
            raise _failed(what, err, status)
        return out

    def _timeout(self, what: str) -> RemoteSourceError:
        """``git.timeout``: the shared deadline passed before or during the
        call *what*."""
        values = {"command": what, "seconds": max(round(self.seconds), 1)}
        return RemoteSourceError(
            "git.timeout",
            GIT_TIMEOUT_LINE.render(values),
            pitloom_code=DOWNLOAD_TIMEOUT.code,
        )


def _failed(what: str, err: str, status: int) -> RemoteSourceError:
    """``git.clone-failed`` for the call *what* that exited *status*: its
    text is git's own (:func:`_failure`); when git could not reach the
    server (:data:`_NETWORK_FAILURE`), it is the ``download-network-failed``
    line."""
    text = _failure(err, status)
    if not is_network_failure(err):
        return RemoteSourceError("git.clone-failed", text)
    return RemoteSourceError(
        "git.clone-failed",
        GIT_NETWORK_FAILED_LINE.render({"command": what, "error": text}),
        pitloom_code=DOWNLOAD_FAILED.code,
    )


def is_network_failure(err: str) -> bool:
    """Whether git's standard error *err* says, in its own words on one of
    its ``fatal:``/``error:`` lines, that the server could not be reached or
    the transfer broke. A ``remote:`` line, and a quoted span, a URL or a
    ``remote error:`` of a line (:data:`_NOT_GITS_WORDS`), are text the
    user or the server chose, never a cause."""
    return any(
        _NETWORK_FAILURE.search(_NOT_GITS_WORDS.sub(" ", line))
        for line in err.splitlines()
        if _OWN_ERROR_LINE.match(line.strip())
    )


def _failure(err: str, status: int) -> str:
    """What git said went wrong, as one line fit for ``ERROR:``: its
    ``fatal:``/``error:``/``remote:`` lines (a server writes the last kind
    itself), without credentials, the temporary path or control characters."""
    lines = [ln.strip() for ln in err.splitlines() if _ERROR_LINE.match(ln.strip())]
    text = "; ".join(lines) or " ".join(err.split()) or f"git exited {status}"
    text = mask_checkout(sanitize_url_credentials(text))
    return loggable(text)


def _environment() -> dict[str, str]:
    """The environment git runs in: the caller's, without what points git
    elsewhere, with no prompt, no LFS download, only the allowed transports
    and English messages (:data:`_LOCALE`)."""
    env = {k: v for k, v in os.environ.items() if not _SCRUBBED_ENV.fullmatch(k)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    env["GIT_ALLOW_PROTOCOL"] = ":".join(sorted(git_url.ALLOWED_SCHEMES))
    for name in _LOCALE_ENV:
        env.pop(name, None)
    env["LC_ALL"] = _LOCALE
    return env


def _drain(stream: IO[bytes], keep: list[bytes]) -> None:
    """Read *stream* to its end, keeping the first :data:`MAX_OUTPUT_BYTES`
    bytes: a server cannot fill the disk or memory with its messages."""
    kept = 0
    while block := stream.read(_READ_CHUNK):
        if kept < MAX_OUTPUT_BYTES:
            keep.append(block[: MAX_OUTPUT_BYTES - kept])
            kept += len(block)


def _taskkill() -> str | None:
    """The path of Windows' ``taskkill`` (``%SystemRoot%\\System32`` first, so
    a copy in the current folder is not run), or ``None`` when there is none."""
    root = os.environ.get("SystemRoot")
    if root:
        candidate = os.path.join(root, "System32", "taskkill.exe")
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("taskkill")


def _kill(proc: subprocess.Popen[bytes]) -> None:
    """Kill *proc* and what it started (git-remote-https holds the pipe
    open): its process group on POSIX, its process tree elsewhere."""
    if _POSIX:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            # Already gone: macOS answers EPERM for the group of a process that
            # has exited and is not yet reaped.
            pass
        return
    # The tree first: once *proc* is gone, taskkill cannot find its children.
    taskkill = _taskkill()
    if taskkill is not None:
        # A non-zero exit means the process is already gone.
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _run_command(  # nosec B603: argv list, no shell
                [taskkill, "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=_TASKKILL_SECONDS,
            )
    proc.kill()


def _watch_size(
    proc: subprocess.Popen[bytes], cap: SizeCap, done: threading.Event
) -> None:
    """Kill *proc* once more than ``cap.limit`` bytes are below ``cap.path``;
    return when *done* is set."""
    while not done.wait(_SIZE_POLL_SECONDS):
        if tree_bytes(cap.path) > cap.limit:
            cap.exceeded = True
            _kill(proc)
            return


@contextlib.contextmanager
def _size_watch(proc: subprocess.Popen[bytes], cap: SizeCap | None) -> Iterator[None]:
    """Watch the size of *cap*'s directory while *proc* runs (nothing when
    *cap* is ``None``)."""
    if cap is None:
        yield
        return
    done = threading.Event()
    watcher = threading.Thread(target=_watch_size, args=(proc, cap, done), daemon=True)
    watcher.start()
    try:
        yield
    finally:
        done.set()
        watcher.join()


def _capture(
    command: list[str], seconds: float, cap: SizeCap | None = None
) -> tuple[int | None, str | None, str]:
    """Run *command* for at most *seconds*: its exit status (``None`` when
    killed for time), its standard output (``None`` when over
    :data:`MAX_OUTPUT_BYTES`, then killed) and its standard error. With *cap*,
    it is killed when it passes it (``cap.exceeded``)."""
    with subprocess.Popen(  # nosec B603: argv list, no shell
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_environment(),
        # Its own process group, so a kill reaches what git started
        # (git-remote-https holds the pipe open).
        start_new_session=_POSIX,
    ) as proc:
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            _kill(proc)

        timer = threading.Timer(seconds, expire)
        timer.start()
        err_chunks: list[bytes] = []
        drain = threading.Thread(
            target=_drain, args=(cast(IO[bytes], proc.stderr), err_chunks), daemon=True
        )
        drain.start()
        chunks: list[bytes] = []
        size = 0
        too_large = False
        stdout = cast(IO[bytes], proc.stdout)  # a pipe: set by PIPE
        try:
            with _size_watch(proc, cap):
                while block := stdout.read(_READ_CHUNK):
                    size += len(block)
                    if size > MAX_OUTPUT_BYTES:
                        too_large = True
                        _kill(proc)
                        break
                    chunks.append(block)
        except BaseException:  # Ctrl-C must not leave git running
            _kill(proc)
            raise
        finally:
            timer.cancel()
        status = proc.wait()
        drain.join()
    err = b"".join(err_chunks).decode("utf-8", "replace")
    if timed_out.is_set():
        return None, None, err
    if too_large:
        return status, None, err
    return status, b"".join(chunks).decode("utf-8", "replace"), err
