"""Run the bundled demo investigation from the command line (no API / UI needed).

    python scripts/run_demo.py [--no-fault] [--markdown out.md] [--json out.json]

Prints the execution trace and a summary; optionally exports the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.observability import configure_logging  # noqa: E402
from app.schemas.investigation import DemoInvestigationCreate  # noqa: E402
from app.services.investigation_service import InvestigationService  # noqa: E402
from app.services.report import build_markdown, build_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fault", action="store_true", help="disable the controlled performance-agent failure")
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging("WARNING", json_output=False)
    init_db()
    svc = InvestigationService(settings)
    iid = svc.create_demo(DemoInvestigationCreate(fault_injection=not args.no_fault, step_delay_ms=0))
    svc.run_sync(iid)
    store = svc.store
    if not args.quiet:
        for e in store.list_events(iid):
            print(f"{e.timestamp.strftime('%H:%M:%S.%f')[:12]}  {e.sender:>24} -> {e.receiver:<22} {e.event_type:<24} {e.message[:150]}")
    report = build_report(store, iid, include_events=False)
    s = report["execution_summary"]
    print("\n=== SUMMARY ===")
    print(f"investigation {iid} status={report['status']} overall_risk={report['overall_risk']}")
    print(
        f"findings={s['findings']} verified={s['verified']} rejected={s['rejected']} insufficient={s['insufficient_evidence']} unchallenged={s['unchallenged']}"
    )
    print(
        f"agent_runs={s['agent_runs']} failures={s['agent_failures']} retries={s['retries']} follow_ups={s['follow_ups']} replans={s['replans']} parallelism={s['parallelism']} duration={s['duration_seconds']}s"
    )
    print("coverage:", {a: c["status"] for a, c in report["coverage"]["agents"].items()})
    for r in report["risks"]:
        print(f"  {r['priority']} {r['score']:>5}  {r['title'][:110]}")
    for f in report["rejected_findings"]:
        print(f"  REJECTED: {f['title']}")
    for f in report["insufficient_evidence_findings"]:
        print(f"  INSUFFICIENT EVIDENCE: {f['title']}")
    if args.markdown:
        args.markdown.write_text(build_markdown(store, iid), encoding="utf-8")
        print(f"markdown -> {args.markdown}")
    if args.json:
        args.json.write_text(json.dumps(build_report(store, iid), indent=2, default=str), encoding="utf-8")
        print(f"json -> {args.json}")
    svc.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
