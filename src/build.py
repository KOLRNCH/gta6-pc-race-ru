#!/usr/bin/env python3
"""Render translated Russian `data_ru.json` (or fallback `data.json`) into `index.html`.

Adapted from https://github.com/vuyp/gta6-pc-race for automatic Russian mirroring.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "data_ru.json"
if not DATA.exists():
    DATA = HERE / "data_upstream.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent / "index.html"
data = json.loads(DATA.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def ru_plural(n: int, one: str, few: str, many: str) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and (mod100 < 12 or mod100 > 14):
        return few
    return many


UNIT = re.compile(
    r"(\d) (?=(?:ГБ|МБ|GB|MB|UTC|fps|к/с|кадр(?:а|ов)?|frames?|секунд[аы]?|seconds?|минут[аы]?|minutes?|час(?:а|ов)?|hours?|дн(?:я|ей)|days?|недел[иь]|weeks?|из 10|in 10|of \d)\b)"
)

CLOCK = re.compile(
    r"\b(\d{1,2}):(\d{2})\b(?:\s*UTC(?:\s*(?:on\s+)?(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|November|Dec|December|"
    r"янв|января|фев|февраля|мар|марта|апр|апреля|май|мая|июн|июня|июл|июля|"
    r"авг|августа|сен|сентября|окт|октября|ноя|ноября|дек|декабря)\b)?)?"
)
MONTH_NO = {
    "Jan": 1, "янв": 1, "января": 1,
    "Feb": 2, "фев": 2, "февраля": 2,
    "Mar": 3, "мар": 3, "марта": 3,
    "Apr": 4, "апр": 4, "апреля": 4,
    "May": 5, "май": 5, "мая": 5,
    "Jun": 6, "июн": 6, "июня": 6,
    "Jul": 7, "июл": 7, "июля": 7,
    "Aug": 8, "авг": 8, "августа": 8,
    "Sep": 9, "сен": 9, "сентября": 9,
    "Oct": 10, "окт": 10, "октября": 10,
    "Nov": 11, "November": 11, "ноя": 11, "ноября": 11,
    "Dec": 12, "December": 12, "дек": 12, "декабря": 12,
}

RU_MONTHS = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}


def parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def clock(iso: str) -> str:
    return parse(iso).strftime("%H:%M")


def day(iso: str) -> str:
    d = parse(iso)
    return f"{d.day} {RU_MONTHS[d.month]}"


def txt(value: object, base: str | None = None) -> str:
    """Escaped prose keeping numbers glued to units and UTC clocks wrapped in `<time>`."""
    ref = parse(base or data["checked"])

    def wrap(m: re.Match[str]) -> str:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            return m.group(0)
        kind = "clock-bare"
        try:
            when = ref.replace(hour=hour, minute=minute, second=0)
            if "UTC" in m.group(0):
                kind = "clock"
            if m.group(3):
                kind = "clock-day"
                when = when.replace(month=MONTH_NO[m.group(4)], day=int(m.group(3)))
        except ValueError:
            return m.group(0)
        return f'<time datetime="{when.strftime("%Y-%m-%dT%H:%M:%SZ")}" data-t="{kind}">{m.group(0)}</time>'

    return UNIT.sub("\\1&nbsp;", CLOCK.sub(wrap, esc(value)))


SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
URL = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9_./-]+$")


def repo_href(repo: str, url: str | None = None) -> str | None:
    if url and URL.match(url):
        return url
    if SLUG.match(repo):
        return f"https://github.com/{repo}"
    return None


def name_link(repo: str, text: str, url: str | None = None, link: bool = True) -> str:
    href = repo_href(repo, url) if link else None
    if not href:
        return esc(text)
    return f'<a class="name" href="{esc(href)}" rel="noopener">{esc(text)}</a>'


stages_raw = data["stages"]
STAGE_NAMES_RU = {
    "Not started": "Не начато",
    "Loads": "Загружается",
    "Starts up": "Запускается",
    "Graphics device": "Графика (GPU)",
    "First frames": "Первые кадры",
    "Recognisable picture": "Узнаваемая картинка",
    "In-game": "В игре",
    "Playable": "Играбельно",
}
stages = [STAGE_NAMES_RU.get(s, s) for s in stages_raw]
top = len(stages) - 1
fc = data["forecast"]
last_rev = fc["revisions"][0]

LANES = [
    {
        "key": "picture",
        "name": "Картинка",
        "what": "Что проект показывает на экране внутри игрового мира по собственным отчётам.",
        "steps": [
            "Почти темно или без освещения",
            "Свет только на солнце, тени полностью чёрные",
            "Освещение и тени есть, но видны артефакты",
            "Свет и сцена цельные, лишь мелкие недочёты",
            "Картинка уровня консоли, включая рейтрейсинг",
        ],
    },
    {
        "key": "speed",
        "name": "Скорость",
        "what": "Средний FPS за сессию от 10 минут (либо середина диапазона кадров в секунду по отчёту).",
        "edges": [0, 2, 5, 10, 20, 30],
        "bar": 5,
        "steps": [
            "Ниже 2 к/с",
            "От 2 к/с и выше",
            "От 5 к/с и выше",
            "От 10 к/с и выше",
            "От 20 к/с и выше",
            "От 30 к/с — уровень консоли",
        ],
    },
    {
        "key": "stability",
        "name": "Стабильность",
        "what": "Самая долгая игровая сессия без вылета, о которой сообщил проект.",
        "field": "minutes",
        "edges": [0, 10, 30, 60],
        "bar": 3,
        "steps": [
            "Меньше 10 минут",
            "От 10 минут и дольше",
            "От 30 минут и дольше",
            "От 1 часа и дольше",
        ],
    },
]
BY_KEY = {lane["key"]: lane for lane in LANES}
INGAME = stages_raw.index("In-game") if "In-game" in stages_raw else top - 1


def lane_value(lane: dict, reading: dict) -> float | None:
    if lane["key"] == "speed":
        low, high = reading.get("low"), reading.get("high")
        return None if low is None or high is None else (low + high) / 2
    return reading.get(lane.get("field", ""))


def lane_step(lane: dict, reading: dict) -> int:
    if "edges" in lane:
        value = lane_value(lane, reading)
        return 0 if value is None else sum(1 for edge in lane["edges"] if value >= edge)
    return int(reading.get("step") or 0)


def lane_steps(p: dict) -> dict[str, int]:
    read = p.get("lanes") or {}
    return {lane["key"]: min(lane_step(lane, read.get(lane["key"]) or {}), len(lane["steps"])) for lane in LANES}


def short_of_bar(p: dict) -> int:
    steps = lane_steps(p)
    return sum(max(0, lane["bar"] - steps[lane["key"]]) for lane in LANES if lane.get("bar"))


def rank_key(p: dict) -> tuple[int, int, float, float]:
    read = p.get("lanes") or {}
    speed = lane_value(BY_KEY["speed"], read.get("speed") or {}) or 0
    minutes = (read.get("stability") or {}).get("minutes") or 0
    return (short_of_bar(p), -lane_steps(p)["picture"], -speed, -minutes)


projects = sorted(data["projects"], key=lambda p: (-p["stage"], rank_key(p) if p["stage"] == INGAME else ()))


def positions(ordered: list[dict]) -> list[str]:
    labels, i = [], 0
    while i < len(ordered):
        p, j = ordered[i], i + 1
        if p["stage"] == INGAME:
            while j < len(ordered) and ordered[j]["stage"] == INGAME and rank_key(ordered[j]) == rank_key(p):
                j += 1
        elif isinstance(p.get("pos"), str) and p["pos"].endswith("="):
            while j < len(ordered) and ordered[j].get("pos") == p["pos"]:
                j += 1
        labels.extend([str(i + 1) if j == i + 1 else f"{i + 1}="] * (j - i))
        i = j
    return labels


place = dict(zip((p["name"] for p in projects), positions(projects)))
lead = projects[0]

ladder = []
LAD_MAX = 5
for n in range(top, 0, -1):
    here = [p for p in projects if p["stage"] == n]
    names = ", ".join(esc(p["name"]) for p in here[:LAD_MAX])
    if len(here) > LAD_MAX:
        names += f' <span class="lad__more">и&nbsp;ещё&nbsp;{len(here) - LAD_MAX}</span>'
    state = "lead" if n == lead["stage"] else ("has" if here else ("past" if n < lead["stage"] else "ahead"))
    ladder.append(
        f'<li class="lad__row lad__row--{state}" style="--i:{top - n}">'
        f'<span class="lad__n">{n}</span><span class="lad__stage">{esc(stages[n])}</span>'
        f'<span class="lad__who">{names}</span></li>'
    )

public = [p for p in projects if not p.get("private")]
private = [p for p in projects if p.get("private")]
pub_count = len(public)
priv_count = len(private)
pub_word = ru_plural(pub_count, "открытый проект", "открытых проекта", "открытых проектов")
extra = ""
if priv_count:
    priv_word = ru_plural(priv_count, "приватная сборка", "приватные сборки", "приватных сборок")
    extra = f" и ещё {priv_count} {priv_word}"

playable_raw = str(data.get("playable", "No")).strip()
playable_ru = {"no": "нет", "yes": "да", "нет": "нет", "да": "да"}.get(playable_raw.lower(), playable_raw.lower())

hero_fact = (
    f"Играбельно: {esc(playable_ru)}. "
    f"Дальше всех продвинулся {esc(lead.get('lead') or lead['name'])} — этап&nbsp;{lead['stage']}&nbsp;из&nbsp;{top}."
)


def meter(stage: int) -> str:
    cells = "".join(f'<span class="meter__seg{" is-on" if i <= stage else ""}"></span>' for i in range(1, top + 1))
    label = f"Этап {stage} из {top}: {stages[stage]}"
    return (
        f'<div class="meter" role="img" aria-label="{esc(label)}">{cells}</div>'
        f'<p class="label">{esc(label)}</p>'
    )


def lanes(p: dict) -> str:
    read = p.get("lanes")
    if not read:
        return ""
    out = []
    for lane in LANES:
        reading = read.get(lane["key"]) or {}
        n = len(lane["steps"])
        step = min(lane_step(lane, reading), n)
        bar = lane.get("bar")
        cells = "".join(
            f'<span class="meter__seg{" is-on" if i <= step else ""}{" is-bar" if bar and i >= bar else ""}"></span>'
            for i in range(1, n + 1)
        )
        head = f"{lane['name']} {step} из {n}:" if step else f"{lane['name']}:"
        out.append(
            f'<div class="lane"><div class="meter meter--lane" aria-hidden="true">{cells}</div>'
            f'<p class="label lane__label"><span class="lane__name">{esc(head)}</span> '
            f'{txt(reading.get("text") or "нет данных")}</p></div>'
        )
    n = short_of_bar(p)
    if n:
        step_word = ru_plural(n, "шаг", "шага", "шагов")
        short = f"До играбельной планки не хватает {n} {step_word}"
    else:
        short = "Планка по скорости и стабильности выполнена"
    return f'<div class="lanes">{"".join(out)}<p class="label lane__short">{esc(short)}</p></div>'


def lane_key() -> str:
    cols = []
    for lane in LANES:
        bar = lane.get("bar")
        items = ""
        for i, s in enumerate(lane["steps"], 1):
            cls = ' class="is-bar"' if bar and i >= bar else ""
            items += f'<li{cls}><span class="steps__n">{i}</span><span>{txt(s)}</span></li>'
        cols.append(
            f'<div class="key__lane"><h3 class="t-card">{esc(lane["name"])}</h3>'
            f'<p class="small muted">{txt(lane["what"])}</p><ol class="steps">{items}</ol></div>'
        )
    return "".join(cols)


def after_colon(text: str) -> str:
    if not text:
        return ""
    first = text.split(" ", 1)[0]
    if len(first) > 1 and first[0].isupper() and first[1:].islower():
        return text[0].lower() + text[1:]
    return text


OS_ORDER = ["Windows", "Linux", "Mac"]
GPU_ORDER = ["NVIDIA", "AMD", "Intel"]


def tested_of(p: dict) -> tuple[list[str], list[str]]:
    t = p.get("tested") or {}
    return [x for x in OS_ORDER if x in (t.get("os") or [])], [x for x in GPU_ORDER if x in (t.get("gpu") or [])]


def tested_line(p: dict) -> str:
    systems, cards = tested_of(p)
    parts = [", ".join(group) for group in (systems, cards) if group]
    return f'<p class="small muted">Проверено на {esc(" · ".join(parts))}</p>' if parts else ""


def row_attrs(p: dict) -> str:
    systems, cards = tested_of(p)
    attrs = f' data-os="{esc(" ".join(x.lower() for x in systems))}" data-gpu="{esc(" ".join(x.lower() for x in cards))}"'
    if p["stage"] == INGAME:
        steps = lane_steps(p)
        attrs += "".join(f' data-{lane["key"]}="{steps[lane["key"]]}"' for lane in LANES)
    return attrs


UPSTREAM_REPO = "https://github.com/vuyp/gta6-pc-race"
REPO = "https://github.com/KOLRNCH/gta6-pc-race-ru"


def filter_panel() -> str:
    systems = [x for x in OS_ORDER if any(x in tested_of(p)[0] for p in projects)]
    cards = [x for x in GPU_ORDER if any(x in tested_of(p)[1] for p in projects)]
    picks = [("os", "Система", [(x.lower(), x) for x in systems]), ("gpu", "Видеокарта", [(x.lower(), x) for x in cards])]
    for lane in LANES:
        cnt = len(lane["steps"])
        if "edges" in lane:
            names = [lane["steps"][i - 1].split(",")[0] for i in range(2, cnt + 1)]
            choices = [(str(i), name[:1].lower() + name[1:]) for i, name in zip(range(2, cnt + 1), names)]
        else:
            choices = [(str(i), f"{i} из {cnt} и выше" if i < cnt else f"{i} из {cnt}") for i in range(2, cnt + 1)]
        picks.append((lane["key"], lane["name"], choices))
    selects = "".join(
        f'<label class="pick"><span class="pick__name">{esc(name)}</span><select data-f="{key}"><option value="">любая</option>'
        + "".join(f'<option value="{esc(value)}">{esc(label)}</option>' for value, label in choices)
        + "</select></label>"
        for key, name, choices in picks
    )
    return f"""
        <details class="more filter" id="filter" hidden>
          <summary><span class="link">Фильтры таблицы</span><span class="label muted" id="filter-count" aria-live="polite"></span></summary>
          <div class="filter__row">{selects}<button class="textbtn textbtn--chip" type="button" id="filter-clear" hidden>Сбросить</button></div>
          <p class="small muted filter__note">ОС и видеокарты указаны по отчётам самих проектов и их тестеров. Фильтр по показателям оставляет только проекты на этапе «В игре».</p>
        </details>"""


rows = []
for p in projects:
    rows.append(
        f"""
        <li class="board__row"{row_attrs(p)}>
          <p class="board__pos" aria-label="Позиция {esc(place[p['name']])}">{esc(place[p['name']])}</p>
          <div class="board__who">
            <h3 class="t-card">{name_link(p['repo'], p['name'], p.get('url'), not p.get('nolink'))}</h3>
            <p class="small muted">{esc(p['kind'])}</p>
            {tested_line(p)}
            {meter(p['stage'])}
            {lanes(p)}
          </div>
          <div class="board__where">
            <p class="measure">{txt(p['status'], p['changed'])}</p>
            <p class="small muted">Источник: {esc(after_colon(p['basis']))}. Обновлено <time datetime="{esc(p['changed'])}" data-t="clock">{clock(p['changed'])} UTC</time>.</p>
          </div>
        </li>"""
    )

IDLE_MARKERS = (
    "No GTA VI work published",
    "Работы по GTA VI не публиковались",
    "Нет опубликованных работ по GTA VI",
)


def is_idle_watch(w: dict) -> bool:
    return bool(w.get("idle")) or any(m in w["note"] for m in IDLE_MARKERS)


active = [w for w in data["watching"] if not is_idle_watch(w)]
idle = [w for w in data["watching"] if is_idle_watch(w)]
watching = "".join(
    f'<li><span class="rows__name">{name_link(w["repo"], w["name"], w.get("url"), not w.get("nolink"))}</span><p>{txt(w["note"])}</p></li>'
    for w in active
)
idle_line = ""
if idle:
    names = [name_link(w["repo"], w["name"], w.get("url")) for w in idle]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]
    idle_line = f'<p class="small muted measure idle">Также проверены (работы по GTA VI не публиковались): {joined}.</p>'

fc_odds = "".join(
    f'<li><span class="rows__name">{esc(o["by"][:1].upper() + o["by"][1:])}</span><span class="rows__value">{esc(o["chance"])}</span></li>'
    for o in fc["odds"]
)
fc_steps = "".join(
    f'<li><span class="rows__name">{esc(s["name"])}</span><span class="rows__value">{esc(s["when"])}, {esc(s["date"])}</span></li>'
    for s in fc["steps"]
)
fc_basis = "".join(f"<li>{txt(b, last_rev['t'])}</li>" for b in fc["basis"][:6])


def entry(u: dict) -> str:
    pre = "около " if u.get("approx") else ""
    when = pre + clock(u["t"])
    points = "".join(f"<li>{txt(pt, u['t'])}</li>" for pt in u["points"])
    return f"""
        <li class="log__row">
          <p class="log__when"><time datetime="{esc(u['t'])}" data-t="log" data-pre="{esc(pre)}">{esc(when)}</time> <span>{esc(day(u['t']))}</span></p>
          <div class="log__what">
            <h3 class="t-card">{esc(u['title'])}</h3>
            <ul class="points measure">{points}</ul>
          </div>
        </li>"""


SHOWN = 4
recent = "".join(entry(u) for u in data["updates"][:SHOWN])
older_list = data["updates"][SHOWN:]
older = ""
if older_list:
    older = f"""
      <details class="more">
        <summary><span class="link">Показать ещё {len(older_list)} предыдущих обновлений</span></summary>
        <ol class="log">{''.join(entry(u) for u in older_list)}
        </ol>
      </details>"""

notes = []
for n in data["notes"]:
    if isinstance(n, dict):
        more = ""
        if n.get("href") and n.get("link") and URL.match(n["href"]):
            more = f' <a class="link" href="{esc(n["href"])}" rel="noopener">{esc(n["link"])}</a>.'
        notes.append(f'<li><span class="rows__name">{esc(n["label"])}</span><p>{txt(n["text"])}{more}</p></li>')
    else:
        notes.append(f"<li><p>{txt(n)}</p></li>")
notes_html = "".join(notes)

CSS = (HERE / "page.css").read_text(encoding="utf-8")
JS = (HERE / "page.js").read_text(encoding="utf-8")

STAR = (
    '<svg class="btn__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<path d="M12 3.6l2.6 5.27 5.82.85-4.21 4.1.99 5.8L12 16.88l-5.2 2.74.99-5.8-4.21-4.1 5.82-.85z"/></svg>'
)
stars = None
try:
    raw = (HERE / "stars.txt").read_text(encoding="utf-8").strip()
    if raw.isdigit() and int(raw) > 0:
        stars = int(raw)
except OSError:
    pass
star_count = f'<span class="btn__count">{stars:,}</span>' if stars else ""
star_said = f" ({stars:,} звёзд)" if stars else ""
star_nav = (
    f'<a class="btn btn--secondary nav__star" href="{REPO}" rel="noopener" '
    f'aria-label="Зеркало на GitHub">{STAR}<span class="btn__word">GitHub</span></a>'
)
star_foot = (
    f'<a class="btn btn--secondary" href="{UPSTREAM_REPO}" rel="noopener" '
    f'aria-label="Оригинал трекера на GitHub{star_said}">{STAR}<span>Оригинал (vuyp)</span>{star_count}</a>'
)

TZ_BTN = '<button class="textbtn" type="button" data-tz aria-pressed="false" hidden>Местное время</button>'
THEME_BTN = '<button class="textbtn textbtn--chip" type="button" data-theme-btn hidden>Тема: авто</button>'
THEME_EARLY = '<script>try{var t=localStorage.getItem("gta6race.theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}</script>'

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='5' fill='%2326251e'/%3E"
    "%3Ctext x='16' y='22.5' text-anchor='middle' font-family='Helvetica,Arial,sans-serif' font-size='19' "
    "font-weight='600' fill='%23dfdedb'%3EG%3C/text%3E%3C/svg%3E"
)

TITLE = "GTA VI PC Race (RU): живой трекер ПК-портов"
DESC = (
    "На каком этапе находится каждый открытый проект по запуску Xbox-сборки GTA VI на ПК. "
    "Автоматический перевод оригинала vuyp/gta6-pc-race."
)
SITE = "https://kolrnch.github.io/gta6-pc-race-ru/"

page = f"""<!DOCTYPE html>
<html lang="ru" data-type="software" data-radius="sharp" data-buttons="tonal">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(TITLE)}</title>
<meta name="description" content="{esc(DESC)}">
<meta name="page-type" content="software">
<meta name="site-kind" content="software">
<meta name="color-scheme" content="light dark">
{THEME_EARLY}
<meta name="theme-color" content="#dfdedb" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1c1b16" media="(prefers-color-scheme: dark)">
<meta property="og:title" content="{esc(TITLE)}">
<meta property="og:description" content="{esc(DESC)}">
<meta property="og:type" content="website">
<meta property="og:image" content="{SITE}share.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Onest:wght@400..800&display=swap" rel="stylesheet">
<style>
{CSS}
</style>
</head>
<body>
<header class="nav nav--centre">
  <div class="wrap nav__bar">
    <a class="skip-link" href="#top">Перейти к содержимому</a>
    <a class="nav__logo" href="#top" aria-label="GTA VI PC Race, наверх"><span class="mark mark--initial" aria-hidden="true">G</span><span>GTA VI PC Race · RU</span></a>
    <nav class="nav__links" id="menu" aria-label="Разделы">
      <a href="#standings">Таблица</a>
      <a href="#forecast">Прогноз</a>
      <a href="#updates">Обновления</a>
      <a href="#method">Методика</a>
    </nav>
    <div class="nav__actions">
      {star_nav}
      <a class="btn btn--primary" href="#standings">К таблице</a>
      <button class="btn btn--secondary nav__toggle" type="button" aria-expanded="false" aria-controls="menu" aria-label="Меню"><span aria-hidden="true"></span></button>
    </div>
  </div>
