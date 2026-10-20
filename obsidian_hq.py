"""Native Obsidian views over the existing HQ. Gordey_ap01.

Only generated regions are refreshed. Owner properties, notes and view settings
are never imported as task acceptance or overwritten by a portfolio refresh.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

import corp

START = "<!-- personal-corp:begin -->"
END = "<!-- personal-corp:end -->"
FOLDER = "Штаб"
BRAND = "Gordey_ap01"
STATUS = {
    "ready": "Готово к работе", "in_progress": "В работе",
    "review": "На вашей проверке", "blocked": "Ожидает зависимости",
    "done": "Принято владельцем",
}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text(value):
    if value is None or value == "":
        return "данных пока нет"
    if isinstance(value, list):
        return "\n".join("- " + text(v) for v in value) or "данных пока нет"
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {text(v)}" for k, v in value.items())
    # Imported text cannot create sync boundaries.
    return str(value).replace(START, "").replace(END, "")


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#^]', "-", str(value)).strip(" .")[:100]
    if not name or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", name):
        name = "Проект-" + digest(str(value))[:8]
    return name


def wiki(path, label=None):
    return f"[[{FOLDER}/{path}|{label or Path(path).stem}]]"


def file_link(label, path):
    uri = Path(path).resolve().as_uri()
    return f"[{str(label).replace('[', '').replace(']', '')}](<{uri}>)"


def mirror_markdown(source):
    """Keep relative links pointing to their original files after projection."""
    content = source.read_text(encoding="utf-8-sig")

    def absolute_link(match):
        target = match.group(2).strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            return match.group(0)
        filename, _, fragment = target.partition("#")
        uri = (source.parent / filename).resolve().as_uri()
        if fragment:
            uri += "#" + quote(fragment, safe="")
        return f"[{match.group(1)}](<{uri}>)"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", absolute_link, content)


def open_uri(vault, relative="Сегодня.md"):
    return "obsidian://open?path=" + quote(str(Path(vault) / FOLDER / relative), safe="")


def navigation():
    return " · ".join(wiki(p) for p in ["Сегодня.md", "Проекты.md", "Задачи.md", "Идеи.md", "Обзоры.md"]) + "\n\n"


def frontmatter(kind="страница", **properties):
    classes = ["personal-corp"] + (["personal-corp-page"] if kind == "страница" else [])
    props = {"автор": BRAND, "тип": kind, "cssclasses": classes, **properties}
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in props.items()) + "\n---\n\n"


class Writer:
    """Conservative writer: reject unknown files and preserve edited regions."""

    def __init__(self, state, vault):
        self.state = state
        self.vault = Path(vault).resolve()
        if not (self.vault / ".obsidian").is_dir():
            raise ValueError("Выберите существующее хранилище Obsidian с папкой .obsidian.")
        self.root = self.vault / FOLDER
        if self.root.is_symlink() or (self.root.exists() and self.root.resolve().parent != self.vault):
            raise ValueError("Раздел штаба должен находиться внутри выбранного хранилища.")
        self.manifest_path = state / "obsidian-manifest.json"
        self.manifest = corp.read_json(self.manifest_path) if self.manifest_path.exists() else {
            "vault": str(self.vault), "files": {}, "project_files": {},
        }
        if Path(self.manifest["vault"]).resolve() != self.vault:
            raise ValueError("Штаб уже подключён к другому хранилищу. Сначала сверить перенос.")
        self.conflicts = []
        self.written = 0

    def target(self, relative):
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("Путь выходит за пределы раздела Штаб.")
        return target

    def conflict(self, relative, incoming):
        self.conflicts.append(relative)
        target = self.state / "obsidian-conflicts" / (digest(relative)[:12] + ".md")
        corp.atomic_write(target, f"# {relative} — {BRAND}\n\n" + incoming)

    def note(self, relative, body, properties=None, owner_section=True):
        path = self.target(relative)
        body = body.replace(START, "").replace(END, "").strip() + "\n"
        block = START + "\n" + body + END
        previous = self.manifest["files"].get(relative)
        if path.exists():
            existing = path.read_text(encoding="utf-8-sig")
            if not previous or existing.count(START) != 1 or existing.count(END) != 1:
                self.conflict(relative, body)
                return
            begin, end = existing.index(START), existing.index(END) + len(END)
            if end <= begin or digest(existing[begin:end]) != previous["hash"]:
                self.conflict(relative, body)
                return
            updated = existing[:begin] + block + existing[end:]
        else:
            updated = (properties or frontmatter()) + block + "\n"
            if owner_section:
                updated += "\n## Мои заметки\n\nЗдесь можно писать: обновление штаба сохраняет этот раздел.\n"
        if not path.exists() or updated != path.read_text(encoding="utf-8-sig"):
            if path.exists():
                current = path.read_text(encoding="utf-8-sig")
                if current != existing:
                    self.conflict(relative, body)
                    return
                # Recovery copy also covers edits made just before refresh.
                backup = self.state / "obsidian-backups" / "previous" / (digest(relative)[:12] + ".md")
                corp.atomic_write(backup, current)
            corp.atomic_write(path, updated)
            self.written += 1
        self.manifest["files"][relative] = {"hash": digest(block)}
        # Checkpoint after each file: retry after an interrupted run is safe.
        corp.write_json(self.manifest_path, self.manifest)

    def seed(self, relative, content):
        path = self.target(relative)
        # Base settings and free-form owner notes belong to the owner thereafter.
        if not path.exists():
            corp.atomic_write(path, content)
            self.written += 1

    def project_file(self, project, index):
        key = str(project.get("projectId") or project.get("path") or project["label"])
        paths = self.manifest["project_files"]
        if key not in paths:
            candidate = f"Проекты/Карточки/{safe_name(project['label'])}.md"
            if candidate in paths.values() or self.target(candidate).exists():
                candidate = f"Проекты/Карточки/{safe_name(project['label'])}-{digest(key)[:8]}.md"
            paths[key] = candidate
        return paths[key]


def project_body(project, stamp):
    review = project.get("latest_review", {})
    lines = [navigation(), f"# {text(project['label'])}", f"**{BRAND}** · Факты из обзора: {stamp}", "",
             "> [!info] Ваши решения",
             "> Свой этап, следующий шаг и фокус меняйте в свойствах карточки или в таблице проектов. Они сохраняются при обновлении. Это план владельца; он не запускает разработку и не меняет приёмку.", "",
             "## Этап и ожидание", text(project.get("stage")), "", text(project.get("recommendation")),
             "", "## Подтверждено в обзоре", text(review.get("done")), "",
             "## Осталось", text(review.get("remaining")), "", "## Три предложенные цели"]
    for i, goal in enumerate(project.get("next_goals_proposed", [])[:3], 1):
        lines.append(f"{i}. {text(goal)}")
    lines += ["", "## Метрики", text(review.get("metrics")), "", "## Гипотеза улучшения", text(review.get("hypothesis"))]
    if project.get("paused_scopes"):
        lines += ["", "> [!warning] Сохранённые паузы и ограничения",
                  *["> " + line for line in text(project["paused_scopes"]).splitlines()]]
    lines += ["", "## Источники"]
    if project.get("path"):
        lines.append(file_link("Папка проекта", project["path"]))
    for source in project.get("sources", []):
        if source.get("path"):
            lines.append("- " + file_link(Path(source["path"]).name, source["path"]))
    lines += ["", wiki("Обзоры.md", "Полный обзор: ресурсы, ограничения и источники")]
    return "\n".join(lines)


def base_config():
    return """# Personal Corp — Gordey_ap01
