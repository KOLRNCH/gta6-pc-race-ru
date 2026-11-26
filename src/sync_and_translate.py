#!/usr/bin/env python3
"""Sync upstream `vuyp/gta6-pc-race/src/data.json` and translate only changed entries via Gemini API.

Design goals:
- Zero-cost friendly: SHA-256 cache (`src/translation_cache.json`) ensures only new/changed strings are translated.
- Strict preservation: Project/team names, repository slugs, hardware models, CLI commands, and UTC dates
  are masked with `⟪T0⟫` placeholders before calling Gemini and verified after unmasking.
- Resilient: Supports retries on HTTP 429, model fallback, and safe per-run request budgets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
UPSTREAM_DATA_URL = "https://raw.githubusercontent.com/vuyp/gta6-pc-race/main/src/data.json"
UPSTREAM_API_URL = "https://api.github.com/repos/vuyp/gta6-pc-race"

UPSTREAM_FILE = HERE / "data_upstream.json"
RU_DATA_FILE = HERE / "data_ru.json"
CACHE_FILE = HERE / "translation_cache.json"
STARS_FILE = HERE / "stars.txt"

STATIC_PROTECTED_TERMS = [
    "Xbox Series S",
    "Xbox Series X",
    "Xbox",
    "Windows",
    "Linux",
    "macOS",
    "Mac",
    "NVIDIA",
    "AMD",
    "Intel",
    "Radeon RX 9070 XT",
    "Radeon RX 7900 XTX",
    "Radeon RX 6600 XT",
    "RTX 5090",
    "RTX 5080",
    "RTX 5070",
    "RTX 4090",
    "RTX 4070 SUPER",
    "RTX 4070",
    "RTX 4060 Ti",
    "RTX 4060",
    "RTX 3070",
    "RTX 3060",
    "RTX 3050",
    "RTX 5060 Ti",
    "Ryzen 7 9800X3D",
    "Rockstar Games",
    "Take-Two Interactive",
    "Take-Two",
    "Rockstar",
    "PortWatch",
    "Manifold",
    "GitHub",
    "Discord",
    "Reddit",
    "VGTimes",
    "TalkEsport",
    "GDeflate",
    "Neptune",
    "VIctory",
    "GTA VI",
    "GTA V",
    "README",
    "DMCA",
    "fps",
    "UTC",
]

SEED_TRANSLATIONS = {
    "No": "Нет",
    "Yes": "Да",
    "No GTA VI work published": "Работы по GTA VI не публиковались",
    "No GTA VI work published.": "Работы по GTA VI не публиковались.",
    "shadows black": "чёрные тени",
    "shadows dark": "тёмные тени",
    "no run length reported": "длительность сессии не указана",
    "nothing reported": "нет данных",
    "reached": "достигнуто",
    "First estimate.": "Первый прогноз.",
    "about half a day": "около полудня",
}

DEFAULT_MODELS = ("gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash")

SYSTEM_PROMPT = """Ты — профессиональный технический и игровой редактор-переводчик (уровень DeepL Pro / редактор DTF).
Переведи массив англоязычных строк с сайта-трекера ПК-портов GTA VI на грамотный, естественный, лаконичный русский язык.

ЖЁСТКИЕ ПРАВИЛА:
1. Токены вида ⟪T0⟫, ⟪T1⟫, ⟪T2⟫ (названия команд, проектов, репозиториев, консолей, видеокарт, программ и консольных команд) НЕЛЬЗЯ изменять, переводить, транслитерировать или удалять. Склоняй окружающие русские слова вокруг них!
2. Все числовые значения, проценты, версии и единицы измерения (14.0, 4K, 32 GB, 37 minutes -> 37 минут) передавай точно без искажений.
3. Отметки времени вида `09:38 UTC` или `09:38 UTC on 26 Nov` переводи строго как `09:38 UTC` или `09:38 UTC 26 ноя` (чтобы сохранялся формат UTC для скрипта часовых поясов).
4. Игровой и технический глоссарий:
   - playable -> играбельно
   - playable bar -> планка «Играбельно»
   - fork -> форк
   - build -> сборка
   - smaller console's profile -> профиль младшей консоли
   - larger console's profile -> профиль старшей консоли
   - upscaling -> апскейлинг
   - frame generation -> генерация кадров
   - ray tracing -> трассировка лучей
   - graphics device lost -> сбой графического драйвера
   - pull request -> пул-реквест (PR)
   - takedown notice -> требование об удалении (DMCA)
   - watch list -> список наблюдения
   - median -> медиана
