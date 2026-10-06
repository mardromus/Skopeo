"""Build ``app/data/offline_snapshot.json`` from the real OSV.dev and PyPI APIs.

The snapshot lets demo / CI / offline runs use genuine advisory data without network access.
It is regenerated, never hand-edited:

    python scripts/build_offline_snapshot.py [extra-package==version ...]

By default it covers every dependency declared in examples/vulnerable-demo-repo/requirements.txt.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.tools.advisories import pypi_license  # noqa: E402

DEMO_REQUIREMENTS = BACKEND.parent / "examples" / "vulnerable-demo-repo" / "requirements.txt"
OUT = BACKEND / "app" / "data" / "offline_snapshot.json"


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: Path) -> list[tuple[str, str | None]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)\s*(==\s*([A-Za-z0-9.+!_-]+))?", line)
        if m:
            out.append((m.group(1), m.group(3)))
    return out


def trim(record: dict) -> dict:
    keep = {k: record.get(k) for k in ("id", "aliases", "summary", "published", "modified", "database_specific", "affected")}
    keep["references"] = (record.get("references") or [])[:3]
    keep["affected"] = [{"package": a.get("package"), "ranges": a.get("ranges")} for a in (record.get("affected") or [])]
    return keep


def main(extra: list[str]) -> None:
    packages = parse_requirements(DEMO_REQUIREMENTS)
    for item in extra:
        name, _, version = item.partition("==")
        packages.append((name, version or None))
    snapshot: dict = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "description": "Real responses from api.osv.dev and pypi.org, trimmed. Regenerate with scripts/build_offline_snapshot.py.",
        "osv": {"PyPI": {}},
        "registry": {"PyPI": {}},
    }
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for name, version in packages:
            key = normalize(name)
            pypi = client.get(f"https://pypi.org/pypi/{key}/json").json()
            info, releases = pypi["info"], pypi["releases"]

            def released(v: str | None, releases: dict = releases) -> str | None:
                files = releases.get(v or "", []) or []
                return min((f["upload_time_iso_8601"] for f in files if f.get("upload_time_iso_8601")), default=None)

            lic = pypi_license(info)
            snapshot["registry"]["PyPI"][key] = {
                "name": info["name"],
                "latest_version": info["version"],
                "latest_release_date": released(info["version"]),
                "license": lic,
                "release_dates": {v: released(v) for v in {version, info["version"]} if v},
            }
            if version:
                resp = client.post(
                    "https://api.osv.dev/v1/query",
                    json={"package": {"name": key, "ecosystem": "PyPI"}, "version": version},
                )
                resp.raise_for_status()
                vulns = [trim(v) for v in resp.json().get("vulns", [])]
                snapshot["osv"]["PyPI"].setdefault(key, {})[version] = vulns
                print(f"{name}=={version}: {len(vulns)} OSV records")
            else:
                print(f"{name}: unpinned, registry metadata only")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
