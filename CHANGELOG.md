# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (none yet)

## [0.3.0] — 2025-XX-XX

### Added
- **TLS support for the XML-RPC server**: set `FREECAD_MCP_TLS_CERT`
  and `FREECAD_MCP_TLS_KEY` to PEM paths; the server will then wrap
  every accepted socket in TLS (TLS 1.2 minimum). Falls back to plain
  HTTP if either env var is missing or invalid (logged loudly).
- **Bearer-token auth**: set `FREECAD_MCP_AUTH_TOKEN` to a shared
  secret; every XML-RPC request must then carry a matching
  `Authorization: Bearer <token>` header. Validation uses
  `hmac.compare_digest` (constant-time).
- **Screenshot in JPEG / WebP**: `get_view` now accepts
  `image_format="jpeg"` (or `"webp"`). FreeCAD's `saveImage` still
  produces PNG internally; the new `_transcode_screenshot` helper
  uses Pillow to convert. If Pillow is not installed, the call
  returns a clear error and the request does not crash.
- **Payload compression for large exports**: new
  `FreeCADConnection.export_object_bytes` returns the exported file
  as a gzipped base64 string when the result is larger than
  `FREECAD_MCP_GZIP_MIN` (default 64 KB). Highly compressible payloads
  shrink by 100x+; tests assert the wire size for all-zeros input.

### Tests
- 177 → 191 (+14): TLS context construction, bad cert fallback,
  bearer-token matching, case-insensitive header, hmac constant-time,
  Pillow transcoding for JPEG and WebP, compression threshold.

## [0.2.0] — 2025-XX-XX

### Added

#### Security & stability
- **Path traversal protection** in `parts_library.insert_part_from_library`:
  rejects empty, absolute, `..`-bearing, and symlink-escape inputs. Closes C1.
- **XML-RPC timeout** via `_TimeoutTransport` in `freecad_client.py`,
  configurable through `FREECAD_MCP_RPC_TIMEOUT` (default 10s). Closes
  the DoS window in C2 and the A1 hang scenario.
- **Per-operation RPC timeouts** with env-var override
  (`FREECAD_MCP_RPC_TIMEOUTS` JSON). Default: create/edit 30-60s, FEM 600s.
- **Guidelines re-scoped**: `check_code_conflict` (regex with word
  boundaries) applies only to executable strings; `check_prompt_conflict`
  handles agreement-trap phrases in free-form prompts;
  `check_path_conflict` rejects absolute/traversal paths. Operators can
  extend the blocklist via `FREECAD_MCP_BLOCKED_PATTERNS`. Closes C3
  and C4.
- **IP-filter wildcard rejection**: `0.0.0.0/0` and `::/0` are now
  refused by `validate_allowed_ips` with an explicit error. Closes M7.
- **Idempotency + cooperative cancellation**: every tracked RPC method
  now accepts an optional `request_id`. Repeated calls with the same id
  return the cached response; `cancel_request(id)` short-circuits a
  queued task before it runs (FIFO eviction, default capacity 256).
- **FEM workdir cleanup**: CalculiX scratch directories are removed
  after every run via a new `_fem_workdir` helper module. Opt out with
  `FREECAD_MCP_KEEP_FEM_WORKDIR=1` for post-mortem inspection.
- **Thread-safe lifecycle**: `start_rpc_server` / `stop_rpc_server` are
  now wrapped in an `RLock`. `stop` also calls `server_close()` so the
  listening socket is released immediately.

#### Robustness
- `process_gui_tasks` guarantees reschedule under any exception.
- `execute_code` isolates `output_buffer` per request.
- `get_active_screenshot` collapses the view-check and capture into a
  single GUI task (no race between the two steps).
- `parts_library.get_parts_list` invalidates its cache based on
  `(latest_mtime, count)` so newly-dropped FCStd files are visible
  without restart.
- `_get_settings_path` walks a fallback chain (FreeCAD user dir →
  `$XDG_CONFIG_HOME` → `$HOME/.config` → `$HOME` → temp dir) so
  read-only installations persist settings.
- `configure_logging` is idempotent.
- `@safe_operation` now applied to all 11 MCP operations.
- `_save_active_screenshot` clears the selection in a `finally` block.
- `set_object_property` reports per-property errors via a callback.

#### Tools (MCP)
- `undo(doc_name, steps=1)` — undo N transactions in a document.
- `redo(doc_name, steps=1)` — redo N previously-undone transactions.
- `save_document(doc_name, path=None)` — save a document to disk.
- `export_object(doc_name, obj_name, path, fmt=None)` — export a single
  object to STL / STEP / IGES / etc. Format inferred from the file
  extension when not given.
- `get_active_view()` — view_type, width, height, has_save_image.
- `health_check()` — uptime, queue sizes, cache stats, settings path.

#### Configuration
- `FREECAD_MCP_NO_DIRECTIVE_PREFIX=1` — drop the audit prefix from
  every text response (saves ~10 tokens/call).
- `FREECAD_MCP_MAX_INSTRUCTIONS_CHARS=8192` — cap on `mcp_instructions`
  size with a logged warning when truncated.
- `FREECAD_MCP_KEEP_FEM_WORKDIR=1` — see "FEM workdir cleanup" above.
- `FREECAD_MCP_RPC_TIMEOUT=10` — XML-RPC client timeout (seconds).
- `FREECAD_MCP_RPC_TIMEOUTS='{"create_object": 120}'` — per-op timeouts.
- `FREECAD_MCP_BLOCKED_PATTERNS='\\bctypes\\s*\\.\\s*CDLL\\s*\\('` — extend
  the dangerous-code blocklist.
- `pyproject.toml` now includes real description, keywords, trove
  classifiers, and project URLs (Homepage, Repository, Issues).

#### CI / DX
- Migrated CI to `pytest` with coverage (matrix Python 3.11/3.12/3.13,
  `--cov-fail-under=50`).
- Added `ruff` lint job and `mypy` type-check job to the CI matrix.
- Added `[project.optional-dependencies] dev = [pytest, pytest-cov,
  ruff, mypy]` to `pyproject.toml`.
- New `pytest` markers: `freecad` (integration tests requiring a real
  FreeCAD instance, skipped by default) and `slow`.

### Fixed
- XML-RPC calls to a hung FreeCAD instance no longer block forever
  (timeout via `_TimeoutTransport`).
- Two concurrent calls to `start_rpc_server` no longer create two
  listening servers (`_rpc_lock`).
- `delete_object` previously reported success even when the
  underlying call failed; now correctly reports the error.
- `safe_operation` decorator applied to all 11 operations so a
  transient RPC failure no longer surfaces as a raw traceback to
  the LLM.

### Tests
- Total: 0 → 175 unit tests across 13 test modules.
- Coverage: 0% → 56% (target 50% for addon met; 91% on `src/freecad_mcp/
  operations/core.py`, 98% on `guidelines.py`, 100% on `_fem_workdir`).
- mypy: clean on `src/`.
- ruff: clean on `src/` and `tests/`.

### Documentation
- New `CHANGELOG.md` (this file).
- New `CONTRIBUTING.md` with dev setup, lint/test commands, and PR
  process.
- New `SECURITY.md` with the threat model, the guidelines blocklist,
  and the vulnerability-reporting process.
- New `docs/IMPROVEMENT_PLAN.md` auditing the codebase and tracking
  the 6-phase remediation plan.
- `README.md` and `pyproject.toml` updated to reflect the new
  features, env vars, and tooling.

## [0.1.18] — 2024-??-??

Initial public release. See git history for the full pre-0.2.0 lineage.