5. Верни ТОЛЬКО JSON-объект вида {"translations": ["...", "..."]} ровно с тем же количеством элементов и в том же порядке."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_protected_terms(data: dict[str, Any]) -> list[str]:
    """Collect dynamic team/project names and static technical tokens to keep untranslated."""
    terms: set[str] = set(STATIC_PROTECTED_TERMS)
    for p in data.get("projects", []):
        if p.get("name"):
            terms.add(str(p["name"]).strip())
        if p.get("repo"):
            terms.add(str(p["repo"]).strip())
    for w in data.get("watching", []):
        if w.get("name"):
            terms.add(str(w["name"]).strip())
        if w.get("repo"):
            terms.add(str(w["repo"]).strip())

    # Sort longest first so `VIctory-Belobug-AMD` matches before `VIctory`
    return sorted((t for t in terms if len(t) >= 2), key=len, reverse=True)


def mask_protected_terms(text: str, terms: list[str]) -> tuple[str, dict[str, str]]:
    """Replace exact team names, repo slugs, and backtick commands with `⟪T#⟫` placeholders."""
    mapping: dict[str, str] = {}
    counter = 0

    def next_token(original: str) -> str:
        nonlocal counter
        token = f"⟪T{counter}⟫"
        mapping[token] = original
        counter += 1
        return token

    # First preserve backticked CLI commands / flags / identifiers and full URLs
    masked = re.sub(r"`[^`]+`|https?://\S+", lambda m: next_token(m.group(0)), text)

    if terms:
        pattern = re.compile(
            r"(?<![A-Za-z0-9_-])(" + "|".join(re.escape(t) for t in terms) + r")(?=(?:'s|’s)?(?![A-Za-z0-9_-]))"
        )
        masked = pattern.sub(lambda m: next_token(m.group(0)), masked)

    return masked, mapping


def unmask_protected_terms(text: str, mapping: dict[str, str]) -> str:
    """Restore `⟪T#⟫` placeholders back to original untranslated names/commands."""
    restored = text
    for token, original in mapping.items():
        restored = restored.replace(token, original)
    return restored


def _all_tokens_preserved(translated: str, mapping: dict[str, str]) -> bool:
    return all(token in translated for token in mapping)


