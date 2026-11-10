# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The library surfaces of a PyPI URL target
(:func:`pitloom.assemble.generate_pypi_sbom`): every surface gives the same
SBOM, the SBOM is the local file's but for the acquisition record, two runs
are byte-identical, nothing names the temporary directory, and the
download's own config is never read.

The JSON API and the file host are a local server (``loopback``).

See also: tests/assemble/test_generate_pypi_provenance.py (the record),
tests/assemble/test_generate_pypi_config.py (the download cap and the
options), tests/assemble/_pypi_dists.py (the builders).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom import assemble
from pitloom.assemble import (
    generate,
    generate_project_sbom,
    generate_pypi_sbom,
    generate_pypi_sbom_with_download,
    generate_wheel_sbom,
    target_is_git_url,
    target_is_pypi_url,
    target_resolves_to_project,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.internal_error import InternalError
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.pypi import SDIST, WHEEL
from pitloom.id_registry import IdRegistry
from tests._fake_pypi_server import Dist, FakePypi
from tests._spdx3_validate import assert_spdx3_valid
from tests.assemble._pypi_dists import (
    CREATION,
    NAME,
    SDIST_NAME,
    URL,
    VERSION,
    WHEEL_NAME,
    fake_pypi,
    graph,
    publish_demo,
    sdist_bytes,
    the_record,
    wheel_bytes,
    without_record,
)

pytestmark = pytest.mark.loopback

_TEMP_PREFIX = "pitloom-pypi-"


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        publish_demo(fake)
        yield fake


# --- surfaces -----------------------------------------------------------


def test_every_wheel_surface_gives_the_same_sbom(fake: FakePypi) -> None:
    del fake
    sboms = [
        generate_pypi_sbom(URL, creation_metadata=CREATION),
        generate_pypi_sbom(URL, kind=WHEEL, creation_metadata=CREATION),
        generate_wheel_sbom(URL, creation_metadata=CREATION),
        generate(URL, creation_metadata=CREATION),
    ]
    assert len(set(sboms)) == 1
    fields = the_record(sboms[0])
    assert fields["download_location"]["file"] == WHEEL_NAME


def test_every_sdist_surface_gives_the_same_sbom(fake: FakePypi) -> None:
    del fake
    sboms = [
        generate_pypi_sbom(URL, kind=SDIST, creation_metadata=CREATION),
        generate_project_sbom(URL, creation_metadata=CREATION),
    ]
    assert sboms[0] == sboms[1]
    fields = the_record(sboms[0])
    assert fields["download_location"]["file"] == SDIST_NAME


def test_generate_names_the_library_sdist_route(
    fake: FakePypi, caplog: pytest.LogCaptureFixture
) -> None:
    """The library's hint names the library call, never a CLI command."""
    del fake
    with caplog.at_level(logging.INFO):
        generate(URL, creation_metadata=CREATION)
    hints = [r for r in caplog.records if "reads the sdist" in r.getMessage()]
    assert [r.getMessage() for r in hints] == [
        f"PYPI={NAME}: generate() reads the wheel; "
        f"generate_pypi_sbom('{URL}', kind='sdist') reads the sdist"
    ]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        generate_pypi_sbom(URL, creation_metadata=CREATION)
    assert not [r for r in caplog.records if "reads the sdist" in r.getMessage()]


@pytest.mark.parametrize(
    "target",
    [
        URL,
        "https://pypi.org/project/demo/",
        "http://PyPI.org/project/demo/",
        "https://files.pythonhosted.org/x.whl",
    ],
)
def test_a_pypi_url_is_classified_before_a_git_url(target: str) -> None:
    assert target_is_pypi_url(target)
    assert not target_is_git_url(target)
    assert not target_resolves_to_project(target)


@pytest.mark.parametrize(
    "target",
    ["https://pythonhosted.org/x.whl", "https://github.com/o/r", "."],
)
def test_other_targets_are_no_pypi_url(target: str) -> None:
    assert not target_is_pypi_url(target)


def test_generate_forwards_every_option_to_the_pypi_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``generate()`` hands each of its options, with the caller's value, to
    :func:`generate_pypi_sbom` (which settles what a wheel cannot use)."""
    called: dict[str, object] = {}

    def _fake(url: str, **kwargs: object) -> str:
        called.update(kwargs, url=url)
        return "sbom"

    monkeypatch.setattr(assemble, "generate_pypi_sbom", _fake)
    monkeypatch.setattr(assemble, "sdist_hint", lambda url, library: None)
    names = [n for n in inspect.signature(generate).parameters if n != "target"]
    sentinels: dict[str, object] = {name: object() for name in names}
    # Checked before the dispatch, so a valid value of each.
    sentinels.update(max_model_extract_bytes=4321, max_download_bytes=4322)
    assert generate(URL, **sentinels) == "sbom"  # type: ignore[arg-type]
    assert called.pop("url") == URL and called.pop("kind") == WHEEL
    assert called == sentinels


# --- the SBOM: the local file's, plus the record ------------------------


def _local_sbom(kind: str, tmp_path: Path) -> str:
    """The SBOM of the same bytes given as a local file."""
    folder = tmp_path / "local"
    folder.mkdir()
    if kind == WHEEL:
        wheel = folder / WHEEL_NAME
        wheel.write_bytes(wheel_bytes())
        return generate_wheel_sbom(wheel, creation_metadata=CREATION)
    sdist = folder / SDIST_NAME
    sdist.write_bytes(sdist_bytes())
    return generate_project_sbom(
        sdist, creation_metadata=CREATION, pitloom_config=PitloomConfig()
    )


@pytest.mark.parametrize("kind", [WHEEL, SDIST])
def test_the_download_sbom_is_the_local_one_but_for_the_record(
    fake: FakePypi, tmp_path: Path, kind: str
) -> None:
    """Drift guard: a downloaded file and the same file given locally give
    the same SBOM, element for element, once the record (its Annotation
    and its comment line) is taken out."""
    del fake
    downloaded = generate_pypi_sbom(URL, kind=kind, creation_metadata=CREATION)
    local = _local_sbom(kind, tmp_path)
    kept, removed = without_record(downloaded)
    assert removed == 2  # the Annotation and the comment line ("both")
    assert kept == graph(local)
    assert len(graph(downloaded)) == len(graph(local)) + 1


@pytest.mark.parametrize("kind", [WHEEL, SDIST])
def test_two_runs_are_byte_identical_and_valid(
    fake: FakePypi, tmp_path: Path, kind: str
) -> None:
    del fake
    first = generate_pypi_sbom(URL, kind=kind, creation_metadata=CREATION)
    second = generate_pypi_sbom(URL, kind=kind, creation_metadata=CREATION)
    assert first == second
    path = tmp_path / "sbom.spdx3.json"
    path.write_text(first, encoding="utf-8")
    assert_spdx3_valid(path)


@pytest.mark.parametrize("kind", [WHEEL, SDIST])
def test_nothing_names_the_temporary_directory(
    fake: FakePypi,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    kind: str,
) -> None:
    del fake
    with caplog.at_level(logging.DEBUG):
        sbom = generate_pypi_sbom(
            URL, kind=kind, creation_metadata=CREATION, enrich=True, project_dir="p"
        )
    err = capsys.readouterr().err
    assert "Options: " in err  # non-vacuous: something was said
    assert _TEMP_PREFIX not in sbom and _TEMP_PREFIX not in err
    assert not [r for r in caplog.records if _TEMP_PREFIX in r.getMessage()]


def test_the_written_file_is_the_sbom(fake: FakePypi, tmp_path: Path) -> None:
    del fake
    output = tmp_path / "out.spdx3.json"
    sbom = generate_pypi_sbom(URL, creation_metadata=CREATION, output_path=output)
    assert output.read_text(encoding="utf-8") == sbom


# --- the download is untrusted ------------------------------------------


@pytest.fixture(name="configured")
def _configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """``demo`` whose sdist has a ``[tool.pitloom]`` that would change the
    SBOM if it were read."""
    tail = '[tool.pitloom]\ncreation-comment = "from-the-sdist"\npretty = true\n'
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        publish_demo(fake, {VERSION: [Dist(SDIST_NAME, sdist_bytes(tail))]})
        local = tmp_path / SDIST_NAME
        local.write_bytes(sdist_bytes(tail))
        # Non-vacuous: read locally, the sdist's own config applies.
        assert "from-the-sdist" in generate_project_sbom(local)
        yield


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, "pitloom_code", "") for r in caplog.records]


def test_the_sdists_own_config_is_never_read(
    configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    del configured
    with caplog.at_level(logging.INFO):
        sbom = generate_pypi_sbom(URL, kind=SDIST)
    assert "from-the-sdist" not in sbom and "\n" not in sbom
    assert _codes(caplog).count("config-unsafe") == 1


def test_an_explicit_config_applies_and_silences_the_note(
    configured: None, caplog: pytest.LogCaptureFixture
) -> None:
    del configured
    with caplog.at_level(logging.INFO):
        sbom = generate_pypi_sbom(
            URL, kind=SDIST, pitloom_config=PitloomConfig(creation_comment="mine")
        )
    assert "mine" in sbom and "from-the-sdist" not in sbom
    assert "config-unsafe" not in _codes(caplog)


@pytest.mark.parametrize(
    "call",
    [
        lambda: generate_pypi_sbom(URL, offline=True),
        lambda: generate_pypi_sbom(URL, pitloom_config=PitloomConfig(offline=True)),
        lambda: generate_project_sbom(URL, offline=True),
        lambda: generate(URL, offline=True),
    ],
    ids=["flag", "config", "project", "generate"],
)
def test_offline_fetches_nothing(fake: FakePypi, call: Callable[[], str]) -> None:
    with pytest.raises(RemoteSourceError) as exc:
        call()
    assert exc.value.code == "pypi.offline"
    assert not fake.seen


def test_an_offline_flag_of_false_beats_the_config(fake: FakePypi) -> None:
    generate_pypi_sbom(
        URL,
        offline=False,
        pitloom_config=PitloomConfig(offline=True),
        creation_metadata=CREATION,
    )
    assert fake.seen  # fetched


def test_every_url_is_checked_before_it_is_asked(fake: FakePypi) -> None:
    checked: list[str] = []
    generate_wheel_sbom(URL, check_url=checked.append, creation_metadata=CREATION)
    assert checked == [
        fake.url(f"/pypi/{NAME}/{VERSION}/json"),
        fake.url(f"/files/{WHEEL_NAME}"),
    ]


@pytest.mark.parametrize("kind", [WHEEL, SDIST])
def test_a_relative_registry_is_the_callers(
    fake: FakePypi,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    del fake
    caller = tmp_path / "caller"
    caller.mkdir()
    IdRegistry(namespace="https://example.invalid/r").save(caller / "reg.json")
    monkeypatch.chdir(caller)
    generate_pypi_sbom(
        URL, kind=kind, creation_metadata=CREATION, id_registry="reg.json"
    )
    # The caller's registry was read and harvested into (a file target's
    # relative registry resolves against the current directory, never the
    # temporary one).
    assert IdRegistry.load(caller / "reg.json").elements


def test_the_download_variant_returns_the_sbom_and_what_was_read(
    fake: FakePypi,
) -> None:
    del fake
    result = generate_pypi_sbom_with_download(URL, creation_metadata=CREATION)
    assert result.sbom == generate_pypi_sbom(URL, creation_metadata=CREATION)
    assert (result.download.filename, result.download.kind) == (WHEEL_NAME, WHEEL)
    assert result.download.version == VERSION
    assert (result.metadata.name, result.metadata.version) == (NAME, VERSION)
    sdist = generate_pypi_sbom_with_download(
        URL, kind=SDIST, creation_metadata=CREATION
    )
    assert (sdist.metadata.name, sdist.metadata.version) == (NAME, VERSION)
    assert sdist.download.filename == SDIST_NAME


@pytest.mark.parametrize("call", [generate_pypi_sbom, generate_pypi_sbom_with_download])
def test_an_unknown_kind_is_a_programming_error(
    fake: FakePypi, call: Callable[..., object]
) -> None:
    """Only a wheel or an sdist is fetched: any other kind raises before a
    request, and the server is never asked."""
    with pytest.raises(InternalError, match="kind must be"):
        call(URL, kind="model", creation_metadata=CREATION)
    assert not fake.seen
