"""Vulnerability (OSV.dev) and package-registry (PyPI / npm) lookups.

Online mode queries the real services. Offline / demo mode reads
``app/data/offline_snapshot.json`` — a snapshot of *real* OSV and PyPI responses produced by
``scripts/build_offline_snapshot.py``. Nothing here is ever invented: a package that is not in
the snapshot yields status ``unavailable`` ("INSUFFICIENT EVIDENCE"), never an empty "clean" result.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from app.config import Settings
from app.observability import get_logger
from app.tools.manifests import Dependency

log = get_logger("tools.advisories")

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "offline_snapshot.json"
_OSV_SEVERITY = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low"}


@dataclass
class Advisory:
    id: str
    aliases: list[str]
    summary: str
    severity: str  # critical|high|medium|low|unknown
    fixed_versions: list[str]
    published: str | None
    url: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class AdvisoryLookup:
    status: str  # ok | unavailable | unpinned | unsupported
    advisories: list[Advisory] = field(default_factory=list)
    source: str = ""
    detail: str = ""


@dataclass
class PackageInfo:
    status: str  # ok | unavailable | unsupported
    latest_version: str | None = None
    latest_release_date: str | None = None
    pinned_release_date: str | None = None
    license: str | None = None
    source: str = ""
    detail: str = ""


_snapshot_cache: dict[str, Any] | None = None
_snapshot_lock = threading.Lock()


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    global _snapshot_cache
    with _snapshot_lock:
        if _snapshot_cache is None:
            _snapshot_cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return _snapshot_cache


def parse_version(value: str | None, ecosystem: str) -> tuple | Version | None:
    if not value:
        return None
    if ecosystem == "PyPI":
        try:
            return Version(value)
        except InvalidVersion:
            return None
    m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def version_gap(current: str | None, latest: str | None, ecosystem: str) -> str | None:
    """Classify how far ``current`` lags ``latest``: major | minor | patch | current | None."""
    a, b = parse_version(current, ecosystem), parse_version(latest, ecosystem)
    if a is None or b is None:
        return None
    if isinstance(a, Version) and isinstance(b, Version):
        ra, rb = (a.release + (0, 0, 0))[:3], (b.release + (0, 0, 0))[:3]
    else:
        ra, rb = a, b  # type: ignore[assignment]
    if ra >= rb:
        return "current"
    if ra[0] < rb[0]:
        return "major"
    if ra[1] < rb[1]:
        return "minor"
    return "patch"


def _group_records(records: list[dict[str, Any]], package: str, source: str) -> list[Advisory]:
    """Merge OSV records that describe the same vulnerability (GHSA / PYSEC / CVE aliases)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    by_id = {r["id"]: r for r in records}
    for r in records:
        for alias in r.get("aliases", []) or []:
            union(r["id"], alias)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        groups.setdefault(find(r["id"]), []).append(r)
    advisories: list[Advisory] = []
    for members in groups.values():
        members.sort(key=lambda r: (0 if (r.get("database_specific") or {}).get("severity") else 1, 0 if r["id"].startswith("GHSA") else 1))
        rep = members[0]
        aliases = sorted({a for m in members for a in ([m["id"]] + (m.get("aliases") or [])) if a != rep["id"]})
        sev_raw = ((rep.get("database_specific") or {}).get("severity") or "").upper()
        fixed: set[str] = set()
        for m in members:
            for aff in m.get("affected", []) or []:
                pkg = (aff.get("package") or {}).get("name", "")
                if re.sub(r"[-_.]+", "-", pkg).lower() != re.sub(r"[-_.]+", "-", package).lower():
                    continue
                for rng in aff.get("ranges", []) or []:
                    if rng.get("type") not in ("ECOSYSTEM", "SEMVER"):
                        continue
                    for ev in rng.get("events", []) or []:
                        if "fixed" in ev:
                            fixed.add(ev["fixed"])
        refs = rep.get("references") or []
        url = next((r.get("url") for r in refs if r.get("type") in ("ADVISORY", "WEB")), None) or (refs[0].get("url") if refs else None)
        advisories.append(
            Advisory(
                id=rep["id"],
                aliases=aliases,
                summary=(rep.get("summary") or next((m.get("summary") for m in members if m.get("summary")), "") or "")[:300],
                severity=_OSV_SEVERITY.get(sev_raw, "unknown"),
                fixed_versions=sorted(fixed),
                published=rep.get("published"),
                url=url,
                source=source,
            )
        )
    _ = by_id
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    advisories.sort(key=lambda a: (order.get(a.severity, 5), a.id))
    return advisories


