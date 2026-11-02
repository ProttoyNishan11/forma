# FORMA — Architecture notes

## Design decision

Preserve the current FORMA browser interface and change the storage boundary first. The existing front end already has the user's dashboard design and workout interactions. Replacing it with a new UI would discard work unnecessarily.

## Current stack

- **Frontend:** existing HTML, CSS, and vanilla JavaScript.
- **Backend:** Python 3 standard-library `http.server`; no external packages needed for the storage MVP.
- **Database:** SQLite via Python's `sqlite3` module.
- **Exports:** existing browser print flow for PDF and Excel-compatible SpreadsheetML export; native PDF/XLSX generation remains a later stage.

## Request flow

```text
Browser (FORMA UI)
  ├── localStorage cache / recoverable draft
  └── fetch('/api/state') ──> Python local server
                              ├── validates state
                              ├── writes within a SQLite transaction
                              └── saves normalized records + compatible JSON snapshot
```

The first GET returns whether the database has been initialized. If it is new, the browser's current state is saved so that a custom exercise library or an existing same-origin cache can be preserved. Once initialized, the SQLite snapshot is loaded as the source of truth. If migrating from a copy opened as a local file or a different origin, export a JSON backup from the old copy and restore it in the new app.

## Data model

- `workouts`: one row per completed session, with date, Home/Gym/Outdoor category, times, duration, weight and notes.
- `exercises`: built-in and custom library entries.
- `workout_exercises`: ordered exercise entries in each session.
- `workout_sets`: set-by-set reps, weights, durations/distances, and notes.
- `body_weight_entries`: weigh-ins.
- `app_settings`: profile and saved draft configuration.
- `app_state`: version-compatible JSON snapshot used by the existing front end. Weekly routines are stored in this snapshot, persisted in SQLite and full JSON backups, and validated server-side; they do not yet have a dedicated normalized table.

All table rebuilds from a saved state happen inside one SQLite transaction. A malformed state is rejected before the transaction so invalid data does not replace the last good state. Category and date indexes support report and history queries in future stages.

## Current boundaries

This is a single-user local application with no authentication or cloud synchronization. The browser caches current state and sends updates to the server after a short debounce. If the local database temporarily becomes unavailable, the app retries the connection and pushes offline edits back to SQLite; SQLite is stored outside the static web directory. The server listens on localhost by default. Do not deploy this server directly to the public internet.

## Routine planning and guided logging

The Schedule page supports editable weekly routines and import/export of JSON or CSV plans. Starting a routine creates a draft with planned exercises and target hints; the user logs actual sets/entries and can skip planned exercises. Routine names and skipped exercise names are attached to the completed session. The guided logger uses exercise search, live per-exercise status, a completion progress bar, a compact main form, and optional details in an expandable section. Routine state is stored in the version-compatible `app_state` JSON snapshot and preserved by full JSON backup/restore.

## Next stages

1. Generate genuine downloadable PDF and `.xlsx` reports server-side, with separate Home/Gym/Outdoor and combined monthly summaries sourced from the database.
2. Move routine records into dedicated normalized tables if future querying or reporting requires it, and add more end-to-end UI tests.
3. Only then add cloud deployment, user authentication, HTTPS, shared database hosting, cross-device synchronization, and conflict handling.
