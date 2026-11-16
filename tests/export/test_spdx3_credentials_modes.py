# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The two ``url-credentials`` modes of
:func:`pitloom.export._spdx3_credentials.check_graph_credentials`: ``warn``
(the default) writes a value holding a credential with one ``WARNING:``,
``refuse`` refuses the SBOM; a value accepted by its fingerprint is the
quieter ``accepted`` line in either mode. One test per side of each
``mode and not accepted``.

See also: tests/export/test_spdx3_credentials.py (the ``refuse`` mode in
depth) and tests/test_credential_surfaces.py (every surface).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any

import pytest
from spdx_python_model.bindings.v3_0_1 import model as spdx_model

from pitloom.core.credential_policy import CredentialPolicy, fingerprint
from pitloom.export._spdx3_credentials import check_graph_credentials
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of

_SECRET = "S3CRET"
_URL = f"https://u:{_SECRET}@h.example/x"
_OTHER = f"{_URL}/other"
_WRITTEN = "credentials-unsafe/written"
_ACCEPTED = "credentials-unsafe/accepted"
_REFUSED = "credentials-unsafe/refused"


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR, "") for r in caplog.records]


def _policy(refuse: bool, accepted: bool) -> CredentialPolicy:
    entries = frozenset([fingerprint(_URL)] if accepted else [])
    return CredentialPolicy(accepted=entries, refuse=refuse)


@pytest.mark.parametrize(
    ("refuse", "accepted", "codes"),
    [
        (False, False, [_WRITTEN]),
        (False, True, [_ACCEPTED]),
        (True, False, [_REFUSED]),
        (True, True, [_ACCEPTED]),
    ],
    ids=["warn", "warn-accepted", "refuse", "refuse-accepted"],
)
def test_the_mode_and_the_acceptance_decide_what_is_said(
    refuse: bool, accepted: bool, codes: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    graph = [{"spdxId": "urn:a", "software_homePage": _URL}]
    before = copy.deepcopy(graph)
    with caplog.at_level(logging.WARNING):
        if refuse and not accepted:
            with pytest.raises(ValueError) as caught:
                check_graph_credentials(graph, _policy(refuse, accepted))
            assert code_of(caught.value) == _REFUSED
        else:
            check_graph_credentials(graph, _policy(refuse, accepted))
    assert _codes(caplog) == codes and graph == before
    assert _SECRET not in caplog.text


def test_the_warn_mode_names_the_place_and_fingerprint_of_each_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [
        {"spdxId": "urn:a", "software_homePage": _URL},
        {"spdxId": "urn:b", "software_downloadLocation": _OTHER},
    ]
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, CredentialPolicy())
    assert _codes(caplog) == [_WRITTEN, _WRITTEN]
    first, second = caplog.messages
    assert f"(urn:a /software_homePage, {fingerprint(_URL)})" in first
    assert f"(urn:b /software_downloadLocation, {fingerprint(_OTHER)})" in second
    assert all(r.levelno == logging.WARNING for r in caplog.records)


def test_the_warn_mode_writes_one_value_accepted_and_warns_of_the_other(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [{"spdxId": "urn:a", "software_homePage": _URL, "build_buildType": _OTHER}]
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, _policy(refuse=False, accepted=True))
    assert _codes(caplog) == [_ACCEPTED, _WRITTEN]
    assert fingerprint(_OTHER) in caplog.messages[1]


@pytest.mark.parametrize("refuse", [False, True], ids=["warn", "refuse"])
def test_a_weak_value_is_only_warned_of_in_either_mode(
    refuse: bool, caplog: pytest.LogCaptureFixture
) -> None:
    graph = [{"software_downloadLocation": "https://h/x?code=ABC"}]
    with caplog.at_level(logging.WARNING):
        check_graph_credentials(graph, CredentialPolicy(refuse=refuse))
    assert _codes(caplog) == ["credentials-unsafe"]


def test_a_stale_fingerprint_is_said_in_the_warn_mode_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stale = fingerprint("https://u:p@elsewhere.example/")
    policy = CredentialPolicy(accepted=frozenset([stale]))
    with caplog.at_level(logging.WARNING):
        check_graph_credentials([{"software_homePage": _URL}], policy)
    assert _codes(caplog) == ["option-no-effect", _WRITTEN]


def test_the_exporter_writes_in_the_warn_mode_by_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A call site that forgets the run's policy warns, never fails."""
    exporter = Spdx3JsonExporter()
    exporter.add_package(
        spdx_model.software_Package(
            spdxId="urn:a#P",
            name="p",
            software_homePage=_URL,
            creationInfo=spdx_model.CreationInfo(
                specVersion="3.0.1",
                created=datetime(2026, 1, 1, tzinfo=timezone.utc),
                createdBy=["urn:agent"],
            ),
        )
    )
    with caplog.at_level(logging.WARNING):
        text = exporter.to_json()
    assert f'"{_URL}"' in text and _codes(caplog) == [_WRITTEN]


@pytest.mark.parametrize(
    ("one", "two", "refuse"),
    [
        ({}, {}, False),
        ({"refuse": True}, {}, True),
        ({}, {"refuse": True}, True),
        ({"refuse": True}, {"refuse": True}, True),
    ],
    ids=["neither", "self", "other", "both"],
)
def test_union_and_inheriting_refuse_when_either_does(
    one: dict[str, Any], two: dict[str, Any], refuse: bool
) -> None:
    """A flag turns refusal on, never off; a project the fragment merges into
    that refuses makes the fragment refuse too."""
    first, second = CredentialPolicy(**one), CredentialPolicy(**two)
    assert first.union(second).refuse is refuse
    assert first.inheriting(second).refuse is refuse
