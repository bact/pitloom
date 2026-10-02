# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract._core_metadata.parse_project_urls -- the
shared RFC 822 Core-Metadata Project-URL parser used by
pitloom.extract.wheel, pitloom.extract.project.sdist,
pitloom.extract.project.installed, and
pitloom.assemble.spdx3.deps_originator.
"""

# Explicit `== []`/`== {}` keeps the None-vs-empty distinction.
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import email

from pitloom.extract._core_metadata import parse_project_urls


def _msg(*headers: tuple[str, str]) -> email.message.Message:
    message = email.message.Message()
    for name, value in headers:
        message[name] = value
    return message


def test_malformed_project_url_entry_is_silently_dropped() -> None:
    """A `Project-URL` entry with no comma cannot be split into
    label/URL -- it is dropped, never raised or warned about."""
    msg = _msg(("Project-URL", "no-comma-here"))
    assert parse_project_urls(msg) == {}


def test_project_url_value_containing_a_comma_is_preserved() -> None:
    """First-comma-only split: a URL whose own query string legally
    contains a comma must not be truncated at that inner comma."""
    msg = _msg(("Project-URL", "Tracker, https://example.com/issues?a=1,2"))
    assert parse_project_urls(msg) == {"Tracker": "https://example.com/issues?a=1,2"}


def test_project_url_wins_over_colliding_homepage() -> None:
    """Home-page and a colliding Project-URL entry both resolve to the
    same key ("Homepage") -- Project-URL's value must win regardless of
    which order the two are set on the message, checking the helper's
    order-independence claim explicitly rather than trusting it."""
    msg = _msg(
        ("Home-page", "https://homepage.example.com"),
        ("Project-URL", "Homepage, https://project-url.example.com"),
    )
    assert parse_project_urls(msg) == {"Homepage": "https://project-url.example.com"}


def test_lowercase_labels_true_vs_false() -> None:
    """lowercase_labels controls only the case of the resulting key, no
    other behavior change."""
    msg = _msg(("Project-URL", "Tracker, https://example.com/issues"))
    assert parse_project_urls(msg, lowercase_labels=False) == {
        "Tracker": "https://example.com/issues"
    }
    assert parse_project_urls(msg, lowercase_labels=True) == {
        "tracker": "https://example.com/issues"
    }


def test_include_homepage_false_omits_homepage() -> None:
    msg = _msg(("Home-page", "https://homepage.example.com"))
    assert parse_project_urls(msg, include_homepage=False) == {}


def test_include_download_true_adds_download_url() -> None:
    msg = _msg(("Download-URL", "https://example.com/dl.tar.gz"))
    assert parse_project_urls(msg, include_download=True) == {
        "Download": "https://example.com/dl.tar.gz"
    }


def test_include_download_default_false_omits_download_url() -> None:
    msg = _msg(("Download-URL", "https://example.com/dl.tar.gz"))
    assert parse_project_urls(msg) == {}


def test_no_headers_at_all_returns_empty_dict() -> None:
    assert parse_project_urls(_msg()) == {}


def test_multiple_project_url_entries_all_kept() -> None:
    msg = _msg(
        ("Project-URL", "Homepage, https://example.com"),
        ("Project-URL", "Tracker, https://example.com/issues"),
    )
    assert parse_project_urls(msg) == {
        "Homepage": "https://example.com",
        "Tracker": "https://example.com/issues",
    }


def test_label_and_url_are_stripped() -> None:
    msg = _msg(("Project-URL", "  Tracker  ,   https://example.com/issues  "))
    assert parse_project_urls(msg) == {"Tracker": "https://example.com/issues"}
