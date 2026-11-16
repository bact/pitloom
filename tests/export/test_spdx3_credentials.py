# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_credentials`: an SBOM whose URL
field holds a credential is refused (one ``ERROR:`` per distinct value),
stated as written when the run accepts it, warned of when the value is weak
only, and never rewritten.

See also: tests/test_credential_surfaces.py and
tests/test_credential_surfaces_accept.py (every surface end to end).
"""

from __future__ import annotations

import copy
import inspect
import json
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any

import pytest
from spdx_python_model.bindings.v3_0_1 import model as spdx_model

from pitloom.core.credential_policy import (
    CredentialPolicy,
    fingerprint,
    full_fingerprint,
)
from pitloom.export._spdx3_credentials import (
    NOT_READ,
    URL_FIELDS,
    GraphFinding,
    check_graph_credentials,
    find_graph_credentials,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of

_SECRET = "S3CRET"
_URL = f"https://u:{_SECRET}@h.example/x"
_REFUSED = "credentials-unsafe/refused"
_ACCEPTED = "credentials-unsafe/accepted"
_PROVENANCE = "https://pitloom.dev/provenance/fields/1"
_ALLOW = CredentialPolicy(allow_all=True)


def _one(graph: list[dict[str, Any]]) -> GraphFinding:
    """The one finding of *graph*."""
    found = find_graph_credentials(graph)
    assert len(found) == 1, found
    return found[0]


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR, "") for r in caplog.records]


def _statement(note: str, schema: str = _PROVENANCE) -> str:
    return json.dumps(
        {"fields": {"declared_constraint": {"note": note}}, "schema": schema}
    )


def _refuse(graph: list[dict[str, Any]], policy: CredentialPolicy) -> Exception:
    with pytest.raises(ValueError) as caught:
        check_graph_credentials(graph, policy)
    return caught.value


#: Each field read: the element holding it, and the pointer refused.
_FIELDS: dict[str, tuple[dict[str, Any], str]] = {
    "spdxId": ({"spdxId": _URL}, "/spdxId"),
    "spdxId-embedded": ({"spdxId": f"urn:x:{_URL}"}, "/spdxId"),
    "@id": ({"@id": _URL}, "/@id"),
    "externalSpdxId": (
        {"spdxId": "urn:a", "import": [{"externalSpdxId": f"urn:x:{_URL}"}]},
        "/import/0/externalSpdxId",
    ),
    "locationHint": (
        {"spdxId": "urn:a", "import": [{"locationHint": _URL}]},
        "/import/0/locationHint",
    ),
    "namespace": (
        {"spdxId": "urn:a", "namespaceMap": [{"namespace": _URL}]},
        "/namespaceMap/0/namespace",
    ),
    "downloadLocation": (
        {"spdxId": "urn:a", "software_downloadLocation": _URL},
        "/software_downloadLocation",
    ),
    "homePage": (
        {"spdxId": "urn:a", "software_homePage": f"dep @ {_URL}"},
        "/software_homePage",
    ),
    "packageUrl": (
        {
            "spdxId": "urn:a",
            "software_packageUrl": "pkg:generic/d?download_url="
            f"https://alice:{_SECRET}%40data.example/d.csv",
        },
        "/software_packageUrl",
    ),
    "contentIdentifierValue": (
        {
            "spdxId": "urn:a",
            "software_contentIdentifier": [{"software_contentIdentifierValue": _URL}],
        },
        "/software_contentIdentifier/0/software_contentIdentifierValue",
    ),
    "locator": (
        {"spdxId": "urn:a", "externalRef": [{"locator": ["https://h/", _URL]}]},
        "/externalRef/0/locator/1",
    ),
    "identifierLocator": (
        {"spdxId": "urn:a", "externalIdentifier": [{"identifierLocator": [_URL]}]},
        "/externalIdentifier/0/identifierLocator/0",
    ),
    "identifier-purl": (
        {
            "spdxId": "urn:a",
            "externalIdentifier": [
                {
                    "externalIdentifierType": "packageUrl",
                    "identifier": f"pkg:pypi/x@1?token={_SECRET}",
                }
            ],
        },
        "/externalIdentifier/0/identifier",
    ),
    "identifier-url": (
        {
            "spdxId": "urn:a",
            "externalIdentifier": [
                {"externalIdentifierType": "urlScheme", "identifier": _URL}
            ],
        },
        "/externalIdentifier/0/identifier",
    ),
    "identifier-doi": (
        {
            "spdxId": "urn:a",
            "externalIdentifier": [
                {"externalIdentifierType": "other", "identifier": _URL}
            ],
        },
        "/externalIdentifier/0/identifier",
    ),
    "identifier-untyped": (
        {"spdxId": "urn:a", "externalIdentifier": [{"identifier": _URL}]},
        "/externalIdentifier/0/identifier",
    ),
    "seeAlso": (
        {"spdxId": "urn:a", "expandedlicensing_seeAlso": [_URL]},
        "/expandedlicensing_seeAlso/0",
    ),
    "configSourceUri": (
        {"spdxId": "urn:a", "build_configSourceUri": [_URL]},
        "/build_configSourceUri/0",
    ),
    "buildType": ({"spdxId": "urn:a", "build_buildType": _URL}, "/build_buildType"),
    "security_locator": (
        {"spdxId": "urn:a", "security_locator": _URL},
        "/security_locator",
    ),
    "provenance-note": (
        {
            "spdxId": "urn:a",
            "contentType": "application/json",
            "statement": _statement(f"foo @ {_URL}"),
        },
        "/statement/fields/declared_constraint/note",
    ),
}


@pytest.mark.parametrize("name", sorted(_FIELDS))
def test_each_url_field_is_refused_with_its_place(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    element, pointer = _FIELDS[name]
    graph = [copy.deepcopy(element)]
    with caplog.at_level(logging.ERROR):
        error = _refuse(graph, CredentialPolicy())
    assert code_of(error) == _REFUSED and graph == [element]
    (line,) = [r.getMessage() for r in caplog.records]
    assert f" {pointer}, sha256:" in line and "1 URL value(s)" in str(error)
    assert _SECRET not in caplog.text


@pytest.mark.parametrize(
    "element",
    [
        {"name": _URL, "description": _URL, "comment": _URL, "summary": _URL},
        {"software_sourceInfo": _URL, "ai_informationAboutTraining": _URL},
        {"dataset_dataCollectionProcess": _URL, "software_copyrightText": _URL},
        {"contentType": "text/plain", "statement": _statement(_URL)},
        {"contentType": "application/json", "statement": _statement(_URL, "x:y")},
        {"contentType": "application/json", "statement": "{not json"},
        {"contentType": "application/json", "statement": json.dumps({"fields": 1})},
        {"import": [{"locationHint": "meet-10:30@ab:c.json"}]},
    ],
    ids=[
        *("prose", "source-info", "dataset"),
        *("text-statement", "other-schema", "bad-json", "fields-not-object"),
        "location-hint-file-name",
    ],
)
def test_a_field_not_read_is_never_refused(
    element: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    graph = [{"spdxId": "urn:a", **element}]
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, CredentialPolicy())
    assert not caplog.records


def test_a_location_hint_reads_no_scp_address_where_a_url_field_does() -> None:
    """Guards the ``scp=False`` of ``locationHint``: the same value is
    refused in a URL field."""
    value = "meet-10:30@ab:c.json"
    assert not find_graph_credentials([{"import": [{"locationHint": value}]}])
    assert find_graph_credentials([{"software_downloadLocation": value}])


def test_an_account_name_is_weak_in_a_url_field_and_refused_in_an_id() -> None:
    value = "ssh://git@github.com/o/r"
    in_field = _one([{"software_downloadLocation": value}])
    in_id = _one([{"spdxId": value}])
    assert in_field.finding.weak and not in_id.finding.weak


def test_one_value_in_two_places_is_one_error_at_the_first() -> None:
    graph: list[dict[str, Any]] = [
        {
            "spdxId": "urn:a",
            "software_homePage": _URL,
            "software_downloadLocation": _URL,
        },
        {"spdxId": "urn:b", "externalRef": [{"locator": [_URL]}]},
        {"spdxId": "urn:c", "software_homePage": f"{_URL}/2"},
    ]
    found = find_graph_credentials(graph)
    assert [(f.element, f.pointer) for f in found] == [
        ("urn:a", "/software_downloadLocation"),
        ("urn:c", "/software_homePage"),
    ]
    assert found[0].fingerprint == fingerprint(_URL)
    assert "2 URL value(s)" in str(_refuse(graph, CredentialPolicy()))


def test_a_weak_value_seen_first_does_not_hide_the_same_value_refused() -> None:
    """``ssh://git@...`` is weak in a URL field, refused as an id: the
    refusal wins wherever it stands."""
    value = "ssh://git@github.com/o/r"
    graph = [{"spdxId": "urn:a", "software_homePage": value}, {"spdxId": value}]
    found = _one(graph)
    assert not found.finding.weak and found.pointer == "/spdxId"


@pytest.mark.parametrize(
    "entry", [fingerprint(_URL), full_fingerprint(_URL)], ids=["printed", "full"]
)
def test_a_value_accepted_by_its_fingerprint_is_kept_and_said(
    entry: str, caplog: pytest.LogCaptureFixture
) -> None:
    graph = [{"spdxId": "urn:a", "software_homePage": _URL}]
    before = copy.deepcopy(graph)
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, CredentialPolicy(accepted=frozenset([entry])))
    assert graph == before and _codes(caplog) == [_ACCEPTED]
    assert fingerprint(_URL) in caplog.text and _SECRET not in caplog.text


def test_a_fingerprint_accepts_only_its_own_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Of two values the one fingerprinted is accepted, the other refused."""
    other = f"{_URL}/other"
    graph = [{"spdxId": "urn:a", "software_homePage": _URL, "build_buildType": other}]
    policy = CredentialPolicy(accepted=frozenset([fingerprint(_URL)]))
    with caplog.at_level(logging.WARNING):
        error = _refuse(graph, policy)
    assert "1 URL value(s)" in str(error)
    assert _codes(caplog) == [_ACCEPTED, _REFUSED]
    assert fingerprint(other) in caplog.records[1].getMessage()


