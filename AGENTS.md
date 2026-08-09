# Repository Guidelines

## Project Structure & Module Organization

`book/` is the authoritative Chinese manuscript; chapter text lives in `book/chapter1.md` through `book/chapter10.md`, with figures in `book/images/`. Community translations live in `book-*/` and localized site content in `docs/<locale>/`. Companion experiments are grouped under `chapter1/` through `chapter10/`; consult each experiment's `README.md` before changing or running it. Shared Python plumbing, especially provider resolution, belongs in `agentbook/`. Repository-wide regression tests are in `tests/`; many experiments also keep tests beside their implementation. Build helpers and site assets live in `scripts/`, `extras/`, and `assets/`.

## Build, Test, and Development Commands

- `uv sync --locked --extra ch2 --extra dev` installs a reproducible Chapter 2 development environment; replace `ch2` with the chapter being changed.
- `uv run python chapter1/context/main.py` runs an experiment from the repository root.
- `uv run pytest tests -q` runs the shared regression suite. Run an experiment's local tests as well, for example `uv run pytest chapter10/multi-role-transfer/tests -q`.
- `uv run ruff check agentbook tests chapter2/context-compression` checks Python style for the touched scope.
- `python -m pip install -r requirements-docs.txt && mkdocs build -d site` builds the documentation site.
- `./build_epub.sh zh-CN` builds the Chinese EPUB; PDF prerequisites and commands are documented in `README.md`.

## Coding Style & Naming Conventions

Target Python 3.10+, use four-space indentation, `snake_case` for functions and files, and `PascalCase` for classes. Add type hints at shared interfaces and keep modules focused. Ruff uses a 100-column limit. Files under `chapter1/web-search-agent/tests/` are instead formatted by Black at 88 columns. Do not reformat vendored trees excluded in `pyproject.toml`. Keep Markdown links relative and store new Chinese figures in `book/images/`.

## Testing Guidelines

Use `pytest`; name files `test_*.py` and tests after observable behavior or regressions. Keep unit tests offline and deterministic—mock model, network, browser, and hardware boundaries. There is no repository-wide coverage threshold, so require relevant regression tests plus a manual experiment run when behavior depends on external systems.

## Commit & Pull Request Guidelines

Follow the history's scoped, imperative convention: `fix(providers): ...`, `feat(ch8): ...`, or `docs(ch7): ...`. Keep commits and PRs focused. PR descriptions should explain the problem and approach, list exact verification commands, link related issues, and include screenshots or rendered artifacts for visual/documentation changes. For experiment changes, record environment assumptions and reproducible evidence without committing secrets. Copy `.env.example` locally and never commit API keys or ad hoc run output.
