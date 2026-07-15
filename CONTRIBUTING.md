# Contributing

Thanks for your interest in improving `mcp-freecad`! This document covers
the development setup, the tools we run, and the PR process.

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/yuri-schmaltz/mcp-freecad
cd mcp-freecad

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# 3. Install runtime + dev dependencies
pip install -e ".[dev]"

# 4. Run the test suite
pytest                      # ~175 tests, ~5s
pytest -m "not freecad"     # default: skip integration tests

# 5. Lint and type-check
ruff check src/ tests/
mypy src/
```

## Code layout

```
src/freecad_mcp/                 # MCP server package (stdlib-only deps)
  server.py                     # FastMCP wiring, 12+ tool definitions
  operations/core.py            # business logic, one function per tool
  freecad_client.py              # XML-RPC client with timeout
  guidelines.py                 # code/prompt/path conflict guards
  responses.py                  # text/json/screenshot helpers
  utils.py                      # safe_operation decorator
  server_state.py               # shared state

addon/FreeCADMCP/rpc_server/    # FreeCAD-side RPC server (runs inside FreeCAD)
  rpc_server.py                 # XML-RPC endpoint + GUI dispatch
  parts_library.py              # parts library access
  serialize.py                  # object -> dict serialiser
  _fem_workdir.py               # FEM scratch dir cleanup
  _request_tracking.py          # idempotency + cooperative cancel

tests/                          # 175 unit tests, no FreeCAD required
docs/IMPROVEMENT_PLAN.md        # the live audit + remediation plan
```

## Conventions

- **Python 3.12+** is the supported target.
- **Public API changes** are tracked in `CHANGELOG.md` under the
  `[Unreleased]` section until the next release.
- **Tests are mandatory** for new code. Mock-heavy tests are fine —
  the codebase has 175 such tests and they catch real regressions
  every week.
- **Lint clean** (`ruff check`) and **type clean** (`mypy src/`) are
  both required to pass CI.
- **Security-relevant changes** (anything in `guidelines.py`,
  `parts_library.py`, `validate_allowed_ips`, the XML-RPC transport,
  or the `execute_code` path) require a test that proves the fix and
  an entry in `CHANGELOG.md`.

## Branching & PRs

1. Branch off `main` with a descriptive name:
   `fix/<one-word-summary>`, `feat/<one-word-summary>`,
   `chore/<one-word-summary>`, `docs/<one-word-summary>`.
2. Make focused commits; prefer several small commits over one giant
   one. Each commit message should be a complete sentence explaining
   *why* the change was made.
3. Open a PR against `main`. CI must pass before review.
4. PRs that touch the security-sensitive surfaces listed above must
   also include a `CHANGELOG.md` entry under `[Unreleased]`.
5. Squash-merge or rebase-merge; the maintainer will pick.

## Release process

1. Update `CHANGELOG.md`: move the `[Unreleased]` block to a dated
   versioned section.
2. Bump the version in `pyproject.toml` and `src/freecad_mcp/__init__.py`
   (if present).
3. Tag the release: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
4. CI publishes to PyPI on tag push (`.github/workflows/publish.yml`,
   when configured).

## Reporting bugs

Use the [GitHub issue tracker](https://github.com/yuri-schmaltz/mcp-freecad/issues).
For security issues, see [SECURITY.md](SECURITY.md) instead.