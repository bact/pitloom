# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""Real Git hosting platforms: the URL forms a person pastes are fetched.

These reach live servers, so they are marked ``network`` (skipped when the
network fails, failing under ``PITLOOM_REQUIRE_NETWORK``). A failure here means
a platform changed how it answers, or a repository moved: the table in
``docs/git-urls.md`` lists what was verified and when.

Only the fetch is run (repository, branch, folder); reading the project is
tested with local servers in ``test_git_http_e2e.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.remote import fetch_git_project
from tests._network import skip_on_network_error

pytestmark = pytest.mark.network

# (id, URL, branch or tag named, folder named, a file expected in the folder)
_PLATFORMS = [
    # GitLab. A bare project URL is answered with a redirect to ``.git``.
    (
        "gitlab-com",
        "https://gitlab.com/freedesktop-sdk/mirrors/github/pypa/pyproject-hooks",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "gitlab-com-page",
        "https://gitlab.com/freedesktop-sdk/mirrors/github/pypa/"
        "pyproject-hooks/-/tree/main/src",
        "main",
        "src",
        "pyproject_hooks",
    ),
    ("gitlab-etsi", "https://labs.etsi.org/rep/ocf/sdk", None, "", "setup.py"),
    (
        "gitlab-etsi-page",
        "https://labs.etsi.org/rep/ocf/capif/-/tree/staging/services/register",
        "staging",
        "services/register",
        "requirements.txt",
    ),
    (
        "gitlab-european-commission",
        "https://code.europa.eu/simpl/simpl-open/administration/"
        "observability/logging/common-logging/common-logging-python-utils",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "gitlab-german-public-sector-page",
        "https://gitlab.opencode.de/umwelt-info/packages/-/tree/main/umwelt_apy",
        "main",
        "umwelt_apy",
        "pyproject.toml",
    ),
    (
        "gitlab-french-education",
        "https://forge.apps.education.fr/philipperackette/AntibiAutomatismes",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "gitlab-framagit",
        "https://framagit.org/justinmponcet/whisper",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "gitlab-cern",
        "https://gitlab.cern.ch/cms-cactus/phase2/pyswatch",
        None,
        "",
        "pyproject.toml",
    ),
    # Forgejo and Gitea. The bare URL is served as it is.
    (
        "forgejo-codeberg",
        "https://codeberg.org/kfdm/pyproject-add-url",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "forgejo-codeberg-page",
        "https://codeberg.org/kfdm/pyproject-add-url/src/branch/main",
        "main",
        "",
        "pyproject.toml",
    ),
    (
        "forgejo-dutch-government",
        "https://code.overheid.nl/Logius/nldoc-lib-python-nldocspec",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "forgejo-dutch-government-page",
        "https://code.overheid.nl/Logius/nldoc-lib-python-nldocspec/"
        "src/branch/main/nldocspec",
        "main",
        "nldocspec",
        "__init__.py",
    ),
    (
        "gitea-com-page",
        "https://gitea.com/gitea/tea/src/branch/main/cmd",
        "main",
        "cmd",
        "actions.go",
    ),
    (
        "gitea-com-tag",
        "https://gitea.com/gitea/tea/src/tag/v0.16.0/cmd",
        "v0.16.0",
        "cmd",
        "actions.go",
    ),
    # Bitbucket Cloud. A file page is written like a folder page.
    (
        "bitbucket",
        "https://bitbucket.org/zzzeek/sqlalchemy",
        None,
        "",
        "pyproject.toml",
    ),
    (
        "bitbucket-src-page",
        "https://bitbucket.org/zzzeek/sqlalchemy/src/main/lib/sqlalchemy",
        "main",
        "lib/sqlalchemy",
        "__init__.py",
    ),
    (
        "bitbucket-file-page",
        "https://bitbucket.org/zzzeek/sqlalchemy/src/main/pyproject.toml",
        "main",
        "",
        "pyproject.toml",
    ),
    (
        "bitbucket-branch-page",
        "https://bitbucket.org/zzzeek/sqlalchemy/branch/rel_0_4",
        "rel_0_4",
        "",
        "setup.py",
    ),
    (
        "bitbucket-commits-tag-page",
        "https://bitbucket.org/zzzeek/sqlalchemy/commits/tag/rel_2_0_9",
        "rel_2_0_9",
        "",
        "pyproject.toml",
    ),
    # SourceHut. ``item`` stands for a folder and a file alike.
    ("sourcehut", "https://git.sr.ht/~sircmpwn/scm.sr.ht", None, "", "setup.py"),
    (
        "sourcehut-tree-page",
        "https://git.sr.ht/~sircmpwn/scm.sr.ht/tree/master/item/scmsrht",
        "master",
        "scmsrht",
        "__init__.py",
    ),
    (
        "sourcehut-file-page",
        "https://git.sr.ht/~sircmpwn/scm.sr.ht/tree/master/item/setup.py",
        "master",
        "",
        "setup.py",
    ),
    (
        "sourcehut-log-page",
        "https://git.sr.ht/~sircmpwn/scm.sr.ht/log/master",
        "master",
        "",
        "setup.py",
    ),
    # GitHub.
    ("github", "https://github.com/pypa/pyproject-hooks", None, "", "pyproject.toml"),
    (
        "github-page",
        "https://github.com/pypa/pyproject-hooks/tree/main/src",
        "main",
        "src",
        "pyproject_hooks",
    ),
    (
        "github-file-page",
        "https://github.com/pypa/pyproject-hooks/blob/main/src/"
        "pyproject_hooks/__init__.py",
        "main",
        "src/pyproject_hooks",
        "__init__.py",
    ),
]


@pytest.mark.parametrize(
    ("url", "ref", "folder", "expected"),
    [pytest.param(u, r, f, e, id=i) for i, u, r, f, e in _PLATFORMS],
)
def test_a_platforms_url_is_fetched(
    url: str, ref: str | None, folder: str, expected: str
) -> None:
    """The branch and folder the URL names are checked out, with a redirect
    followed where the platform sends one."""
    with skip_on_network_error(), fetch_git_project(url) as checkout:
        assert checkout.ref == ref and checkout.subdir == folder
        assert (Path(checkout.folder) / expected).exists()
        assert len(checkout.commit) in {40, 64}
