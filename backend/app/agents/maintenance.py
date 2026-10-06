"""Maintenance Activity Agent — commit cadence, contributor concentration, stale modules,
releases and PR/issue activity from git history and GitHub metadata."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from app.agents.base import AgentContext, SpecialistAgent, Step
from app.schemas import Category, EvidenceDraft, FindingDraft, Severity, SourceType
from app.tools.github import GitHubError, GitHubRateLimited

MIN_COMMITS = 5


class MaintenanceAgent(SpecialistAgent):
    name = "maintenance_agent"
    display_name = "Maintenance Activity Agent"
    category = "maintenance"
    description = "Commit activity, contributor concentration, stale modules, release cadence, PR/issue activity."

    def plan(self, ctx: AgentContext) -> list[Step]:
        steps: list[Step] = [("analyse git history", self._git)]
        if ctx.repo.source == "github" and not ctx.settings.skopeo_offline:
            steps.append(("query GitHub repository metadata", self._github))
        else:
            ctx.limitation("GitHub metadata unavailable (offline or bundled fixture) — issues/PRs/releases not assessed")
        return steps

    def _git(self, ctx: AgentContext) -> None:
        commits = ctx.tool("get_git_log", ctx.tools.get_git_log, ctx.settings.clone_depth)
        self.commits = commits
        if len(commits) < MIN_COMMITS:
            ctx.limitation(f"INSUFFICIENT EVIDENCE: only {len(commits)} commit(s) available — activity metrics would be meaningless")
            ctx.message(
                "orchestrator",
                f"Maintenance analysis limited: {len(commits)} commit(s) of history available",
                payload={"commits": len(commits)},
            )
            return
        if len(commits) >= ctx.settings.clone_depth:
            ctx.limitation(f"History truncated at clone depth {ctx.settings.clone_depth}; older activity not considered")
        now = datetime.now(UTC)
        newest = max(c.date for c in commits)
        age_days = (now - newest.astimezone(UTC)).days
        last_year = [c for c in commits if c.date.astimezone(UTC) > now - timedelta(days=365)]
        authors = Counter(c.author for c in (last_year or commits))
        total = sum(authors.values())
        top_author, top_count = authors.most_common(1)[0]
        ctx.analyzed(f"{len(commits)} commits analysed; last commit {age_days} days ago; {len(authors)} contributor(s) in window")
        ctx.coverage["activity"] = {
            "commits": len(commits),
            "last_commit_days": age_days,
            "commits_last_year": len(last_year),
            "contributors": len(authors),
        }
        evidence = EvidenceDraft(
            source_type=SourceType.GIT,
            source="git log",
            tool="git",
            excerpt=f"{len(commits)} commits; newest {newest.date()} ({commits[0].sha[:10]}): {commits[0].subject[:120]}",
            confidence=0.95,
            data={"commits": len(commits), "newest": newest.isoformat()},
        )
        if age_days > 365:
            ctx.publish(
                FindingDraft(
                    category=Category.MAINTENANCE,
                    rule_id="maintenance.inactive",
                    title=f"No commits for {age_days} days",
                    description=f"The most recent commit on the analysed branch is from {newest.date()}.",
                    severity=Severity.HIGH if age_days > 730 else Severity.MEDIUM,
                    subject="maintenance:activity",
                    affected_files=[],
                    affected_components=["project"],
                    attributes={"last_commit_days": age_days},
                    reasoning_summary="Derived from git log of the cloned branch.",
                    recommended_action="Confirm the project is maintained before depending on it; plan ownership.",
                ),
                [evidence],
            )
        if total >= 20 and top_count / total >= 0.8:
            ctx.publish(
                FindingDraft(
                    category=Category.MAINTENANCE,
                    rule_id="maintenance.bus_factor",
                    title=f"One contributor authored {top_count / total:.0%} of recent commits",
                    description=f"{top_count} of {total} commits in the analysis window come from a single author ({len(authors)} contributor(s) total).",
                    severity=Severity.MEDIUM,
                    subject="maintenance:contributors",
                    affected_files=[],
                    affected_components=["project"],
                    attributes={"top_share": round(top_count / total, 3), "contributors": len(authors)},
                    reasoning_summary="Author concentration computed from git log (names only; emails are not stored).",
                    recommended_action="Spread ownership: reviews, docs and a second maintainer.",
                ),
                [evidence],
            )
        last_touch: dict[str, datetime] = {}
        for c in commits:
            for f in c.files:
                top = f.split("/")[0] if "/" in f else "(root)"
                if top not in last_touch or c.date > last_touch[top]:
                    last_touch[top] = c.date
        if age_days < 90:
            stale = sorted(d for d, when in last_touch.items() if (now - when.astimezone(UTC)).days > 540 and d != "(root)")
            if stale:
                ctx.publish(
                    FindingDraft(
                        category=Category.MAINTENANCE,
                        rule_id="maintenance.stale_module",
                        title=f"{len(stale)} top-level module(s) untouched for 18+ months while the project is active",
                        description=", ".join(stale[:10]),
                        severity=Severity.LOW,
                        subject="maintenance:stale_modules",
                        affected_files=[],
                        affected_components=stale[:10],
                        attributes={"modules": stale},
                        reasoning_summary="Per-directory last-modified dates from git numstat.",
                        recommended_action="Confirm these modules are still needed and owned.",
                    ),
                    [evidence],
                )

    def _github(self, ctx: AgentContext) -> None:
        gh = ctx.services.github
        name = ctx.repo.full_name
        try:
            repo = ctx.tool("github_repo", gh.get_repo, name)
        except GitHubRateLimited as exc:
            ctx.limitation(f"GitHub rate limit reached ({exc}); metadata partially unavailable")
            return
        except GitHubError as exc:
            ctx.limitation(f"GitHub metadata unavailable: {exc}")
            return
        meta = {k: repo.get(k) for k in ("archived", "open_issues_count", "pushed_at", "stargazers_count", "forks_count", "default_branch")}
        ctx.coverage["github"] = meta
        gh_ev = EvidenceDraft(
            source_type=SourceType.GITHUB,
            source=f"GET /repos/{name}",
            tool="github-api",
            excerpt=str(meta)[:500],
            raw_reference=f"https://github.com/{name}",
            confidence=0.95,
        )
        if repo.get("archived"):
            ctx.publish(
                FindingDraft(
                    category=Category.MAINTENANCE,
                    rule_id="maintenance.archived",
                    title="Repository is archived on GitHub",
                    description="Archived repositories receive no fixes, including security fixes.",
                    severity=Severity.HIGH,
                    subject="maintenance:activity",
                    affected_files=[],
                    affected_components=["project"],
                    attributes={"archived": True},
                    reasoning_summary="GitHub API reports archived=true.",
                    recommended_action="Migrate to a maintained fork or alternative.",
                ),
                [gh_ev],
            )
        try:
            releases = ctx.tool("github_releases", gh.list_releases, name)
            pulls = ctx.tool("github_pulls", gh.list_pulls, name)
        except GitHubError as exc:
            ctx.limitation(f"GitHub releases/PRs unavailable: {exc}")
            return
        now = datetime.now(UTC)
        if releases:
            latest = max(datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")) for r in releases if r.get("published_at"))
            days = (now - latest).days
            ctx.coverage["github"]["last_release_days"] = days
            if days > 730 and getattr(self, "commits", None) and (now - max(c.date for c in self.commits).astimezone(UTC)).days < 180:
                ctx.publish(
                    FindingDraft(
                        category=Category.MAINTENANCE,
                        rule_id="maintenance.no_recent_release",
                        title=f"No release in {days} days despite recent commits",
                        description="Fixes on the default branch are not reaching users through releases.",
                        severity=Severity.LOW,
                        subject="maintenance:releases",
                        affected_files=[],
                        affected_components=["project"],
                        attributes={"last_release_days": days},
                        reasoning_summary="GitHub releases API vs git activity.",
                        recommended_action="Establish a regular release cadence.",
                    ),
                    [
                        EvidenceDraft(
                            source_type=SourceType.GITHUB,
                            source=f"GET /repos/{name}/releases",
                            tool="github-api",
                            excerpt=f"latest release {latest.date()}",
                            confidence=0.9,
                        )
                    ],
                )
        else:
            ctx.analyzed("No GitHub releases published")
        stale_prs = [
            p
            for p in pulls
            if p.get("state") == "open" and (now - datetime.fromisoformat(p["updated_at"].replace("Z", "+00:00"))).days > 180
        ]
        states = defaultdict(int)
        for p in pulls:
            states["merged" if p.get("merged_at") else p.get("state", "unknown")] += 1
        ctx.coverage["github"]["recent_pull_requests"] = dict(states)
        if len(stale_prs) >= 5:
            ctx.publish(
                FindingDraft(
                    category=Category.MAINTENANCE,
                    rule_id="maintenance.stale_pull_requests",
                    title=f"{len(stale_prs)} open pull requests without activity for 6+ months",
                    description=", ".join(f"#{p['number']}" for p in stale_prs[:10]),
                    severity=Severity.LOW,
                    subject="maintenance:pulls",
                    affected_files=[],
                    affected_components=["project"],
                    attributes={"stale_prs": [p["number"] for p in stale_prs]},
                    reasoning_summary="GitHub pulls API (most recently updated 30).",
                    recommended_action="Triage or close stale pull requests.",
                ),
                [
                    EvidenceDraft(
                        source_type=SourceType.GITHUB,
                        source=f"GET /repos/{name}/pulls",
                        tool="github-api",
                        excerpt=f"{len(stale_prs)} stale open PRs",
                        confidence=0.9,
                    )
                ],
            )
