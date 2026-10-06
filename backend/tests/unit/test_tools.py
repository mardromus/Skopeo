from pathlib import Path

from app.config import get_settings
from app.security.redaction import REDACTED, redact, register_secrets
from app.tools.advisories import AdvisoryClient, RegistryClient, _group_records, load_snapshot, version_gap
from app.tools.command_runner import SafeCommandRunner
from app.tools.licenses import compatibility_issue, identify_license_text, normalize_expression
from app.tools.manifests import Dependency
from app.tools.python_ast import ImportGraph, call_sites, cyclomatic_complexity, parse_python
from app.tools.repository import RepositoryHandle, RepositoryTools, parse_pytest_output
from app.tools.secrets import placeholder_assessment, scan_text


def _tools(root: Path) -> RepositoryTools:
    s = get_settings()
    handle = RepositoryHandle(
        root=root, workspace=root.parent, source="github", full_name="t/r", url="https://github.com/t/r", branch="main"
    )
    return RepositoryTools(handle, SafeCommandRunner(30, 100_000), s)


def test_manifest_parsing_across_ecosystems(tmp_path):
    (tmp_path / "requirements.txt").write_text("PyJWT==1.7.1\nrequests>=2.20  # comment\n-r dev-requirements.txt\n")
    (tmp_path / "dev-requirements.txt").write_text("pytest==8.0.0\n")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"lodash": "4.17.20", "express": "^4.18.0"}, "devDependencies": {"jest": "29.0.0"}}'
    )
    (tmp_path / "go.mod").write_text("module x\n\nrequire (\n\tgithub.com/pkg/errors v0.9.1\n)\n")
    (tmp_path / "Cargo.toml").write_text('[dependencies]\nserde = "1.0"\nrand = "=0.8.5"\n')
    deps = {d.name: d for d in _tools(tmp_path).inspect_dependencies()}
    assert deps["pyjwt"].version == "1.7.1" and deps["pyjwt"].pinned
    assert not deps["requests"].pinned
    assert deps["pytest"].dev
    assert deps["lodash"].pinned and not deps["express"].pinned
    assert deps["github.com/pkg/errors"].ecosystem == "Go"
    assert deps["rand"].pinned and not deps["serde"].pinned


def test_offline_advisories_are_real_snapshot_records():
    snap = load_snapshot()
    assert snap["generated_at"] and "api.osv.dev" in snap["description"]
    client = AdvisoryClient(get_settings(), offline=True)
    lookup = client.lookup(Dependency("pyjwt", "PyJWT", "PyPI", "==1.7.1", "1.7.1", True, "requirements.txt", 1))
    assert lookup.status == "ok"
    ids = {a.id for a in lookup.advisories} | {x for a in lookup.advisories for x in a.aliases}
    assert "GHSA-ffqj-6fqr-9h24" in ids and "CVE-2022-29217" in ids
    # aliases (GHSA / PYSEC / CVE) are merged into one advisory per vulnerability
    assert len(lookup.advisories) < len(snap["osv"]["PyPI"]["pyjwt"]["1.7.1"])


def test_unknown_packages_are_insufficient_evidence_not_clean():
    client = AdvisoryClient(get_settings(), offline=True)
    lookup = client.lookup(Dependency("leftpadx", "leftpadx", "PyPI", "==1.0", "1.0", True, "requirements.txt", 1))
    assert lookup.status == "unavailable"
    reg = RegistryClient(get_settings(), offline=True).package_info(
        Dependency("leftpadx", "leftpadx", "PyPI", "==1.0", "1.0", True, "r.txt", 1)
    )
    assert reg.status == "unavailable"


def test_alias_grouping():
    recs = [
        {
            "id": "GHSA-1",
            "aliases": ["CVE-1"],
            "database_specific": {"severity": "HIGH"},
            "affected": [{"package": {"name": "x"}, "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0"}]}]}],
        },
        {"id": "PYSEC-1", "aliases": ["CVE-1", "GHSA-1"], "affected": []},
        {"id": "GHSA-2", "aliases": [], "database_specific": {"severity": "LOW"}, "affected": []},
    ]
    adv = _group_records(recs, "x", "test")
    assert [a.id for a in adv] == ["GHSA-1", "GHSA-2"]
    assert adv[0].severity == "high" and adv[0].fixed_versions == ["2.0"]


def test_version_gap():
    assert version_gap("1.7.1", "2.15.1", "PyPI") == "major"
    assert version_gap("2.1.0", "2.15.1", "PyPI") == "minor"
    assert version_gap("2.15.0", "2.15.1", "PyPI") == "patch"
    assert version_gap("2.15.1", "2.15.1", "PyPI") == "current"


def test_secret_scanner_and_placeholder_recognition():
    hits = scan_text("aws_access_key_id = AKIAIOSFODNN7EXAMPLE\napi_key = 'q8Zr2LmV9xKp4TnW'\nname = 'bob'\n")
    rules = {h.rule_id for h in hits}
    assert "secret.aws_access_key" in rules and "secret.generic_assignment" in rules
    assert all("AKIAIOSFODNN7EXAMPLE" not in h.masked for h in hits)
    assert placeholder_assessment("AKIAIOSFODNN7EXAMPLE")[0] is True
    assert placeholder_assessment("AKIA" + "Q3EGRQ7RXMKV5N2P")[0] is False


def test_license_identification_and_compatibility():
    mit = "Permission is hereby granted, free of charge, to any person obtaining a copy"
    assert identify_license_text(mit) == "MIT"
    assert normalize_expression("Apache Software License OR BSD License") == ["Apache-2.0", "BSD"]
    assert compatibility_issue("MIT", "GPL-3.0")[0] == "high"
    assert compatibility_issue("MIT", "Apache-2.0") is None


def test_ast_helpers(tmp_path):
    src = "def f(x):\n    for i in x:\n        if i and x:\n            db.execute('q', (i,))\n    return 1\n"
    tree = parse_python(src)
    fn = tree.body[0]
    assert cyclomatic_complexity(fn) == 4
    sites = [s for s in call_sites(tree) if s.dotted == "db.execute"]
    assert sites and sites[0].in_loop and sites[0].loop_lineno == 2
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("import jwt\n")
    (pkg / "b.py").write_text("from pkg import a\n")
    graph = ImportGraph(_tools(tmp_path))
    assert graph.files_importing_external("jwt") == ["pkg/a.py"]
    assert "pkg/b.py" in graph.transitive_importers("pkg/a.py")


def test_redaction():
    token = "ghp_" + "x" * 36
    assert token not in redact(f"Authorization: Bearer {token}")
    assert redact("https://user:hunter2@github.com/a/b").count(REDACTED) == 1
    register_secrets(["super-secret-value-123"])
    assert "super-secret-value-123" not in redact("value super-secret-value-123 leaked")
    assert "-----BEGIN" not in redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")


def test_pytest_output_parser():
    out = "....F\nFAILED tests/test_a.py::test_x - AssertionError: assert 1 == 2\n1 failed, 4 passed in 0.10s\n"
    parsed = parse_pytest_output(out)
    assert parsed["counts"] == {"failed": 1, "passed": 4}
    assert parsed["failures"][0]["node_id"] == "tests/test_a.py::test_x"