</header>

<main id="top">
  <section class="hero" data-enter>
    <div class="wrap grid">
      <div class="hero__words">
        <h1 class="enter">Трекер ПК-портов GTA VI</h1>
        <p class="lead hero__fact enter">{hero_fact}</p>
        <p class="hero__how enter">Сейчас за запуском Xbox-сборки игры на ПК следят {pub_count} {pub_word}{extra}. Страница автоматически синхронизируется с оригиналом каждые {esc(data['cadence_minutes'])} минут и переводит отчёты без искажения названий команд. <span class="muted">Проверено <time id="checked" datetime="{esc(data['checked'])}" data-t="clock-day">{clock(data['checked'])} UTC, {esc(day(data['checked']))}</time><span id="ago"></span>. {TZ_BTN}</span></p>
        <div class="btn-row enter">
          <a class="btn btn--primary" href="#standings">Открыть таблицу</a>
          <a class="btn btn--secondary" href="#updates">Последние новости</a>
        </div>
      </div>
      <div class="hero__visual enter">
        <div class="frame" role="group" aria-label="Семь этапов прогресса и проекты на каждом из них">
          <p class="frame__head"><span>Пройденные этапы</span><time class="mono" datetime="{esc(data['checked'])}" data-t="clock">{clock(data['checked'])} UTC</time></p>
          <ol class="lad" reversed>{''.join(ladder)}</ol>
          <p class="frame__foot"><span>Ближайший прогноз до «Играбельно»</span><span id="fc-short" data-target="{esc(fc['target'])}">{esc(fc['label'])}</span></p>
        </div>
      </div>
    </div>
  </section>

  <section id="standings">
    <div class="wrap">
      <div class="head">
        <h2>Таблица участников</h2>
        <details class="more">
          <summary><span class="link">Как устроены шкалы и сортировка</span></summary>
          <p class="measure">Каждый проект на этапе «В игре» (этап&nbsp;{INGAME}) оценивается дополнительно по трём шкалам. Значения берутся из отчётов самого проекта или источника, указанного в строке; пустая шкала означает, что точных цифр не публиковалось. Синим выделена планка «Играбельно»: 20&nbsp;к/с и 30&nbsp;минут игры без вылетов.</p>
          <p class="measure">Места внутри этапа «В игре» считаются автоматически только по этим трём шкалам: сначала кто ближе к планке по скорости и стабильности, затем лучшее качество картинки, выше FPS и длиннее сессия.</p>
          <div class="key">{lane_key()}</div>
        </details>{filter_panel()}
      </div>
      <ol class="board">{''.join(rows)}
      </ol>
      <p class="small muted" id="filter-none" hidden>Нет проектов, подходящих под выбранные фильтры.</p>
      <h3 class="sub">Также под наблюдением</h3>
      <ul class="pairs">{watching}</ul>
      {idle_line}
    </div>
  </section>

  <section id="forecast" class="ground-inverse">
    <div class="wrap">
      <h2>Время до «Играбельно»</h2>
      <div class="grid fc">
        <div class="fc__main">
          <p class="stat" id="fc-rel" data-target="{esc(fc['target'])}">{esc(fc['label'])}</p>
          <p class="lead">Ориентировочно <time datetime="{esc(fc['target'])}">{esc(fc['date_label'])}</time>.</p>
          <p class="measure">{txt(fc['definition'])}</p>
          <h3 class="t-card">На чём основан прогноз</h3>
          <ul class="points measure">{fc_basis}</ul>
        </div>
        <div class="fc__side">
          <h3 class="t-card">Вероятность по срокам</h3>
          <ul class="rows">{fc_odds}</ul>
          <h3 class="t-card">Ключевые вехи</h3>
          <ul class="rows">{fc_steps}</ul>
          <p class="small muted">Прогноз составляется ИИ-системой оригинального трекера и сдвигается по мере выхода новых отчётов. Последний пересмотр <time datetime="{esc(last_rev['t'])}" data-t="clock-day">{clock(last_rev['t'])} UTC, {esc(day(last_rev['t']))}</time>: {txt(last_rev['note'], last_rev['t'])}</p>
        </div>
      </div>
    </div>
  </section>

  <section id="updates">
    <div class="wrap">
      <h2>Лента обновлений</h2>
      <ol class="log">{recent}
      </ol>{older}
    </div>
  </section>

  <section id="method">
    <div class="wrap">
      <h2>Методика и ограничения</h2>
      <ul class="rows rows--spec">{notes_html}</ul>
    </div>
  </section>
