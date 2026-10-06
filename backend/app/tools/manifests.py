"""Deterministic manifest parsing for Python, JavaScript/TypeScript, Java, Go and Rust."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.repository import RepositoryTools

MANIFEST_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "go.mod",
    "Cargo.toml",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}

ECOSYSTEM_BY_MANIFEST = {
    "pyproject.toml": "PyPI",
    "setup.cfg": "PyPI",
    "Pipfile": "PyPI",
    "package.json": "npm",
    "go.mod": "Go",
    "Cargo.toml": "crates.io",
    "pom.xml": "Maven",
    "build.gradle": "Maven",
    "build.gradle.kts": "Maven",
}

_PEP508_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(\(?[^;#]*\)?)?\s*(;.*)?$")
_EXACT_PY_RE = re.compile(r"^===?\s*([A-Za-z0-9.+!_-]+)$")
_EXACT_SEMVER_RE = re.compile(r"^=?v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


@dataclass
class Dependency:
    name: str
    display_name: str
    ecosystem: str
    spec: str
    version: str | None
    pinned: bool
    manifest: str
    line: int | None = None
    dev: bool = False
    resolved_from: str | None = None

    @property
    def key(self) -> str:
        return f"{self.ecosystem}:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_name(name: str, ecosystem: str) -> str:
    if ecosystem == "PyPI":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name


def _python_requirement(raw: str, manifest: str, line: int | None, dev: bool = False) -> Dependency | None:
    text = raw.strip()
    if not text or text.startswith(("#", "-", "git+", "http:", "https:", "file:", ".")):
        return None
    text = text.split(" #", 1)[0].strip()
    m = _PEP508_RE.match(text)
    if not m:
        return None
    name = m.group(1)
    spec = (m.group(3) or "").strip().strip("()").replace(" ", "")
    version = None
    exact = _EXACT_PY_RE.match(spec)
    if exact and "*" not in exact.group(1):
        version = exact.group(1)
    return Dependency(
        name=normalize_name(name, "PyPI"),
        display_name=name,
        ecosystem="PyPI",
        spec=spec or "*",
        version=version,
        pinned=version is not None,
        manifest=manifest,
        line=line,
        dev=dev,
    )


def _parse_requirements(tools: RepositoryTools, rel: str, seen: set[str], depth: int = 0) -> list[Dependency]:
    if rel in seen or depth > 3:
        return []
    seen.add(rel)
    text = tools.try_get_file(rel)
    if text is None:
        return []
    deps: list[Dependency] = []
    dev = "dev" in Path(rel).name or "test" in Path(rel).name
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("-r ", "--requirement ")):
            include = stripped.split(None, 1)[1].strip()
            target = (Path(rel).parent / include).as_posix()
            if ".." not in target.split("/"):
                deps.extend(_parse_requirements(tools, target, seen, depth + 1))
            continue
        dep = _python_requirement(stripped, rel, lineno, dev=dev)
        if dep:
            deps.append(dep)
    return deps


def _find_line(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return None


def _parse_pyproject(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps: list[Dependency] = []
    project = data.get("project", {}) or {}
    for req in project.get("dependencies", []) or []:
        if isinstance(req, str):
            dep = _python_requirement(req, rel, _find_line(text, req))
            if dep:
                deps.append(dep)
    for group, reqs in (project.get("optional-dependencies", {}) or {}).items():
        for req in reqs or []:
            if isinstance(req, str):
                dep = _python_requirement(req, rel, _find_line(text, req), dev=group in {"dev", "test", "tests", "lint"})
                if dep:
                    deps.append(dep)
    poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
    for section, dev in (("dependencies", False), ("dev-dependencies", True)):
        for name, spec in (poetry.get(section, {}) or {}).items():
            if name.lower() == "python":
                continue
            version_spec = spec.get("version", "*") if isinstance(spec, dict) else str(spec)
            exact = re.fullmatch(r"=?=?(\d+(?:\.\d+)*)", version_spec.strip())
            deps.append(
                Dependency(
                    name=normalize_name(name, "PyPI"),
                    display_name=name,
                    ecosystem="PyPI",
                    spec=version_spec,
                    version=exact.group(1) if exact else None,
                    pinned=bool(exact),
                    manifest=rel,
                    line=_find_line(text, name),
                    dev=dev,
                )
            )
    return deps


def _parse_pipfile(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps = []
    for section, dev in (("packages", False), ("dev-packages", True)):
        for name, spec in (data.get(section, {}) or {}).items():
            version_spec = spec.get("version", "*") if isinstance(spec, dict) else str(spec)
            exact = _EXACT_PY_RE.match(version_spec.replace(" ", ""))
            deps.append(
                Dependency(
                    normalize_name(name, "PyPI"),
                    name,
                    "PyPI",
                    version_spec,
                    exact.group(1) if exact else None,
                    bool(exact),
                    rel,
                    _find_line(text, name),
                    dev,
                )
            )
    return deps


def _parse_package_json(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    lock_versions: dict[str, str] = {}
    lock_rel = (PurePosixPath(rel).parent / "package-lock.json").as_posix()
    lock_text = tools.try_get_file(lock_rel)
    if lock_text:
        try:
            lock = json.loads(lock_text)
            for path, meta in (lock.get("packages") or {}).items():
                if path.startswith("node_modules/") and isinstance(meta, dict) and meta.get("version"):
                    lock_versions[path[len("node_modules/") :]] = meta["version"]
            for name, meta in (lock.get("dependencies") or {}).items():
                if isinstance(meta, dict) and meta.get("version"):
                    lock_versions.setdefault(name, meta["version"])
        except json.JSONDecodeError:
            pass
    deps = []
    for section, dev in (("dependencies", False), ("devDependencies", True)):
        for name, spec in (data.get(section) or {}).items():
            spec = str(spec)
            exact = _EXACT_SEMVER_RE.match(spec.strip())
            version = exact.group(1) if exact else lock_versions.get(name)
            deps.append(
                Dependency(
                    name=name,
                    display_name=name,
                    ecosystem="npm",
                    spec=spec,
                    version=version,
                    pinned=bool(exact),
                    manifest=rel,
                    line=_find_line(text, f'"{name}"'),
                    dev=dev,
                    resolved_from="package-lock.json" if (not exact and version) else None,
                )
            )
    return deps


def _parse_go_mod(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    deps = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.split("//", 1)[0].strip()
        if s.startswith("require ("):
            in_block = True
            continue
        if in_block and s == ")":
            in_block = False
            continue
        m = None
        if in_block:
            m = re.match(r"^(\S+)\s+(v\S+)", s)
        elif s.startswith("require "):
            m = re.match(r"^require\s+(\S+)\s+(v\S+)", s)
        if m:
            deps.append(Dependency(m.group(1), m.group(1), "Go", m.group(2), m.group(2), True, rel, lineno, "// indirect" in line))
    return deps


def _parse_cargo(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps = []
    for section, dev in (("dependencies", False), ("dev-dependencies", True)):
        for name, spec in (data.get(section, {}) or {}).items():
            version_spec = spec.get("version", "*") if isinstance(spec, dict) else str(spec)
            exact = re.fullmatch(r"=\s*(\d+\.\d+\.\d+)", version_spec.strip())
            deps.append(
                Dependency(
                    name, name, "crates.io", version_spec, exact.group(1) if exact else None, bool(exact), rel, _find_line(text, name), dev
                )
            )
    return deps


def _parse_pom(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    deps = []
    for block in re.finditer(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
        body = block.group(1)
        g = re.search(r"<groupId>\s*([^<\s]+)\s*</groupId>", body)
        a = re.search(r"<artifactId>\s*([^<\s]+)\s*</artifactId>", body)
        v = re.search(r"<version>\s*([^<\s]+)\s*</version>", body)
        scope = re.search(r"<scope>\s*([^<\s]+)\s*</scope>", body)
        if not (g and a):
            continue
        name = f"{g.group(1)}:{a.group(1)}"
        version = v.group(1) if v and "${" not in v.group(1) else None
        line = text[: block.start()].count("\n") + 1
        deps.append(
            Dependency(
                name,
                name,
                "Maven",
                v.group(1) if v else "*",
                version,
                version is not None,
                rel,
                line,
                bool(scope and scope.group(1) == "test"),
            )
        )
    return deps


def _parse_gradle(tools: RepositoryTools, rel: str) -> list[Dependency]:
    text = tools.try_get_file(rel)
    if not text:
        return []
    deps = []
    pattern = re.compile(r"(implementation|api|compile|runtimeOnly|testImplementation)\s*\(?\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]")
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = pattern.search(line)
        if m:
            name = f"{m.group(2)}:{m.group(3)}"
            version = m.group(4) if "$" not in m.group(4) and "+" not in m.group(4) else None
            deps.append(
                Dependency(name, name, "Maven", m.group(4), version, version is not None, rel, lineno, m.group(1).startswith("test"))
            )
    return deps


def parse_dependencies(tools: RepositoryTools) -> list[Dependency]:
    deps: list[Dependency] = []
    seen_req: set[str] = set()
    for rel in tools.list_files():
        name = Path(rel).name
        if "/" in rel and rel.count("/") > 3:
            continue  # nested vendored manifests are out of scope
        if re.fullmatch(r"requirements[^/]*\.txt", name):
            deps.extend(_parse_requirements(tools, rel, seen_req))
        elif name == "pyproject.toml":
            deps.extend(_parse_pyproject(tools, rel))
        elif name == "Pipfile":
            deps.extend(_parse_pipfile(tools, rel))
        elif name == "package.json" and "node_modules" not in rel:
            deps.extend(_parse_package_json(tools, rel))
        elif name == "go.mod":
            deps.extend(_parse_go_mod(tools, rel))
        elif name == "Cargo.toml":
            deps.extend(_parse_cargo(tools, rel))
        elif name == "pom.xml":
            deps.extend(_parse_pom(tools, rel))
        elif name in ("build.gradle", "build.gradle.kts"):
            deps.extend(_parse_gradle(tools, rel))
    # de-duplicate by (ecosystem, name, manifest) keeping the first occurrence
    unique: dict[tuple[str, str, str], Dependency] = {}
    for d in deps:
        unique.setdefault((d.ecosystem, d.name, d.manifest), d)
    return list(unique.values())


def detect_ecosystems(files: list[str]) -> list[str]:
    ecos: set[str] = set()
    for f in files:
        name = Path(f).name
        if name in ECOSYSTEM_BY_MANIFEST:
            ecos.add(ECOSYSTEM_BY_MANIFEST[name])
        elif re.fullmatch(r"requirements[^/]*\.txt", name):
            ecos.add("PyPI")
    return sorted(ecos)
