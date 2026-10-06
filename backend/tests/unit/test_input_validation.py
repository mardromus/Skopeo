import pytest
from pydantic import ValidationError

from app.schemas.investigation import InvestigationCreate
from app.security.url_validation import InvalidBranchName, InvalidRepositoryURL, validate_branch, validate_repository_url


@pytest.mark.parametrize(
    "url,full",
    [
        ("https://github.com/psf/requests", "psf/requests"),
        ("https://github.com/psf/requests.git", "psf/requests"),
        ("https://github.com/psf/requests/", "psf/requests"),
        ("https://www.github.com/a-b/c.d_e", "a-b/c.d_e"),
    ],
)
def test_valid_github_urls(url, full):
    assert validate_repository_url(url).full_name == full


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "git@github.com:a/b.git",
        "ssh://github.com/a/b",
        "file:///etc/passwd",
        "https://gitlab.com/a/b",
        "https://github.com.evil.com/a/b",
        "https://user:pass@github.com/a/b",
        "https://github.com:8443/a/b",
        "https://github.com/a/b?ref=x",
        "https://github.com/a/b#frag",
        "https://github.com/a/b/tree/main",
        "https://github.com/a",
        "https://github.com/../b",
        "https://github.com/a/..",
        "https://github.com/a/b%2F..",
        "https://github.com/-a/b",
        "https://github.com/settings/profile",
        "https://github.com/a/b\n",
        "",
    ],
)
def test_malicious_or_invalid_urls_rejected(url):
    with pytest.raises(InvalidRepositoryURL):
        validate_repository_url(url)


@pytest.mark.parametrize("branch", ["main", "release/1.2", "feature_x-y.z"])
def test_valid_branches(branch):
    assert validate_branch(branch) == branch


@pytest.mark.parametrize("branch", ["--upload-pack=evil", "-x", "a..b", "a//b", "x.lock", "a/", "@{-1}", "a b", "", "a/.hidden"])
def test_invalid_branches(branch):
    with pytest.raises(InvalidBranchName):
        validate_branch(branch)


def test_input_schema_validates_and_canonicalises():
    body = InvestigationCreate(repository_url="https://github.com/psf/requests.git", branch="main", analysis_depth="deep")
    assert body.repository_url == "https://github.com/psf/requests"
    with pytest.raises(ValidationError):
        InvestigationCreate(repository_url="https://github.com/psf/requests", analysis_depth="extreme")
    with pytest.raises(ValidationError):
        InvestigationCreate(repository_url="https://github.com/psf/requests", unexpected=True)