class AdvisoryClient:
    def __init__(self, settings: Settings, offline: bool | None = None) -> None:
        self.settings = settings
        self.offline = settings.skopeo_offline if offline is None else offline
        self._cache: dict[str, AdvisoryLookup] = {}

    def lookup(self, dep: Dependency) -> AdvisoryLookup:
        if dep.ecosystem not in ("PyPI", "npm", "Go", "crates.io", "Maven"):
            return AdvisoryLookup(status="unsupported", detail=f"ecosystem {dep.ecosystem} not supported")
        if not dep.version:
            return AdvisoryLookup(status="unpinned", detail="no exact version; cannot match advisories reliably")
        key = f"{dep.ecosystem}:{dep.name}@{dep.version}"
        if key in self._cache:
            return self._cache[key]
        result = self._offline(dep) if self.offline else self._online(dep)
        self._cache[key] = result
        return result

    def _offline(self, dep: Dependency) -> AdvisoryLookup:
        snap = load_snapshot()
        retrieved = snap.get("generated_at", "unknown date")
        source = f"offline snapshot of osv.dev (retrieved {retrieved})"
        versions = ((snap.get("osv") or {}).get(dep.ecosystem) or {}).get(dep.name)
        if versions is None or dep.version not in versions:
            return AdvisoryLookup(status="unavailable", source=source, detail="package/version not present in offline snapshot")
        return AdvisoryLookup(status="ok", advisories=_group_records(versions[dep.version], dep.name, source), source=source)

    def _online(self, dep: Dependency) -> AdvisoryLookup:
        source = "osv.dev API"
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    "https://api.osv.dev/v1/query",
                    json={
                        "package": {"name": dep.display_name if dep.ecosystem != "PyPI" else dep.name, "ecosystem": dep.ecosystem},
                        "version": dep.version,
                    },
                )
            resp.raise_for_status()
            records = resp.json().get("vulns", []) or []
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("osv lookup failed", extra={"data": {"package": dep.name, "error": str(exc)[:200]}})
            return AdvisoryLookup(status="unavailable", source=source, detail=f"osv.dev unreachable: {type(exc).__name__}")
        return AdvisoryLookup(status="ok", advisories=_group_records(records, dep.name, source), source=source)


class RegistryClient:
    def __init__(self, settings: Settings, offline: bool | None = None) -> None:
        self.settings = settings
        self.offline = settings.skopeo_offline if offline is None else offline
        self._cache: dict[str, PackageInfo] = {}

    def package_info(self, dep: Dependency) -> PackageInfo:
        if dep.ecosystem not in ("PyPI", "npm"):
            return PackageInfo(status="unsupported", detail=f"registry metadata for {dep.ecosystem} not implemented")
        key = f"{dep.ecosystem}:{dep.name}@{dep.version}"
        if key not in self._cache:
            self._cache[key] = self._offline(dep) if self.offline else self._online(dep)
        return self._cache[key]

    def _offline(self, dep: Dependency) -> PackageInfo:
        snap = load_snapshot()
        source = f"offline snapshot of {'pypi.org' if dep.ecosystem == 'PyPI' else 'registry.npmjs.org'} (retrieved {snap.get('generated_at', 'unknown')})"
        meta = ((snap.get("registry") or {}).get(dep.ecosystem) or {}).get(dep.name)
        if not meta:
            return PackageInfo(status="unavailable", source=source, detail="package not present in offline snapshot")
        return PackageInfo(
            status="ok",
            latest_version=meta.get("latest_version"),
            latest_release_date=meta.get("latest_release_date"),
            pinned_release_date=(meta.get("release_dates") or {}).get(dep.version or ""),
            license=meta.get("license"),
            source=source,
        )

    def _online(self, dep: Dependency) -> PackageInfo:
        try:
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                if dep.ecosystem == "PyPI":
                    resp = client.get(f"https://pypi.org/pypi/{dep.name}/json")
                    resp.raise_for_status()
                    data = resp.json()
                    info = data.get("info", {})
                    releases = data.get("releases", {})

                    def released(v: str | None) -> str | None:
                        files = releases.get(v or "", []) or []
                        return min((f.get("upload_time_iso_8601") for f in files if f.get("upload_time_iso_8601")), default=None)

                    return PackageInfo(
                        status="ok",
                        latest_version=info.get("version"),
                        latest_release_date=released(info.get("version")),
                        pinned_release_date=released(dep.version),
                        license=pypi_license(info),
                        source="pypi.org JSON API",
                    )
                resp = client.get(f"https://registry.npmjs.org/{dep.name}")
                resp.raise_for_status()
                data = resp.json()
                latest = (data.get("dist-tags") or {}).get("latest")
                times = data.get("time") or {}
                lic = data.get("license")
                return PackageInfo(
                    status="ok",
                    latest_version=latest,
                    latest_release_date=times.get(latest or ""),
                    pinned_release_date=times.get(dep.version or ""),
                    license=lic if isinstance(lic, str) else (lic or {}).get("type"),
                    source="registry.npmjs.org",
                )
        except (httpx.HTTPError, ValueError) as exc:
            return PackageInfo(status="unavailable", source="registry", detail=f"registry unreachable: {type(exc).__name__}")


def pypi_license(info: dict[str, Any]) -> str | None:
    """Best license expression from PyPI metadata: SPDX expression, else a recognisable license
    field, else the OSI classifiers (joined with OR)."""
    from app.tools.licenses import normalize_expression

    if info.get("license_expression"):
        return info["license_expression"]
    lic = info.get("license")
    if lic and len(lic) < 60 and "\n" not in lic and normalize_expression(lic):
        return lic
    classifiers = [c.rsplit("::", 1)[-1].strip() for c in info.get("classifiers", []) or [] if c.startswith("License :: OSI Approved :: ")]
    if classifiers:
        return " OR ".join(classifiers)
    return lic[:60] if lic else None


def age_in_days(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - when).days
