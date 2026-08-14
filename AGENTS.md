# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test,
release, architecture, and sharp-edge notes that should travel with the code.

## State of the repository

The data layer is landed: `api.py` (T4), `models.py` (T3), `const.py` (T1), `config_flow.py`
(T9 scaffold), and `coordinator.py` + `__init__.py` (T5). Sensors (T6), binary sensor (T7) and
events (T8) are next. The design is finished and lives in [`docs/`](docs/) (`01` to `05`): read
`docs/01-data-sources.md` before touching anything that talks to the data source,
`docs/04-architecture.md` §5 for the coordinator cycle and reconciliation key, and §11 for the
fourteen architectural decisions and why each alternative was rejected.

The coordinator maintains the cycle-to-cycle state (`_previous` keyed by `(acronym, phase)`,
`_last_modified`, `_unknown_*` sets, resilience counters) but does **not** fire bus events yet:
phase events and `cecat_service_degraded` land in T8 (`_emit_events`).

## Language

Documents in **Catalan** (matching the sibling repositories). Code, identifiers, comments, commit
messages, event names and this file in **English**. User-facing strings go through
`_attr_translation_key` + `translations/{ca,es,en}.json`, Catalan as the reference language.

Never use the em dash (`—`) anywhere, including documentation.

## Evidence discipline

This is the rule that makes the docs trustworthy, and it is not optional:

- Every claim about the data source is marked ✅ verified live, 🗄️ verified on an archived
  capture, 📄 documented by the official source, 🔶 inference, or ❓ unverified. Keep the marks
  when editing.
- `docs/captures/` holds only **observed** data. Synthetic test data goes in `tests/fixtures/`
  with a `_SYNTHETIC` suffix and a `_comment` key saying so. Never blur the two.
- Test fixtures must be real captured responses, not invented, except the marked synthetic ones.

## Data source sharp edges

The full list is `docs/01-data-sources.md` §12 (15 numbered traps). The three that bite hardest:

1. **Never filter on `plaactivat='SI'`.** `plaactivat: "NO"` is the `PREALERTA` phase and is
   51.4% of the signal. `plafase` is authoritative; `plaactivat` is derived.
2. **Episode identity is `(plaacronim, plafase)`**, never Socrata's `:id` nor a hash of the row.
   `comunicatpdf` changes several times within one phase, and `:id` changes on a phase change.
3. **An empty response `[]` is a valid state**, not an error. It is the most likely state at any
   given instant. Entities go to `none` / `0` / `off`, never `unavailable`.

## Read-only research etiquette

The source is a public service of a public administration. Read-only requests only, spaced out,
never authenticated, never aggressive. The Azure communiqué container
(`documents.dadesobertes.gencat.cat/cecat`) is publicly listable and was decisive for the
research, but it is **not a documented API**: never consume it at runtime (decision AD-14).

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