filters:
  and:
    - file.inFolder("Штаб/Проекты/Карточки")
    - 'тип == "проект"'
properties:
  file.name:
    displayName: Проект
views:
  - type: cards
    name: Доска
    groupBy:
      property: note.Мой этап
      direction: ASC
    order:
      - file.name
      - note.Следующий шаг
      - note.Фокус
    cardSize: 280
  - type: table
    name: Таблица
    order:
      - file.name
      - note.Мой этап
      - note.Следующий шаг
      - note.Фокус
  - type: cards
    name: Мой фокус
    filters:
      and:
        - 'Фокус == true'
    order:
      - file.name
      - note.Следующий шаг
    cardSize: 280
"""


def sync(state, vault=None):
    config = corp.load_config(state)
    vault = vault or config.get("obsidian", {}).get("vault")
    if not vault:
        raise ValueError("Не задано хранилище. Выполните obsidian --vault ПУТЬ.")
    with corp.locked(state):
        writer = Writer(state, vault)
        inv = corp.read_json(state / "inventory.json")
        tasks = corp.load_tasks(state)["tasks"]
        stamp = inv["portfolio_checked_at"]
        for index, project in enumerate(inv["projects"]):
            relative = writer.project_file(project, index)
            props = frontmatter("проект", **{
                "project_id": project.get("projectId", ""),
                "Мой этап": "Разобрать", "Следующий шаг": "", "Фокус": False,
            })
            writer.note(relative, project_body(project, stamp), props)
        writer.seed("Проекты/Портфель.base", base_config())
        writer.note("Проекты.md", navigation() + f"""# Проекты
