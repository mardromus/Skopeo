# Contributing to Skopeo

Thank you for your interest in contributing to Skopeo! This guide outlines the development workflow, local environment setup, code style standards, and pull request procedures.

---

## Table of Contents
1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Backend Setup](#backend-setup)
   - [Frontend Setup](#frontend-setup)
3. [Running Quality Checks & Tests](#running-quality-checks--tests)
   - [Backend Linting & Tests](#backend-linting--tests)
   - [Frontend Linting & Typecheck](#frontend-linting--typecheck)
   - [Full Container Verification](#full-container-verification)
4. [Development Workflow](#development-workflow)
   - [Branch Naming](#branch-naming)
   - [Commit Guidelines](#commit-guidelines)
   - [Pull Request Process](#pull-request-process)
5. [Reporting Bugs & Feature Requests](#reporting-bugs--feature-requests)

---

## Code of Conduct

All contributors and maintainers are expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it to understand expected standards of behavior.

---

## Getting Started

### Prerequisites
- **Python**: 3.12+ (CI runs on Python 3.14)
- **Node.js**: 20+ (CI runs on Node.js 24)
- **Git**
- **Docker** (optional, recommended for end-to-end container testing)

### Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt

# Start the development server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://127.0.0.1:8000`. Fast-API auto-generated interactive documentation is at `http://127.0.0.1:8000/docs`.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm ci

# Start Vite development server
npm run dev
```

The development server will run at `http://localhost:5173`, proxying API requests to the backend on port 8000.

---

## Running Quality Checks & Tests

Before submitting changes, ensure all linting and automated tests pass locally.

### Backend Linting & Tests

Skopeo uses **Ruff** for fast Python linting and formatting, and **Pytest** for testing.

```bash
cd backend

# Check code for linting issues
ruff check .

# Check formatting
ruff format --check .

# Automatically apply formatting fixes
ruff format .

# Run the test suite (unit, integration, and reference case)
python -m pytest -q
```

### Frontend Linting & Typecheck

Skopeo's frontend uses ESLint and TypeScript strict mode.

```bash
cd frontend

# Lint JavaScript and TypeScript files
npm run lint

# Verify TypeScript types without emitting build files
npm run typecheck

# Verify production build succeeds
npm run build
```

### Full Container Verification

To run the exact single-container build used in CI:

```bash
# Build the unified container
docker build -t skopeo:local .

# Run the container
docker run -p 8000:8000 -e SKOPEO_DEMO_STEP_DELAY_MS=0 skopeo:local
```

Verify that `http://localhost:8000/api/health` returns healthy.

---

## Development Workflow

1. **Fork or create a topic branch** from `main`:
   ```bash
   git checkout -b feat/add-new-rule
   # or
   git checkout -b fix/auth-token-validation
   ```

2. **Branch Naming Conventions**:
   - `feat/*`: New features, agent rules, or endpoints.
   - `fix/*`: Bug fixes.
   - `docs/*`: Documentation improvements.
   - `refactor/*`: Code refactoring without behavioral change.
   - `test/*`: New or modified tests.

3. **Commit Guidelines**:
   Use clear, conventional commit messages:
   - `feat(agent): add license compliance risk rule`
   - `fix(scheduler): handle database sleep timeout in watch scheduler`
   - `docs(api): document websocket stream endpoint`

4. **Pull Request Process**:
   - Push your branch to GitHub and open a Pull Request against `main`.
   - Fill out the provided [Pull Request Template](.github/pull_request_template.md).
   - Ensure all GitHub Actions CI checks (`Backend · lint and tests`, `Frontend · lint and build`, `Container · build and run`) pass.
   - Request review from maintainers.

---

## Reporting Bugs & Feature Requests

- To report bugs or security vulnerabilities, refer to [SECURITY.md](SECURITY.md).
- To request features or propose new specialist agents, please open an issue using the [Agent Proposal Template](.github/ISSUE_TEMPLATE/agent_proposal.md).
