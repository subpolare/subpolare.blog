# Repository Guidelines

## Project Structure & Module Organization

`subpolare/` contains Django settings, URLs, and application entry points. Feature apps are `posts/`, `comments/`, `users/`, `clickers/`, `rss/`, and `inside/`; database migrations live in each app’s `migrations/`. Shared rendering and Markdown plugins live in `common/`, with helpers in `utils/`. Templates are in `frontend/html/`; CSS, JavaScript, and vendored assets are in `frontend/static/`. Edit these source assets rather than generated copies in `tmp/static/`. Deployment configuration lives in the Docker files and `etc/nginx/`.

## Build, Test, and Development Commands

Use Python 3.12+ and Poetry, following `pyproject.toml` rather than the README’s older version summary. Local development requires PostgreSQL.

- `poetry install`: install Python dependencies.
- `make migrate`: apply database migrations.
- `make run-dev`: start Django on port 8000.
- `poetry run python3 manage.py createsuperuser`: create an administrator.
- `poetry run python3 manage.py test --settings=subpolare.test_settings`: run offline backend tests.
- `node --test frontend/tests/post-editor.test.cjs`: run frontend tests.
- `node --check frontend/static/js/post-editor.js`: check JavaScript syntax.
- `git diff --check`: check whitespace errors before submitting.

Frontend assets run directly; no npm installation or bundler is required.

## Coding Style & Naming Conventions

Follow surrounding code: four-space indentation in Python and JavaScript, `snake_case` Python functions and variables, `PascalCase` classes, and `camelCase` JavaScript functions. Keep templates organized by feature and use descriptive, hyphenated frontend filenames such as `post-editor.js`. Include Django migrations when changing models. No repository-wide formatter or linter is configured.

## Testing Guidelines

Backend tests use Django `SimpleTestCase` and `unittest.mock` in `posts/tests.py`; name methods `test_<behavior>`. Frontend tests use Node’s built-in test runner in `frontend/tests/*.test.cjs`. Add regression coverage for changed behavior, particularly permissions, Markdown rendering, and upload failures. Offline settings disable the database, so verify persistence changes separately against test PostgreSQL. No coverage threshold is configured.

## Commit & Pull Request Guidelines

History mixes plain summaries with `feat:` and `fix:` prefixes. Write short, action-oriented subjects and keep commits focused. Pull requests should explain the change, link relevant issues, list validation performed, and include screenshots for visual changes. Identify migrations and configuration changes explicitly.

## Configuration & Secrets

Use `.env.example` as a reference; never commit credentials. Poetry does not automatically load `.env`: export required `POSTGRES_*` variables. Keep `PEPIC_UPLOAD_CODE` server-side and mock external uploads in tests.
