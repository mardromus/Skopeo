# Security Policy

The Skopeo team takes the security of our application, its specialist agents, and user repositories seriously. This document outlines our vulnerability disclosure process and security posture.

For a detailed analysis of our threat model, sandbox boundaries, prompt injection safeguards, and runtime controls, please see our [Architecture & Security Model](docs/security.md).

---

## Supported Versions

Only the latest release and the current `main` branch receive security patches and updates.

| Version / Branch | Supported          |
| ---------------- | ------------------ |
| `main`           | :white_check_mark: |
| < 1.0.0          | :x:                |

---

## Reporting a Vulnerability

If you believe you have found a security vulnerability in Skopeo (such as command injection, path traversal, authentication bypass, SSRF, or prompt injection boundary bypass):

1. **Do not disclose the issue publicly.** Please refrain from opening a public GitHub issue or publishing details before maintainers have investigated.
2. **Submit a report:** Contact the project maintainers via private security advisory on GitHub or email [security@skopeo.dev](mailto:security@skopeo.dev).
3. **Include the following information in your report:**
   - A description of the vulnerability and its potential impact.
   - Exact steps or a minimal repository/payload to reproduce the issue.
   - Any proposed fixes or mitigations.
   - Whether the vulnerability affects local execution, the single-container deployment, or cloud configurations.

---

## What to Expect

- **Acknowledgment:** We will acknowledge receipt of your vulnerability report within 48 hours.
- **Triage & Assessment:** Maintainers will verify the issue, assess the severity (using CVSS guidelines), and determine an appropriate remediation plan.
- **Remediation & Patch:** A fix will be developed, tested against our end-to-end test suite, and deployed to `main`.
- **Disclosure:** We will coordinate public disclosure after a patch is available and affected users have had an opportunity to update.

---

## Security Principles in Skopeo

By design, Skopeo treats both LLM outputs and analysed third-party repositories as untrusted:
- **No Shell Execution:** Commands are executed as structured argument lists with an allowlist policy.
- **Safe Path Resolution:** All filesystem accesses are validated against path traversal (`..`, symlinks).
- **Prompt Isolation:** Untrusted repository contents are enclosed within delimited, neutralized blocks to prevent prompt injection.
- **Human Approval & Dry Run:** Automated remediations are strictly draft proposals requiring explicit human confirmation.

See [docs/security.md](docs/security.md) for full architecture details.
