# Repository Guidelines

## Project Structure & Module Organization

The Python backend uses a `src` layout. Place importable code under `src/guojing/`, mirror it under `tests/`, and keep module learning notes under `docs/learning/`. Keep the root `README.md` aligned with the implemented project state and record each completed module in the learning documentation.

The legacy React management app has been removed. Do not recreate tutorial authoring, administrator authentication, or human-review features unless a new product decision explicitly restores them.

The Android client lives under `android/app/`. Keep backend protocol and network code under `data/`, immutable client models under `model/`, deterministic tutorial walking and safety rules under `execution/`, local Accessibility adapters and sanitized evidence matching under `observation/`, visible cross-app overlay ports, pure layout planning, and Android window adapters under `guidance/`, session-scoped screenshot import and pixel redaction under `privacy/`, and Compose screens plus ViewModels under feature packages in `ui/`. UI depends on repository, observation, guidance, and privacy ports rather than concrete HTTP or Android Service implementations and must not advance graph state independently of the execution engine. Accessibility collection is session-scoped: check the target package and privacy mode before reading a node tree, never retain raw node text, never traverse in `capture_paused`, and never upload `local_only` evidence. Guidance overlays must be non-touchable, disappear outside the target package or on weak evidence, never perform node actions or gestures, and account for the overlay viewport's system-bar offset when mapping normalized display coordinates. Screenshot intake accepts only user-selected `content://` image URIs, must not retain a URI grant or raw file, bounds decoded dimensions and encoded bytes, replaces selected pixels in a new local copy, and best-effort erases session buffers when replaced or dismissed; no screenshot may cross a network boundary before local sanitization and a separate explicit send decision. Keep Gradle Wrapper files and `gradle/libs.versions.toml` tracked; never commit `local.properties`, `.gradle/`, build outputs, APKs, emulator state, or screenshots.

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

The Android app requires JDK 17, Android SDK Platform 37, and Build Tools 37.0.0. Use its checked-in Wrapper; do not require a global Gradle or Kotlin installation:

- `cd android && ./gradlew testDebugUnitTest` — run JVM unit tests without a device.
- `cd android && ./gradlew lintDebug` — run Android static analysis.
- `cd android && ./gradlew assembleDebug assembleDebugAndroidTest` — build application and instrumentation-test APKs.
- `cd android && ./gradlew connectedDebugAndroidTest` — run Compose tests on a connected device or booted AVD.

Use `uv add <package>` or `uv add --dev <package>` to change declared dependencies; do not mutate the project environment with `pip install`.

## Coding Style & Naming Conventions

Follow PEP 8 with four-space indentation. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Add type hints to public interfaces and concise docstrings where intent is not evident. Ruff formatting/linting and strict mypy settings live in `pyproject.toml`.

Android Kotlin follows standard Kotlin naming and four-space continuation indentation. Keep Compose functions small and state-hoisted, expose immutable `StateFlow` from ViewModels, collect it with lifecycle awareness, and model loading, empty, content, failure, blocked, and completed states explicitly. Parse wire enums and `schema_version` fail-closed. Do not guess a tutorial branch, repeat a cycle without screen evidence, or permit financial/irreversible progress from UI callbacks. AccessibilityService may observe and explain but must not call node actions or dispatch gestures. Debug cleartext exceptions belong only in `src/debug`; release endpoints must use HTTPS.

## Testing Guidelines

Use pytest and files named `test_*.py`. Name tests after behavior, such as `test_rejects_empty_input`. Mirror source modules in the test tree. Cover normal, boundary, and failure paths, and include regression tests with bug fixes. Backend tests must not require network access, paid models, or a running database unless explicitly marked as integration tests.

Use JUnit for Android JVM tests and Compose UI Test for device behavior. JSON contracts, repositories, execution policy, and ViewModels must remain testable without Android runtime or network access. Cover every new execution block reason with a pure JVM test. Run device tests for user-visible semantics, navigation, and interaction, then inspect a real emulator screenshot for major layout changes; do not commit generated screenshots unless explicitly requested as product documentation.

## Commit & Pull Request Guidelines

Use short imperative commit messages, for example `Add input validation`. Keep commits focused. Pull requests should explain the change and motivation, list validation performed, link relevant issues, and include screenshots or recordings for user-facing changes.

When the project owner asks to commit changes, treat that as authorization to stage the agreed scope, create the commit, push the current branch to its configured remote, and verify synchronization. Do not push only when the owner explicitly requests a local-only commit.

## Security & Configuration

Never commit secrets, credentials, or `.env` files. The root `.gitignore` is a safety net, not a substitute for reviewing staged changes. Document new dependencies, required environment variables, safe defaults, and generated artifacts alongside the change that introduces them. Do not change the repository license without an explicit owner decision.