def call_gemini_batch(
    masked_texts: list[str],
    api_key: str,
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> list[str]:
    """Translate a list of masked strings using Google Gemini REST API."""
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps({"strings": masked_texts}, ensure_ascii=False)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.15,
            "responseMimeType": "application/json",
        },
    }
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_err: Exception | None = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            req = urllib.request.Request(
                url,
                data=raw_body,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                text_out = body["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_out)
                items = parsed.get("translations")
                if isinstance(items, list) and len(items) == len(masked_texts):
                    return [str(x) for x in items]
                raise ValueError(f"Unexpected Gemini JSON shape from {model}")
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code == 429 and attempt < 2:
                    time.sleep(4 * (attempt + 1))
                    continue
                if exc.code in (404, 400):
                    break  # try next model
                raise
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(f"Gemini translation failed across models {models}: {last_err}")


def extract_translatable_slots(data: dict[str, Any]) -> list[tuple[list[str | int], str]]:
    """Collect `(json_path, source_text)` pairs ordered by highest visual priority."""
    slots: list[tuple[list[str | int], str]] = []

    for key in ("playable", "leader", "headline", "summary"):
        if data.get(key):
            slots.append(([key], str(data[key])))

    fc = data.get("forecast") or {}
    for key in ("label", "date_label", "definition"):
        if fc.get(key):
            slots.append((["forecast", key], str(fc[key])))
    for idx, odd in enumerate(fc.get("odds") or []):
        for key in ("chance", "by"):
            if odd.get(key):
                slots.append((["forecast", "odds", idx, key], str(odd[key])))
    for idx, step in enumerate(fc.get("steps") or []):
        for key in ("name", "when", "date"):
            if step.get(key):
                slots.append((["forecast", "steps", idx, key], str(step[key])))
    for idx, item in enumerate((fc.get("basis") or [])[:6]):
        if item:
            slots.append((["forecast", "basis", idx], str(item)))

    for idx, p in enumerate(data.get("projects") or []):
        for key in ("kind", "basis", "status", "lead"):
            if p.get(key):
                slots.append((["projects", idx, key], str(p[key])))
        lanes = p.get("lanes") or {}
        for lane_key in ("picture", "speed", "stability"):
            ln = lanes.get(lane_key)
            if isinstance(ln, dict) and ln.get("text"):
                slots.append((["projects", idx, "lanes", lane_key, "text"], str(ln["text"])))

    for idx, w in enumerate(data.get("watching") or []):
        if w.get("note"):
            slots.append((["watching", idx, "note"], str(w["note"])))

    for idx, n in enumerate(data.get("notes") or []):
        if isinstance(n, dict):
            for key in ("label", "text", "link"):
                if n.get(key):
                    slots.append((["notes", idx, key], str(n[key])))
        elif n:
            slots.append((["notes", idx], str(n)))

    # Prioritize latest forecast revisions and recent updates first
    for idx, rev in enumerate(fc.get("revisions") or []):
        if rev.get("note"):
            slots.append((["forecast", "revisions", idx, "note"], str(rev["note"])))

    for idx, upd in enumerate(data.get("updates") or []):
        if upd.get("title"):
            slots.append((["updates", idx, "title"], str(upd["title"])))
        for p_idx, pt in enumerate(upd.get("points") or []):
            if pt:
                slots.append((["updates", idx, "points", p_idx], str(pt)))

    return slots


def set_by_path(obj: Any, path: list[str | int], value: str) -> None:
    cur = obj
    for part in path[:-1]:
        cur = cur[part]
    cur[path[-1]] = value


def translate_dataset(
    data: dict[str, Any],
    cache: dict[str, str],
    api_key: str | None,
    *,
    max_requests: int = 12,
    batch_char_limit: int = 5500,
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> tuple[dict[str, Any], dict[str, str], int]:
    """Translate `data` incrementally using `cache` and Gemini API; return `(ru_data, cache, api_calls)`."""
    ru_data = json.loads(json.dumps(data))
    terms = collect_protected_terms(data)
    slots = extract_translatable_slots(data)

    pending: dict[str, tuple[str, str, dict[str, str]]] = {}
    for _, src in slots:
        if src in SEED_TRANSLATIONS:
            cache[sha256_text(src)] = SEED_TRANSLATIONS[src]
            continue
        digest = sha256_text(src)
        if digest not in cache and digest not in pending:
            masked, mapping = mask_protected_terms(src, terms)
            pending[digest] = (src, masked, mapping)

    api_calls = 0
    pending_items = list(pending.items())
    idx = 0

    if api_key and pending_items:
        while idx < len(pending_items) and api_calls < max_requests:
            batch: list[tuple[str, str, str, dict[str, str]]] = []
            chars = 0
            while idx < len(pending_items):
                digest, (src, masked, mapping) = pending_items[idx]
                if batch and (chars + len(masked) > batch_char_limit or len(batch) >= 20):
                    break
                batch.append((digest, src, masked, mapping))
                chars += len(masked)
                idx += 1

            translated_batch = call_gemini_batch([b[2] for b in batch], api_key=api_key, models=models)
            api_calls += 1

            for (digest, src, _masked, mapping), tr_masked in zip(batch, translated_batch):
                if _all_tokens_preserved(tr_masked, mapping):
                    cache[digest] = unmask_protected_terms(tr_masked, mapping)
                else:
                    # Fallback safely without corrupting team names
                    cache[digest] = src

            if idx < len(pending_items) and api_calls < max_requests:
                time.sleep(1.5)

    for path, src in slots:
        digest = sha256_text(src)
        translated = cache.get(digest, src)
        set_by_path(ru_data, path, translated)

    for orig_w, ru_w in zip(data.get("watching") or [], ru_data.get("watching") or []):
        if "No GTA VI work published" in str(orig_w.get("note", "")):
            ru_w["idle"] = True

    return ru_data, cache, api_calls


def fetch_upstream() -> dict[str, Any]:
    req = urllib.request.Request(UPSTREAM_DATA_URL, headers={"User-Agent": "gta6-pc-race-ru-sync"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_upstream_stars() -> int | None:
    try:
        req = urllib.request.Request(UPSTREAM_API_URL, headers={"User-Agent": "gta6-pc-race-ru-sync"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read().decode("utf-8"))
        return int(info.get("stargazers_count") or 0)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync and translate upstream gta6-pc-race data.")
    parser.add_argument("--no-fetch", action="store_true", help="Use local src/data_upstream.json instead of fetching")
    parser.add_argument("--max-requests", type=int, default=12, help="Max Gemini API requests per run")
    args = parser.parse_args()

    if args.no_fetch:
        upstream = json.loads(UPSTREAM_FILE.read_text(encoding="utf-8"))
    else:
        upstream = fetch_upstream()
        UPSTREAM_FILE.write_text(json.dumps(upstream, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stars = fetch_upstream_stars()
        if stars:
            STARS_FILE.write_text(f"{stars}\n", encoding="utf-8")

    cache: dict[str, str] = {}
    if CACHE_FILE.exists():
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    env_model = os.getenv("GEMINI_MODEL", "").strip()
    models = (env_model, *DEFAULT_MODELS) if env_model else DEFAULT_MODELS
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or None

    ru_data, updated_cache, api_calls = translate_dataset(
        upstream,
        cache,
        api_key=api_key,
        max_requests=args.max_requests,
        models=models,
    )

    CACHE_FILE.write_text(json.dumps(updated_cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    RU_DATA_FILE.write_text(json.dumps(ru_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Synced {upstream['checked']}: cached={len(updated_cache)} entries, gemini_calls={api_calls}")


if __name__ == "__main__":
    main()
