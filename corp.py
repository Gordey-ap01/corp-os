"""Local Personal Corp HQ. Gordey_ap01. Standard library only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
STATUSES = {"ready", "in_progress", "review", "done", "blocked"}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".corp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def locked(state):
    lock = state / ".write-lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Штаб уже изменяется другим процессом. Повторите после его завершения; не удаляйте активную блокировку.")
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def load_config(state):
    path = state / "config.json"
    if not path.exists():
        raise ValueError("Штаб не настроен. Выполните init --portfolio ПУТЬ.")
    return read_json(path)


def load_tasks(state):
    value = read_json(state / "tasks.json")
    tasks = value["tasks"]
    if len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("В очереди повторяются идентификаторы задач.")
    if any(t["status"] not in STATUSES for t in tasks):
        raise ValueError("В очереди неизвестное состояние задачи.")
    if sum(t["status"] == "in_progress" for t in tasks) > 1:
        raise ValueError("В очереди больше одной активной задачи.")
    return value


def init(state, portfolio):
    source = Path(portfolio).resolve()
    data = read_json(source)
    if not isinstance(data.get("projects"), list) or not isinstance(data.get("github", []), list):
        raise ValueError("Портфель должен содержать массив projects и, при наличии, github.")
    state.mkdir(parents=True, exist_ok=True)
    with locked(state):
        if (state / "config.json").exists() or (state / "tasks.json").exists():
            raise ValueError("Настройка уже существует; init не перезаписывает состояние.")
        write_json(state / "tasks.json", {"brand": "Gordey_ap01", "tasks": []})
        write_json(state / "config.json", {"brand": "Gordey_ap01", "portfolio": str(source), "created_at": now(), "resources": []})
    refresh(state)


def refresh(state):
    config = load_config(state)
    source = Path(config["portfolio"])
    raw = read_json(source)
    projects = []
    for item in raw["projects"]:
        p = dict(item)
        folder = p.get("path")
        p["folder_available_now"] = Path(folder).is_dir() if folder else None
        projects.append(p)
    inventory = {"brand": config["brand"], "generated_at": now(), "portfolio_checked_at": raw.get("checked_at", raw.get("checked_on", "не указано")), "source": str(source), "coverage": raw.get("coverage", {}), "projects": projects, "github": raw.get("github", []), "scope": "Импорт существующего обзора и проверка наличия папок. Приложения, публикации и история чатов повторно не испытывались."}
    with locked(state):
        write_json(state / "inventory.json", inventory)
    return inventory


def ordered(tasks):
    return sorted(tasks, key=lambda t: (t.get("priority", 3), t["id"]))


def next_task(tasks):
    active = [t for t in tasks if t["status"] == "in_progress"]
    return (active or ordered([t for t in tasks if t["status"] == "ready"]) or [None])[0]


def transition(state, action, task_id, note="", evidence=None):
    with locked(state):
        data = load_tasks(state)
        task = next((t for t in data["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise ValueError("Нет задачи с таким идентификатором.")
        before = task["status"]
        if action == "start":
            if before != "ready":
                raise ValueError("Начать можно только готовую задачу.")
            if any(t["status"] == "in_progress" for t in data["tasks"]):
                raise ValueError("Уже есть активная задача. Сначала завершите или приостановите её.")
            after = "in_progress"
        elif action == "review":
            if before != "in_progress":
                raise ValueError("На проверку передаётся активная задача.")
            proof = Path(evidence or "").resolve()
            if not evidence or not proof.is_file():
                raise ValueError("Нужен существующий файл результата --evidence.")
            task.setdefault("evidence", []).append(str(proof))
            after = "review"
        elif action == "accept":
            if before != "review" or not note.strip():
                raise ValueError("Приёмка требует review и текст решения владельца --note.")
            if not all(Path(p).is_file() for p in task.get("evidence", [])) or not task.get("evidence"):
                raise ValueError("Доказательство результата недоступно; приёмка остановлена.")
            after = "done"
        elif action == "block":
            if before not in {"ready", "in_progress"} or not note.strip():
                raise ValueError("Пауза требует ready/in_progress и причину --note.")
            after = "blocked"
        elif action == "ready":
            if before != "blocked":
                raise ValueError("Возобновить можно только задачу blocked.")
            after = "ready"
        else:
            raise ValueError("Неизвестное действие.")
        task["status"] = after
        task["updated_at"] = now()
        task.setdefault("history", []).append({"at": now(), "from": before, "to": after, "note": note})
        write_json(state / "tasks.json", data)
    return task


def add_task(state, args):
    with locked(state):
        data = load_tasks(state)
        if any(t["id"] == args.id for t in data["tasks"]):
            raise ValueError("Такой идентификатор уже существует.")
        task = {"id": args.id, "title": args.title, "department": args.department, "assignee": getattr(args, "assignee", "agent"), "priority": args.priority, "status": "ready", "acceptance": args.acceptance, "created_at": now(), "evidence": [], "history": [{"at": now(), "to": "ready", "note": "Задача создана"}]}
        data["tasks"].append(task)
        write_json(state / "tasks.json", data)
    return task


def daily(state):
    config = load_config(state)
    inv = read_json(state / "inventory.json")
    tasks = load_tasks(state)["tasks"]
    focus = next_task(tasks)
    lines = [f"# День Personal Corp — {config['brand']}", "", f"Обзор сформирован: {now()}", f"Источник портфеля: {inv['portfolio_checked_at']}; импорт: {inv['generated_at']}", "", "## Один следующий результат", ""]
    if focus:
        lines += [f"**{focus['id']} · {focus['title']}**", f"Исполнитель: {'владелец' if focus.get('assignee') == 'owner' else 'агент'}", f"Критерий: {focus['acceptance']}"]
    else:
        lines += ["Готовых задач нет. Проверьте результаты в review; не выдумывайте новый приоритет."]
    lines += ["", "## Ожидают проверки владельца", ""]
    review = [t for t in tasks if t["status"] == "review"]
    lines += [f"- {t['id']}: {t['title']} · {', '.join(t.get('evidence', []))}" for t in ordered(review)] or ["Нет."]
    lines += ["", "## Ограничения", "", inv["scope"], "Запущенного фонового исполнителя нет. Новые поручения выполняются при открытии чата и явном запуске. Измеренная экономия времени и бизнес-эффект пока неизвестны.", "", "## Пауза и зависимости", ""]
    lines += [f"- {t['id']}: {t['title']} — {t.get('history', [{}])[-1].get('note', '')}" for t in tasks if t["status"] == "blocked"] or ["Нет."]
    result = "\n".join(lines) + "\n"
    atomic_write(state / "daily.md", result)
    return result


def retro(state):
    tasks = load_tasks(state)["tasks"]
    counts = {s: sum(t["status"] == s for t in tasks) for s in sorted(STATUSES)}
    report = {"brand": "Gordey_ap01", "at": now(), "counts": counts, "measured_time_saved": None, "business_outcome": None, "note": "review — подготовлено агентом, done — принято владельцем. Нет оснований считать число задач экономией времени."}
    write_json(state / "retro.json", report)
    return json.dumps(report, ensure_ascii=False, indent=2)


def dashboard(state):
    config = load_config(state)
    inv = read_json(state / "inventory.json")
    tasks = load_tasks(state)["tasks"]
    observations = read_json(state / "observations.json") if (state / "observations.json").exists() else []
    command = f'python "{(ROOT / "corp.py").as_posix()}" --state "{state.as_posix()}"'
    payload = {"config": config, "inventory": inv, "tasks": tasks, "observations": observations, "built_at": now(), "next": next_task(tasks), "runtime": {"root": ROOT.as_posix(), "command": command}}
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (ROOT / "ui/index.html").read_text(encoding="utf-8")
    result = template.replace("/*__STYLE__*/", (ROOT / "ui/style.css").read_text(encoding="utf-8")).replace("/*__APP__*/", (ROOT / "ui/app.js").read_text(encoding="utf-8")).replace("__CORP_DATA__", encoded)
    atomic_write(state / "dashboard.html", result)
    return str(state / "dashboard.html")


def doctor(state):
    config = load_config(state)
    tasks = load_tasks(state)["tasks"]
    checks = []
    source = Path(config["portfolio"])
    checks.append({"name": "Источник портфеля доступен", "ok": source.is_file()})
    checks.append({"name": "Одна активная задача или ни одной", "ok": sum(t["status"] == "in_progress" for t in tasks) <= 1})
    for t in tasks:
        if t["status"] in {"review", "done"}:
            checks.append({"name": f"{t['id']}: файл результата доступен", "ok": bool(t.get("evidence")) and all(Path(p).is_file() for p in t["evidence"])})
    inv = read_json(state / "inventory.json")
    missing = [p["label"] for p in inv["projects"] if p.get("path") and not Path(p["path"]).is_dir()]
    result = {"brand": config["brand"], "at": now(), "checks": checks, "missing_project_folders": missing, "portfolio_checked_at": inv["portfolio_checked_at"], "note": "Отсутствующая папка — пробел обзора, а не разрешение удалить или считать проект завершённым."}
    write_json(state / "doctor.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description="Personal Corp — Gordey_ap01")
    parser.add_argument("--state", type=Path, default=ROOT / ".local")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("--portfolio", required=True)
    for name in ["refresh", "doctor", "daily", "dashboard", "retro"]:
        sub.add_parser(name)
    p = sub.add_parser("task")
    actions = p.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    a = actions.add_parser("add")
    for key in ["id", "title", "department", "acceptance"]:
        a.add_argument("--" + key, required=True)
    a.add_argument("--priority", type=int, choices=range(1, 6), default=3)
    a.add_argument("--assignee", choices=["agent", "owner"], default="agent")
    for action in ["start", "review", "accept", "block", "ready"]:
        a = actions.add_parser(action)
        a.add_argument("id")
        a.add_argument("--note", default="")
        if action == "review":
            a.add_argument("--evidence", required=True)
    args = parser.parse_args()
    state = args.state.resolve()
    try:
        if args.command == "init":
            init(state, args.portfolio)
            print("Штаб создан. Gordey_ap01")
        elif args.command == "refresh":
            value = refresh(state)
            print(f"Импортировано проектов: {len(value['projects'])}; репозиториев: {len(value['github'])}. Источник: {value['portfolio_checked_at']}")
        elif args.command == "task":
            if args.action == "list":
                for t in ordered(load_tasks(state)["tasks"]):
                    print(f"{t['id']} [{t['status']}] {t['title']}")
            else:
                task = add_task(state, args) if args.action == "add" else transition(state, args.action, args.id, args.note, getattr(args, "evidence", None))
                print(f"{task['id']} → {task['status']}")
        elif args.command == "doctor":
            value = doctor(state)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0 if all(c["ok"] for c in value["checks"]) else 1
        else:
            print({"daily": daily, "dashboard": dashboard, "retro": retro}[args.command](state))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
