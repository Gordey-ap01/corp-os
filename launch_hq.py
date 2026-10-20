"""One-click local HQ launcher; suitable for pythonw. Gordey_ap01."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import traceback

import corp
import obsidian_hq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Refresh and validate without opening a window")
    args = parser.parse_args()
    state = corp.ROOT / ".local"
    try:
        corp.refresh(state)
        corp.daily(state)
        corp.dashboard(state)
        result = obsidian_hq.sync(state)
        if result["conflicts"]:
            raise ValueError("Сохранены ваши изменения; автоматически не обновлены: " +
                             ", ".join(result["conflicts"]) +
                             ". Новые версии для сверки: .local/obsidian-conflicts.")
        if not args.check:
            if args.browser:
                os.startfile(str(state / "dashboard.html"))
            else:
                config = corp.load_config(state)["obsidian"]
                executable = config.get("executable")
                if not executable or not Path(executable).is_file():
                    raise ValueError("Программа Obsidian не найдена. Проверьте executable в настройке штаба.")
                subprocess.Popen([executable, obsidian_hq.open_uri(config["vault"])])
        corp.write_json(state / "launcher-status.json", {"ok": True, "at": corp.now(), "home": result["home"]})
        return 0
    except Exception as exc:
        corp.atomic_write(state / "launcher-error.log", traceback.format_exc())
        corp.write_json(state / "launcher-status.json", {"ok": False, "at": corp.now(), "error": str(exc)})
        if args.check:
            if sys.stderr:
                print(str(exc), file=sys.stderr)
        else:
            from tkinter import Tk, messagebox
            root = Tk()
            root.withdraw()
            messagebox.showerror("Штаб — Gordey_ap01", f"Обновление требует внимания:\n\n{exc}\n\nПодробности: {state / 'launcher-error.log'}")
            root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
