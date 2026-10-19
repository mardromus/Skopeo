# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Architecture Decision Records (`docs/adr/`) documenting blackboard architecture, red-team verification, and dual-database strategy.
- Specialist agent authoring and extension tutorial (`docs/adding-an-agent.md`).
- REST API cURL cheat sheet (`docs/api-cheat-sheet.md`).
- Community health standards: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and root `SECURITY.md`.
- GitHub issue templates for bug reporting and specialist agent proposals, along with a pull request verification checklist.

### Changed
- Strengthened verification constraints: live LLM verification agents may only request evidence when checks fail or yield inconclusive findings.
- Guardrails ensuring orchestrator reviews cannot finalize an investigation without formal risk assessment.

---

## [1.0.0] - 2026-10-15

### Added
- **Multi-Agent Orchestration**:
  - Dynamic Orchestrator Agent built on LangGraph with adaptive replanning, retries, and budget caps.
  - Eight domain specialist agents: Security, Dependency Health, Code Quality, API Compatibility, Test Reliability, License Compliance, Maintenance Activity, and Performance.
  - Correlation Agent connecting related findings across specialist domains into compound risks.
  - Adversarial Red-Team Verification Agent testing and rejecting false positives (e.g. test fixtures, dead code).
  - Risk Assessment (P0–P4 scoring) and Recommendation agents proposing targeted remediation.
- **Human-in-the-Loop & Safety**:
  - Human review approval gate for any proposed external actions (GitHub issues / draft PRs).
  - Default `DRY_RUN=true` configuration preventing accidental external mutations.
  - Strict command execution allowlist with no shell invocations and path-traversal safeguards.
  - Redaction of sensitive tokens and secrets across execution logs, events, and reports.
- **Repository Monitoring & Notifications**:
  - Scheduled watch engine checking repositories for upstream drift and dependency updates.
  - Multi-channel delivery: email (SMTP, Brevo, Resend) and signed webhooks (Slack, Discord, generic HTTPS).
- **Authentication & Accounts**:
  - Firebase JWT verification for Google sign-in.
  - GitHub OAuth integration with encrypted access token storage (`SKOPEO_SECRET_KEY`).
- **Interactive User Interface**:
  - Responsive React 19 + Vite dashboard featuring the 8-blade aperture risk visualization.
  - Detailed case explorer, agent run inspect tabs, evidence timelines, and report exports (JSON & Markdown).
- **Deployment & Infrastructure**:
  - Single-container Docker deployment where FastAPI serves the built UI and API on a single port.
  - Blueprint specification for zero-config Render cloud deployment (`render.yaml`).
  - Zero-config local SQLite storage with optional Neon PostgreSQL persistence.
  - End-to-end reference demo test suite exercising all specialist agents against a bundled vulnerable repository.
