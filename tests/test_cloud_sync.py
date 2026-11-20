"""Static security and wiring checks for optional FORMA Firebase Cloud Sync."""
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


class CloudSyncTests(unittest.TestCase):
    def test_firebase_module_is_loaded_after_the_classic_frontend(self):
        html = (PROJECT / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="js/app.js"></script>', html)
        self.assertIn('<script type="module" src="js/cloud-sync.js"></script>', html)
        self.assertLess(html.index('<script src="js/app.js"></script>'), html.index('<script type="module" src="js/cloud-sync.js"></script>'))

    def test_firestore_rules_are_uid_scoped_and_not_public(self):
        rules = (PROJECT / "firestore.rules").read_text(encoding="utf-8")
        self.assertIn("request.auth != null && request.auth.uid == uid", rules)
        self.assertIn("match /users/{uid}/items/{itemId}", rules)
        self.assertIn("allow read: if ownsAccount(uid)", rules)
        self.assertIn("allow create, update: if ownsAccount(uid) && validItem()", rules)
        self.assertIn("allow delete: if ownsAccount(uid)", rules)
        self.assertNotIn("allow read, write: if true", rules)

    def test_public_firebase_config_contains_only_setup_placeholders(self):
        config = (PROJECT / "js" / "firebase-config.js").read_text(encoding="utf-8")
        self.assertIn("YOUR_FIREBASE_API_KEY", config)
        self.assertIn("YOUR_PROJECT_ID", config)
        self.assertNotIn("BEGIN PRIVATE KEY", config)
        self.assertNotIn("private_key", config)

    def test_cloud_sync_is_per_user_and_uses_document_level_realtime_updates(self):
        source = (PROJECT / "js" / "cloud-sync.js").read_text(encoding="utf-8")
        self.assertIn("collection(firestore, 'users', user.uid, 'items')", source)
        self.assertIn("onSnapshot(", source)
        self.assertIn("writeBatch(firestore)", source)
        self.assertIn("localStorage.getItem(OWNER_KEY)", source)
        self.assertIn("forma:local-change", source)
        self.assertIn("persistentLocalCache", source)

    def test_static_host_does_not_poll_the_local_python_api(self):
        source = (PROJECT / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("['localhost','127.0.0.1'].includes(window.location.hostname)", source)
        self.assertIn("window.FORMACloudBridge", source)
