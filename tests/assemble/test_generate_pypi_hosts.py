# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The hosts of the PyPI family on every library surface: ``pypi.org`` with
a trailing dot, or a dot spelled as a resolver maps it (``%2E``, an
ideographic or full-width dot), is read as ``pypi.org``; another index
(``test.pypi.org``) and PyPI's old address (``pypi.python.org``) are refused
as PyPI URLs, and the Git route refuses each, so nothing is fetched or
cloned; the model
call refuses every PyPI URL as ``loom model`` does. The URL is read before
``offline``.

See also: tests/cli/test_cli_pypi_url_hosts.py (the same on the command
line), tests/extract/remote/test_pypi_url.py (the URL itself).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom.assemble import (
    generate,
    generate_git_project_sbom,
    generate_git_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_wheel_sbom,
)
from pitloom.extract.remote import git, pypi
from pitloom.extract.remote._git_run import GitRunner
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.pypi import SDIST
from pitloom.messages import (
    GIT_PYPI_URL_LINE,
    MODEL_URL_LINE,
    PYPI_URL_INVALID,
    PYPI_URL_UNUSABLE,
    Line,
    code_of,
)
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import (
    CREATION,
    DOTTED,
    REFUSED,
    REFUSED_IDS,
    SPELLED,
    SPELLED_IDS,
    URL,
    fake_pypi,
    publish_demo,
)

pytestmark = pytest.mark.loopback

#: The library calls that read a PyPI URL.
READERS: dict[str, Callable[..., str]] = {
    "generate": generate,
    "generate_pypi_sbom": generate_pypi_sbom,
    "generate_wheel_sbom": generate_wheel_sbom,
    "generate_project_sbom": generate_project_sbom,
}
#: The library calls that clone a Git repository.
CLONERS: dict[str, Callable[..., str]] = {
    "generate_git_sbom": generate_git_sbom,
    "generate_git_project_sbom": generate_git_project_sbom,
}


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        publish_demo(fake)
        yield fake


@pytest.fixture(name="no_fetch")
def _no_fetch(monkeypatch: pytest.MonkeyPatch, fake: FakePypi) -> Iterator[None]:
    """Fail on any download, Git command or Git redirect probe; and assert
    the fake PyPI was never asked."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fetched")

    monkeypatch.setattr(pypi, "_download", boom)
    monkeypatch.setattr(git, "_resolve", boom)
    monkeypatch.setattr(GitRunner, "run", boom)
    yield
    assert not fake.seen


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
@pytest.mark.parametrize(("url", "line"), REFUSED, ids=REFUSED_IDS)
@pytest.mark.parametrize("reader", list(READERS))
@pytest.mark.usefixtures("no_fetch")
def test_a_reader_refuses_another_pypi_host(
    reader: str, url: str, line: Line, offline: bool
) -> None:
    """The URL is read first: ``offline`` does not hide the refusal."""
    with pytest.raises(ValueError) as info:
        READERS[reader](url, creation_metadata=CREATION, offline=offline)
    assert code_of(info.value) == PYPI_URL_INVALID.code
    assert str(info.value) == line.render({"url": url})


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
@pytest.mark.parametrize(
    "url",
    [DOTTED, *SPELLED, *(url for url, _line in REFUSED)],
    ids=["dot", *SPELLED_IDS, *REFUSED_IDS],
)
@pytest.mark.parametrize("cloner", list(CLONERS))
@pytest.mark.usefixtures("no_fetch")
def test_the_git_route_refuses_a_pypi_url(cloner: str, url: str, offline: bool) -> None:
    with pytest.raises(RemoteSourceError) as info:
        CLONERS[cloner](url, offline=offline)
    assert (info.value.code, code_of(info.value)) == (
        "git.url-invalid",
        PYPI_URL_UNUSABLE.code,
    )
    assert str(info.value) == GIT_PYPI_URL_LINE.render({"url": url})


@pytest.mark.parametrize(
    ("call", "kind"),
    [(generate, None), (generate_pypi_sbom, SDIST), (generate_project_sbom, None)],
    ids=["generate", "pypi-sdist", "project"],
)
@pytest.mark.parametrize("spelled", [DOTTED, *SPELLED], ids=["dot", *SPELLED_IDS])
def test_a_spelling_of_pypi_org_reads_pypi_org(
    fake: FakePypi, call: Callable[..., str], kind: str | None, spelled: str
) -> None:
    """A trailing dot, an encoded or a non-ASCII dot: the host a resolver
    maps it to."""
    extra = {} if kind is None else {"kind": kind}
    dotted = call(spelled, creation_metadata=CREATION, **extra)
    assert fake.seen  # read from the (fake) pypi.org
    assert dotted == call(URL, creation_metadata=CREATION, **extra)


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
@pytest.mark.parametrize(
    "url",
    [URL, DOTTED, *SPELLED, *(url for url, _line in REFUSED)],
    ids=["url", "dot", *SPELLED_IDS, *REFUSED_IDS],
)
@pytest.mark.usefixtures("no_fetch")
def test_the_model_call_refuses_a_pypi_url_as_loom_model_does(
    url: str, offline: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Not read as a missing local path (``Model file not found``)."""
    with pytest.raises(ValueError) as info:
        generate_model_sbom(url, offline=offline)
    assert code_of(info.value) == PYPI_URL_UNUSABLE.code
    assert str(info.value) == MODEL_URL_LINE.render({"url": url})
    assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == [
        str(info.value)
    ]
