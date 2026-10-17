## Description
<!-- Provide a clear summary of what this pull request changes or introduces and why. -->

## Type of Change
<!-- Check all that apply -->
- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] ✨ New feature (new specialist agent, rule, endpoint, or UI capability)
- [ ] 📝 Documentation update (guides, specifications, ADRs)
- [ ] ⚙️ Tooling / CI / Chore (workflows, dependencies, configs)
- [ ] ♻️ Refactoring (no functional or architectural changes)

## Related Issue / Ticket
<!-- Link any related issues or discussions (e.g. Closes #123) -->

## Verification & Testing
<!-- Describe how these changes were tested locally -->
- [ ] Backend linting passed (`ruff check .` and `ruff format --check .`)
- [ ] Backend tests passed (`python -m pytest -q`)
- [ ] Frontend linting and typecheck passed (`npm run lint` and `npm run typecheck`)
- [ ] Frontend build succeeded (`npm run build`)
- [ ] Single-container Docker build verified (if modifying backend/frontend/container setup)

## Security & Risk Checklist
- [ ] Untrusted repository input is sanitized and does not introduce path traversal or SSRF risk
- [ ] Secrets or credentials are not exposed in logs or test fixtures
- [ ] Any automated agent actions require human approval and respect `DRY_RUN` defaults
- [ ] No regression introduced to existing CI workflows or deployment blueprints (`render.yaml`)

## Additional Context / Screenshots
<!-- Add any supporting screenshots, agent execution traces, or logs if applicable. -->
