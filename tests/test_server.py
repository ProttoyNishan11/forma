import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from server import InvalidState, StateStore, create_server


def sample_state():
    return {
        "sessions": [{
            "id": "session-1", "location": "Home", "date": "2026-10-18",
            "startTime": "23:30", "endTime": "00:10", "durationMinutes": 40,
            "bodyWeight": 65, "notes": "test workout", "exercises": [{
                "exerciseId": "push-up", "name": "Push-up", "muscle": "Chest",
                "equipment": "Bodyweight", "type": "Strength", "measurement": "reps",
                "sets": [{"weight": "0", "reps": "12"}, {"weight": "0", "reps": "10"}]
            }]
        }],
        "exercises": [{"id": "push-up", "name": "Push-up", "muscle": "Chest",
                       "equipment": "Bodyweight", "location": "Home", "type": "Strength",
                       "measurement": "reps", "custom": False}],
        "bodyWeightHistory": [{"date": "2026-10-18", "weight": 65}],
        "routines": [{
            "id": "routine-push", "name": "Push Day", "location": "Gym", "days": [0, 4],
            "notes": "Controlled reps", "exercises": [{
                "id": "routine-ex-1", "exerciseId": "push-up", "name": "Push-up",
                "muscle": "Chest", "equipment": "Bodyweight", "type": "Strength",
                "measurement": "reps", "targetSets": 3, "targetReps": 10,
                "targetWeight": "", "targetValue": "", "notes": ""
            }]
        }],
        "settings": {"name": "Tester", "sound": False}, "draft": None
    }


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = StateStore(Path(self.tmp.name) / "test.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_database_is_uninitialized(self):
        self.assertEqual(self.db.get_state(), (False, None, None))

    def test_round_trip_preserves_state(self):
        state = sample_state()
        self.db.save_state(state)
        initialized, restored, updated = self.db.get_state()
        self.assertTrue(initialized)
        self.assertEqual(restored, state)
        self.assertTrue(updated)

    def test_state_survives_database_reopen(self):
        state = sample_state()
        path = self.db.db_path
        self.db.save_state(state)
        reopened = StateStore(path)
        self.assertEqual(reopened.get_state()[1], state)

    def test_routine_schedule_persists_through_sqlite_snapshot(self):
        state = sample_state()
        self.db.save_state(state)
        initialized, restored, _ = self.db.get_state()
        self.assertTrue(initialized)
        self.assertEqual(restored["routines"], state["routines"])

    def test_invalid_routine_day_is_rejected(self):
        state = sample_state()
        state["routines"][0]["days"] = [7]
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_invalid_routine_target_is_rejected(self):
        state = sample_state()
        state["routines"][0]["exercises"][0]["targetSets"] = 0
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_records_are_normalized_into_sqlite_tables(self):
        self.db.save_state(sample_state())
        counts = self.db.counts()
        self.assertEqual(counts["workouts"], 1)
        self.assertEqual(counts["exercises"], 1)
        self.assertEqual(counts["workout_exercises"], 1)
        self.assertEqual(counts["workout_sets"], 2)
        self.assertEqual(counts["body_weight_entries"], 1)

    def test_home_and_gym_categories_are_preserved(self):
        state = sample_state()
        gym = dict(state["sessions"][0], id="session-2", location="Gym")
        state["sessions"].append(gym)
        self.db.save_state(state)
        with self.db._connect() as conn:
            categories = [row[0] for row in conn.execute("SELECT category FROM workouts ORDER BY id")]
        self.assertEqual(categories, ["Home", "Gym"])

    def test_invalid_location_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["location"] = "Outside"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_invalid_date_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["date"] = "18/10/2026"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_impossible_calendar_date_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["date"] = "2026-02-30"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_malformed_set_is_rejected_without_crashing(self):
        state = sample_state()
        state["sessions"][0]["exercises"][0]["sets"][0] = "not-a-set-object"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_non_finite_duration_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["durationMinutes"] = float("nan")
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_invalid_body_weight_history_is_rejected(self):
        state = sample_state()
        state["bodyWeightHistory"] = {"not": "an array"}
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_invalid_time_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["startTime"] = "25:90"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_duration_bounds_are_checked(self):
        state = sample_state()
        state["sessions"][0]["durationMinutes"] = 1500
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_boolean_duration_is_rejected(self):
        state = sample_state()
        state["sessions"][0]["durationMinutes"] = True
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_profile_settings_are_validated(self):
        state = sample_state()
        state["settings"]["name"] = {"unexpected": "object"}
        with self.assertRaises(InvalidState):
            self.db.save_state(state)
        state = sample_state()
        state["settings"]["height"] = 350
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_fractional_reps_are_rejected(self):
        state = sample_state()
        state["sessions"][0]["exercises"][0]["sets"][0]["reps"] = "10.5"
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_malformed_draft_notes_are_rejected(self):
        state = sample_state()
        state["draft"] = {"location": "Home", "date": "2026-10-21", "notes": {"bad": "shape"}, "exercises": []}
        with self.assertRaises(InvalidState):
            self.db.save_state(state)

    def test_invalid_write_does_not_overwrite_saved_state(self):
        state = sample_state()
        self.db.save_state(state)
        invalid = sample_state()
        invalid["sessions"][0]["location"] = "Mars"
        with self.assertRaises(InvalidState):
            self.db.save_state(invalid)
        self.assertEqual(self.db.get_state()[1], state)


    def test_outdoor_category_and_fractional_duration_are_preserved(self):
        state = sample_state()
        state["sessions"][0]["location"] = "Outdoor"
        state["sessions"][0]["durationMinutes"] = 1.5
        self.db.save_state(state)
        self.assertEqual(self.db.get_state()[1]["sessions"][0]["durationMinutes"], 1.5)
        with self.db._connect() as conn:
            row = conn.execute("SELECT category, duration_minutes FROM workouts").fetchone()
        self.assertEqual(row["category"], "Outdoor")
        self.assertEqual(row["duration_minutes"], 1.5)

class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, Path(self.tmp.name) / "api.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, path, method="GET", body=None, content_type="application/json"):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": content_type} if data is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.headers.get("Content-Type", ""), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read()

    def test_health_endpoint(self):
        status, _, raw = self.request("/api/health")
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["workouts"], 0)

    def test_state_get_put_get(self):
        status, _, raw = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw)["initialized"])
        state = sample_state()
        status, _, raw = self.request("/api/state", "PUT", state)
        self.assertEqual(status, 200, raw.decode())
        self.assertTrue(json.loads(raw)["ok"])
        status, _, raw = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["state"], state)

    def test_invalid_api_request_is_rejected_and_saved_data_survives(self):
        state = sample_state()
        self.assertEqual(self.request("/api/state", "PUT", state)[0], 200)
        invalid = sample_state()
        invalid["sessions"][0]["location"] = "Gym and home"
        status, _, raw = self.request("/api/state", "PUT", invalid)
        self.assertEqual(status, 400)
        self.assertIn("location", json.loads(raw)["error"])
        self.assertEqual(json.loads(self.request("/api/state")[2])["state"], state)

    def test_serves_website(self):
        status, content_type, raw = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"FORMA", raw)

    def test_database_file_is_not_served_as_static_content(self):
        status, _, _ = self.request("/data/forma.sqlite3")
        self.assertEqual(status, 404)

    def test_server_source_is_not_served_as_static_content(self):
        status, _, _ = self.request("/server.py")
        self.assertEqual(status, 404)

    def test_static_directories_and_unlisted_files_are_not_exposed(self):
        for path in ("/css/", "/js/", "/tests/", "/__pycache__/server.cpython-311.pyc", "/ARCHITECTURE.md"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_serves_frontend_assets_from_allowlist(self):
        status, content_type, raw = self.request("/js/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)
        self.assertIn(b"sessionValidationError", raw)

    def test_http_api_returns_400_for_malformed_set(self):
        state = sample_state()
        self.assertEqual(self.request("/api/state", "PUT", state)[0], 200)
        invalid = sample_state()
        invalid["sessions"][0]["exercises"][0]["sets"][0] = "bad set"
        status, _, raw = self.request("/api/state", "PUT", invalid)
        self.assertEqual(status, 400)
        self.assertIn("set", json.loads(raw)["error"].lower())
        self.assertEqual(json.loads(self.request("/api/state")[2])["state"], state)

    def test_existing_database_migrates_workout_category_constraint(self):
        path = Path(self.tmp.name) / "legacy.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.execute("""CREATE TABLE workouts (
                id TEXT PRIMARY KEY, workout_date TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('Home', 'Gym')),
                start_time TEXT, end_time TEXT, duration_minutes INTEGER NOT NULL DEFAULT 0,
                body_weight_kg REAL, notes TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL
            )""")
            conn.execute("INSERT INTO workouts VALUES ('old-row','2026-10-18','Home','10:00','10:30',30,NULL,'preserve me','{}')")
        migrated_store = StateStore(path)
        with migrated_store._connect() as conn:
            old_row = conn.execute("SELECT id, notes FROM workouts WHERE id='old-row'").fetchone()
        self.assertIsNotNone(old_row)
        self.assertEqual(old_row["notes"], "preserve me")
        state = sample_state()
        state["sessions"][0]["location"] = "Outdoor"
        migrated_store.save_state(state)
        with migrated_store._connect() as conn:
            row = conn.execute("SELECT category FROM workouts").fetchone()
            self.assertEqual(list(conn.execute("PRAGMA foreign_key_check")), [])
        self.assertEqual(row["category"], "Outdoor")


if __name__ == "__main__":
    unittest.main(verbosity=2)
