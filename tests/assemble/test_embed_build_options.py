# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests that ``ConfigOverrides.build_options`` reaches
``get_wheel_files()`` unchanged through ``embed_wheel_sbom()``'s
project-directory rescan, and that ``EmbedFileCache`` (the multi-wheel
batch's shared, at-most-once resolution of that rescan) behaves
correctly.

See also:
- :mod:`tests.assemble.test_embed_overrides` for every other
  ``ConfigOverrides``/``embed_wheel_sbom`` test.
- :mod:`tests.assemble.test_embed_cli` for the real
  ``loom embed-wheel <wheel1> <wheel2>`` multi-wheel CLI regression.
- :mod:`tests.test_build_flag_warnings` for the "build flag has no
  effect" warnings on every embed path, including the multi-wheel case.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.build_options import BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.config import PitloomConfig
from pitloom.embed import ConfigOverrides, EmbedFileCache, embed_wheel_sbom
from tests.build_and_read_shared import spied_raise_signal

from .conftest import _make_dummy_wheel
from .test_embed_overrides import _make_ctpkg_project_and_wheel

_GET_WHEEL_FILES = "pitloom._embed_build_sbom.get_wheel_files"


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def test_embed_wheel_threads_build_options(tmp_path: Path) -> None:
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)
    options = BuildOptions(allow=True, no_isolation=True, timeout=321)

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files",
        autospec=True,
        return_value=(None, [], lambda: None),
    ) as mocked:
        embed_wheel_sbom(
            wheel_path,
            project_dir=tmp_path,
            overrides=ConfigOverrides(build_options=options),
        )

    assert mocked.call_args.kwargs["build_options"] is options


def test_embed_wheel_defaults_to_no_build_options(tmp_path: Path) -> None:
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files",
        autospec=True,
        return_value=(None, [], lambda: None),
    ) as mocked:
        embed_wheel_sbom(wheel_path, project_dir=tmp_path)

    assert mocked.call_args.kwargs["build_options"] == BuildOptions()


def test_embed_file_cache_resolves_get_wheel_files_at_most_once(
    tmp_path: Path,
) -> None:
    """Regression for the multi-wheel embed batch: two wheels from the
    same project directory, sharing one ``EmbedFileCache``, must
    resolve ``get_wheel_files()`` (and, with ``--allow-build``, run its
    one real PEP 517 build) exactly once between them, not once per
    wheel -- see ``EmbedFileCache``'s own docstring."""
    wheel1 = _make_ctpkg_project_and_wheel(tmp_path)
    wheel2 = _make_dummy_wheel(tmp_path / "dist2", "ctpkg", "1.0.0")
    cleanup = mock.Mock()

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files",
        autospec=True,
        return_value=(None, [], cleanup),
    ) as mocked:
        with EmbedFileCache() as cache:
            for wheel_path in (wheel1, wheel2):
                embed_wheel_sbom(wheel_path, project_dir=tmp_path, file_cache=cache)
            assert mocked.call_count == 1
            cleanup.assert_not_called()

    cleanup.assert_called_once()


def test_embed_file_cache_cleans_up_once_when_the_batch_fails(
    tmp_path: Path,
) -> None:
    """Leaving the block by an exception (a wheel failing, Ctrl-C) still
    runs the cleanup callback, exactly once."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)
    cleanup = mock.Mock()

    with (
        mock.patch(
            "pitloom._embed_build_sbom.get_wheel_files",
            autospec=True,
            return_value=(None, [], cleanup),
        ),
        pytest.raises(KeyboardInterrupt),
        EmbedFileCache() as cache,
    ):
        embed_wheel_sbom(wheel_path, project_dir=tmp_path, file_cache=cache)
        raise KeyboardInterrupt

    cleanup.assert_called_once()


def test_embed_wheel_without_file_cache_resolves_and_cleans_up_every_call(
    tmp_path: Path,
) -> None:
    """Regression: with no ``file_cache`` (every caller before this
    change, and every caller today except the multi-wheel CLI batch),
    each ``embed_wheel_sbom()`` call must keep resolving and cleaning up
    its own ``get_wheel_files()`` result independently -- the per-wheel
    behaviour this change must not alter."""
    wheel1 = _make_ctpkg_project_and_wheel(tmp_path)
    wheel2 = _make_dummy_wheel(tmp_path / "dist2", "ctpkg", "1.0.0")
    cleanup_calls: list[int] = []

    def _cleanup() -> None:
        cleanup_calls.append(len(cleanup_calls))

    with mock.patch(
        "pitloom._embed_build_sbom.get_wheel_files",
        autospec=True,
        return_value=(None, [], _cleanup),
    ) as mocked:
        for wheel_path in (wheel1, wheel2):
            embed_wheel_sbom(wheel_path, project_dir=tmp_path)

    assert mocked.call_count == 2
    assert len(cleanup_calls) == 2


def test_embed_file_cache_outside_its_block_raises(tmp_path: Path) -> None:
    """Outside its block nothing would run the cleanup callback (a
    build-and-read dir would leak): resolving raises before discovery."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)
    cache = EmbedFileCache()

    with mock.patch(_GET_WHEEL_FILES, autospec=True) as mocked:
        with pytest.raises(RuntimeError, match="with EmbedFileCache"):
            embed_wheel_sbom(wheel_path, project_dir=tmp_path, file_cache=cache)
        with cache:
            pass
        with pytest.raises(RuntimeError, match="with EmbedFileCache"):
            embed_wheel_sbom(wheel_path, project_dir=tmp_path, file_cache=cache)

    mocked.assert_not_called()


