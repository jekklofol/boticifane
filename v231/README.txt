Please Donate Bot v2 — публичная раздача с Telegram-ботом
==========================================================

СТРУКТУРА ФАЙЛОВ
────────────────
v2/
  loader_v2.lua            ← ТОЛЬКО ЭТО раздаётся пользователям
  bot.py                   ← Telegram-бот (aiogram 3.x)
  server_v2.py             ← Flask API (порт 5001)
  db_v2.py                 ← SQLite база данных
  config.py                ← Конфигурация (заполни перед запуском!)
  requirements.txt
  obfuscate.bat            ← Обфусцировать скрипт перед релизом

  src/
    botplsdonate_v2_core.lua  ← исходник скрипта (НИКОМУ не показывать!)

  obfuscated_script.lua    ← генерируется из src/ через obfuscate.bat


БЫСТРЫЙ СТАРТ
────────────────

1. Заполни config.py:
   - BOT_TOKEN       → получи у @BotFather
   - ADMIN_TG_ID     → свой Telegram ID (узнай у @userinfobot)
   - API_SECRET      → любая случайная строка

2. Установи зависимости:
   pip install -r requirements.txt

3. Установи Prometheus (один раз для обфускации):
   git clone https://github.com/levno-710/Prometheus
   (нужен Lua 5.x — скачай с https://www.lua.org/download.html)

4. Обфусцируй скрипт:
   obfuscate.bat

5. Запусти три терминала:
   Терминал 1: python bot.py
   Терминал 2: python server_v2.py
   Терминал 3: cloudflared tunnel --url http://localhost:5001

6. Скопируй URL из Терминала 3 в loader_v2.lua и в config.py (API_BASE_URL).
   Сейчас: https://spy-resulted-lou-photo.trycloudflare.com

7. Раздай пользователям только loader_v2.lua


ПОТОК РАБОТЫ
────────────────
Пользователь → /start боту → выполняет условия → подаёт заявку
Ты → видишь заявку в Telegram → проверяешь скриншоты → нажимаешь "Одобрить"
Пользователь → получает ключ → инжектит loader_v2.lua → вводит ключ → запускает


КОМАНДЫ БОТА
────────────────
/start    — приветствие + кнопка подачи заявки
/status   — статус заявки / ключа
/mystats  — статистика Roblox-аккаунта
/mykey    — показать ключ

Только для тебя (ADMIN_TG_ID):
/admin    — панель управления
/stats    — общая статистика
/users    — список пользователей
/revoke <ключ или tg_id>  — отозвать ключ
/give <tg_id>             — выдать ключ вручную


ОБНОВЛЕНИЕ СКРИПТА
────────────────
1. Измени src/botplsdonate_v2_core.lua
2. Запусти obfuscate.bat
3. Перезапусти server_v2.py
   (loader_v2.lua обновлять не нужно — он всегда скачивает свежий код с сервера)
