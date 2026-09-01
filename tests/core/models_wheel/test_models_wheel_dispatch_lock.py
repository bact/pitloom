# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for get_wheel_files()'s discovery-lock concurrency behavior
(``_DiscoveryLock``'s reader/writer split and writer-priority guarantee).

See also: tests/core/models_wheel/test_models_wheel_dispatch.py for
backend-routing and fallback-warning tests -- split out of that file once
it crossed the ~400-500 line soft limit; this half shares its
``_make_backend_project`` helper rather than duplicating it.
"""

import threading
import time
from pathlib import Path

import pytest

from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.models import get_wheel_files

from .test_models_wheel_dispatch import _make_backend_project


def test_get_wheel_files_backend_discovery_is_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: two concurrent ``get_wheel_files()`` calls (e.g. a
    setuptools discovery, which process-wide ``os.chdir()``s for its
    duration, racing a Hatchling discovery in another thread) must never
    overlap -- both backend discoverers funnel through one shared lock
    in the facade, so at most one is ever mid-flight at a time."""
    _make_backend_project(tmp_path, "setuptools.build_meta")

    concurrent_calls = 0
    max_concurrent = 0
    lock = threading.Lock()

    def _slow_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        nonlocal concurrent_calls, max_concurrent
        del project_dir, pyproject_data
        with lock:
            concurrent_calls += 1
            max_concurrent = max(max_concurrent, concurrent_calls)
        time.sleep(0.05)
        with lock:
            concurrent_calls -= 1
        return []

    monkeypatch.setattr(
        "pitloom.core._models_wheel_setuptools.discover", _slow_discover
    )

    threads = [
        threading.Thread(target=get_wheel_files, args=(tmp_path,)) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent == 1


def test_get_wheel_files_hatchling_discovery_is_not_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: concurrent ``get_wheel_files()`` calls that both
    resolve to Hatchling (no chdir involved) must NOT serialize against
    each other -- only a concurrent setuptools (write-mode) call needs
    exclusive access. Guards the discovery lock's read/write split."""
    concurrent_calls = 0
    max_concurrent = 0
    lock = threading.Lock()

    def _slow_discover(project_dir: Path) -> list[IncludedFile]:
        nonlocal concurrent_calls, max_concurrent
        del project_dir
        with lock:
            concurrent_calls += 1
            max_concurrent = max(max_concurrent, concurrent_calls)
        time.sleep(0.05)
        with lock:
            concurrent_calls -= 1
        return []

    monkeypatch.setattr("pitloom.core._models_wheel_hatchling.discover", _slow_discover)

    threads = [
        threading.Thread(target=get_wheel_files, args=(tmp_path,)) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent > 1


def test_get_wheel_files_poetry_discovery_is_not_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: Poetry's discoverer never touches cwd (poetry-core's
    ``find_files_to_add()`` doesn't chdir), so it's a "reader" like
    Hatchling's -- concurrent ``get_wheel_files()`` calls that both
    resolve to Poetry must NOT serialize against each other. Guards
    against the discovery lock's dispatch defaulting every non-setuptools
    backend to the same exclusive write mode setuptools needs."""
    _make_backend_project(tmp_path, "poetry.core.masonry.api")

    concurrent_calls = 0
    max_concurrent = 0
    lock = threading.Lock()

    def _slow_discover(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        nonlocal concurrent_calls, max_concurrent
        del project_dir, pyproject_data
        with lock:
            concurrent_calls += 1
            max_concurrent = max(max_concurrent, concurrent_calls)
        time.sleep(0.05)
        with lock:
            concurrent_calls -= 1
        return []

    monkeypatch.setattr("pitloom.core._models_wheel_poetry.discover", _slow_discover)

    threads = [
        threading.Thread(target=get_wheel_files, args=(tmp_path,)) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent > 1


def test_get_wheel_files_writer_not_starved_by_continuous_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the discovery lock is writer-priority -- once a
    setuptools (write-mode) call announces itself, new Hatchling
    (read-mode) calls stop being admitted ahead of it, so it only waits
    for readers already in flight when it arrived, never for a
    continuous stream of freshly-arriving ones. Under a plain
    reader-preference lock (readers count never sustained above zero by
    a single caller, but easily sustained by a *pool* of overlapping
    concurrent readers -- confirmed: a single sequential spammer isn't
    enough, since it always has a gap between calls where the reader
    count can transiently hit zero and let the writer slip in by luck),
    that pool alone would starve the writer forever."""
    _make_backend_project(tmp_path, "setuptools.build_meta")
    hatchling_dir = tmp_path.parent / "hatchling_proj_starvation"
    hatchling_dir.mkdir()

    release_first_reader = threading.Event()
    writer_done = threading.Event()
    stop_spamming = threading.Event()

    def _held_reader(project_dir: Path) -> list[IncludedFile]:
        del project_dir
        release_first_reader.wait(timeout=5)
        return []

    def _quick_reader(project_dir: Path) -> list[IncludedFile]:
        del project_dir
        time.sleep(0.005)
        return []

    def _writer(
        project_dir: Path, *, pyproject_data: dict[str, object] | None = None
    ) -> list[IncludedFile]:
        del project_dir, pyproject_data
        writer_done.set()
        return []

    monkeypatch.setattr("pitloom.core._models_wheel_setuptools.discover", _writer)
    monkeypatch.setattr("pitloom.core._models_wheel_hatchling.discover", _held_reader)

    first_reader = threading.Thread(target=get_wheel_files, args=(hatchling_dir,))
    first_reader.start()
    time.sleep(0.05)  # let it register as an already-in-flight reader

    writer_thread = threading.Thread(target=get_wheel_files, args=(tmp_path,))
    writer_thread.start()
    time.sleep(0.05)  # let the writer register as waiting

    monkeypatch.setattr("pitloom.core._models_wheel_hatchling.discover", _quick_reader)

    def _spam() -> None:
        while not stop_spamming.is_set():
            get_wheel_files(hatchling_dir)

    # A *pool* of overlapping spammers, not just one -- with only one
    # sequential caller, the reader count has a gap between each of its
    # own calls where it can transiently hit zero, giving the writer a
    # lucky chance to slip in even under the buggy reader-preference
    # design this test guards against.
    spammers = [threading.Thread(target=_spam) for _ in range(16)]
    for t in spammers:
        t.start()
    time.sleep(0.05)  # let spamming ramp up before releasing the first reader

    release_first_reader.set()
    starved = not writer_done.wait(timeout=2)
    stop_spamming.set()

    for t in spammers:
        t.join(timeout=5)
    first_reader.join(timeout=5)
    writer_thread.join(timeout=5)

    assert not starved, "writer starved by continuously arriving readers"
