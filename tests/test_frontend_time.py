"""Regression tests for time calculations and workout entry validation in app.js."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
APP_JS = PROJECT / "js" / "app.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is optional; skipping JavaScript helper tests")
class FrontendTests(unittest.TestCase):
    def run_node(self, script: str) -> None:
        result = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_time_helper_handles_midnight_and_same_day(self):
        source = APP_JS.read_text(encoding="utf-8")
        match = re.search(r"(const minsBetween=.*?);\s*const durationLabel", source, re.S)
        self.assertIsNotNone(match, "The minsBetween helper should remain in app.js")
        helper = match.group(1).replace("const minsBetween=", "globalThis.minsBetween=", 1) + ";"
        script = helper + "\n" + """
const assert = require('node:assert/strict');
assert.equal(minsBetween('2026-10-18','23:30','00:10'), 40);
assert.equal(minsBetween('2026-10-18','09:15','10:00'), 45);
assert.equal(minsBetween('2026-10-18','','10:00'), 0);
"""
        self.run_node(script)

    def test_session_validation_rejects_invalid_entries_and_accepts_valid_workout(self):
        source = APP_JS.read_text(encoding="utf-8")
        helpers = re.search(r"(const isISODate=.*?;\s*const isClockTime=.*?;)", source, re.S)
        validator = re.search(r"function sessionValidationError\(value,fallbackEndTime\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(helpers, "The date/time validation helpers should remain in app.js")
        self.assertIsNotNone(validator, "Workout save validation should remain a standalone helper")
        script = helpers.group(1) + "\n" + "function sessionValidationError(value,fallbackEndTime){" + validator.group(1) + "\n}\n" + """
const assert = require('node:assert/strict');
const valid = {date:'2026-10-21', location:'Gym', startTime:'17:10', endTime:'18:20', bodyWeight:'62', exercises:[{name:'Dumbbell Chest Press',measurement:'reps',sets:[{weight:'5.2',reps:'10'}]}]};
assert.equal(sessionValidationError(valid, '18:20'), '');
assert.match(sessionValidationError({...valid,date:'2026-02-30'}, '18:20'), /date/i);
assert.match(sessionValidationError({...valid,bodyWeight:'-2'}, '18:20'), /body weight/i);
assert.match(sessionValidationError({...valid,startTime:'bad'}, '18:20'), /start time/i);
assert.match(sessionValidationError({...valid,exercises:[{name:'Push-up',measurement:'reps',sets:[{weight:'-1',reps:'10'}]}]}, '18:20'), /weight/i);
assert.match(sessionValidationError({...valid,exercises:[{name:'Push-up',measurement:'reps',sets:[{weight:'',reps:''}]}]}, '18:20'), /completed set/i);
assert.match(sessionValidationError({...valid,startTime:'17:10',endTime:'17:10'}, '17:10'), /same/i);
"""
        self.run_node(script)

    def test_backup_validation_rejects_malformed_settings_and_sets(self):
        source = APP_JS.read_text(encoding="utf-8")
        helpers = re.search(r"(const isISODate=.*?;\s*const isClockTime=.*?;)", source, re.S)
        validator = re.search(r"function backupValidationError\(obj\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(helpers, "Date/time validators should be available")
        self.assertIsNotNone(validator, "Backup validation should be a standalone helper")
        script = helpers.group(1) + "\n" + "function backupValidationError(obj){" + validator.group(1) + "\n}\n" + """
