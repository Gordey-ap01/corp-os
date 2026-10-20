"""Install scoped styling and bookmarks without replacing vault settings. Gordey_ap01."""
import argparse
from pathlib import Path
import shutil
import time

import corp
import obsidian_hq


def setup(vault, executable):
    vault, executable = Path(vault).resolve(), Path(executable).resolve()
    if not (vault / ".obsidian").is_dir() or not executable.is_file():
        raise ValueError("Нужны существующие хранилище и Obsidian.exe.")
    state = corp.ROOT / ".local"
    result = obsidian_hq.sync(state, vault)
    if result["conflicts"]:
        raise ValueError("Сначала сверить конфликты: " + ", ".join(result["conflicts"]))
    config = corp.load_config(state)
    config["obsidian"]["executable"] = str(executable)
    corp.write_json(state / "config.json", config)
    settings = vault / ".obsidian"
    backup = state / "obsidian-backups" / str(time.time_ns())
    backup.mkdir(parents=True)
    for name in ["app.json", "appearance.json", "bookmarks.json", "workspace.json"]:
        if (settings / name).is_file():
            shutil.copy2(settings / name, backup / name)
    snippet = settings / "snippets/personal-corp.css"
    if snippet.exists():
        shutil.copy2(snippet, backup / "personal-corp.css")
    corp.atomic_write(snippet, (corp.ROOT / "ui/obsidian.css").read_text(encoding="utf-8"))
    appearance = corp.read_json(settings / "appearance.json") if (settings / "appearance.json").exists() else {}
    enabled = appearance.setdefault("enabledCssSnippets", [])
    if "personal-corp" not in enabled:
        enabled.append("personal-corp")
    corp.write_json(settings / "appearance.json", appearance)
    preferences = corp.read_json(settings / "app.json") if (settings / "app.json").exists() else {}
    preferences["defaultViewMode"] = "preview"
    corp.write_json(settings / "app.json", preferences)
    bookmarks = corp.read_json(settings / "bookmarks.json") if (settings / "bookmarks.json").exists() else {"items": []}
    group_name = "Штаб — Gordey_ap01"
    if not any(item.get("title") == group_name for item in bookmarks["items"]):
        bookmarks["items"].insert(0, {"type": "group", "title": group_name, "ctime": int(time.time() * 1000), "items": [
            {"type": "file", "path": "Штаб/" + name, "title": title, "ctime": int(time.time() * 1000)}
            for name, title in [("Сегодня.md", "Сегодня"), ("Проекты/Портфель.base", "Проекты · доска"),
                                ("Входящие.md", "Записать мысль"), ("Обзоры.md", "Обзоры"),
                                ("Мои решения.md", "Мои решения")]
        ]})
    corp.write_json(settings / "bookmarks.json", bookmarks)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    print(setup(args.vault, args.executable))
