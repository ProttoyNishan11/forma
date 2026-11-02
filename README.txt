FORMA — Personal Fitness Dashboard (SQLite edition)
Theme accent: #0f568a (blue).

QUICK START (Windows)
1. Extract this ZIP.
2. Open the forma-website folder in File Explorer.
3. Click the address bar, type powershell, and press Enter.
4. Run: python run.py  (or: py run.py)
5. Open http://127.0.0.1:8000 in your browser. Keep the terminal open.
6. Press Ctrl+C in the terminal to stop the application.

Python 3.10+ is recommended. No third-party packages or database credentials are required.

STORAGE
Workouts are stored in a SQLite database at ../data/forma.sqlite3, outside the static website folder. The first launch creates it automatically. A browser cache remains as a secondary draft/cache layer. The app retries the local database connection after temporary outages, while preserving offline edits in the cache.

MIGRATING OLD FORMA DATA
In your old copy, open Settings & backup > Download full backup (.json). In this SQLite version, open Settings & backup > Restore backup (.json). Restore replaces existing app data, so save a backup first if needed.

PERSONAL WORKOUT SCHEDULES
Open Workout schedule from the desktop sidebar or the mobile Plan tab. Create multiple routines, select training days, choose Home/Gym/Outdoor, add exercises, and enter target sets/reps/weights or duration/distance. Start a routine to load its planned exercise list into the guided logger. Enter what you actually completed, use the Log planned targets shortcut only as a starting point, and skip exercises you did not do. Schedules are included in full JSON backups.

Upload routines as JSON or CSV. Use Download CSV template from the Schedule page to get the right format. PDF and image routines are not automatically read by this offline app; enter them manually or convert their table to the CSV template. Do not use routine upload to restore workout history; use Settings & backup > Restore backup for full backups.

GUIDED WORKOUT LOGGING
The logger has a session progress bar, set-by-set inputs, exercise search, target hints, Start now/End now shortcuts, and an expandable area for body weight, session name, and notes. Sessions started from a routine record the routine name and skipped planned exercises.

TESTS
From this folder, run:
  python -m unittest discover -s tests -v
The regression tests cover persistence, Home/Gym/Outdoor records, routines and their validation/import, the guided logger, malformed backups, static serving, and front-end helpers.
Optional JavaScript syntax check (if Node.js is installed):
  node --check js/app.js

See README.md for architecture, storage, backups, testing, security limitations, and features still planned for a later stage. This is a local single-user build without authentication or cloud synchronization. Do not expose it directly to the public internet.

DISPLAY STABILITY
The app does not animate page content on each render. Background SQLite reconnects no longer rebuild an unchanged screen, preventing repeated flashes when the local database is temporarily unavailable. The app also respects the operating system's reduced-motion preference.
