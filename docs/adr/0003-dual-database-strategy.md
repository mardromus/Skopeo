# ADR-0003: Dual Database Strategy (SQLite Fallback & Neon PostgreSQL)

## Status
Accepted

## Context
Skopeo is designed to run in multiple environments:
1. **Local Development & Standalone CLI/Container:** Developers and CI runners need a zero-friction, zero-setup storage layer that works out-of-the-box without provisioning an external database container.
2. **Cloud Deployment (e.g., Render Free Tier):** On ephemeral cloud container instances, disk storage is non-persistent across sleep/restart cycles. Persisting accounts, watches, and investigation histories requires an external cloud database.
3. **Database Serverless Suspend/Resume:** Serverless PostgreSQL providers (such as Neon) put inactive compute endpoints into sleep mode to conserve resources. Continuous polling can prevent instances from idling or exhaust free tier allowances.

## Decision
We implemented a **Dual Database Storage Strategy** using SQLAlchemy:
- **Zero-Config Default (SQLite):**
  - By default, Skopeo uses a local file-based SQLite database (`sqlite:////data/skopeo.db` in container or `backend/data/skopeo.db` in development).
  - WAL mode and proper locking ensure clean concurrent writes between API requests and investigation background threads.
- **Production Persistence (Neon PostgreSQL):**
  - When the `DATABASE_URL` environment variable is configured with a PostgreSQL connection string (`postgresql://...`), Skopeo automatically targets Neon.
  - Alembic migrations run automatically on startup (`SKOPEO_RUN_MIGRATIONS=true`).
- **Sleep-Friendly Scheduler Interval:**
  - The repository watch scheduler runs checks at a configurable interval (`WATCH_SCHEDULER_INTERVAL_SECONDS=1800` by default on Render).
  - This allows free-tier serverless PostgreSQL databases to suspend cleanly between scheduled evaluations.

## Consequences

### Positive
- **Instant Developer Onboarding:** A single command (`uvicorn` or `docker run`) starts the system with no database setup required.
- **Production Durability:** Cloud deployments survive container restarts, retaining user settings, GitHub tokens, and case records.
- **Cost & Resource Efficiency:** Respects serverless database sleep cycles while maintaining scheduled watches.

### Negative
- **Dialect Differences:** SQLAlchemy models and Alembic migrations must maintain compatibility across both SQLite and PostgreSQL dialects (e.g., JSON fields, datetime handling, and foreign key constraints).
- **Concurrency Constraints on SQLite:** In high-concurrency local testing, SQLite may experience write locks, which is mitigated by running single-worker uvicorn with asynchronous background threads.
