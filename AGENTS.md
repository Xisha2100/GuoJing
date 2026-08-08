# Repository Guidelines

## Project Structure & Module Organization

The Python backend uses a `src` layout. Place importable code under `src/guojing/`, mirror it under `tests/`, and keep module learning notes under `docs/learning/`. Keep the root `README.md` aligned with the implemented project state and record each completed module in the learning documentation.

The React management app lives under `web/admin/`. Keep browser API adapters under `src/api/`, feature components in feature folders such as `src/auth/` and `src/workspaces/`, and colocate frontend behavior tests as `*.test.ts` or `*.test.tsx`. Generated `dist`, coverage, Playwright, and TypeScript build-info artifacts remain ignored; track `web/admin/pnpm-lock.yaml`.

Keep HTTP adapters under `src/guojing/api/`, use cases and ports under `src/guojing/application/`, cross-cutting configuration under `src/guojing/core/`, framework-independent business rules under `src/guojing/domain/`, and external adapters under `src/guojing/infrastructure/`. Dependencies point inward: domain modules must not import FastAPI, SQLAlchemy, storage clients, or agent frameworks, and application services depend on repository protocols rather than concrete adapters. Prefer immutable domain value objects and deterministic functions whose tests require no I/O. Do not create speculative database, agent, or infrastructure layers before a concrete use case needs them. Keep root-level files for project-wide documentation and configuration.

The root `.gitignore` is the single project-wide source for generated files, local configuration, secrets, Python, Android, Gradle, Node.js, and IDE artifacts. Keep lockfiles such as `uv.lock` tracked.

## Build, Test, and Development Commands

The backend requires Python 3.12.13 and uv. Keep working setup and validation commands synchronized between this guide and the root `README.md`.

- `uv sync` — create/update `.venv` from `pyproject.toml` and `uv.lock`.
- `uv run alembic upgrade head` — migrate the configured database before starting the API.
- `uv run uvicorn guojing.main:app --reload` — run the local API on port 8000.
- `uv run pytest` — run the backend test suite.
- `uv run ruff check .` — run lint and import-order checks.
- `uv run ruff format --check .` — verify formatting without changing files.
- `uv run mypy` — run strict static type checks.
- `uv lock --check` — verify that `uv.lock` matches `pyproject.toml`.
- `git diff --check` — detect whitespace errors before committing.

The management web app requires Node.js 22.12 or newer and pnpm 11:

- `pnpm --dir web/admin install --frozen-lockfile` — reproduce frontend dependencies.
- `pnpm --dir web/admin dev` — run Vite on port 5173 and proxy `/api` to port 8000.
- `pnpm --dir web/admin check` — run Prettier, ESLint, TypeScript, Vitest, and production build checks.
- `pnpm --dir web/admin build` — emit production static assets under ignored `web/admin/dist/`.

Use `uv add <package>` or `uv add --dev <package>` to change declared dependencies; do not mutate the project environment with `pip install`.

## Coding Style & Naming Conventions

Follow PEP 8 with four-space indentation. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Add type hints to public interfaces and concise docstrings where intent is not evident. Ruff formatting/linting and strict mypy settings live in `pyproject.toml`.

Frontend TypeScript is strict. Use `PascalCase` for React components, keep network and Cookie behavior inside the typed API client, use semantic HTML and accessible labels, and do not duplicate CSRF logic in feature components. Prettier and ESLint configuration live under `web/admin/`.

## Testing Guidelines

Use pytest and files named `test_*.py`. Name tests after behavior, such as `test_rejects_empty_input`. Mirror source modules in the test tree. Cover normal, boundary, and failure paths, and include regression tests with bug fixes. Backend tests must not require network access, paid models, or a running database unless explicitly marked as integration tests.

Use Vitest and React Testing Library for frontend behavior. Test observable user flows and HTTP contracts rather than component implementation details. Real-browser Playwright checks are a local integration/visual gate and must use temporary data; do not commit their generated artifacts.

## Commit & Pull Request Guidelines

Use short imperative commit messages, for example `Add input validation`. Keep commits focused. Pull requests should explain the change and motivation, list validation performed, link relevant issues, and include screenshots or recordings for user-facing changes.

When the project owner asks to commit changes, treat that as authorization to stage the agreed scope, create the commit, push the current branch to its configured remote, and verify synchronization. Do not push only when the owner explicitly requests a local-only commit.

## Security & Configuration

Never commit secrets, credentials, or `.env` files. The root `.gitignore` is a safety net, not a substitute for reviewing staged changes. Document new dependencies, required environment variables, safe defaults, and generated artifacts alongside the change that introduces them. Do not change the repository license without an explicit owner decision.