@pytest.mark.usefixtures("raise_spy")
def test_embed_file_cache_can_be_entered_again(tmp_path: Path) -> None:
    """Each block resolves afresh, cleans up its own result and, once a
    build starts inside it, handles termination signals again."""
    wheel_path = _make_ctpkg_project_and_wheel(tmp_path)
    cleanups = [mock.Mock(), mock.Mock()]
    cache = EmbedFileCache()
    handled: list[bool] = []

    with mock.patch(
        _GET_WHEEL_FILES,
        autospec=True,
        side_effect=[(None, [], cleanup) for cleanup in cleanups],
    ) as mocked:
        for cleanup in cleanups:
            with cache:
                embed_wheel_sbom(wheel_path, project_dir=tmp_path, file_cache=cache)
                # What build_and_read_wheel() does inside the batch's guard.
                with TerminationGuard() as guard, guard.hold():
                    handled.append(callable(signal.getsignal(signal.SIGTERM)))
            cleanup.assert_called_once_with()

    assert mocked.call_count == 2
    assert handled == [True, True]
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_embed_file_cache_entered_twice_raises() -> None:
    with EmbedFileCache() as cache:
        with pytest.raises(RuntimeError, match="already entered"), cache:
            pytest.fail("entered twice")


@pytest.mark.parametrize("reason", [None, "for this batch's target"])
def test_embed_file_cache_settles_once_per_block(
    caplog: pytest.LogCaptureFixture, reason: str | None
) -> None:
    """The first settle in a block warns and is reused for the rest of the
    batch; a new block settles (and warns) afresh."""
    stray = BuildOptions(timeout=900)
    cache = EmbedFileCache()
    for _ in range(2):
        caplog.clear()
        with cache:
            first = cache.settle(stray, "wheel-a", reason)
            assert cache.settle(stray, "wheel-b", reason) is first
        assert first == BuildOptions()
        lines = [r.getMessage() for r in caplog.records]
        assert len(lines) == 1, lines
        assert "wheel-a: --build-timeout has no effect" in lines[0]


def test_embed_file_cache_settle_outside_its_block_raises() -> None:
    with pytest.raises(RuntimeError, match="with EmbedFileCache"):
        EmbedFileCache().settle(BuildOptions(), "wheel")


def test_embed_file_cache_settles_each_distinct_options_separately() -> None:
    """Another call's options are never replaced by the first call's
    settled result: a later ``allow=True`` still reaches discovery."""
    with EmbedFileCache() as cache:
        first = cache.settle(BuildOptions(timeout=900), "wheel-a", "for a --sbom")
        later = cache.settle(BuildOptions(allow=True), "wheel-b")
    assert first == BuildOptions()
    assert later == BuildOptions(allow=True)


def test_embed_file_cache_rejects_a_mismatched_batch(tmp_path: Path) -> None:
    """A later call asking for other build options than the cached file
    list was resolved with raises, rather than silently reusing it."""
    config = PitloomConfig()
    with mock.patch(
        _GET_WHEEL_FILES, autospec=True, return_value=(None, [], mock.Mock())
    ) as mocked:
        with EmbedFileCache() as cache:
            cache.resolve(tmp_path, config, BuildOptions())
            cache.resolve(tmp_path, config, BuildOptions())
            with pytest.raises(ValueError, match="same project directory"):
                cache.resolve(tmp_path, config, BuildOptions(allow=True))
    mocked.assert_called_once()