def test_the_fingerprint_of_the_url_inside_a_value_does_not_accept_it() -> None:
    """The whole field value is fingerprinted, not the URL the detector
    found in it: a fingerprint of that URL alone accepts nothing here."""
    value = f"dep @ {_URL}"
    found = _one([{"software_homePage": value}])
    assert found.finding.view == _URL != value
    policy = CredentialPolicy(accepted=frozenset([fingerprint(_URL)]))
    _refuse([{"software_homePage": value}], policy)


def test_allow_all_keeps_every_value_and_says_each(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [{"spdxId": _URL, "software_homePage": f"{_URL}/2"}]
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, CredentialPolicy(allow_all=True))
    assert _codes(caplog) == [_ACCEPTED, _ACCEPTED]
    assert "--allow-url-credentials" in caplog.text and _SECRET not in caplog.text


def test_a_fingerprint_is_preferred_over_allow_all_in_what_is_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = CredentialPolicy(accepted=frozenset([fingerprint(_URL)]), allow_all=True)
    with caplog.at_level(logging.WARNING):
        check_graph_credentials([{"software_homePage": _URL}], policy)
    assert "--allow-url-credentials" not in caplog.text
    assert fingerprint(_URL) in caplog.text


@pytest.mark.parametrize(
    "value", ["https://h/x?code=ABC", "git+ssh://git@github.com/o/r"]
)
def test_a_weak_value_is_warned_of_and_never_refused(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(
            [{"software_downloadLocation": value}], CredentialPolicy()
        )
    assert _codes(caplog) == ["credentials-unsafe"]
    assert "ABC" not in caplog.text


def test_a_fingerprint_that_matches_no_value_is_said_stale(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stale = fingerprint("https://u:p@elsewhere.example/")
    policy = CredentialPolicy(accepted=frozenset([stale, fingerprint(_URL)]))
    with caplog.at_level(logging.WARNING):
        check_graph_credentials([{"software_homePage": _URL}], policy)
    assert _codes(caplog) == [_ACCEPTED, "option-no-effect"]
    assert stale in caplog.records[1].getMessage()


def test_a_fingerprint_is_stale_on_a_clean_graph_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = CredentialPolicy(accepted=frozenset([fingerprint(_URL)]))
    with caplog.at_level(logging.WARNING):
        check_graph_credentials([{"software_homePage": "https://h/"}], policy)
    assert _codes(caplog) == ["option-no-effect"]


def test_the_refusal_carries_no_secret_anywhere() -> None:
    """Text, ``args``, context, cause and the formatted traceback (the
    Hatchling hook prints it raw) hold no credential; the repr of a finding
    neither."""
    graph = [{"spdxId": f"urn:x:{_URL}", "software_homePage": f"{_URL}?token=T0KEN"}]
    error = _refuse(graph, CredentialPolicy())
    assert error.__context__ is None and error.__cause__ is None
    shown = "".join(traceback.format_exception(type(error), error, None))
    shown += str(error) + repr(error.args) + repr(find_graph_credentials(graph))
    assert _SECRET not in shown and "T0KEN" not in shown


def test_the_refusal_inside_an_except_block_has_no_context() -> None:
    """A caller's handled exception holding the URL is not chained in."""
    with pytest.raises(ValueError) as caught:
        try:
            raise KeyError(_URL)
        except KeyError:
            check_graph_credentials([{"software_homePage": _URL}], CredentialPolicy())
    error = caught.value
    assert code_of(error) == _REFUSED and error.__suppress_context__
    shown = "".join(traceback.format_exception(type(error), error, None))
    assert _SECRET not in shown


def test_a_deeply_nested_element_is_walked_without_recursion() -> None:
    node: dict[str, Any] = {"software_homePage": _URL}
    for _ in range(5000):
        node = {"extension": [node]}
    found = _one([node])
    assert found.pointer.endswith("/0/software_homePage")


def test_a_long_value_is_checked_in_linear_time() -> None:
    started = time.perf_counter()
    graph = [
        {"software_homePage": "https://h/" + "a" * 2**20},
        {"software_homePage": "@ " * 2**19},
        {"spdxId": "urn:" + "x:" * 2**19},
    ]
    check_graph_credentials(graph, CredentialPolicy())
    assert time.perf_counter() - started < 5


def test_a_pointer_token_escapes_tilde_and_slash() -> None:
    element = {
        "contentType": "application/json",
        "statement": json.dumps(
            {"schema": _PROVENANCE, "fields": {"a/b~c": {"note": _URL}}}
        ),
    }
    found = _one([element])
    assert found.pointer == "/statement/fields/a~1b~0c/note"


def _any_uri_fields() -> set[str]:
    names: set[str] = set()
    for cls in vars(spdx_model).values():
        props = vars(cls).get("_OBJ_COMPACT_PROPS") if inspect.isclass(cls) else None
        for compact, prop in (props or {}).items():
            # The binding resolves a property once, then drops its factory.
            kind = prop.prop if prop.prop is not None else prop.reg()
            inner = kind.prop if isinstance(kind, spdx_model.ListProp) else kind
            if isinstance(inner, spdx_model.AnyURIProp):
                names.add(compact)
    return names


def test_every_any_uri_field_of_the_model_is_read_or_said_not_read() -> None:
    fields = _any_uri_fields()
    assert "software_homePage" in fields and len(fields) >= 12
    assert fields <= set(URL_FIELDS) | set(NOT_READ)
    assert all(NOT_READ.values())


def _exporter(*packages: tuple[str, str]) -> Spdx3JsonExporter:
    exporter = Spdx3JsonExporter()
    info = spdx_model.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["urn:agent"],
    )
    for spdx_id, home in packages:
        exporter.add_package(
            spdx_model.software_Package(
                spdxId=spdx_id, name="p", software_homePage=home, creationInfo=info
            )
        )
    return exporter


@pytest.mark.parametrize("count", [1, 2], ids=["lone-element", "graph"])
def test_the_exporter_refuses_by_default_and_writes_an_accepted_value_as_is(
    count: int,
) -> None:
    """A lone element is written without ``@graph`` and checked too."""
    exporter = _exporter(*[("urn:a#P", _URL), ("urn:b#P", "https://h/")][:count])
    assert ("@graph" in exporter.to_json(credentials=_ALLOW)) is (count == 2)
    with pytest.raises(ValueError) as caught:
        exporter.to_json()
    assert code_of(caught.value) == _REFUSED
    text = exporter.to_json(
        credentials=CredentialPolicy(accepted=frozenset([fingerprint(_URL)]))
    )
    assert json.dumps(_URL) in text


def test_the_exporter_reports_in_output_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The check runs on the sorted graph: the values are named in the order
    the SBOM would hold them, whatever order they were added in."""
    exporter = _exporter(("urn:z#P", f"{_URL}/z"), ("urn:a#P", f"{_URL}/a"))
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        exporter.to_json()
    lines = [r.getMessage() for r in caplog.records[:2]]
    assert "urn:a#P" in lines[0] and "urn:z#P" in lines[1]
