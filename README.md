# GTA VI PC Race — Русское автообновляемое зеркало

Автоматически обновляемый перевод трекера ПК-портов GTA VI (оригинал: [vuyp/gta6-pc-race](https://github.com/vuyp/gta6-pc-race)).

## Как работает автообновление и перевод
1. **Каждые 20 минут** (и по ручной кнопке *Run workflow*) запускается GitHub Action ([sync.yml](.github/workflows/sync.yml)).
2. Скрипт [src/sync_and_translate.py](src/sync_and_translate.py) скачивает свежий `src/data.json` из `vuyp/gta6-pc-race`.
3. **Кэш по хэшу (SHA-256):** уже переведённые записи берутся из [src/translation_cache.json](src/translation_cache.json) мгновенно — заново переводятся только изменившиеся абзацы.
4. **Защита имён команд и команд/кода:** все названия проектов (`klbf-lab`, `Vice-Tay`, `CGBJ`, `VIctory`, `PortWatch` и др.), видеокарты, репозитории и фрагменты в `` `обратных кавычках` `` маскируются в плейсхолдеры `⟪T0⟫` до отправки в Google Gemini API и возвращаются без искажений.
5. Скрипт [src/build.py](src/build.py) собирает готовый русский `index.html` для GitHub Pages.

## Подключение бесплатного ключа Gemini API (1 минута)
Чтобы перевод новых обновлений работал автоматически в облаке:
1. Получите бесплатный ключ в **Google AI Studio**: https://aistudio.google.com/apikey (банковская карта не требуется).
2. В вашем репозитории на GitHub откройте: **Settings → Secrets and variables → Actions → New repository secret**.
3. Добавьте секрет:
   * **Name:** `GEMINI_API_KEY`
   * **Secret:** ваш ключ от Google AI Studio.
4. Откройте вкладку **Actions → Sync and Translate Upstream → Run workflow**, чтобы запустить первый полный прогон перевода (если записей много, остаток докачается в следующих автозапусках без превышения лимита).

## Атрибуция
Оригинальный проект и данные: [vuyp/gta6-pc-race](https://github.com/vuyp/gta6-pc-race).
Шрифты: Onest и JetBrains Mono (SIL Open Font License 1.1).
