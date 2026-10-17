---
name: Specialist Agent or Rule Proposal
about: Propose a new specialist agent or risk correlation rule for Skopeo
title: "[PROPOSAL] "
labels: ["enhancement", "agent"]
assignees: []
---

## Summary
A clear description of the new specialist agent or risk detection rule you are proposing.

## Problem Statement
What risk, antipattern, or vulnerability in modern software repositories does this agent/rule aim to identify? Why can't existing agents adequately detect this?

## Agent Specification
- **Agent Name**: [e.g. `license_compliance`, `infrastructure_as_code`, `api_breaking_changes`]
- **Domain Focus**: [e.g. Open source licensing, Terraform/CloudFormation safety, GraphQL/REST schema drift]
- **Target Files / Artifacts**: [e.g. `package.json`, `*.tf`, `openapi.yaml`]

## Evidence & Verification Strategy
1. **Initial Evidence Collection**:
   - What static tools, parsers, or heuristics does the agent use?
   - What structured evidence fields does it post to the blackboard?

2. **Red-Team Verification**:
   - How can the red-team agent challenge or attempt to disprove findings produced by this agent?
   - What constitutes an obvious false positive (e.g., test fixtures, documentation examples)?

3. **Cross-Agent Correlations**:
   - Does this finding correlate with other specialists (e.g., Security, Architecture, Performance)?

## Proposed Fixes & Human Control
- Can the recommendation agent suggest automated fixes or remediation diffs?
- What dry-run or human approval safeguards are needed?
