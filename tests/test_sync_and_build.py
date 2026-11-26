"""Tests for upstream masking, diff caching, and Russian HTML rendering."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.sync_and_translate import (
    collect_protected_terms,
    mask_protected_terms,
    sha256_text,
    translate_dataset,
    unmask_protected_terms,
)

ROOT = Path(__file__).resolve().parent.parent


def test_masking_preserves_team_names_commands_and_substrings() -> None:
    sample = {
        "projects": [
            {"name": "klbf-lab", "repo": "PastiiJay/klbf-lab"},
            {"name": "Vice-Tay", "repo": "user/Vice-Tay"},
            {"name": "Doomsday", "repo": ""},
            {"name": "suri", "repo": ""},
            {"name": "VIctory-Belobug-AMD", "repo": "Belobug/VIctory-Belobug-AMD"},
        ],
        "watching": [{"name": "Neptune + GDeflate", "repo": ""}],
    }
    terms = collect_protected_terms(sample)
    text = (
        "klbf-lab measuring Vice-Tay's build on VIctory-Belobug-AMD and Doomsday, "
        "not suri, running `gta6 --fps 20` and/or Belobug/VIctory-Belobug-AMD."
    )
    masked, mapping = mask_protected_terms(text, terms)

    # `suri` inside `measuring` must NOT be masked, while standalone `suri` and teams MUST be masked
    assert "measuring" in masked
    assert "and/or" in masked
    assert "klbf-lab" not in masked
    assert "Vice-Tay" not in masked
    assert "VIctory-Belobug-AMD" not in masked
    assert "Doomsday" not in masked
    assert "`gta6 --fps 20`" not in masked

    restored = unmask_protected_terms(masked, mapping)
    assert restored == text


def test_diff_cache_skips_api_when_already_translated() -> None:
    upstream = {
        "checked": "2026-11-26T09:38:00Z",
        "cadence_minutes": 15,
        "playable": "No",
        "leader": "klbf-lab leads",
        "headline": "headline text",
        "summary": "summary text",
        "forecast": {
            "made": "2026-11-23T17:40:00Z",
            "target": "2026-11-27T00:00:00Z",
            "label": "about half a day",
            "date_label": "midnight UTC",
            "definition": "definition text",
            "odds": [{"chance": "5 in 10", "by": "Thu"}],
            "steps": [{"name": "Playable", "when": "reached", "date": "Thu"}],
            "basis": ["basis one"],
            "revisions": [{"t": "2026-11-26T09:02:00Z", "note": "First estimate."}],
        },
        "stages": ["Not started", "In-game", "Playable"],
        "projects": [
            {
                "name": "klbf-lab",
                "repo": "PastiiJay/klbf-lab",
                "kind": "Fork",
                "stage": 1,
                "basis": "README",
                "status": "cached status",
                "changed": "2026-11-26T09:38:00Z",
            }
        ],
        "watching": [{"name": "Palmwave", "repo": "fablinoo/palmwave", "note": "No GTA VI work published."}],
        "updates": [{"t": "2026-11-26T09:38:00Z", "title": "Update title", "points": ["Point A"]}],
        "notes": [{"label": "Sources", "text": "Public repos."}],
    }
    cache = {
        sha256_text("klbf-lab leads"): "klbf-lab лидирует",
        sha256_text("headline text"): "заголовок",
        sha256_text("summary text"): "кратко",
        sha256_text("midnight UTC"): "полночь UTC",
        sha256_text("definition text"): "определение",
        sha256_text("5 in 10"): "5 из 10",
        sha256_text("Thu"): "чт",
        sha256_text("Playable"): "Играбельно",
        sha256_text("basis one"): "основа",
        sha256_text("Fork"): "Форк",
        sha256_text("README"): "README",
        sha256_text("cached status"): "кэшированный статус",
        sha256_text("Update title"): "Заголовок обновления",
        sha256_text("Point A"): "Пункт А",
        sha256_text("Sources"): "Источники",
        sha256_text("Public repos."): "Публичные репозитории.",
    }

    ru_data, _, api_calls = translate_dataset(upstream, cache, api_key=None)
    assert api_calls == 0
    assert ru_data["projects"][0]["name"] == "klbf-lab"
    assert ru_data["projects"][0]["status"] == "кэшированный статус"
    assert ru_data["watching"][0]["idle"] is True


def test_mocked_gemini_batch_preserves_placeholders(monkeypatch) -> None:
    import src.sync_and_translate as sat

    upstream = {
        "checked": "2026-11-26T09:38:00Z",
        "cadence_minutes": 15,
        "playable": "No",
        "leader": "klbf-lab leads on Radeon RX 9070 XT",
        "headline": "Vice-Tay reports 20 fps",
        "summary": "klbf-lab and Vice-Tay test builds.",
        "forecast": {
            "made": "2026-11-23T17:40:00Z",
            "target": "2026-11-27T00:00:00Z",
            "label": "about half a day",
            "date_label": "midnight UTC",
            "definition": "Playable definition",
            "odds": [],
            "steps": [],
            "basis": [],
            "revisions": [{"t": "2026-11-26T09:02:00Z", "note": "First estimate."}],
        },
        "stages": ["Not started", "In-game", "Playable"],
        "projects": [
            {
                "name": "klbf-lab",
                "repo": "PastiiJay/klbf-lab",
                "kind": "Fork of VIctory",
                "stage": 1,
                "basis": "README",
                "status": "klbf-lab runs fast",
                "changed": "2026-11-26T09:38:00Z",
            },
            {
                "name": "Vice-Tay",
                "repo": "user/Vice-Tay",
                "kind": "Fork",
                "stage": 1,
                "basis": "README",
                "status": "Vice-Tay runs well",
                "changed": "2026-11-26T09:38:00Z",
            },
        ],
        "watching": [],
        "updates": [],
        "notes": [],
    }

    def fake_call(masked_texts, api_key, models=()):
        assert api_key == "test-key"
        # Echo back Russian prefix + keep all ⟪T#⟫ placeholders intact
        return [f"Перевод: {t}" for t in masked_texts]

    monkeypatch.setattr(sat, "call_gemini_batch", fake_call)
    ru_data, cache, calls = sat.translate_dataset(upstream, {}, api_key="test-key")
    assert calls >= 1
    assert "klbf-lab" in ru_data["leader"]
    assert "Radeon RX 9070 XT" in ru_data["leader"]
    assert "Vice-Tay" in ru_data["headline"]
    assert "⟪T" not in json.dumps(ru_data, ensure_ascii=False)
    # Re-running with populated cache must make 0 API calls
    _, _, calls_second = sat.translate_dataset(upstream, cache, api_key="test-key")
    assert calls_second == 0


def test_build_py_renders_russian_html(tmp_path: Path) -> None:
    upstream_sample = ROOT / "src" / "data_upstream.json"
    assert upstream_sample.exists()
    out_html = tmp_path / "index.html"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "build.py"), str(upstream_sample), str(out_html)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    html_text = out_html.read_text(encoding="utf-8")
    assert '<html lang="ru"' in html_text
    assert "Трекер ПК-портов GTA VI" in html_text
    assert "klbf-lab" in html_text
    assert "vuyp/gta6-pc-race" in html_text
    assert "wrote " in proc.stdout