**{BRAND}** · Ваш портфель и точка продолжения

[[Штаб/Проекты/Портфель.base|Открыть доску и таблицу на весь экран ↗]]

> [!tip] Как пользоваться доской
> Откройте карточку и измените «Мой этап»: Разобрать, Фокус, Ожидаю или Пауза. Карточки группируются по этому свойству. В виде «Таблица» можно менять его прямо в ячейке. Галочка «Фокус» выводит проект на «Сегодня».
>
> Начальные этапы «Разобрать» — пустой личный план, не оценка готовности проектов. Ограничения из обзора находятся внутри карточек.

![[Штаб/Проекты/Портфель.base#Доска]]
""")
        for task in tasks:
            evidence = "\n".join("- " + file_link("Открыть результат", p) for p in task.get("evidence", [])) or "Файл результата ещё не приложен."
            if task.get("reference"):
                evidence += "\n\n" + file_link("Материал для этой задачи", task["reference"])
            writer.note(f"Задачи/{safe_name(task['id'])}.md", navigation() + f"""# {text(task['title'])}
**{BRAND}** · {task['id']} · **{STATUS[task['status']]}**

Исполнитель: {"владелец" if task.get("assignee") == "owner" else "агент"}

## Ожидаемый результат
{text(task.get('acceptance'))}

## Доказательства
{evidence}

## Последняя запись
{text(task.get('history', [{}])[-1].get('note'))}

Состояние берётся из Personal Corp. Отзыв пишите ниже или в «Мои решения». Приёмку владельца агент фиксирует отдельным действием после вашего решения.
""")
        task_lines = [navigation(), "# Задачи и результаты", f"**{BRAND}**", ""]
        for status, label in STATUS.items():
            relevant = [t for t in tasks if t["status"] == status]
            if relevant:
                task_lines += [f"## {label}", ""]
                task_lines += ["- " + wiki(f"Задачи/{safe_name(t['id'])}.md", f"{t['id']} · {t['title']}") for t in relevant]
                task_lines += [""]
        writer.note("Задачи.md", "\n".join(task_lines))

        source_root = Path(config["portfolio"]).parent.parent
        report_links = []
        for filename in ["ПРОЕКТЫ.md", "АНАЛИТИКА.md"]:
            source = source_root / filename
            if source.is_file():
                writer.note(f"Обзоры/{filename}", navigation() +
                            f"> Снимок исходного файла. {file_link('Оригинал', source)}. Обновляется при открытии штаба.\n\n" + mirror_markdown(source))
                report_links.append("- " + wiki(f"Обзоры/{filename}", "Все проекты" if filename == "ПРОЕКТЫ.md" else "Аналитика идей"))
        writer.note("Обзоры.md", navigation() + f"""# Обзоры
**{BRAND}**

Портфель проверен: **{stamp}**. Представление обновлено: {inv['generated_at']}.

{chr(10).join(report_links) or "Файлы обзоров пока недоступны."}

{inv['scope']}

Расписание куратора остаётся прежним. Обновление представления не означает новый обход проектов.
""")
        idea_links = []
        notes_dir = source_root / "наброски"
        if notes_dir.is_dir():
            for source in sorted(notes_dir.glob("*.md")):
                writer.note(f"Идеи/Источники/{source.name}", navigation() +
                            f"> {file_link('Исходная карточка', source)} · Представление из набросков.\n\n" +
                            mirror_markdown(source))
                idea_links.append("- " + wiki(f"Идеи/Источники/{source.name}", source.stem))
        writer.note("Идеи.md", navigation() + f"""# Идеи
**{BRAND}**

[[Штаб/Входящие|Записать новую мысль ↗]]

## Сохранённые наброски
{chr(10).join(idea_links) or "Набросков пока нет."}

Новая мысль остаётся записью. Поручение на разработку — отдельное решение.
""")
        writer.seed("Входящие.md", frontmatter() + f"""# Входящие — {BRAND}

{navigation()}Записывайте новые мысли свободно. Этот файл принадлежит вам и не перезаписывается при обновлении. Для переноса в наброски скажите в чате: «Разбери входящие штаба».

## Новые мысли

""")
        writer.seed("Мои решения.md", frontmatter() + f"""# Мои решения — {BRAND}

{navigation()}Здесь можно записать выбранный фокус, отзыв на результат или конкретное поручение. При следующем обращении попросите агента прочитать этот журнал. Запись не запускает агента автоматически.

## Журнал

""")
        focus = corp.next_task(tasks)
        focus_link = wiki(f"Задачи/{safe_name(focus['id'])}.md", focus["title"]) if focus else "Готовых задач нет."
        reviews = [t for t in corp.ordered(tasks) if t["status"] == "review"]
        review_links = "\n".join("- " + wiki(f"Задачи/{safe_name(t['id'])}.md", t["title"]) for t in reviews) or "Нет результатов, ожидающих проверки."
        writer.note("Сегодня.md", navigation() + f"""# Сегодня
**{BRAND}** · Личный штаб Personal Corp

> [!abstract] Один следующий шаг
> {focus_link}
>
> {text(focus.get('acceptance')) if focus else 'Можно просмотреть результаты и выбрать дальнейшее направление.'}

[[Штаб/Входящие|＋ Записать мысль]] · [[Штаб/Мои решения|Оставить решение]] · [[Штаб/Обзоры|Читать обзор]]

## Мой фокус
Отметьте «Фокус» у выбранного проекта в таблице. Здесь появятся отмеченные карточки.

![[Штаб/Проекты/Портфель.base#Мой фокус]]

## Ждут вашей проверки
{review_links}

## Свежесть данных
**{len(inv['projects'])} проектов** в источнике · **{len(inv['github'])} репозиториев** · обзор **{stamp}**

Представление обновлено: {inv['generated_at']}. Это импорт прежнего обзора; повторная проверка приложений не запускалась.

[[Штаб/Как пользоваться|Как работать со штабом →]]
""")
        writer.note("Как пользоваться.md", navigation() + f"""# Как пользоваться штабом
**{BRAND}**

1. Откройте ярлык **Штаб — Gordey_ap01** на рабочем столе. Он обновит представление и откроет «Сегодня».
2. В **Проектах** переключайтесь между доской и таблицей. Меняйте «Мой этап», «Следующий шаг» и «Фокус» — это ваши сохранённые решения. Доска группирует карточки; перенос между группами выполняется изменением свойства.
3. В **Задачах** откройте файл результата, затем напишите отзыв в «Мои решения».
4. Новую мысль запишите во **Входящие**. Для обработки скажите агенту: «Прочитай входящие и решения в моём Obsidian».
5. В **Обзорах** находятся полные отчёты с датами и ограничениями проверки.

## Что обновляется
Сводки проектов, результаты и обзоры берутся из существующего Personal Corp и куратора. Обновление выполняется при запуске ярлыка. Без повторного запуска данные не обновляются сами.

Свойства проектов, раздел «Мои заметки», входящие и журнал решений сохраняются. Не редактируйте область фактов между служебными маркерами в режиме исходного текста: при конфликте штаб сохранит вашу версию и сообщит об этом.

## Где оригиналы
- {file_link("Personal Corp", corp.ROOT)}
- {file_link("Браузерное представление", state / "dashboard.html")}
- {file_link("Наброски и отчёты", source_root)}

Все записи этого раздела — локальные файлы в вашем существующем хранилище Obsidian. Они не добавляются в публичный Git штаба. Приёмка, публикация и удаление проектов не выполняются изменением карточки.
""")
        config["obsidian"] = {**config.get("obsidian", {}), "vault": str(writer.vault), "folder": FOLDER}
        corp.write_json(state / "config.json", config)
        result = {"brand": BRAND, "at": corp.now(), "vault": str(writer.vault),
                  "home": str(writer.root / "Сегодня.md"), "projects": len(inv["projects"]),
                  "written": writer.written, "conflicts": writer.conflicts}
        corp.write_json(state / "obsidian-sync.json", result)
        return result
