"""FORMA local web server and SQLite persistence API (Python standard library only)."""
from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR.parent / "data"
DEFAULT_DB_PATH = DATA_DIR / "forma.sqlite3"
MAX_REQUEST_BYTES = 5 * 1024 * 1024
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATIC_FILES = {
    "/": PROJECT_DIR / "index.html",
    "/index.html": PROJECT_DIR / "index.html",
    "/css/styles.css": PROJECT_DIR / "css" / "styles.css",
    "/js/app.js": PROJECT_DIR / "js" / "app.js",
}


class InvalidState(ValueError):
    """Raised when a client sends malformed or unsupported application data."""


def _check_time(value: Any, label: str, allow_empty: bool = True) -> None:
    if value in (None, "") and allow_empty:
        return
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise InvalidState(f"{label} must be a valid 24-hour time (HH:MM).")


def _check_date(value: Any, label: str) -> None:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise InvalidState(f"{label} must use YYYY-MM-DD format.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise InvalidState(f"{label} must be a valid calendar date.") from None


def _check_optional_number(value: Any, label: str, minimum: float = 0, maximum: float = 1_000_000) -> None:
    if value in (None, ""):
        return
    if isinstance(value, bool):
        raise InvalidState(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InvalidState(f"{label} must be a number.") from None
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise InvalidState(f"{label} must be between {minimum:g} and {maximum:g}.")


def _check_text(value: Any, label: str, maximum_length: int = 5000, allow_empty: bool = True) -> None:
    if value is None and allow_empty:
        return
    if not isinstance(value, str):
        raise InvalidState(f"{label} must be text.")
    if not allow_empty and not value.strip():
        raise InvalidState(f"{label} cannot be empty.")
    if len(value) > maximum_length:
        raise InvalidState(f"{label} is too long (maximum {maximum_length} characters).")


def validate_state(state: Any) -> dict[str, Any]:
    """Validate the existing FORMA front-end state shape before storing it."""
    if not isinstance(state, dict):
        raise InvalidState("The request body must be a JSON object.")
    sessions = state.get("sessions")
    exercises = state.get("exercises")
    if not isinstance(sessions, list) or not isinstance(exercises, list):
        raise InvalidState("State must contain sessions and exercises arrays.")
    if len(sessions) > 10000 or len(exercises) > 5000:
        raise InvalidState("This backup contains too many records.")

    session_ids: set[str] = set()
    for index, session in enumerate(sessions):
        label = f"Session {index + 1}"
        if not isinstance(session, dict):
            raise InvalidState(f"{label} must be an object.")
        sid = session.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise InvalidState(f"{label} is missing its ID.")
        if sid in session_ids:
            raise InvalidState(f"Duplicate session ID: {sid}.")
        session_ids.add(sid)
        if session.get("location") not in ("Home", "Gym", "Outdoor"):
            raise InvalidState(f"{label} location must be Home, Gym, or Outdoor.")
        _check_date(session.get("date"), f"{label} date")
        _check_time(session.get("startTime", ""), f"{label} start time")
        _check_time(session.get("endTime", ""), f"{label} end time")
        _check_text(session.get("title", ""), f"{label} title", 200)
        _check_text(session.get("notes", ""), f"{label} notes", 5000)
        if session.get("createdAt") is not None:
            _check_text(session["createdAt"], f"{label} creation timestamp", 100)
        duration = session.get("durationMinutes", 0)
        if duration not in (None, ""):
            if isinstance(duration, bool):
                raise InvalidState(f"{label} duration must be a number.")
            try:
                duration_num = float(duration)
            except (TypeError, ValueError):
                raise InvalidState(f"{label} duration must be a number.") from None
            if not math.isfinite(duration_num) or duration_num < 0 or duration_num > 1440:
                raise InvalidState(f"{label} duration must be a number from 0 to 1440 minutes.")
        _check_optional_number(session.get("bodyWeight", ""), f"{label} body weight", 0.01, 500)
        workout_exercises = session.get("exercises", [])
        if not isinstance(workout_exercises, list):
            raise InvalidState(f"{label} exercises must be an array.")
        for ex_index, item in enumerate(workout_exercises, 1):
            if not isinstance(item, dict) or not isinstance(item.get("sets", []), list):
                raise InvalidState(f"{label}, exercise {ex_index} has an invalid sets list.")
            if not isinstance(item.get("name", ""), str) or not item.get("name", "").strip():
                raise InvalidState(f"{label}, exercise {ex_index} needs a name.")
            if item.get("measurement", "reps") not in ("reps", "seconds", "minutes", "distance"):
                raise InvalidState(f"{label}, exercise {ex_index} has an unsupported measurement type.")
            for field in ("muscle", "equipment", "type"):
                _check_text(item.get(field, ""), f"{label}, exercise {ex_index} {field}", 200)
            for set_index, one_set in enumerate(item.get("sets", []), 1):
                if not isinstance(one_set, dict):
                    raise InvalidState(f"{label}, exercise {ex_index}, set {set_index} must be an object.")
                _check_optional_number(one_set.get("weight", ""), f"{label} set weight", 0, 1000)
                reps = one_set.get("reps", "")
                _check_optional_number(reps, f"{label} set reps", 1, 10000)
                if reps not in (None, "") and not float(reps).is_integer():
                    raise InvalidState(f"{label} set reps must be a whole number.")
                _check_optional_number(one_set.get("value", ""), f"{label} set value", 0, 1_000_000)
                if one_set.get("value", "") not in (None, "") and float(one_set["value"]) <= 0:
                    raise InvalidState(f"{label} set value must be greater than zero.")
                _check_text(one_set.get("note", ""), f"{label} set note", 1000)

    exercise_ids: set[str] = set()
    for index, exercise in enumerate(exercises):
        label = f"Exercise {index + 1}"
        if not isinstance(exercise, dict):
            raise InvalidState(f"{label} must be an object.")
        eid = exercise.get("id")
        name = exercise.get("name")
        if not isinstance(eid, str) or not eid.strip() or not isinstance(name, str) or not name.strip():
            raise InvalidState(f"{label} needs a non-empty ID and name.")
        if eid in exercise_ids:
            raise InvalidState(f"Duplicate exercise ID: {eid}.")
        exercise_ids.add(eid)
        if exercise.get("location", "Both") not in ("Home", "Gym", "Outdoor", "Both"):
            raise InvalidState(f"{label} location must be Home, Gym, or Both.")
        if exercise.get("measurement", "reps") not in ("reps", "seconds", "minutes", "distance"):
            raise InvalidState(f"{label} has an unsupported measurement type.")
        for field in ("muscle", "equipment", "type"):
            _check_text(exercise.get(field, ""), f"{label} {field}", 200)
        if exercise.get("custom") is not None and not isinstance(exercise["custom"], bool):
            raise InvalidState(f"{label} custom flag must be true or false.")

    history = state.get("bodyWeightHistory", [])
    if not isinstance(history, list):
        raise InvalidState("Body-weight history must be an array.")
    for index, entry in enumerate(history, 1):
        if not isinstance(entry, dict):
            raise InvalidState(f"Body-weight entry {index} must be an object.")
        _check_date(entry.get("date"), f"Body-weight entry {index} date")
        _check_optional_number(entry.get("weight"), f"Body-weight entry {index} weight", 0.01, 500)
        if entry.get("weight") in (None, ""):
            raise InvalidState(f"Body-weight entry {index} needs a weight.")
        if entry.get("recordedAt") is not None:
            _check_text(entry["recordedAt"], f"Body-weight entry {index} timestamp", 100)

    settings = state.get("settings", {})
    if not isinstance(settings, dict):
        raise InvalidState("Profile settings must be an object.")
    _check_text(settings.get("name", "Athlete"), "Profile name", 50)
    _check_optional_number(settings.get("height", ""), "Profile height", 0.01, 300)
    if settings.get("sound") is not None and not isinstance(settings["sound"], bool):
        raise InvalidState("Profile sound setting must be true or false.")
    draft = state.get("draft")
    if draft is not None:
        if not isinstance(draft, dict) or not isinstance(draft.get("exercises", []), list):
            raise InvalidState("The saved workout draft is invalid.")
        if draft.get("location", "Home") not in ("Home", "Gym", "Outdoor"):
            raise InvalidState("The saved workout draft must be Home or Gym.")
        if draft.get("date") not in (None, ""):
            _check_date(draft["date"], "Saved workout draft date")
        _check_time(draft.get("startTime", ""), "Saved workout draft start time")
        _check_time(draft.get("endTime", ""), "Saved workout draft end time")
        _check_text(draft.get("title", ""), "Saved workout draft title", 200)
        _check_text(draft.get("notes", ""), "Saved workout draft notes", 5000)
        _check_optional_number(draft.get("bodyWeight", ""), "Saved workout draft body weight", 0.01, 500)
        for index, item in enumerate(draft.get("exercises", []), 1):
            if not isinstance(item, dict) or not isinstance(item.get("sets", []), list):
                raise InvalidState(f"Saved workout draft exercise {index} is invalid.")
            if not isinstance(item.get("name", ""), str) or not item.get("name", "").strip():
                raise InvalidState(f"Saved workout draft exercise {index} needs a name.")
            if item.get("measurement", "reps") not in ("reps", "seconds", "minutes", "distance"):
                raise InvalidState(f"Saved workout draft exercise {index} has an unsupported measurement type.")
            for set_index, one_set in enumerate(item.get("sets", []), 1):
                if not isinstance(one_set, dict):
                    raise InvalidState(f"Saved workout draft set {set_index} must be an object.")
                _check_optional_number(one_set.get("weight", ""), "Draft set weight", 0, 1000)
                reps = one_set.get("reps", "")
                _check_optional_number(reps, "Draft set reps", 1, 10000)
                if reps not in (None, "") and not float(reps).is_integer():
                    raise InvalidState("Draft set reps must be a whole number.")
                _check_optional_number(one_set.get("value", ""), "Draft set value", 0, 1_000_000)
                if one_set.get("value", "") not in (None, "") and float(one_set["value"]) <= 0:
                    raise InvalidState("Draft set value must be greater than zero.")
                _check_text(one_set.get("note", ""), "Draft set note", 1000)

    routines = state.get("routines", [])
    if not isinstance(routines, list):
        raise InvalidState("Workout routines must be an array.")
    if len(routines) > 500:
        raise InvalidState("This schedule contains too many routines.")
    routine_ids: set[str] = set()
    for index, routine in enumerate(routines, 1):
        label = f"Routine {index}"
        if not isinstance(routine, dict):
            raise InvalidState(f"{label} must be an object.")
        routine_id = routine.get("id")
        if not isinstance(routine_id, str) or not routine_id.strip() or routine_id in routine_ids:
            raise InvalidState(f"{label} needs a unique ID.")
        routine_ids.add(routine_id)
        _check_text(routine.get("name", ""), f"{label} name", 100, allow_empty=False)
        if routine.get("location") not in ("Home", "Gym", "Outdoor"):
            raise InvalidState(f"{label} location must be Home, Gym, or Outdoor.")
        days = routine.get("days")
        if not isinstance(days, list) or not days:
            raise InvalidState(f"{label} needs at least one scheduled day.")
        if any(isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6 for day in days):
            raise InvalidState(f"{label} days must be weekday numbers from 0 to 6.")
        _check_text(routine.get("notes", ""), f"{label} notes", 1000)
        planned_exercises = routine.get("exercises")
        if not isinstance(planned_exercises, list) or not planned_exercises or len(planned_exercises) > 100:
            raise InvalidState(f"{label} must contain between 1 and 100 planned exercises.")
        for ex_index, planned in enumerate(planned_exercises, 1):
            ex_label = f"{label}, exercise {ex_index}"
            if not isinstance(planned, dict):
                raise InvalidState(f"{ex_label} must be an object.")
            _check_text(planned.get("name", ""), f"{ex_label} name", 100, allow_empty=False)
            if planned.get("measurement", "reps") not in ("reps", "seconds", "minutes", "distance"):
                raise InvalidState(f"{ex_label} has an unsupported measurement type.")
            target_sets = planned.get("targetSets", 3)
            if isinstance(target_sets, bool) or not isinstance(target_sets, int) or not 1 <= target_sets <= 100:
                raise InvalidState(f"{ex_label} target sets must be a whole number from 1 to 100.")
            target_reps = planned.get("targetReps", "")
            if target_reps not in (None, ""):
                _check_optional_number(target_reps, f"{ex_label} target reps", 1, 10000)
                if not float(target_reps).is_integer():
                    raise InvalidState(f"{ex_label} target reps must be a whole number.")
            _check_optional_number(planned.get("targetWeight", ""), f"{ex_label} target weight", 0, 1000)
            target_value = planned.get("targetValue", "")
            _check_optional_number(target_value, f"{ex_label} target value", 0, 1_000_000)
            if target_value not in (None, "") and float(target_value) <= 0:
                raise InvalidState(f"{ex_label} target value must be greater than zero.")
            _check_text(planned.get("notes", ""), f"{ex_label} notes", 1000)
    return state


class StateStore:
    """SQLite store. A JSON snapshot preserves the front-end contract while normalized
    tables keep workouts, exercises, sets, and body-weight entries queryable.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workouts (
                    id TEXT PRIMARY KEY,
                    workout_date TEXT NOT NULL,
                    category TEXT NOT NULL CHECK (category IN ('Home', 'Gym', 'Outdoor')),
                    start_time TEXT,
                    end_time TEXT,
                    duration_minutes INTEGER NOT NULL DEFAULT 0,
                    body_weight_kg REAL,
                    notes TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(workout_date);
                CREATE INDEX IF NOT EXISTS idx_workouts_category_date ON workouts(category, workout_date);
                CREATE TABLE IF NOT EXISTS exercises (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    muscle_group TEXT NOT NULL DEFAULT '',
                    equipment TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT 'Both',
                    exercise_type TEXT NOT NULL DEFAULT '',
                    measurement TEXT NOT NULL DEFAULT 'reps',
                    is_custom INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workout_exercises (
                    id TEXT PRIMARY KEY,
                    workout_id TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                    exercise_id TEXT,
                    position INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workout_exercises_workout ON workout_exercises(workout_id, position);
                CREATE TABLE IF NOT EXISTS workout_sets (
                    id TEXT PRIMARY KEY,
                    workout_exercise_id TEXT NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
                    set_number INTEGER NOT NULL,
                    weight_kg REAL,
                    reps REAL,
                    value REAL,
                    note TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS body_weight_entries (
                    id TEXT PRIMARY KEY,
                    entry_date TEXT NOT NULL,
                    weight_kg REAL NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL
                );
            """)
            self._migrate_workout_categories(conn)

    @staticmethod
    def _migrate_workout_categories(conn: sqlite3.Connection) -> None:
        """Expand an existing workouts table to accept Outdoor without losing rows or FKs."""
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workouts'").fetchone()
        if row is None or "Outdoor" in (row["sql"] or ""):
            return
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE workouts_new (
                id TEXT PRIMARY KEY,
                workout_date TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('Home', 'Gym', 'Outdoor')),
                start_time TEXT,
                end_time TEXT,
                duration_minutes INTEGER NOT NULL DEFAULT 0,
                body_weight_kg REAL,
                notes TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL
            )""")
            conn.execute("""INSERT INTO workouts_new
                (id, workout_date, category, start_time, end_time, duration_minutes, body_weight_kg, notes, payload_json)
                SELECT id, workout_date, category, start_time, end_time, duration_minutes, body_weight_kg, notes, payload_json
                FROM workouts""")
            conn.execute("DROP TABLE workouts")
            conn.execute("ALTER TABLE workouts_new RENAME TO workouts")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(workout_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workouts_category_date ON workouts(category, workout_date)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def get_state(self) -> tuple[bool, dict[str, Any] | None, str | None]:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT payload_json, updated_at FROM app_state WHERE id = 1").fetchone()
        if row is None:
            return False, None, None
        try:
            state = json.loads(row["payload_json"])
        except json.JSONDecodeError as exc:
            raise RuntimeError("The saved database state is not valid JSON.") from exc
        return True, state, row["updated_at"]

    @staticmethod
    def _number(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def save_state(self, state: Any) -> str:
        state = validate_state(state)
        try:
            encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise InvalidState("The request contains unsupported or non-finite values.") from None
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        # This transaction updates the front-end snapshot and its normalized tables atomically.
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT INTO app_state(id, payload_json, updated_at) VALUES(1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
                (encoded, timestamp))
            conn.execute("DELETE FROM workout_sets")
            conn.execute("DELETE FROM workout_exercises")
            conn.execute("DELETE FROM workouts")
            conn.execute("DELETE FROM exercises")
            conn.execute("DELETE FROM body_weight_entries")
            conn.execute("DELETE FROM app_settings")

            for exercise in state["exercises"]:
                conn.execute("""INSERT INTO exercises
                    (id,name,muscle_group,equipment,location,exercise_type,measurement,is_custom,payload_json)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (
                    exercise["id"], exercise["name"], str(exercise.get("muscle", "")),
                    str(exercise.get("equipment", "")), str(exercise.get("location", "Both")),
                    str(exercise.get("type", "")), str(exercise.get("measurement", "reps")),
                    int(bool(exercise.get("custom", False))), json.dumps(exercise, ensure_ascii=False, allow_nan=False)))

            for session in state["sessions"]:
                bodyweight = self._number(session.get("bodyWeight"))
                duration = self._number(session.get("durationMinutes")) or 0
                conn.execute("""INSERT INTO workouts
                    (id,workout_date,category,start_time,end_time,duration_minutes,body_weight_kg,notes,payload_json)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (
                    session["id"], session["date"], session["location"], session.get("startTime") or None,
                    session.get("endTime") or None, duration, bodyweight,
                    str(session.get("notes", "")), json.dumps(session, ensure_ascii=False, allow_nan=False)))
                for position, item in enumerate(session.get("exercises", [])):
                    we_id = f"{session['id']}::exercise::{position}"
                    conn.execute("""INSERT INTO workout_exercises
                        (id,workout_id,exercise_id,position,name,payload_json) VALUES(?,?,?,?,?,?)""", (
                        we_id, session["id"], item.get("exerciseId"), position,
                        str(item.get("name", "Unnamed exercise")), json.dumps(item, ensure_ascii=False, allow_nan=False)))
                    for set_number, one_set in enumerate(item.get("sets", []), 1):
                        conn.execute("""INSERT INTO workout_sets
                            (id,workout_exercise_id,set_number,weight_kg,reps,value,note,payload_json)
                            VALUES(?,?,?,?,?,?,?,?)""", (
                            f"{we_id}::set::{set_number}", we_id, set_number,
                            self._number(one_set.get("weight")), self._number(one_set.get("reps")),
                            self._number(one_set.get("value")), str(one_set.get("note", "")),
                            json.dumps(one_set, ensure_ascii=False, allow_nan=False)))

            for index, item in enumerate(state.get("bodyWeightHistory", [])):
                if not isinstance(item, dict) or not item.get("date") or self._number(item.get("weight")) is None:
                    continue
                ident = f"{item['date']}::{item['weight']}::{index}"
                conn.execute("INSERT INTO body_weight_entries(id,entry_date,weight_kg,source,payload_json) VALUES(?,?,?,?,?)", (
                    ident, str(item["date"]), float(item["weight"]), "weigh-in", json.dumps(item, ensure_ascii=False, allow_nan=False)))
            conn.execute("INSERT INTO app_settings(id,payload_json) VALUES(1,?)", (
                json.dumps({"settings": state.get("settings", {}), "draft": state.get("draft")}, ensure_ascii=False, allow_nan=False),))
        return timestamp

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as conn, conn:
            return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in ("workouts", "exercises", "workout_exercises", "workout_sets", "body_weight_entries")}


def make_handler(store: StateStore):
    class Handler(SimpleHTTPRequestHandler):
        server_version = "FORMA-local/1.0"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

        def log_message(self, fmt, *args):
            # Keep local output readable while retaining standard request information.
            print(f"[{self.log_date_time_string()}] {fmt % args}")

        def _json(self, status: int, value: Any) -> None:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _serve_static(self, head_only: bool = False) -> None:
            path = urlparse(self.path).path
            target = STATIC_FILES.get(path)
            if target is None or not target.is_file():
                self.send_error(404, "File not found")
                return
            try:
                raw = target.read_bytes()
            except OSError:
                self.send_error(500, "Could not read static asset")
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix.lower() in {".html", ".css", ".js"}:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache" if target.suffix.lower() in {".html", ".js", ".css"} else "public, max-age=3600")
            self.end_headers()
            if not head_only:
                self.wfile.write(raw)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/health":
                self._json(200, {"ok": True, "database": str(store.db_path.name), "counts": store.counts()})
                return
            if path == "/api/state":
                try:
                    initialized, state, updated_at = store.get_state()
                    if initialized:
                        validate_state(state)
                    self._json(200, {"initialized": initialized, "state": state, "updatedAt": updated_at})
                except Exception:
                    self._json(500, {"error": "Could not read the saved application data."})
                return
            if path.startswith("/api/"):
                self._json(404, {"error": "API route not found."})
                return
            self._serve_static()

        def do_HEAD(self):
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                self.send_error(405, "HEAD is not supported for API routes")
                return
            self._serve_static(head_only=True)

        def do_PUT(self):
            path = urlparse(self.path).path
            if path != "/api/state":
                self._json(404, {"error": "API route not found."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "Invalid Content-Length."})
                return
            if length <= 0:
                self._json(400, {"error": "A JSON request body is required."})
                return
            if length > MAX_REQUEST_BYTES:
                self._json(413, {"error": "Request is too large (5 MB maximum)."})
                return
            if "application/json" not in self.headers.get("Content-Type", "").lower():
                self._json(415, {"error": "Content-Type must be application/json."})
                return
            try:
                body = self.rfile.read(length)
                state = json.loads(body.decode("utf-8"))
                updated_at = store.save_state(state)
                self._json(200, {"ok": True, "updatedAt": updated_at})
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "Request body is not valid UTF-8 JSON."})
            except InvalidState as exc:
                self._json(400, {"error": str(exc)})
            except (sqlite3.Error, ValueError, TypeError):
                self._json(500, {"error": "The database could not save this change."})

    return Handler


def create_server(host: str = "127.0.0.1", port: int = 8000, db_path: str | Path | None = None) -> ThreadingHTTPServer:
    configured = db_path or os.environ.get("FORMA_DB_PATH") or DEFAULT_DB_PATH
    store = StateStore(configured)
    handler = make_handler(store)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    # Expose the store for integration tests and health inspection.
    httpd.forma_store = store  # type: ignore[attr-defined]
    return httpd


if __name__ == "__main__":
    host = os.environ.get("FORMA_HOST", "127.0.0.1")
    port = int(os.environ.get("FORMA_PORT", "8000"))
    server = create_server(host, port)
    print(f"FORMA is running at http://{host}:{port}")
    print(f"SQLite database: {server.forma_store.db_path}")  # type: ignore[attr-defined]
    print("Press Ctrl+C to stop. This local build has no login or cloud synchronization.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down FORMA...")
    finally:
        server.server_close()
