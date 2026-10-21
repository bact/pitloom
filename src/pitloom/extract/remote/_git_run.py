# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run ``git`` for a remote source: no redirect followed, no credential
prompt, no LFS download, a time and an output limit."""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import signal
import subprocess  # nosec B404
import threading
import time
from dataclasses import dataclass, field
from typing import IO, cast

from pitloom.extract._extract_utils import sanitize_url_credentials
from pitloom.extract.remote import git_url
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = ["GIT_TIMEOUT_SECONDS", "MAX_OUTPUT_BYTES", "GitRunner"]

#: Seconds one ``git`` call may take; the calls of one fetch share a deadline.
GIT_TIMEOUT_SECONDS = 600.0

#: Bytes of output one call may produce (a server listing a million refs).
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_READ_CHUNK = 64 * 1024

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

#: The temporary checkout's path, which a git message quotes.
_CHECKOUT_PATH = re.compile(r"\S*pitloom-git-\w+")

#: Lines of git's standard error that say what went wrong.
_ERROR_LINE = re.compile(r"(fatal|error|remote): ")


@dataclass
class GitRunner:
    """Runs ``git`` calls that share one deadline.

    Every call runs with ``http.followRedirects=false`` (the URL was checked,
    and redirects were followed by hand with each hop checked), with git-lfs
    off (it would fetch from an address the repository names), without a
    credential prompt (a private repository must fail fast) and with only
    the http(s) transports allowed.
    """

    seconds: float = field(default_factory=lambda: GIT_TIMEOUT_SECONDS)
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        """Seconds left of the shared deadline."""
        return self.seconds - (time.monotonic() - self.started)

    def run(self, args: list[str], what: str, *, echo: bool = True) -> str:
        """Run ``git`` with *args*; return its standard output.

        Raises:
            RemoteSourceError: ``git.not-found`` (no ``git``),
                ``git.timeout`` (the deadline passed),
                ``git.output-too-large`` or ``git.clone-failed`` (git failed;
                the message is its own).
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
                loggable(sanitize_url_credentials(shlex.join(command))),
            )
        left = self.remaining()
        if left <= 0:
            raise RemoteSourceError(
                "git.timeout", f"git {what} did not start within {self.seconds:.0f}s"
            )
        status, out, err = _capture(command, left)
        if status is None:
            raise RemoteSourceError(
                "git.timeout", f"git {what} exceeded {self.seconds:.0f}s"
            )
        if out is None:
            raise RemoteSourceError(
                "git.output-too-large",
                f"git {what} produced more than {MAX_OUTPUT_BYTES} bytes",
            )
        if status != 0:
            raise RemoteSourceError("git.clone-failed", _failure(err, status))
        return out


def _failure(err: str, status: int) -> str:
    """What git said went wrong, as one line fit for ``ERROR:``: its
    ``fatal:``/``error:``/``remote:`` lines (a server writes the last kind
    itself), without credentials, the temporary path or control characters."""
    lines = [ln.strip() for ln in err.splitlines() if _ERROR_LINE.match(ln.strip())]
    text = "; ".join(lines) or " ".join(err.split()) or f"git exited {status}"
    text = _CHECKOUT_PATH.sub("<checkout>", sanitize_url_credentials(text))
    return loggable(text)


def _environment() -> dict[str, str]:
    """The environment git runs in."""
    env = {k: v for k, v in os.environ.items() if not _SCRUBBED_ENV.fullmatch(k)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    env["GIT_ALLOW_PROTOCOL"] = ":".join(sorted(git_url.ALLOWED_SCHEMES))
    return env


def _drain(stream: IO[bytes], keep: list[bytes]) -> None:
    """Read *stream* to its end, keeping the first :data:`MAX_OUTPUT_BYTES`
    bytes: a server cannot fill the disk or memory with its messages."""
    kept = 0
    while block := stream.read(_READ_CHUNK):
        if kept < MAX_OUTPUT_BYTES:
            keep.append(block[: MAX_OUTPUT_BYTES - kept])
            kept += len(block)


def _kill(proc: subprocess.Popen[bytes]) -> None:
    """Kill *proc* and, where it has its own process group, what it started."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:  # already gone
            pass
    else:  # pragma: no cover
        proc.kill()


def _capture(command: list[str], seconds: float) -> tuple[int | None, str | None, str]:
    """Run *command* for at most *seconds*: its exit status (``None`` when
    killed for time), its standard output (``None`` when over
    :data:`MAX_OUTPUT_BYTES`, then killed) and its standard error."""
    with subprocess.Popen(  # nosec B603: argv list, no shell
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_environment(),
        # Its own process group, so a kill reaches what git started
        # (git-remote-https holds the pipe open).
        start_new_session=os.name == "posix",
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
