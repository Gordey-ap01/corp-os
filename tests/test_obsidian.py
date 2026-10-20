"""Safety of the Obsidian projection; all fixtures are temporary. Gordey_ap01."""
from pathlib import Path
import tempfile
import unittest

import corp
import obsidian_hq as obs


class ObsidianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.source = self.root / "portfolio" / "snapshot.json"
        corp.write_json(self.source, {"checked_at": "2026-10-20T21:00:00+10:00",
                                     "projects": [{"projectId": "p1", "label": "Первый",
                                                   "paused_scopes": ["Print remains paused"],
                                                   "next_goals_proposed": ["a", "b", "c"]}],
                                     "github": []})
        corp.init(self.state, self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_refresh_keeps_owner_properties_notes_and_source(self):
        source_before = self.source.read_bytes()
        obs.sync(self.state, self.vault)
        card = self.vault / "Штаб/Проекты/Карточки/Первый.md"
        edited = card.read_text(encoding="utf-8").replace('Мой этап: "Разобрать"', 'Мой этап: "Ожидаю"')
        edited = edited.replace("Фокус: false", "Фокус: true") + "\nМоё решение — сохранить.\n"
        card.write_text(edited, encoding="utf-8")
        data = corp.read_json(self.source)
        data["projects"][0]["stage"] = "Новый факт"
        corp.write_json(self.source, data)
        corp.refresh(self.state)
        result = obs.sync(self.state)
        self.assertFalse(result["conflicts"])
        current = card.read_text(encoding="utf-8")
        for expected in ['Мой этап: "Ожидаю"', "Фокус: true", "Моё решение — сохранить.", "Новый факт", "Print remains paused"]:
            self.assertIn(expected, current)
        self.assertNotEqual(self.source.read_bytes(), source_before)
        self.assertEqual(corp.read_json(self.source), data)

    def test_repeat_is_idempotent_and_does_not_accept_tasks(self):
        before_tasks = (self.state / "tasks.json").read_bytes()
        obs.sync(self.state, self.vault)
        result = obs.sync(self.state)
        self.assertEqual(result["written"], 0)
        self.assertEqual((self.state / "tasks.json").read_bytes(), before_tasks)

    def test_modified_generated_region_is_not_overwritten(self):
        obs.sync(self.state, self.vault)
        home = self.vault / "Штаб/Сегодня.md"
        edited = home.read_text(encoding="utf-8").replace("# Сегодня", "# Сегодня — моя правка")
        home.write_text(edited, encoding="utf-8")
        result = obs.sync(self.state)
        self.assertIn("Сегодня.md", result["conflicts"])
        self.assertEqual(home.read_text(encoding="utf-8"), edited)
        self.assertTrue(list((self.state / "obsidian-conflicts").glob("*.md")))

    def test_unknown_existing_file_and_unrelated_notes_are_preserved(self):
        path = self.vault / "Штаб/Сегодня.md"
        path.parent.mkdir()
        path.write_text("Existing personal note", encoding="utf-8")
        other = self.vault / "Другие записи.md"
        other.write_text("Unrelated", encoding="utf-8")
        result = obs.sync(self.state, self.vault)
        self.assertIn("Сегодня.md", result["conflicts"])
        self.assertEqual(path.read_text(encoding="utf-8"), "Existing personal note")
        self.assertEqual(other.read_text(encoding="utf-8"), "Unrelated")

    def test_path_escape_and_nonvault_are_rejected(self):
        writer = obs.Writer(self.state, self.vault)
        with self.assertRaises(ValueError):
            writer.seed("../outside.md", "bad")
        with self.assertRaises(ValueError):
            obs.Writer(self.state, self.root)
        self.assertFalse((self.vault / "outside.md").exists())

    def test_custom_base_and_inbox_survive_refresh(self):
        obs.sync(self.state, self.vault)
        paths = ["Проекты/Портфель.base", "Входящие.md", "Мои решения.md"]
        for relative in paths:
            (self.vault / "Штаб" / relative).write_text("Owner custom content", encoding="utf-8")
        obs.sync(self.state)
        for relative in paths:
            self.assertEqual((self.vault / "Штаб" / relative).read_text(encoding="utf-8"), "Owner custom content")

    def test_mirrored_relative_links_open_the_original_location(self):
        source = self.root / "notes" / "idea.md"
        source.parent.mkdir()
        source.write_text("[Proposal](../proposals/design.md#details)\n[Web](https://example.org)\n", encoding="utf-8")
        mirrored = obs.mirror_markdown(source)
        self.assertIn((self.root / "proposals/design.md").as_uri() + "#details", mirrored)
        self.assertIn("[Web](https://example.org)", mirrored)


if __name__ == "__main__":
    unittest.main()
