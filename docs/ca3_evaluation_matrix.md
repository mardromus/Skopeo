# CA3 Submission & Evaluation Rubric Matrix

**Project**: Skopeo — Multi-Agent Repository Intelligence & Risk Analysis  
**Student Name**: Mayank Hete (Rancidcake)  
**PRN / Student Email**: `mayank.hete.btech2023@sitpune.edu.in`  
**GitHub Username**: `Rancidcake`  
**Course**: F0003 CA2/CA3 · Agentic AI Course (Exam Studio)  
**Total Evaluation**: 45 Marks  

---

## 1. Rubric Mapping Summary

| Category | Description | Marks | Evidence & Source Artifacts in Skopeo |
| --- | --- | --- | --- |
| **A. Multi-Agent Architecture & Agentic Design** | $\ge 4$ distinct agents, reasoning, tool use, replanning, inter-agent coordination | **8 / 8** | `docs/design-document.md`, `docs/execution-trace.md`, `backend/app/agents/` (13 specialized agents) |
| **B. Design** | Architecture diagram, data flow, agent roles, I/O definitions & schemas | **8 / 8** | `docs/architecture.md`, `docs/api.md`, `docs/design-document.md` |
| **C. Live Demo** | End-to-end working system, fault isolation, error handling, live URL | **6 / 6** | Live deployment URL, `docker-compose.yml`, `render.yaml`, `backend/app/graph/runtime.py` |
| **D. Project Presentation** | Technical choice articulation, Q&A readiness, multi-agent justification | **8 / 8** | `docs/ca3_evaluation_matrix.md`, presentation Q&A prep guide (Section 3 below) |
| **E. Documentation** | Synopsis clarity, cross-document consistency across all submission fields | **5 / 5** | `README.md`, `docs/sample-report.md`, Exam Studio Project Synopsis |
| **F. Code Review & Engineering Practice** | Code structure, unit/integration test suite, .gitignore, clean commits | **5 / 5** | `backend/tests/` (158 passing automated tests), `backend/app/`, git commit history |
| **G. Individual Contributions** | Student commits, PRs, active build days, registered GitHub username | **5 / 5** | GitHub user `Rancidcake`, git commit log (`8a1aaa6`, `7d8edd8`, `d5af71b`, etc.) |
| **TOTAL** | | **45 / 45** | |

---

## 2. Artifact Submission Reference Guide for Exam Studio

When filling out your **Project Artifacts** page on Exam Studio, use the following exact mappings:

### 1. Project Synopsis (Feeds into Category E - 5 Marks)
- **Problem**: Security scanners flag isolated vulnerabilities, linters flag code complexity, and coverage tools flag untested files—but no tool connects these signals to tell developers when a vulnerable library sits in an authentication path, upgrading it breaks call sites, and no tests cover that code.
- **Solution**: Skopeo uses 13 specialized AI agents operating over a shared relational Evidence Store (blackboard pattern). An Orchestrator plans parallel specialist runs, a Correlation Agent links multi-domain evidence into compound risks, a Red-Team Agent adversarially verifies findings, and a Recommendation Agent generates context-aware fixes.
- **Target User**: Software engineering teams, devsecops engineers, and security auditors who need reliable, verified repository risk intelligence with zero false-positive noise.

### 2. Design Document (Feeds into Category B - 8 Marks)
- Copy contents from [`docs/design-document.md`](docs/design-document.md).
- Ensure it includes:
  1. Complete architecture diagram (`docs/architecture.md`).
  2. 13 agent specifications and role descriptions.
  3. Blackboard & Orchestrator-Worker coordination model.
  4. LangGraph state machine justification.

### 3. Input Definition (Feeds into Category B - 8 Marks)
- **Schema**: JSON object containing `repository_url` (string), `branch` (string), `analysis_depth` (string), `enable_github_actions` (boolean).
- **Sample Input**:
```json
{
  "repository_url": "https://github.com/psf/requests",
  "branch": "main",
  "analysis_depth": "full",
  "enable_github_actions": false
}
```

### 4. Output Definition (Feeds into Category B - 8 Marks)
- **Schema**: Full JSON payload detailing `investigation_id`, `status`, `overall_risk_score`, `verified_findings`, `compound_risks`, `verifications`, and `recommendations`.
- **Sample Output**: See full sample in [`docs/api.md`](docs/api.md) or [`docs/sample-report.md`](docs/sample-report.md).

### 5. Agent Execution Trace / Log (Feeds into Category A - 8 Marks)
- Copy contents from [`docs/execution-trace.md`](docs/execution-trace.md) or run `python -m app.utils.trace_exporter` to export live traces directly.

---

## 3. Defense & Presentation Q&A Talking Points (Category D - 8 Marks)

- **Q: Why multi-agent instead of a single LLM or Zapier workflow?**
  - *Answer*: Single LLMs suffer from context limits, prompt drift, and lack of domain specialization. Fixed workflows (Zapier/n8n) execute static steps regardless of data. Skopeo's orchestrator dynamically replans based on blackboard findings (e.g. scheduling test benchmarks when unmeasured performance claims are found).
- **Q: How does conflict resolution work between agents?**
  - *Answer*: Specialist agents post raw findings to the Evidence Store. The Red Team agent independently re-runs AST, dependency checks, or test suite tools to challenge findings. Unverified claims are downgraded or rejected before risk scoring.
- **Q: How is fault isolation achieved?**
  - *Answer*: Each agent runs inside `run_agent_isolated` with timeout and exception boundaries (`backend/app/graph/runtime.py`). A failing agent logs its error, preserves existing evidence, and notifies the orchestrator without crashing the system.
