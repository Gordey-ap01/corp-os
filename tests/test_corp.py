"""Behavior and persistence checks for Personal Corp. Gordey_ap01."""
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys
import tempfile
import unittest

import corp


class HQTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.source = self.root / "portfolio.json"
        folder = self.root / "available"
        folder.mkdir()
        corp.write_json(self.source, {"checked_at": "2026-10-18T21:07:00+10:00", "projects": [
            {"label": "Available", "path": str(folder)},
            {"label": "Missing", "path": str(self.root / "missing")},
            {"label": "Cloud", "path": None},
        ], "github": []})
        self.original_source = self.source.read_bytes()
        corp.init(self.state, self.source)

    def tearDown(self):
        self.temp.cleanup()

    def add(self, task_id="PC-001"):
        return corp.add_task(self.state, SimpleNamespace(id=task_id, title="Useful result", department="hq", priority=1, acceptance="An existing usable file"))

    def test_inventory_preserves_canonical_source_and_cloud_distinction(self):
        inv = corp.refresh(self.state)
        self.assertEqual([p["folder_available_now"] for p in inv["projects"]], [True, False, None])
        self.assertEqual(self.source.read_bytes(), self.original_source)
        self.assertEqual(inv["portfolio_checked_at"], "2026-10-18T21:07:00+10:00")

    def test_init_will_not_overwrite_work(self):
        self.add()
        before = (self.state / "tasks.json").read_bytes()
        with self.assertRaises(ValueError):
            corp.init(self.state, self.source)
        self.assertEqual(before, (self.state / "tasks.json").read_bytes())

    def test_active_limit_and_resume_after_block(self):
        self.add()
        self.add("PC-002")
        corp.transition(self.state, "start", "PC-001")
        with self.assertRaises(ValueError):
            corp.transition(self.state, "start", "PC-002")
        corp.transition(self.state, "block", "PC-001", "Requires input")
        corp.transition(self.state, "start", "PC-002")
        corp.transition(self.state, "ready", "PC-001")
        self.assertEqual(corp.next_task(corp.load_tasks(self.state)["tasks"])["id"], "PC-002")

    def test_review_requires_file_and_acceptance_is_separate(self):
        self.add()
        corp.transition(self.state, "start", "PC-001")
        with self.assertRaises(ValueError):
            corp.transition(self.state, "review", "PC-001", evidence=str(self.root / "missing.txt"))
        proof = self.root / "proof.txt"
        proof.write_text("Actual result", encoding="utf-8")
        corp.transition(self.state, "review", "PC-001", evidence=str(proof))
        self.assertEqual(corp.load_tasks(self.state)["tasks"][0]["status"], "review")
        with self.assertRaises(ValueError):
            corp.transition(self.state, "accept", "PC-001")
        corp.transition(self.state, "accept", "PC-001", "Explicit owner decision (test fixture)")
        self.assertEqual(corp.load_tasks(self.state)["tasks"][0]["status"], "done")

    def test_missing_evidence_is_detected_before_acceptance(self):
        self.add()
        proof = self.root / "proof.txt"
        proof.write_text("Result", encoding="utf-8")
        corp.transition(self.state, "start", "PC-001")
        corp.transition(self.state, "review", "PC-001", evidence=str(proof))
        proof.unlink()
        self.assertTrue(any(not c["ok"] for c in corp.doctor(self.state)["checks"]))
        with self.assertRaises(ValueError):
            corp.transition(self.state, "accept", "PC-001", "Accept")

    def test_another_writer_is_rejected_without_losing_state(self):
        self.add()
        before = (self.state / "tasks.json").read_bytes()
        with corp.locked(self.state):
            with self.assertRaises(ValueError):
                self.add("PC-002")
        self.assertEqual(before, (self.state / "tasks.json").read_bytes())
        self.assertFalse((self.state / ".write-lock").exists())

    def test_fresh_cli_process_restores_persisted_queue(self):
        self.add()
        corp.transition(self.state, "start", "PC-001")
        result = subprocess.run([sys.executable, str(corp.ROOT / "corp.py"), "--state", str(self.state), "task", "list"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PC-001 [in_progress]", result.stdout)

    def test_dashboard_escapes_source_content_inside_script(self):
        inv = corp.read_json(self.state / "inventory.json")
        inv["projects"][0]["label"] = '</script><img src=x onerror="alert(1)">'
        corp.write_json(self.state / "inventory.json", inv)
        page = Path(corp.dashboard(self.state)).read_text(encoding="utf-8")
        self.assertNotIn('</script><img', page)
        payload = page.split('<script type="application/json" id="corp-data">', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(payload)["inventory"]["projects"][0]["label"], inv["projects"][0]["label"])


if __name__ == "__main__":
    unittest.main()