</main>

<footer class="footer closing footer--statement">
  <div class="wrap slab">
    <div class="close close--word">
      <div class="close__head">
        <h2>Синхронизация и автоперевод каждые {esc(data['cadence_minutes'])} минут</h2>
        <div class="btn-row">
          <a class="btn btn--primary" href="#standings">К таблице</a>
          {star_foot}
        </div>
      </div>
      <p class="close__name" aria-hidden="true">GTA VI PC Race</p>
    </div>
    <p class="legal small muted">Русское автообновляемое зеркало проекта <a class="link" href="{UPSTREAM_REPO}" rel="noopener">vuyp/gta6-pc-race</a> (2026). Не связано с Rockstar Games или Take-Two Interactive. <span id="tz-note">Время указано в UTC.</span> {TZ_BTN} {THEME_BTN}</p>
  </div>
</footer>
<script>
{JS}
</script>
</body>
</html>
"""

OUT.write_text(page, encoding="utf-8")
(HERE / "order.txt").write_text(
    "".join(
        f"{place[p['name']]} {p['name']} | {short_of_bar(p)} short | speed "
        f"{lane_value(BY_KEY['speed'], (p.get('lanes') or {}).get('speed') or {})} step {lane_steps(p)['speed']} | "
        f"stability {((p.get('lanes') or {}).get('stability') or {}).get('minutes')} step {lane_steps(p)['stability']} | "
        f"picture {lane_steps(p)['picture']}\n"
        for p in projects if p["stage"] == INGAME
    ),
    encoding="utf-8",
)
print(f"wrote {OUT} ({len(page.encode('utf-8'))} bytes), checked {data['checked']}")