const assert = require('node:assert/strict');
const valid = {sessions:[], exercises:[{id:'ex-1',name:'Push-up',location:'Home',measurement:'reps'}], bodyWeightHistory:[], settings:{name:'Tester',height:'170',sound:false}, draft:null};
assert.equal(backupValidationError(valid), '');
assert.match(backupValidationError({...valid,settings:{name:{bad:true}}}), /profile name/i);
const badSet = {...valid, sessions:[{id:'s-1',location:'Gym',date:'2026-10-21',startTime:'17:00',endTime:'18:00',exercises:[{name:'Press',measurement:'reps',sets:[{reps:'10.5',weight:'5'}]}]}]};
assert.match(backupValidationError(badSet), /rep count/i);
const badDraft = {...valid, draft:{location:'Home',date:'2026-10-21',startTime:'17:00',notes:{bad:true},exercises:[]}};
assert.match(backupValidationError(badDraft), /draft title or notes/i);
"""
        self.run_node(script)

    def test_mobile_navigation_exposes_reports_and_settings(self):
        html = (PROJECT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT / "css" / "styles.css").read_text(encoding="utf-8")
        mobile = re.search(r'<nav class="mobile-nav".*?</nav>', html, re.S)
        self.assertIsNotNone(mobile)
        self.assertIn('data-page="reports"', mobile.group(0))
        self.assertIn('data-page="settings"', html)
        self.assertIn('.top-actions .icon-button{display:inline-grid;flex:none}', css)

    def test_legacy_backup_migrates_weight_ranges_and_keeps_outdoor_fractional_sessions(self):
        source = APP_JS.read_text(encoding="utf-8")
        helpers = re.search(r"(const isISODate=.*?;\s*const isClockTime=.*?;)", source, re.S)
        normalizer = re.search(r"function normalizeLegacyBackup\(source\)\{([\s\S]*?)\n\}", source)
        validator = re.search(r"function backupValidationError\(obj\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(helpers)
        self.assertIsNotNone(normalizer)
        self.assertIsNotNone(validator)
        script = helpers.group(1) + "\n" + "function normalizeLegacyBackup(source){" + normalizer.group(1) + "\n}\n" + "function backupValidationError(obj){" + validator.group(1) + "\n}\n" + """
const assert = require('node:assert/strict');
const source = {sessions:[{id:'legacy-outdoor',location:'Outdoor',date:'2026-10-19',durationMinutes:1.5,startTime:'09:30',endTime:'',exercises:[{name:'Squat',measurement:'reps',sets:[{weight:'5-7',reps:'10'}]}]}],exercises:[{id:'cycle',name:'Cycling',location:'Both',measurement:'minutes'}],bodyWeightHistory:[],settings:{name:'Tester',height:'',sound:false},draft:null};
const migrated = normalizeLegacyBackup(source);
assert.equal(migrated.migratedWeightRanges, 1);
assert.equal(migrated.backup.sessions[0].location, 'Outdoor');
assert.equal(migrated.backup.sessions[0].durationMinutes, 1.5);
assert.equal(migrated.backup.sessions[0].exercises[0].sets[0].weight, '');
assert.match(migrated.backup.sessions[0].exercises[0].sets[0].note, /5-7 kg/);
assert.equal(source.sessions[0].exercises[0].sets[0].weight, '5-7', 'The original backup object must not be mutated');
assert.equal(backupValidationError(migrated.backup), '');
"""
        self.run_node(script)


    def test_schedule_page_and_guided_logger_are_wired(self):
        html = (PROJECT / "index.html").read_text(encoding="utf-8")
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn('data-page="schedule"', html)
        self.assertIn('id="routine-file"', source)
        self.assertIn('function scheduleHTML()', source)
        self.assertIn('function startRoutine(id)', source)
        self.assertIn('data-action="fill-targets"', source)
        self.assertIn('id="log-progress-bar"', source)
        self.assertIn('id="exercise-search"', source)

    def test_new_guided_logger_is_not_shadowed_by_duplicate_functions(self):
        source = APP_JS.read_text(encoding="utf-8")
        functions = re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", source)
        duplicates = sorted({name for name in functions if functions.count(name) > 1})
        self.assertEqual(duplicates, [], f"Duplicate function declarations can shadow new implementations: {duplicates}")
        logger = re.search(r"function logHTML\(\)\{([\s\S]*?)\nfunction availableExercises", source)
        self.assertIsNotNone(logger)
        self.assertIn('id="log-progress-count"', logger.group(1))
        self.assertIn('id="exercise-search"', logger.group(1))
        self.assertIn('Body weight, session name & notes', logger.group(1))

    def test_json_routine_normalizer_preserves_schedule_and_targets(self):
        source = APP_JS.read_text(encoding="utf-8")
        normalizer = re.search(r"function normalizeImportedRoutine\(raw,index,pendingExercises\)\{([\s\S]*?)\n\}", source)
        day_parser = re.search(r"function parseRoutineDays\(value\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(normalizer)
        self.assertIsNotNone(day_parser)
        script = "const WEEKDAYS=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];\n" + \
            "function parseRoutineDays(value){" + day_parser.group(1) + "\n}\n" + \
            "let idCounter=0; const uid=()=>`test-${++idCounter}`;\n" + \
            "const db={exercises:[{id:'bench',name:'Bench Press',muscle:'Chest',equipment:'Barbell',location:'Gym',type:'Strength',measurement:'reps'}]};\n" + \
            "function normalizeImportedRoutine(raw,index,pendingExercises){" + normalizer.group(1) + "\n}\n" + r"""
