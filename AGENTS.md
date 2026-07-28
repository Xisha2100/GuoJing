# Repository Guidelines

## Project Structure & Module Organization

The Python backend uses a `src` layout. Place importable code under `src/guojing/`, mirror it under `tests/`, and keep module learning notes under `docs/learning/`. The initial commit contains a short `README.md`, a `LICENSE`, and a Python-oriented `.gitignore`; these files are currently absent from the working tree. Do not restore or replace those user deletions as part of unrelated changes.

Keep HTTP adapters under `src/guojing/api/` and cross-cutting configuration under `src/guojing/core/`. Do not create speculative database, agent, or infrastructure layers before a concrete use case needs them. Keep root-level files for project-wide documentation and configuration.

The scoped `src/.gitignore` and `tests/.gitignore` files exclude generated Python bytecode while the root `.gitignore` remains intentionally absent.

## Build, Test, and Development Commands

The backend requires Python 3.12.13 and uv. The root `README.md` remains intentionally absent because of the pre-existing user deletion, so the same commands are currently recorded here and in `docs/learning/00-backend-foundation.md`.

- `uv sync` — create/update `.venv` from `pyproject.toml` and `uv.lock`.
- `uv run uvicorn guojing.main:app --reload` — run the local API on port 8000.
- `uv run pytest` — run the backend test suite.
- `uv run ruff check .` — run lint and import-order checks.
- `uv run ruff format --check .` — verify formatting without changing files.
- `uv run mypy` — run strict static type checks.
- `uv lock --check` — verify that `uv.lock` matches `pyproject.toml`.
- `git diff --check` — detect whitespace errors before committing.

Use `uv add <package>` or `uv add --dev <package>` to change declared dependencies; do not mutate the project environment with `pip install`.

## Coding Style & Naming Conventions

Follow PEP 8 with four-space indentation. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Add type hints to public interfaces and concise docstrings where intent is not evident. Ruff formatting/linting and strict mypy settings live in `pyproject.toml`.

## Testing Guidelines

Use pytest and files named `test_*.py`. Name tests after behavior, such as `test_rejects_empty_input`. Mirror source modules in the test tree. Cover normal, boundary, and failure paths, and include regression tests with bug fixes. Backend tests must not require network access, paid models, or a running database unless explicitly marked as integration tests.

## Commit & Pull Request Guidelines

The history currently contains only `Initial commit`; follow its short, imperative style, for example `Add input validation`. Keep commits focused. Pull requests should explain the change and motivation, list validation performed, link relevant issues, and include screenshots or recordings for user-facing changes.

## Security & Configuration

Never commit secrets, credentials, or `.env` files. Document new dependencies, required environment variables, safe defaults, and generated artifacts alongside the change that introduces them.
