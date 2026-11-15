# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_strip`: the credentials removed
from every URL of an SBOM's graph, a PURL's qualifier values included, and
the one ``WARNING:`` per URL, which says what is kept as kept.

See also: tests/test_credential_surfaces.py (every surface end to end) and
tests/core/url_masking/test_url_masking_strip.py (the strip of a text).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import quote

import pytest

from pitloom.core.purl import (
    build_generic_purl,
    purl_qualifier_values,
    strip_purl_secrets,
)
from pitloom.export._spdx3_strip import _url_words, strip_graph_credentials
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from pitloom.messages._url_credentials import (
    KEPT_LINE,
    STRIPPED_KEPT_LINE,
    STRIPPED_LINE,
)

_SECRET = "S3CRET"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _template_tail(template: str) -> str:
    return template.split("%(url)s", 1)[1]


@pytest.mark.parametrize(
    ("purl", "plain"),
    [
        (
            f"pkg:generic/d?download_url=https://alice:{_SECRET}%40data.example"
            "/d.csv%3Ftoken%3DXYZ",
            "pkg:generic/d?download_url=https://data.example/d.csv",
        ),
        (
            f"pkg:generic/d@1?u=https%3A%2F%2Fu%3A{_SECRET}%40h&a=1#sub",
            "pkg:generic/d@1?u=https://h&a=1#sub",
        ),
    ],
    ids=["encoded-at", "encoded-url"],
)
def test_a_purl_qualifier_is_decoded_stripped_and_said(
    purl: str, plain: str, caplog: pytest.LogCaptureFixture
) -> None:
    graph: list[dict[str, Any]] = [{"software_packageUrl": purl}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert graph == [{"software_packageUrl": plain}]
    assert len(_warnings(caplog)) == 1 and _SECRET not in caplog.text
    assert getattr(_warnings(caplog)[0], CODE_ATTR) == "credentials-unsafe"


@pytest.mark.parametrize(
    "purl",
    [
        "pkg:generic/d?download_url=https://h/x%3Fa%3D1",
        "pkg:pypi/foo@1.0",
        "pkg:generic/d?checksum=sha256:ab&download_url=https://h/x%3Fsession%3D2",
    ],
    ids=["clean", "no-qualifier", "weak"],
)
def test_a_purl_without_a_secret_is_left_as_written(purl: str) -> None:
    assert strip_purl_secrets(purl) == (purl, [])


def test_a_generic_purl_is_built_from_the_url_without_its_credentials() -> None:
    purl = build_generic_purl(
        "d", download_url=f"https://u:{_SECRET}@h/d?token={_SECRET}&a=1"
    )
    assert purl == "pkg:generic/d?download_url=https://h/d%3Fa%3D1"


@pytest.mark.parametrize(
    ("url", "plain", "line"),
    [
        ("git+ssh://git@github.com/o/r", "git+ssh://git@github.com/o/r", KEPT_LINE),
        ("https://h/x?code=ABC", "https://h/x?code=ABC", KEPT_LINE),
        ("ssh://git@h/r?token=T", "ssh://git@h/r", STRIPPED_KEPT_LINE),
        ("https://u:p@h/x?code=ABC", "https://h/x?code=ABC", STRIPPED_KEPT_LINE),
        ("https://u:p@h/x?token=T", "https://h/x", STRIPPED_LINE),
        ("ssh://ghp_TOKEN@github.com/o/r", "ssh://github.com/o/r", STRIPPED_LINE),
    ],
    ids=["account", "weak", "account-token", "weak-userinfo", "plain", "ssh-token"],
)
def test_one_warning_per_url_says_what_is_kept(
    url: str, plain: str, line: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """The line names a kept value only when one is kept, and the URL it
    shows keeps that value as written."""
    graph: list[dict[str, Any]] = [{"d": f"see {url}.", "e": [url]}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert graph == [{"d": f"see {plain}.", "e": [plain]}]
    (said,) = _warnings(caplog)
    assert said.getMessage().endswith(_template_tail(line.template))
    for kept in ("git@", "code=ABC"):
        assert (kept in said.getMessage()) is (kept in plain)


def test_a_clean_graph_is_left_as_the_same_object_and_said_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    inner = {"d": "https://h/x?a=1", "n": 3}
    graph: list[dict[str, Any]] = [inner]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert graph[0] is inner and not caplog.records


def test_a_collision_names_the_id_masked_and_leaves_the_graph() -> None:
    graph: list[dict[str, Any]] = [
        {"spdxId": f"https://u:{_SECRET}@h/x#P", "d": f"https://u:{_SECRET}@h"},
        {"spdxId": "https://h/x#P"},
    ]
    with pytest.raises(ValueError, match="once its credentials are removed") as e:
        strip_graph_credentials(graph)
    assert _SECRET not in str(e.value) and _SECRET in graph[0]["d"]


def test_the_stripped_url_warning_is_said_once_per_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Numbers pass, each URL is said once (also on a second run), an id that
    holds a secret and every reference to it become the same new id."""
    old = f"https://u:{_SECRET}@id.example/doc?token={_SECRET}#P-1"
    graph: list[dict[str, Any]] = [
        {"spdxId": old, "n": 3, "d": f"https://u:{_SECRET}@once.example/p"},
        {"c": [f"https://u:{_SECRET}@once.example/p"], "to": [old]},
    ]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
        strip_graph_credentials(graph)
    assert graph[0]["spdxId"] == "https://id.example/doc#P-1"
    assert graph[1]["to"] == [graph[0]["spdxId"]] and graph[0]["n"] == 3
    assert _SECRET not in json.dumps(graph)
    assert len(_warnings(caplog)) == 2 and _SECRET not in caplog.text


def test_two_identical_copies_of_one_credentialed_element_are_no_collision() -> None:
    element = {"spdxId": f"https://u:{_SECRET}@h/x#P", "name": "n"}
    graph: list[dict[str, Any]] = [element, dict(element)]
    strip_graph_credentials(graph)
    assert [e["spdxId"] for e in graph] == ["https://h/x#P"] * 2


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (f"https://u:{_SECRET}@h/x#P", "https://h/x#P"),
        (f"https://h/x?token={_SECRET}#P", "https://h/x?token=other#P"),
    ],
    ids=["userinfo", "query"],
)
def test_two_ids_that_differ_only_by_credentials_are_an_error(
    first: str, second: str
) -> None:
    graph: list[dict[str, Any]] = [{"spdxId": first}, {"spdxId": second}]
    with pytest.raises(ValueError, match="another element has this id") as caught:
        strip_graph_credentials(graph)
    assert _SECRET not in str(caught.value)
    assert code_of(caught.value) == "credentials-unsafe/id-collision"


@pytest.mark.parametrize(
    "url",
    [
        f"https://o'brien:{_SECRET}@h.example/x",
        f"https://TOK'EN{_SECRET}@h.example/x",
        f"user:{_SECRET}@h.example:o/r",
        f"https:/u:{_SECRET}@h/x",
    ],
    ids=["apostrophe", "token-apostrophe", "address", "one-slash"],
)
def test_a_url_field_is_read_as_one_url(
    url: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A string that is one URL is a URL field: what ``urllib`` reads as its
    user information is removed, whatever characters it holds."""
    graph: list[dict[str, Any]] = [{"software_homePage": url}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert _SECRET not in json.dumps(graph)
    (said,) = _warnings(caplog)
    assert _SECRET not in said.getMessage()


@pytest.mark.parametrize(
    "text",
    [
        "Open http://localhost:<port> in a browser. Questions: dev@example.org",
        "Serve on http://host:port and report bugs to bugs@example.org",
        'Use "http://HOST:PORT" - author jane@example.org',
    ],
    ids=range(3),
)
def test_prose_is_left_as_written_and_said_nothing(
    text: str, caplog: pytest.LogCaptureFixture
) -> None:
    graph: list[dict[str, Any]] = [{"description": text}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert graph == [{"description": text}] and not caplog.records


def test_a_purl_qualifier_encoded_twice_is_stripped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    twice = f"https%253A%252F%252Fu%253A{_SECRET}%2540h%252Fx"
    graph: list[dict[str, Any]] = [{"p": f"pkg:generic/d?download_url={twice}&a=1"}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert _SECRET not in json.dumps(graph) and len(_warnings(caplog)) == 1


def test_a_purl_qualifier_that_keeps_a_value_says_so_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    purl = "pkg:generic/d?download_url=https://h/x%3Fcode%3DABC"
    graph: list[dict[str, Any]] = [{"p": purl, "q": [purl]}]
    with caplog.at_level(logging.WARNING):
        strip_graph_credentials(graph)
    assert graph == [{"p": purl, "q": [purl]}]
    (said,) = _warnings(caplog)
    assert said.getMessage().endswith(_template_tail(KEPT_LINE.template))
    assert "code=ABC" in said.getMessage()


def test_two_json_ld_ids_that_differ_only_by_credentials_collide() -> None:
    """The ``@id`` key is an id as ``spdxId`` is."""
    graph: list[dict[str, Any]] = [
        {"@id": f"https://u:{_SECRET}@h/x#P"},
        {"@id": "https://h/x#P"},
    ]
    with pytest.raises(ValueError, match="another element has this id") as caught:
        strip_graph_credentials(graph)
    assert code_of(caught.value) == "credentials-unsafe/id-collision"


def test_a_long_string_with_a_late_scheme_separator_is_read_in_linear_time() -> None:
    """A million characters before a ``://`` are one word walked once, not
    once per start (a quadratic scan took minutes)."""
    started = time.perf_counter()
    strip_graph_credentials(
        [{"name": "n" * 2**20 + " https://u:p@h/x", "type": "Element"}]
    )
    assert time.perf_counter() - started < 5


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("dep @ https://o'brien:PW@h.example/d.whl", "dep @ https://h.example/d.whl"),
        (
            "dep @ https://TOK'EN@h/d.whl ; python_version>'3'",
            "dep @ https://h/d.whl ; python_version>'3'",
        ),
        ("dep[x]@ https://u:PW@h/d.whl", "dep[x]@ https://h/d.whl"),
        ("foo@https://u:S3'CRET@h/x.whl", "foo@https://h/x.whl"),
        ("foo @ https://h/x?token=T0KEN, bar", "foo @ https://h/x, bar"),
        ("see foo @ https://u:p@h/x.", "see foo @ https://h/x."),
        (
            "Metadata provenance: Note: dep @ https://o'brien:PW@h/d.whl",
            "Metadata provenance: Note: dep @ https://h/d.whl",
        ),
    ],
    ids=[
        "apostrophe",
        "token-and-marker",
        "extras",
        "no-space",
        "comma",
        "full-stop",
        "in-a-comment",
    ],
)
def test_a_pep_508_direct_reference_reads_its_url_as_a_field(
    text: str, plain: str
) -> None:
    """A quote in the user information of the URL of ``name @ URL`` is part
    of it, so the password is not left in a requirement note."""
    graph: list[dict[str, Any]] = [{"type": "Element", "note": text}]
    strip_graph_credentials(graph)
    assert graph[0]["note"] == plain


def test_the_direct_reference_scan_is_linear() -> None:
    started = time.perf_counter()
    graph: list[dict[str, Any]] = [
        {"type": "Element", "note": "n" * 2**20},
        {"type": "Element", "note": "@ " * 2**19},
        {"type": "Element", "note": "@ a" * 2**19},
    ]
    strip_graph_credentials(graph)
    assert time.perf_counter() - started < 5


def test_a_scheme_separator_without_a_word_after_it_is_no_url_word() -> None:
    assert _url_words("a:// b https://h/x ://") == ["https://h/x"]


def test_a_purl_value_encoded_more_often_than_the_cap_is_still_cut_short() -> None:
    value = "https://u:PW@h/x"
    for _ in range(8):
        value = value.replace("%", "%25").replace("@", "%40")
    assert strip_purl_secrets(f"pkg:generic/a?download_url={value}")[0]


def test_a_qualifier_value_keeps_the_encoding_of_what_is_inside_it() -> None:
    """Only the levels that showed the credentials are undone: an inner
    ``%2525`` stays ``%25`` after one decode of the result."""
    value = "https%3A%2F%2Fu%3AS3CRET%40h%2Fx%3Fa%3D100%2525"
    purl, changed = strip_purl_secrets(f"pkg:generic/a?download_url={value}")
    assert changed and "S3CRET" not in purl and purl.endswith("%3Fa%3D100%2525")


def test_credentials_in_every_layer_of_nested_encoding_are_stripped() -> None:
    """A URL inside a URL's parameter, encoded at each layer, is found layer
    by layer up to the limit; more layers than it are left, not looped on."""
    value = "https://uN:S3CRET@h/x"
    for layer in range(5):
        value = f"https://u{layer}:S3CRET@h/x?a=" + quote(value, safe="")
    purl, changed = strip_purl_secrets(f"pkg:generic/a?download_url={value}")
    assert len(changed) == 5 and "u0:" not in purl
    deep = value
    for _ in range(8):
        deep = quote(deep, safe="")
    assert purl_qualifier_values(f"pkg:generic/a?download_url={deep}")