const assert = require('node:assert/strict');
const pending = [];
const routine = normalizeImportedRoutine({name:'Push Day',location:'Gym',days:['Sunday','Thursday'],exercises:[{name:'Bench Press',sets:3,reps:10,weight:20,measurement:'reps'}]},0,pending);
assert.deepEqual(routine.days,[0,4]);
assert.equal(routine.location,'Gym');
assert.equal(routine.exercises[0].targetSets,3);
assert.equal(routine.exercises[0].targetReps,10);
assert.equal(routine.exercises[0].targetWeight,20);
assert.equal(pending.length,0);
"""
        self.run_node(script)

    def test_routine_csv_parser_supports_quoted_days(self):
        source = APP_JS.read_text(encoding="utf-8")
        csv_parser = re.search(r"function parseCSV\(text\)\{([\s\S]*?)\n\}", source)
        day_parser = re.search(r"function parseRoutineDays\(value\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(csv_parser)
        self.assertIsNotNone(day_parser)
        script = "const WEEKDAYS=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];\n" + \
            "function parseCSV(text){" + csv_parser.group(1) + "\n}\n" + \
            "function parseRoutineDays(value){" + day_parser.group(1) + "\n}\n" + r"""
const assert = require('node:assert/strict');
const rows = parseCSV('routine,location,days,exercise,sets,reps,weight,measurement,value,notes\r\nPush Day,Gym,"Sunday;Thursday",Bench Press,3,10,20,reps,,\r\n');
assert.equal(rows[1][2], 'Sunday;Thursday');
assert.deepEqual(parseRoutineDays(rows[1][2]), [0,4]);
assert.deepEqual(parseRoutineDays(['Mon', 'Wed', 'Fri']), [1,3,5]);
"""
        self.run_node(script)

    def test_background_database_retries_do_not_rebuild_unchanged_page(self):
        source = APP_JS.read_text(encoding="utf-8")
        sync = re.search(r"async function syncServerState\(isRetry=false\)\{([\s\S]*?)\n\}", source)
        self.assertIsNotNone(sync, "Server synchronization should remain in one function")
        body = sync.group(1)
        self.assertIn("const stateBeforeSync=JSON.stringify(db)", body)
        self.assertIn("if(!isRetry||stateBeforeSync!==JSON.stringify(db))render()", body)
        catch = body[body.index("}catch(error){"):]
        self.assertNotIn("render()", catch, "A failed background retry must not re-render the page")

    def test_content_fade_animation_is_disabled(self):
        css = (PROJECT / "css" / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.view\{animation:none!important\}")
        self.assertNotIn("@keyframes appear", css)
        self.assertIn("@media(prefers-reduced-motion:reduce)", css)

    def test_fractional_duration_displays_minutes_and_seconds(self):
        source = APP_JS.read_text(encoding="utf-8")
        match = re.search(r"^const durationLabel=m=>.*$", source, re.M)
        self.assertIsNotNone(match)
        safe = re.search(r"^const safe=.*$", source, re.M)
        self.assertIsNotNone(safe)
        script = safe.group(0) + "\n" + match.group(0).replace("const durationLabel=", "globalThis.durationLabel=", 1) + "\n" + """
const assert = require('node:assert/strict');
assert.equal(durationLabel(1.5), '1m 30s');
assert.equal(durationLabel(45), '45 min');
assert.equal(durationLabel(60), '1h 0m');
"""
        self.run_node(script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
