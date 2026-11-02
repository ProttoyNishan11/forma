# FORMA — Personal Fitness Tracker

FORMA is a personal workout-tracking web app for logging Home, Gym, and Outdoor sessions, planning a weekly workout routine, reviewing progress, and exporting workout data. It uses a browser-based interface with a small Python server and a local SQLite database.

**Theme accent:** `#0f568a`

> **Status:** Local, single-user application. This repository contains the app source code. It is not a hosted website, and it cannot run on GitHub Pages because it needs a Python backend and a SQLite database.

## Features

- **Workout logging:** Record session dates, start/end times, duration, body weight, notes, exercises, sets, reps, weights, and time- or distance-based entries.
- **Home, Gym, and Outdoor categories:** Keep workout locations separate and review them individually or together.
- **Exercise library:** Search built-in exercises and add custom exercises.
- **Weekly workout schedule:** Create multiple routines, choose training days and locations, and assign target exercises and sets, reps, weights, or durations.
- **Routine import/export:** Import routine plans in JSON or CSV format and export saved routines. A CSV template is available from the Schedule page.
- **Guided logging:** Start a planned routine to load its exercises into the workout logger, then record what you actually completed and skip exercises when needed.
- **History and statistics:** Review saved workouts and view dashboard summaries and charts.
- **Backup and restore:** Export a full JSON backup and restore saved app data. Restoring replaces the current app records, so back up first.
- **Reports:** Print reports or save them as PDF through the browser, and export Excel-compatible spreadsheet data.
- **Persistent storage:** Store app state and normalized workout records in SQLite instead of relying on browser storage alone.
- **Responsive interface:** Desktop and mobile navigation with a blue accent theme and reduced-motion support.

## Technology stack

- **Frontend:** HTML, CSS, and vanilla JavaScript
- **Backend:** Python standard library (`http.server`)
- **Database:** SQLite via Python's built-in `sqlite3` module
- **Automated tests:** Python `unittest`; an optional JavaScript syntax check can be run with Node.js

No third-party Python packages are required for the current local version.

## Requirements

- Python **3.10 or newer**
- A modern browser such as Chrome, Edge, Firefox, or Safari
- Optional: Node.js, for checking JavaScript syntax

## Run locally

### Windows / VS Code

1. Clone or download this repository and open the project folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Run:

   ```powershell
   py run.py
   ```

   If the `py` launcher is unavailable, try:

   ```powershell
   python run.py
   ```

4. Open <http://127.0.0.1:8000> in your browser.
5. Keep the terminal open while using FORMA. Press `Ctrl+C` in the terminal to stop the server.

### macOS / Linux

From the project directory, run:

```bash
python3 run.py
```

Then open <http://127.0.0.1:8000>.

### Port configuration

If port `8000` is already in use, choose another port before starting the app.

Windows PowerShell:

```powershell
$env:FORMA_PORT = "8001"
py run.py
```

macOS / Linux:

```bash
FORMA_PORT=8001 python3 run.py
```

Then visit <http://127.0.0.1:8001>.

## Data storage and backups

- On the first run, FORMA creates its SQLite database at `../data/forma.sqlite3` relative to the project directory.
- The SQLite database is intentionally outside the static website folder so it is not served as a downloadable website asset.
- App state is cached in the browser to support draft recovery, while saved records are persisted through the local Python server into SQLite.
- Use **Settings → Data & portability** to download a JSON backup before restoring data, changing installations, or moving to another computer.
- **Restore replaces the current app data.** Save a backup of the destination app first.
- Keep backups in a safe location outside the repository. Do not commit personal workout history or a live database to a public GitHub repository.

## Import a weekly routine

Open **Workout schedule** on desktop or **Plan** on mobile.

You can create routines manually, upload JSON, or upload CSV. For CSV imports, use the **Download CSV template** button in the Schedule page. The expected columns are:

```text
routine,location,days,exercise,sets,reps,weight,measurement,value,notes
```

Use one row per exercise. Rows with the same routine name are grouped together. Multiple days can be separated with semicolons, for example `Sunday;Thursday`. Valid locations are `Home`, `Gym`, and `Outdoor`.

For JSON imports, upload a single routine object, an array of routine objects, or an object containing a `routines` array. Each routine includes a name, location, scheduled days, and an exercise list.

The app does **not** automatically read workout routines from PDF or image files. Convert a table to the supported CSV format or enter the routine manually.

After setting up a routine, use **Start plan** on a scheduled day. The planned exercises and target values are loaded into the logger, where you should record the sets and reps you actually completed.

## Reports and calorie estimates

- PDF output currently uses the browser's print dialog. Choose **Save as PDF** in the print destination.
- The spreadsheet export is Excel-compatible SpreadsheetML with an `.xls` extension. It is **not** a native `.xlsx` workbook.
- Calories are estimates, not direct measurements. The app uses a simplified MET-based approximation and broad assumptions based on the session's exercise category, so the displayed value can differ substantially from actual energy expenditure.

## Run the tests

From the project directory:

```bash
python -m unittest discover -s tests -v
```

At the time this README was prepared, the included suite passed **44 tests** covering data validation, SQLite persistence, backup migration, routine scheduling and import, workout timing, HTTP API behavior, and safe static-file serving.

If Node.js is installed, also run:

```bash
node --check js/app.js
```

## Project structure

```text
.
├── index.html             # Main app page
├── css/
│   └── styles.css         # Layout, theme, and responsive styles
├── js/
│   └── app.js             # Frontend state, views, logging, and interactions
├── server.py              # Local HTTP API and SQLite storage
├── run.py                 # Development server entry point
├── tests/
│   ├── test_frontend_time.py
│   └── test_server.py
├── README.md
└── ARCHITECTURE.md         # Implementation and data-model notes
```

## Security and deployment notes

This version is designed for **local use by one person**. It does not include user accounts, authentication, HTTPS, cloud synchronization, or multi-user conflict handling. The server listens on `127.0.0.1` by default.

Do not expose this development server directly to the public internet or change its host to `0.0.0.0` as a substitute for production security. Hosting FORMA for remote access would require a properly secured deployment, authentication, HTTPS, persistent shared storage, and a synchronization/conflict strategy.

GitHub is suitable for storing and sharing the source code. **GitHub Pages alone cannot run this version** because it does not execute the Python server or provide the app's SQLite database.

## Contributing

Bug reports, feature ideas, and pull requests are welcome. When reporting a bug, include the steps to reproduce it and any relevant error message, but do not upload your personal workout database or private backup.

## License

No license is included in this repository by default. Add a `LICENSE` file if you intend to specify how others may use, modify, or redistribute the project.
