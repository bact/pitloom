# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Run ``git`` for a remote source: no redirect followed, no credential
prompt, a time and an output limit."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field

from pitloom.extract._extract_utils import sanitize_url_credentials
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = ["GIT_TIMEOUT_SECONDS", "MAX_OUTPUT_BYTES", "GitRunner"]

#: Seconds one ``git`` call may take; the calls of one fetch share a deadline.
GIT_TIMEOUT_SECONDS = 600.0

#: Bytes of output one call may produce (a server listing a million refs).
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

_READ_CHUNK = 64 * 1024


@dataclass
class GitRunner:
    """Runs ``git`` calls that share one deadline.

    Every call runs with ``http.followRedirects=false`` (the URL was checked,
    and redirects were followed by hand with each hop checked) and without a
    credential prompt (a private repository must fail fast).
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
        command = [git, "-c", "http.followRedirects=false", *args]
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
            detail = sanitize_url_credentials(err.strip()) or f"git exited {status}"
            raise RemoteSourceError("git.clone-failed", detail)
        return out


def _capture(command: list[str], seconds: float) -> tuple[int | None, str | None, str]:
    """Run *command* for at most *seconds*: its exit status (``None`` when
    killed for time), its standard output (``None`` when over
    :data:`MAX_OUTPUT_BYTES`, then killed) and its standard error."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryFile() as err_file:
        with subprocess.Popen(  # nosec B603: argv list, no shell
            command,
            stdout=subprocess.PIPE,
            stderr=err_file,
            env=env,
        ) as proc:
            timed_out = threading.Event()

            def expire() -> None:
                timed_out.set()
                proc.kill()

            timer = threading.Timer(seconds, expire)
            timer.start()
            chunks: list[bytes] = []
            size = 0
            too_large = False
            stdout = proc.stdout
            try:
                while stdout is not None:
                    block = stdout.read(_READ_CHUNK)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_OUTPUT_BYTES:
                        too_large = True
                        proc.kill()
                        break
                    chunks.append(block)
            finally:
                timer.cancel()
            status = proc.wait()
        err_file.seek(0)
        err = err_file.read(MAX_OUTPUT_BYTES).decode("utf-8", "replace")
    if timed_out.is_set():
        return None, None, err
    if too_large:
        return status, None, err
    return status, b"".join(chunks).decode("utf-8", "replace"), err
