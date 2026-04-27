"""
Please Donate Bot v2 — Telegram Bot (aiogram 3.x)
==================================================
Запуск: python bot.py
"""

import asyncio, logging, time, os, collections
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    BufferedInputFile,
)
import db_v2
from config import BOT_TOKEN, ADMIN_TG_ID, TG_CHANNEL_URL, API_BASE_URL

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

_bot_username: str = ""   # set at startup

# ── Middleware: global rate-limit + block file uploads ────────────────────
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        upd: Update = data.get("event_update") or event
        # Достаём tg_id и тип события
        msg      = getattr(upd, "message", None)
        callback = getattr(upd, "callback_query", None)
        tg_id    = None
        if msg and msg.from_user:
            tg_id = msg.from_user.id
            # Блокируем document / photo / video / audio — бот их не принимает
            if msg.document or msg.video or msg.audio or msg.sticker:
                return
            if msg.photo and not is_admin(tg_id):
                return
            if not _check_rate(tg_id, is_callback=False):
                return
        elif callback and callback.from_user:
            tg_id = callback.from_user.id
            if not _check_rate(tg_id, is_callback=True):
                await callback.answer("Не так быстро!", show_alert=False)
                return
        return await handler(event, data)

dp.update.middleware(AntiSpamMiddleware())

# ── Rate limiting ──────────────────────────────────────────────────────────
# Хранит timestamps последних запросов по tg_id
_rl_store: dict[int, collections.deque] = {}
_RL_WINDOW   = 10    # секунд
_RL_MAX_MSG  = 5     # макс сообщений за окно
_RL_CB_WINDOW = 3    # секунд для callback
_RL_MAX_CB   = 8     # макс callback за окно

def _check_rate(tg_id: int, is_callback: bool = False) -> bool:
    """True = пропустить, False = заблокировать (слишком часто)."""
    if tg_id == ADMIN_TG_ID:
        return True
    now    = time.time()
    window = _RL_CB_WINDOW if is_callback else _RL_WINDOW
    limit  = _RL_MAX_CB   if is_callback else _RL_MAX_MSG
    key    = (tg_id, is_callback)
    if key not in _rl_store:
        _rl_store[key] = collections.deque()
    dq = _rl_store[key]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


# ── FSM States ────────────────────────────────────────────────────────────

class SupportForm(StatesGroup):
    message = State()

class SupportReply(StatesGroup):
    text = State()

class BroadcastForm(StatesGroup):
    text    = State()
    confirm = State()


# ── Helpers ───────────────────────────────────────────────────────────────

def is_admin(tg_id: int) -> bool:
    return tg_id == ADMIN_TG_ID


def _fmt_ago(ts: float | None) -> str:
    if not ts:
        return "никогда"
    d = time.time() - ts
    if d < 60:
        return f"{int(d)}с назад"
    if d < 3600:
        return f"{int(d/60)}мин назад"
    return f"{int(d/3600)}ч назад"


def _fmt_dur(secs: int) -> str:
    if secs <= 0:
        return "—"
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def _session_str(acc: dict) -> str:
    start = acc.get("session_start") or 0
    seen  = acc.get("last_seen") or 0
    if not start:
        return "—"
    is_on = (time.time() - seen) < 35
    end   = time.time() if is_on else seen
    return _fmt_dur(int(end - start))


def _total_r(acc: dict) -> int:
    return (acc.get("robux_alltime") or 0) + (acc.get("robux_gross") or 0)

def _total_d(acc: dict) -> int:
    return (acc.get("donations_alltime") or 0) + (acc.get("donations") or 0)

def _total(acc: dict, field: str) -> int:
    return (acc.get(f"{field}_alltime") or 0) + (acc.get(field) or 0)


def _bar(ratio: float, width: int = 10) -> str:
    filled = round(max(0.0, min(1.0, ratio)) * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _ref_link(tg_id: int) -> str:
    return f"https://t.me/{_bot_username}?start=ref_{tg_id}"


def _trial_time_str(expires_at: float) -> str:
    left = expires_at - time.time()
    if left <= 0:
        return "истёк"
    d = int(left // 86400)
    h = int((left % 86400) // 3600)
    if d > 0:
        return f"{d}д {h}ч"
    m = int((left % 3600) // 60)
    return f"{h}ч {m}м"


# ── Keyboards ─────────────────────────────────────────────────────────────

def _user_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"),      KeyboardButton(text="🔑 Мой ключ")],
            [KeyboardButton(text="📜 Получить скрипт"), KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="🌐 Дашборд"),         KeyboardButton(text="📖 Инструкция")],
            [KeyboardButton(text="📬 Поддержка"),        KeyboardButton(text="📣 Новости")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def _no_key_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="📬 Поддержка"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def _cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


# ── Texts ─────────────────────────────────────────────────────────────────

_GUIDE_TEXT = (
    "🚀 <b>Запуск за 3 минуты</b>\n\n"

    "  1.  Напиши /getscript — скачай файл\n"
    "  2.  Открой <b>Xeno</b> (инжектор)\n"
    "  3.  Зайди в <b>Please Donate</b>\n"
    "  4.  Инжектируй скрипт → вставь ключ → готово\n\n"

    "Бот сам найдёт игроков, напишет им и попросит донат.\n"
    "Ты просто оставляешь его работать.\n\n"

    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"

    "🎮 <b>Перед запуском</b>\n\n"

    "  <b>Геймпасс</b> — без него тебе не смогут задонатить:\n"
    "  create.roblox.com → Creations → любая игра →\n"
    "  Monetization → Passes → Create a Pass → задай цену\n\n"

    "  <b>Верификация лица</b> — <b>обязательно!</b> Без неё бот\n"
    "  не сможет писать в чат и соберёт в разы меньше робуксов.\n"
    "  Пройди верификацию и убедись что чат работает!\n\n"

    "  <b>VPN</b> — если ты из РФ, включи VPN перед запуском\n"
    "  (Cloudflare заблокирован).\n\n"

    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"

    "🔒 <b>Безопасность</b>\n\n"
    "  Ключ привязан к твоему ПК (HWID). Запускай с любого аккаунта.\n"
    "  Передать другому человеку — не получится.\n"
    "  Другой ПК — напиши в /support.\n\n"

    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"

    "🔄 <b>Несколько аккаунтов</b>\n\n"
    "  Хочешь фармить сразу с нескольких?\n"
    "  Установи MultiRoblox + Roblox Account Manager\n"
    "  и запусти скрипт в каждом клиенте с тем же ключом.\n\n"

    "Вопросы — /support\n\n"
    "📺 YouTube: youtube.com/@coldyz\n"
    "📢 Telegram: t.me/coldyz"
)

_NEWS_TEXT = (
    "📣 <b>Что нового — v23</b>\n\n"

    "🧠 <b>Умный скрипт</b>\n"
    "  Полностью переписан движок общения.\n"
    "  Бот анализирует ответы игроков и подстраивает\n"
    "  стратегию — комплименты, разные фразы, дожим.\n"
    "  Конверсия выросла в 2-3 раза.\n\n"

    "⚡ <b>Стабильность</b>\n"
    "  Автоматический серверхоп если сервер пустой.\n"
    "  Защита от AFK-кика. Антидетект модераторов.\n"
    "  Автопереподключение при вылете.\n"
    "  Работает часами без перезапуска.\n\n"

    "🌐 <b>Дашборд</b>\n"
    "  Новая панель в браузере — /dashboard\n"
    "  Статистика в реальном времени, лог диалогов,\n"
    "  конверсия, история сессий.\n\n"

    "📊 <b>Аналитика</b>\n"
    "  Графики по часам, экспорт в CSV,\n"
    "  топ ответов игроков, фильтры по аккаунтам.\n\n"

    "🎁 <b>Рефералы</b>\n"
    "  2 друга → пожизненный доступ\n"
    "  5+ друзей → 10% от их заработка\n"
    "  Ссылка: /myrefs\n\n"

    "🔮 <b>Что дальше</b>\n"
    "  В планах — подключить нейросеть для генерации\n"
    "  сообщений. Бот будет общаться как живой человек,\n"
    "  адаптироваться под каждого игрока и поднимать\n"
    "  конверсию ещё выше.\n\n"

    "📬 Идеи и баги — /support"
)



# ── Ref threshold check ───────────────────────────────────────────────────

async def _check_ref_thresholds(ref_id: int):
    """Проверяет пороги рефералов и апгрейдит ключ если нужно."""
    ref_count = db_v2.get_ref_count(ref_id)
    lic = db_v2.get_license_by_tg(ref_id)

    # Порог 1: 2 рефа → лайфтайм
    if ref_count >= 2 and lic and lic.get("key_type") == "trial":
        new_key = db_v2.give_lifetime_key(ref_id)
        try:
            await bot.send_message(
                ref_id,
                f"🎉 <b>Ты пригласил {ref_count} друзей — получаешь пожизненный доступ!</b>\n\n"
                f"♾ Новый ключ: <code>{new_key}</code>\n\n"
                f"Перезапусти скрипт с новым ключом.",
                parse_mode="HTML",
                reply_markup=_user_kb(),
            )
        except Exception:
            pass

    # Порог 2: 3й реф → начало начисления 10%
    elif ref_count == 3:
        try:
            await bot.send_message(
                ref_id,
                f"💸 <b>Ты пригласил 3 друзей!</b>\n\n"
                f"Теперь с каждого нового реферала ты получаешь <b>10% от его заработка</b> автоматически.\n"
                f"Смотри накопленное: /myrefs",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ── /start ────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    if not _check_rate(msg.from_user.id):
        return
    await state.clear()
    tg_id = msg.from_user.id

    # Парсим реферальный параметр
    ref_id = None
    args = msg.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            candidate = int(args[1][4:])
            if 1 <= candidate <= 9_999_999_999:
                ref_id = candidate
        except ValueError:
            pass

    db_v2.upsert_user(tg_id, msg.from_user.username or "", msg.from_user.full_name)

    # Засчитываем реферала (только новый пользователь без referred_by)
    if ref_id and ref_id != tg_id:
        user_row = db_v2.get_user(tg_id)
        ref_user = db_v2.get_user(ref_id)
        if ref_user and user_row and not user_row.get("referred_by"):
            db_v2.set_referred_by(tg_id, ref_id)
            await _check_ref_thresholds(ref_id)

    lic = db_v2.get_license_by_tg(tg_id)

    # Есть валидный ключ (trial или lifetime)
    if lic and db_v2.is_key_valid(lic):
        key_type   = lic.get("key_type", "lifetime")
        expires_at = lic.get("expires_at")
        ref_count  = db_v2.get_ref_count(tg_id)
        bound      = lic.get("roblox_name") or lic.get("roblox_user_id") or "не привязан"

        if key_type == "trial" and expires_at:
            time_str   = _trial_time_str(expires_at)
            key_notice = f"⏳ Пробный ключ: осталось <b>{time_str}</b>"
            if ref_count < 2:
                needed = 2 - ref_count
                key_notice += (
                    f"\n🔗 Пригласи ещё <b>{needed}</b> друга чтобы получить пожизненный доступ:\n"
                    f"<code>{_ref_link(tg_id)}</code>"
                )
        else:
            ref_balance = db_v2.get_ref_balance(tg_id)
            bal_str = f"  💸 R${_fmt_num(ref_balance)} накоплено с рефералов" if ref_balance > 0 else ""
            key_notice = f"♾ Доступ: <b>пожизненный</b>{bal_str}"

        await msg.answer(
            f"👋 С возвращением, <b>{msg.from_user.first_name}</b>!\n\n"
            f"🔑 <code>{lic['key']}</code>\n"
            f"🎮 {bound}\n"
            f"{key_notice}\n\n"
            f"👥 Рефералов: <b>{ref_count}</b>  ·  /myrefs",
            parse_mode="HTML",
            reply_markup=_user_kb(),
        )
        return

    # Пробный период истёк
    if lic and lic.get("key_type") == "trial":
        ref_count = db_v2.get_ref_count(tg_id)
        if ref_count >= 2:
            new_key = db_v2.give_lifetime_key(tg_id)
            await msg.answer(
                f"♾ <b>Пробный период закончился, но ты уже пригласил {ref_count} друзей!</b>\n\n"
                f"🎉 Получаешь пожизненный доступ!\n"
                f"🔑 Новый ключ: <code>{new_key}</code>\n\n"
                f"Используй /getscript чтобы скачать скрипт.",
                parse_mode="HTML",
                reply_markup=_user_kb(),
            )
            return

        needed = 2 - ref_count
        await msg.answer(
            f"⏰ <b>Пробный период закончился</b>\n\n"
            f"Чтобы продолжить — пригласи ещё <b>{needed}</b>:\n"
            f"<code>{_ref_link(tg_id)}</code>\n\n"
            f"Прогресс: <b>{ref_count}/2</b>  {_bar(ref_count/2)}",
            parse_mode="HTML",
            reply_markup=_no_key_kb(),
        )
        return

    # Новый пользователь или нет ключа → выдаём пробный
    key = db_v2.give_trial_key(tg_id)
    await msg.answer(
        f"👋 <b>{msg.from_user.first_name}</b>, добро пожаловать!\n\n"
        f"Этот бот автоматически зарабатывает Robux в Please Donate.\n"
        f"Ты просто запускаешь скрипт — он сам подходит к игрокам,\n"
        f"пишет им и просит задонатить. Всё на автопилоте.\n\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        f"🎁 Твой пробный ключ <b>(3 дня)</b>:\n"
        f"<code>{key}</code>\n\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        f"💡 <b>Что дальше?</b>\n\n"
        f"  1. Нажми «📖 Инструкция» — там 4 простых шага\n"
        f"  2. Или сразу /getscript — скачай и запускай\n\n"
        f"♾ Пригласи <b>2 друзей</b> — получишь доступ навсегда:\n"
        f"<code>{_ref_link(tg_id)}</code>\n\n"
        f"📺 YouTube: youtube.com/@coldyz\n"
        f"📢 Telegram: t.me/coldyz",
        parse_mode="HTML",
        reply_markup=_user_kb(),
    )


# ── Кнопки главного меню ──────────────────────────────────────────────────

@dp.message(F.text == "📊 Статистика")
async def btn_stats(msg: Message):
    await cmd_mystats(msg)

@dp.message(F.text == "🔑 Мой ключ")
async def btn_mykey(msg: Message):
    await cmd_mykey(msg)

@dp.message(F.text == "📜 Получить скрипт")
async def btn_getscript(msg: Message):
    await cmd_getscript(msg)

@dp.message(F.text == "👥 Рефералы")
async def btn_refs(msg: Message):
    await cmd_myrefs(msg)

@dp.message(F.text == "📬 Поддержка")
async def btn_support(msg: Message, state: FSMContext):
    await cmd_support(msg, state)

@dp.message(F.text == "ℹ️ Помощь")
async def btn_help(msg: Message):
    await cmd_help(msg)

@dp.message(F.text == "📖 Инструкция")
async def btn_guide(msg: Message):
    await cmd_guide(msg)

@dp.message(F.text == "📣 Новости")
async def btn_news(msg: Message):
    await cmd_news(msg)

@dp.message(F.text == "🌐 Дашборд")
async def btn_dashboard(msg: Message):
    await cmd_dashboard(msg)


# ── /dashboard ───────────────────────────────────────────────────────

@dp.message(Command("dashboard"))
async def cmd_dashboard(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    if not lic or not db_v2.is_key_valid(lic):
        await msg.answer("❌ У тебя нет активного ключа. Напиши /start.", reply_markup=_no_key_kb())
        return

    token = db_v2.create_dashboard_token(lic["key"])
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/dashboard?token={token}"

    await msg.answer(
        f"🌐 <b>Твоя панель управления</b>\n\n"
        f"<a href=\"{url}\">🔗 Открыть дашборд</a>\n\n"
        f"⏳ Ссылка действует <b>1 час</b>\n"
        f"🔒 Одноразовая — не передавай другим\n\n"
        f"<i>Для новой ссылки нажми /dashboard ещё раз</i>",
        parse_mode="HTML",
        reply_markup=_user_kb(),
        disable_web_page_preview=True,
    )


# ── /guide ────────────────────────────────────────────────────────────────

@dp.message(Command("guide"))
async def cmd_guide(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    kb  = _user_kb() if (lic and db_v2.is_key_valid(lic)) else _no_key_kb()
    await msg.answer(_GUIDE_TEXT, parse_mode="HTML", reply_markup=kb)


# ── /help ─────────────────────────────────────────────────────────────────

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    lic     = db_v2.get_license_by_tg(msg.from_user.id)
    has_key = lic and db_v2.is_key_valid(lic)

    if has_key:
        text = (
            "ℹ️ <b>Команды:</b>\n\n"
            "📊 /mystats — статистика и сессии\n"
            "🔑 /mykey — посмотреть ключ\n"
            "🌐 /dashboard — панель в браузере\n"
            "👥 /myrefs — рефералы и ссылка\n"
            "📜 /getscript — файл лоадера\n"
            "📣 /news — новости\n"
            "📬 /support — тех. поддержка\n"
            "📖 /guide — инструкция\n\n"
            "📺 youtube.com/@coldyz"
        )
        kb = _user_kb()
    else:
        text = (
            "ℹ️ <b>Команды:</b>\n\n"
            "🏠 /start — главная\n"
            "👥 /myrefs — рефералы и ссылка\n"
            "📬 /support — тех. поддержка"
        )
        kb = _no_key_kb()

    await msg.answer(text, parse_mode="HTML", reply_markup=kb)


# ── /myrefs ───────────────────────────────────────────────────────────────

@dp.message(Command("myrefs"))
async def cmd_myrefs(msg: Message):
    tg_id = msg.from_user.id
    db_v2.upsert_user(tg_id, msg.from_user.username or "", msg.from_user.full_name)

    ref_count   = db_v2.get_ref_count(tg_id)
    refs        = db_v2.get_refs_with_earnings(tg_id)
    link        = _ref_link(tg_id)
    ref_balance = db_v2.get_ref_balance(tg_id)

    ref_lines = []
    for i, r in enumerate(refs[:20]):
        uname    = f"@{r['tg_username']}" if r.get("tg_username") else f"ID:{r['tg_id']}"
        r_lic    = db_v2.get_license_by_tg(r["tg_id"])
        icon     = "✅" if (r_lic and db_v2.is_key_valid(r_lic)) else "⏸"
        earned   = r.get("robux_earned", 0)
        num      = i + 1
        # рефы #1-#2 помечены как "бесплатные" (за лайфтайм)
        if num <= 2:
            ref_lines.append(f"  {icon} #{num} {uname}  <i>+лайфтайм</i>")
        else:
            ref_lines.append(f"  {icon} #{num} {uname}  R${_fmt_num(earned)} заработал → тебе R${_fmt_num(int(earned*0.10))}")
    if len(refs) > 20:
        ref_lines.append(f"  <i>...и ещё {len(refs)-20}</i>")
    ref_block = "\n".join(ref_lines) if ref_lines else "  <i>пока никого нет</i>"

    if ref_count < 2:
        tier = f"До пожизненного доступа: <b>{ref_count}/2</b>  {_bar(ref_count/2)}"
    elif ref_count < 3:
        tier = f"До начала 10% от рефералов: <b>{ref_count}/3</b>  {_bar(ref_count/3)}"
    else:
        tier = f"💸 Накоплено с рефералов: <b>R$ {_fmt_num(ref_balance)}</b>  (10% с каждого)"

    text = (
        f"👥 <b>Мои рефералы</b>\n\n"
        f"Приглашено: <b>{ref_count}</b>\n"
        f"{tier}\n\n"
        f"🔗 Твоя ссылка:\n"
        f"<code>{link}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Кто пришёл по твоей ссылке:\n"
        f"{ref_block}"
    )

    buttons = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="myrefs_refresh")]]
    if ref_balance > 0 and not db_v2.has_pending_payout(tg_id):
        buttons.append([InlineKeyboardButton(text=f"💸 Вывести R$ {_fmt_num(ref_balance)}", callback_data="payout_request")])
    elif db_v2.has_pending_payout(tg_id):
        buttons.append([InlineKeyboardButton(text="⏳ Заявка уже отправлена", callback_data="payout_already")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data == "myrefs_refresh")
async def cb_myrefs_refresh(cb: CallbackQuery):
    await cb.answer()
    await cmd_myrefs(cb.message)


# ── /refpanel ─────────────────────────────────────────────────────────────

@dp.message(Command("refpanel"))
async def cmd_refpanel(msg: Message):
    tg_id = msg.from_user.id
    db_v2.upsert_user(tg_id, msg.from_user.username or "", msg.from_user.full_name)
    ref_count = db_v2.get_ref_count(tg_id)
    if ref_count == 0:
        await msg.answer(
            "👥 У тебя пока нет рефералов. Поделись ссылкой — /myrefs",
            reply_markup=_user_kb(),
        )
        return
    token = db_v2.create_ref_token(tg_id)
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/ref?token={token}"
    await msg.answer(
        f"💸 <b>Реферальная панель</b>\n\n"
        f"<a href=\"{url}\">🔗 Открыть панель</a>\n\n"
        f"👥 Рефералов: <b>{ref_count}</b>\n"
        f"⏳ Ссылка действует <b>30 дней</b>\n\n"
        f"<i>Для новой ссылки нажми /refpanel ещё раз</i>",
        parse_mode="HTML",
        reply_markup=_user_kb(),
        disable_web_page_preview=True,
    )


@dp.callback_query(F.data == "payout_already")
async def cb_payout_already(cb: CallbackQuery):
    await cb.answer("Твоя заявка уже на рассмотрении, подожди.", show_alert=True)


@dp.callback_query(F.data == "payout_request")
async def cb_payout_request(cb: CallbackQuery):
    tg_id   = cb.from_user.id
    balance = db_v2.get_ref_balance(tg_id)
    if balance <= 0:
        await cb.answer("Баланс пустой.", show_alert=True); return
    if db_v2.has_pending_payout(tg_id):
        await cb.answer("Заявка уже отправлена, подожди.", show_alert=True); return

    uname = cb.from_user.username or ""
    name  = cb.from_user.full_name or ""
    rid   = db_v2.create_payout_request(tg_id, uname, name, balance)

    tg_link = f"@{uname}" if uname else f"<a href='tg://user?id={tg_id}'>{name}</a>"
    await bot.send_message(
        ADMIN_TG_ID,
        f"💸 <b>Заявка на вывод #{rid}</b>\n\n"
        f"👤 {tg_link}  (ID: <code>{tg_id}</code>)\n"
        f"💰 Сумма: <b>R$ {_fmt_num(balance)}</b>\n\n"
        f"Выплати и нажми ✅, или отклони ❌",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Выплачено", callback_data=f"payout_paid:{rid}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"payout_reject:{rid}"),
        ]]),
    )
    await cb.answer("Заявка отправлена! Мы свяжемся с тобой.", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏳ Заявка отправлена", callback_data="payout_already"),
    ]]))


@dp.callback_query(F.data.startswith("payout_paid:"))
async def cb_payout_paid(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        rid = int(cb.data.split(":")[1])
    except (IndexError, ValueError):
        await cb.answer("Неверный запрос", show_alert=True); return
    info = db_v2.resolve_payout(rid, "paid")
    if not info:
        await cb.answer("Заявка не найдена", show_alert=True); return
    await cb.message.edit_text(
        cb.message.text + "\n\n✅ <b>Выплачено</b>", parse_mode="HTML"
    )
    try:
        await bot.send_message(
            info["tg_id"],
            f"✅ <b>Выплата R$ {_fmt_num(info['amount'])} подтверждена!</b>\n\n"
            f"Спасибо за приглашённых рефералов 🙌",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await cb.answer("Выплата подтверждена")


@dp.callback_query(F.data.startswith("payout_reject:"))
async def cb_payout_reject(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        rid = int(cb.data.split(":")[1])
    except (IndexError, ValueError):
        await cb.answer("Неверный запрос", show_alert=True); return
    info = db_v2.resolve_payout(rid, "rejected")
    if not info:
        await cb.answer("Заявка не найдена", show_alert=True); return
    await cb.message.edit_text(
        cb.message.text + "\n\n❌ <b>Отклонено</b>", parse_mode="HTML"
    )
    try:
        await bot.send_message(
            info["tg_id"],
            f"❌ Заявка на вывод R$ {_fmt_num(info['amount'])} отклонена.\n"
            f"Напиши нам если есть вопросы.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await cb.answer("Заявка отклонена")


# ── ADMIN: список заявок на вывод ─────────────────────────────────────────

@dp.callback_query(F.data == "admin_payouts")
async def admin_payouts_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    pending = db_v2.get_pending_payouts()
    if not pending:
        await cb.answer("Нет ожидающих заявок", show_alert=True); return
    for p in pending:
        uname   = f"@{p['tg_username']}" if p.get("tg_username") else p["tg_name"] or str(p["tg_id"])
        created = time.strftime("%d.%m %H:%M", time.localtime(p["created_at"]))
        await cb.message.answer(
            f"💸 <b>Заявка #{p['id']}</b>  [{created}]\n"
            f"👤 {uname}  (ID: <code>{p['tg_id']}</code>)\n"
            f"💰 R$ {_fmt_num(p['amount'])}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Выплачено", callback_data=f"payout_paid:{p['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"payout_reject:{p['id']}"),
            ]]),
        )
    await cb.answer()


# ── /mykey ────────────────────────────────────────────────────────────────

@dp.message(Command("mykey"))
async def cmd_mykey(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    if not lic:
        await msg.answer("У тебя нет ключа. Напиши /start.", reply_markup=_no_key_kb())
        return

    bound      = lic.get("roblox_name") or lic.get("roblox_user_id") or "не привязан"
    key_type   = lic.get("key_type", "lifetime")
    expires_at = lic.get("expires_at")
    valid      = db_v2.is_key_valid(lic)

    if key_type == "trial" and expires_at:
        if valid:
            type_str = f"⏳ Пробный — осталось <b>{_trial_time_str(expires_at)}</b>"
        else:
            type_str = "❌ Пробный — <b>истёк</b>"
    else:
        type_str = "♾ <b>Пожизненный</b>"

    icon = "✅" if valid else "❌"
    hwid_str = "🔒 привязано" if lic.get("hwid") else "🔓 не привязано"
    await msg.answer(
        f"{icon} Твой ключ:\n<code>{lic['key']}</code>\n\n"
        f"Тип: {type_str}\n"
        f"Аккаунт: {bound}\n"
        f"Устройство: {hwid_str}\n\n"
        f"<i>Ключ работает только на одном ПК.\n"
        f"Нужно больше устройств? Напиши /support</i>",
        parse_mode="HTML",
    )


# ── /mystats ──────────────────────────────────────────────────────────────

def _build_mystats_text(acc: dict, lic: dict, sessions: list[dict]) -> str:
    name      = lic.get("roblox_name") or lic.get("roblox_user_id") or "не привязан"
    is_online = (time.time() - (acc.get("last_seen") or 0)) < 35
    status    = "🟢 <b>Online</b>" if is_online else "🔴 Offline"
    sess_str  = _session_str(acc) if is_online else "—"

    gross     = _total_r(acc)
    gross_now = acc.get("robux_gross") or 0
    net       = int(gross * 0.6)
    booth     = acc.get("raised_current") or 0
    appr      = _total(acc, "approached")
    agr       = _total(acc, "agreed")
    ref_val   = _total(acc, "refused")
    nor       = _total(acc, "no_response")
    dons      = _total_d(acc)
    hops      = acc.get("hops")        or 0
    conv_pct  = agr * 100 // appr if appr > 0 else 0
    conv_bar  = _bar(conv_pct / 100)

    sess_lines = []
    for i, s in enumerate(sessions[:3], 1):
        dur    = _fmt_dur(int(s.get("duration") or 0))
        rgross = s.get("robux_gross") or 0
        rnet   = int(rgross * 0.6)
        sdons  = s.get("donations") or 0
        sappr  = s.get("approached") or 0
        sagr   = s.get("agreed") or 0
        active = not s.get("ended_at")
        tag    = " 🔴 <i>сейчас</i>" if active else ""
        sess_lines.append(
            f"  #{i}{tag}\n"
            f"  ⏱ {dur}  •  💰 R${_fmt_num(rgross)} → R${_fmt_num(rnet)}"
            f"  •  🎁 {sdons}  •  👥 {sappr}/{sagr}"
        )
    sess_block    = "\n".join(sess_lines) if sess_lines else "  <i>сессий пока нет</i>"
    last_seen_str = _fmt_ago(acc.get("last_seen")) if not is_online else "сейчас"

    lines = [
        f"╔═══════════════════════╗",
        f"  📊  <b>МОЯ СТАТИСТИКА</b>",
        f"╚═══════════════════════╝",
        f"",
        f"👤 <b>{name}</b>   {status}",
        f"⏰ Последний онлайн: <i>{last_seen_str}</i>",
    ]
    if is_online:
        lines.append(f"⏱ Текущая сессия: <b>{sess_str}</b>")
    lines += [
        f"",
        f"━━━━━━  💰 ЗАРАБОТОК  ━━━━━━",
        f"  Всего gross:    <b>R$ {_fmt_num(gross)}</b>",
        f"  Net (60%):      <b>R$ {_fmt_num(net)}</b>",
        f"  На стенде:      <b>R$ {_fmt_num(booth)}</b>",
        f"  Тек. сессия:    <b>R$ {_fmt_num(gross_now)}</b>",
        f"  Донаций всего:  <b>{dons}</b>",
        f"",
        f"━━━━━  📈 АКТИВНОСТЬ  ━━━━━━",
        f"  Подошёл:    <b>{_fmt_num(appr)}</b>",
        f"  Согласился: <b>{agr}</b>  ({conv_pct}%)  {conv_bar}",
        f"  Отказал:    <b>{ref_val}</b>",
        f"  Нет ответа: <b>{nor}</b>",
        f"  Прыжков:    <b>{hops}</b>",
        f"",
        f"━━━━━━  🕐 СЕССИИ  ━━━━━━━━",
        sess_block,
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>Открой /dashboard</b> — лог диалогов,",
        f"графики, подробная аналитика в реалтайме!",
    ]
    return "\n".join(lines)


def _mystats_kb(acc_id: str, total_sessions: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="my_refresh")]]
    if total_sessions > 3:
        buttons[0].append(
            InlineKeyboardButton(text=f"📋 Все сессии ({total_sessions})",
                                 callback_data=f"my_sess:{acc_id}:0")
        )
    buttons.append([InlineKeyboardButton(text="🌐 Открыть дашборд", callback_data="open_dashboard")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("mystats"))
async def cmd_mystats(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    if not lic:
        await msg.answer("❌ У тебя нет ключа. Напиши /start.")
        return

    acc = db_v2.get_account_by_license(lic["key"])
    if not acc:
        await msg.answer(
            "⏳ Скрипт ещё не запускался — статистика появится после первого запуска.",
            parse_mode="HTML",
        )
        return

    acc_id   = str(acc["id"])
    sessions = db_v2.get_sessions(acc_id, limit=3)
    total_s  = db_v2.count_sessions(acc_id)
    await msg.answer(
        _build_mystats_text(acc, lic, sessions),
        parse_mode="HTML",
        reply_markup=_mystats_kb(acc_id, total_s),
    )


def _own_acc_id(tg_id: int) -> str | None:
    lic = db_v2.get_license_by_tg(tg_id)
    if not lic or not db_v2.is_key_valid(lic):
        return None
    acc = db_v2.get_account_by_license(lic["key"])
    return str(acc["id"]) if acc else None


@dp.callback_query(F.data == "my_refresh")
async def cb_my_refresh(call: CallbackQuery):
    lic = db_v2.get_license_by_tg(call.from_user.id)
    if not lic:
        await call.answer("❌ Нет ключа", show_alert=True)
        return
    acc = db_v2.get_account_by_license(lic["key"])
    if not acc:
        await call.answer("Данных пока нет", show_alert=True)
        return
    acc_id   = str(acc["id"])
    sessions = db_v2.get_sessions(acc_id, limit=3)
    total_s  = db_v2.count_sessions(acc_id)
    text     = _build_mystats_text(acc, lic, sessions)
    kb       = _mystats_kb(acc_id, total_s)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await call.answer("✅ Обновлено")


@dp.callback_query(F.data == "open_dashboard")
async def cb_open_dashboard(call: CallbackQuery):
    lic = db_v2.get_license_by_tg(call.from_user.id)
    if not lic or not db_v2.is_key_valid(lic):
        await call.answer("❌ Нет активного ключа", show_alert=True)
        return
    token = db_v2.create_dashboard_token(lic["key"])
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/dashboard?token={token}"
    await call.message.answer(
        f"🌐 <b>Твой дашборд:</b>\n\n"
        f"<a href=\"{url}\">Открыть дашборд</a>\n\n"
        f"⏳ Ссылка действует <b>1 час</b>\n"
        f"📊 Лог диалогов, аналитика, сессии — всё в реалтайме!",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await call.answer()


@dp.callback_query(F.data.startswith("my_sess:"))
async def cb_my_sessions(call: CallbackQuery):
    try:
        parts = call.data.split(":")
        acc_id   = parts[1]
        raw_page = parts[2] if len(parts) > 2 else "0"
        page     = max(0, int(raw_page))
    except (IndexError, ValueError):
        await call.answer("Неверный запрос", show_alert=True); return
    if not is_admin(call.from_user.id):
        own = _own_acc_id(call.from_user.id)
        if own != acc_id:
            await call.answer("⛔ Это не твои данные.", show_alert=True)
            return

    lic = db_v2.get_license_by_tg(call.from_user.id)
    if not lic:
        await call.answer("❌ Нет ключа", show_alert=True)
        return
    limit = 5
    total = db_v2.count_sessions(acc_id)
    sessions = db_v2.get_sessions(acc_id, limit=limit, offset=page * limit)

    lines = [f"🕐 <b>История сессий</b>  (стр. {page+1}/{max(1,(total+limit-1)//limit)})\n"]
    for i, s in enumerate(sessions, page * limit + 1):
        dur    = _fmt_dur(int(s.get("duration") or 0))
        rg     = s.get("robux_gross") or 0
        rn     = int(rg * 0.6)
        dons   = s.get("donations") or 0
        appr   = s.get("approached") or 0
        agr    = s.get("agreed") or 0
        active = not s.get("ended_at")
        ts_str = time.strftime("%d.%m %H:%M", time.localtime(s.get("started_at") or 0))
        tag    = " 🔴 <i>активна</i>" if active else ""
        lines.append(
            f"<b>#{i}</b>  {ts_str}{tag}\n"
            f"  ⏱ {dur}  💰 R${_fmt_num(rg)}→R${_fmt_num(rn)}  🎁 {dons}  👥 {appr}/{agr}\n"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"my_sess:{acc_id}:{page-1}"))
    if (page + 1) * limit < total:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"my_sess:{acc_id}:{page+1}"))

    back_cb = "my_refresh" if not is_admin(call.from_user.id) else f"acc:{acc_id}"
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="↩ Назад", callback_data=back_cb)])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await call.answer()


# ── /getscript ────────────────────────────────────────────────────────────

@dp.message(Command("getscript"))
async def cmd_getscript(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    if not lic or not db_v2.is_key_valid(lic):
        if lic and lic.get("key_type") == "trial":
            await msg.answer(
                "❌ Пробный период истёк.\n\nПригласи 2 друзей чтобы продолжить: /myrefs",
                reply_markup=_no_key_kb(),
            )
        else:
            await msg.answer("❌ У тебя нет активного ключа. Напиши /start.")
        return

    # Prefer obfuscated loader; fall back to source if not built yet
    loader_path = os.path.join(os.path.dirname(__file__), "loader_v2_obf.lua")
    if not os.path.exists(loader_path):
        loader_path = os.path.join(os.path.dirname(__file__), "loader_v2.lua")
    if not os.path.exists(loader_path):
        await msg.answer("⚠️ Файл скрипта не найден. Обратись к администратору.")
        return

    with open(loader_path, "rb") as f:
        data = f.read()

    await msg.answer_document(
        BufferedInputFile(data, filename="loader.lua"),
        caption=(
            "📜 <b>Скрипт для инжектора</b>\n\n"
            "1. Скачай файл\n"
            "2. Открой в инжекторе (Xeno, Solara, Delta...)\n"
            "3. Зайди в <b>Please Donate</b> и инжектируй\n"
            "4. Введи ключ из /mykey\n\n"
            "🔑 Ключ — твой личный. Не передавай его другим."
        ),
        parse_mode="HTML",
    )


# ── /news ─────────────────────────────────────────────────────────────────

@dp.message(Command("news"))
async def cmd_news(msg: Message):
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    kb  = _user_kb() if (lic and db_v2.is_key_valid(lic)) else _no_key_kb()
    await msg.answer(_NEWS_TEXT, parse_mode="HTML", reply_markup=kb)


# ── ADMIN: /admin ─────────────────────────────────────────────────────────

@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer(
        "👑 <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users:0")],
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🤖 Аккаунты ботов",  callback_data="accp:0"),
             InlineKeyboardButton(text="📈 Сводка ботов",    callback_data="admin_botstat")],
            [InlineKeyboardButton(text="💸 Реф. статистика", callback_data="admin_refstats")],
            [InlineKeyboardButton(text=f"💳 Заявки на вывод ({len(db_v2.get_pending_payouts())})", callback_data="admin_payouts")],
        ]),
    )


@dp.callback_query(F.data == "admin_stats")
async def admin_stats_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.message.answer(
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: {db_v2.count_users()}\n"
        f"• Активных ключей: {db_v2.count_licenses()}\n"
        f"• Онлайн сейчас: {db_v2.count_active_accounts()}\n"
        f"• Всего R$ через бот: {db_v2.total_robux()}",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("admin_users:"))
async def admin_users_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        offset = max(0, int(cb.data.split(":")[1]))
    except (IndexError, ValueError):
        offset = 0
    users  = db_v2.get_all_users(limit=10, offset=offset)
    if not users:
        await cb.answer("Больше нет.", show_alert=True); return

    lines = []
    for u in users:
        lic       = db_v2.get_license_by_tg(u["tg_id"])
        ref_count = db_v2.get_ref_count(u["tg_id"])
        uname     = f"@{u['tg_username']}" if u.get("tg_username") else str(u["tg_id"])
        if not lic:
            key_s = "нет ключа"
        elif lic.get("key_type") == "lifetime":
            key_s = "♾ lifetime"
        elif db_v2.is_key_valid(lic):
            left = _trial_time_str(lic["expires_at"]) if lic.get("expires_at") else "?"
            key_s = f"⏳ trial ({left})"
        else:
            key_s = "❌ истёк"
        lines.append(f"• {uname} | {key_s} | рефов: {ref_count}")

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"admin_users:{offset-10}"))
    if len(users) == 10:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"admin_users:{offset+10}"))

    await cb.message.answer(
        f"👥 <b>Пользователи ({offset+1}–{offset+len(users)}):</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav]) if nav else None,
    )
    await cb.answer()


# ── ADMIN: реф. статистика ────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_refstats")
async def admin_refstats_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return

    top = db_v2.get_top_referrers(limit=20)
    if not top:
        await cb.message.answer("Рефералов пока нет.")
        await cb.answer()
        return

    lines = ["💸 <b>Реферальная статистика</b>\n"]
    for u in top:
        uname     = f"@{u['tg_username']}" if u.get("tg_username") else str(u["tg_id"])
        ref_count = u.get("ref_count", 0)

        # Считаем заработок рефералов (все аккаунты каждого реферала)
        refs = db_v2.get_refs(u["tg_id"])
        total_ref_r = 0
        for r in refs:
            r_lic = db_v2.get_license_by_tg(r["tg_id"])
            if r_lic:
                for acc in db_v2.get_all_accounts_by_license(r_lic["key"]):
                    total_ref_r += _total_r(acc)
        payout = int(total_ref_r * 0.6 * 0.10)
        tier_icon = "💸" if ref_count >= 5 else ("♾" if ref_count >= 2 else "⏳")
        lines.append(
            f"{tier_icon} <b>{uname}</b> — {ref_count} реф.  |  "
            f"заработали R${_fmt_num(total_ref_r)}  |  "
            f"{'долг R$' + _fmt_num(payout) if ref_count >= 5 else '—'}"
        )

    await cb.message.answer("\n".join(lines), parse_mode="HTML")
    await cb.answer()


@dp.message(Command("refstats"))
async def cmd_refstats(msg: Message):
    if not is_admin(msg.from_user.id): return
    cb_fake = type("Obj", (), {
        "from_user": msg.from_user,
        "message":   msg,
        "answer":    lambda *a, **kw: None,
    })()
    await admin_refstats_cb(cb_fake)


# ── ADMIN: /revoke, /give, /stats, /users ─────────────────────────────────

@dp.message(Command("revoke"))
async def cmd_revoke(msg: Message):
    if not is_admin(msg.from_user.id): return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        await msg.answer("Использование: /revoke <ключ или tg_id>"); return

    arg = args[1].strip()
    if "-" in arg and len(arg) > 10:
        lic = db_v2.get_license(arg)
        if not lic:
            await msg.answer("Ключ не найден."); return
        db_v2.revoke_license(arg)
        try:
            await bot.send_message(lic["tg_id"],
                                   "❌ Твой ключ был <b>отозван</b> администратором.",
                                   parse_mode="HTML")
        except Exception:
            pass
        await msg.answer(f"✅ Ключ <code>{arg}</code> отозван.", parse_mode="HTML")
    else:
        try:
            tg_id = int(arg)
        except ValueError:
            await msg.answer("Неверный формат."); return
        lic = db_v2.get_license_by_tg(tg_id)
        if not lic:
            await msg.answer("Ключ не найден."); return
        db_v2.revoke_license(lic["key"])
        try:
            await bot.send_message(tg_id,
                                   "❌ Твой ключ был <b>отозван</b> администратором.",
                                   parse_mode="HTML")
        except Exception:
            pass
        await msg.answer(f"✅ Ключ пользователя {tg_id} отозван.")


@dp.message(Command("reset"))
async def cmd_reset(msg: Message):
    if not is_admin(msg.from_user.id): return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        await msg.answer("Использование: /reset <tg_id>"); return
    try:
        tg_id = int(args[1].strip())
    except ValueError:
        await msg.answer("Неверный tg_id."); return

    lic = db_v2.get_license_by_tg(tg_id)
    old_key = lic["key"] if lic else None
    db_v2.reset_license(tg_id)
    try:
        await bot.send_message(tg_id,
                               "🔄 Твой ключ был <b>сброшен</b> администратором.\n"
                               "Напиши /start чтобы получить новый.",
                               parse_mode="HTML")
    except Exception:
        pass
    if old_key:
        await msg.answer(f"✅ Ключ <code>{old_key}</code> удалён.", parse_mode="HTML")
    else:
        await msg.answer(f"✅ У пользователя {tg_id} не было ключа — статус сброшен.")


@dp.message(Command("give"))
async def cmd_give(msg: Message):
    if not is_admin(msg.from_user.id): return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        await msg.answer("Использование: /give <tg_id>"); return
    try:
        tg_id = int(args[1].strip())
    except ValueError:
        await msg.answer("Неверный tg_id."); return

    user = db_v2.get_user(tg_id)
    if not user:
        await msg.answer("Пользователь не найден. Он должен сначала написать /start."); return

    key = db_v2.give_license(tg_id)
    try:
        await bot.send_message(
            tg_id,
            f"🎁 <b>Пожизненный ключ от администратора:</b>\n<code>{key}</code>\n\n"
            f"Напиши /getscript чтобы скачать скрипт.",
            parse_mode="HTML",
            reply_markup=_user_kb(),
        )
    except Exception:
        pass
    await msg.answer(f"✅ Ключ <code>{key}</code> (lifetime) выдан {tg_id}.", parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not is_admin(msg.from_user.id): return
    await msg.answer(
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: {db_v2.count_users()}\n"
        f"• Активных ключей: {db_v2.count_licenses()}\n"
        f"• Онлайн сейчас: {db_v2.count_active_accounts()}\n"
        f"• Всего R$ через бот: {db_v2.total_robux()}",
        parse_mode="HTML",
    )


@dp.message(Command("users"))
async def cmd_users(msg: Message):
    if not is_admin(msg.from_user.id): return
    users = db_v2.get_all_users(limit=10, offset=0)
    lines = []
    for u in users:
        lic   = db_v2.get_license_by_tg(u["tg_id"])
        key_s = f"🔑 {lic['status']}" if lic else "нет ключа"
        uname = f"@{u['tg_username']}" if u.get("tg_username") else str(u["tg_id"])
        lines.append(f"• {uname} | {key_s}")
    total = db_v2.count_users()
    kb = None
    if total > 10:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Вперёд ▶", callback_data="admin_users:10")
        ]])
    await msg.answer(
        f"👥 <b>Пользователи (1–{len(users)} из {total}):</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
    )


# ── ADMIN: аккаунты ботов ─────────────────────────────────────────────────

_ACCS_PAGE = 5


async def _render_accounts_page(target, page: int, edit: bool = False):
    now   = time.time()
    total = db_v2.count_all_accounts()
    pages = max(1, (total + _ACCS_PAGE - 1) // _ACCS_PAGE)
    page  = max(0, min(page, pages - 1))
    accs  = db_v2.get_all_accounts(limit=_ACCS_PAGE, offset=page * _ACCS_PAGE)

    if not accs:
        text = "📊 Нет аккаунтов в базе."
        kb   = None
    else:
        lines = [f"📊 <b>Аккаунты — стр. {page+1}/{pages}</b>  (всего: {total})\n"]
        for acc in accs:
            on   = (now - (acc["last_seen"] or 0)) < 35
            icon = "🟢" if on else "🔴"
            name = acc["name"] or f"UID:{acc['id']}"
            sess = _session_str(acc)
            r    = acc["robux_gross"] or 0
            lines.append(f"{icon} <b>{name}</b>  R${r}  сессия: {sess}")
        text = "\n".join(lines)

        btn_rows = []
        for acc in accs:
            on   = (now - (acc["last_seen"] or 0)) < 35
            icon = "🟢" if on else "🔴"
            name = acc["name"] or f"UID:{acc['id']}"
            btn_rows.append([InlineKeyboardButton(
                text=f"{icon} {name}", callback_data=f"acc:{acc['id']}",
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀", callback_data=f"accp:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="pg_noop"))
        if page + 1 < pages:
            nav.append(InlineKeyboardButton(text="▶", callback_data=f"accp:{page+1}"))
        btn_rows.append(nav)
        btn_rows.append([InlineKeyboardButton(text="📈 Общая сводка", callback_data="admin_botstat")])
        kb = InlineKeyboardMarkup(inline_keyboard=btn_rows)

    msg = target if isinstance(target, Message) else target.message
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        if not isinstance(target, Message):
            await target.answer()
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@dp.message(Command("accounts"))
async def cmd_accounts(msg: Message):
    if not is_admin(msg.from_user.id): return
    await _render_accounts_page(msg, page=0)


@dp.callback_query(F.data.startswith("accp:"))
async def accp_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        page = max(0, int(cb.data.split(":", 1)[1]))
    except (IndexError, ValueError):
        page = 0
    await _render_accounts_page(cb, page=page, edit=True)


@dp.callback_query(F.data == "pg_noop")
async def pg_noop_cb(cb: CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data.startswith("acc:"))
async def acc_detail_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return

    acc_id = cb.data.split(":", 1)[1]
    acc    = db_v2.get_account(acc_id)
    if not acc:
        await cb.answer("Аккаунт не найден", show_alert=True); return

    now   = time.time()
    is_on = (now - (acc["last_seen"] or 0)) < 35
    st_icon = "🟢 Online" if is_on else "🔴 Offline"
    sess  = _session_str(acc)
    conv  = (
        f"{acc['agreed'] * 100 // acc['approached']}%"
        if (acc["approached"] or 0) > 0 else "—"
    )
    gross = acc["robux_gross"] or 0
    net   = int(gross * 0.6)

    owner_line = ""
    lic = db_v2.get_license(acc["license_key"]) if acc.get("license_key") else None
    if lic:
        u     = db_v2.get_user(lic["tg_id"])
        uname = f"@{u['tg_username']}" if u and u.get("tg_username") else str(lic["tg_id"])
        key_s = lic["key"]
        owner_line = f"\n👤 Владелец: {uname}  🔑 <code>{key_s}</code>"

    recent_sessions = db_v2.get_sessions(acc_id, limit=3)
    total_sess      = db_v2.count_sessions(acc_id)
    sess_lines = []
    for s in recent_sessions:
        is_open  = s["ended_at"] is None
        dt       = time.strftime("%d.%m %H:%M", time.localtime(s["started_at"]))
        dur_str  = "▶ активна" if is_open else _fmt_dur(int(s["duration"] or 0))
        r        = s["robux_gross"] or 0
        don      = s["donations"]   or 0
        sess_lines.append(f"  • {dt}  ⏱{dur_str}  💰R${r}  💸{don}дон.")
    sess_preview = "\n".join(sess_lines) if sess_lines else "  —"

    text = (
        f"👤 <b>{acc['name'] or acc['id']}</b>  {st_icon}"
        f"{owner_line}\n"
        f"⏱ Сессия: <b>{sess}</b>  |  Онлайн: {_fmt_ago(acc['last_seen'])}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💬 Подошёл:       <b>{acc['approached'] or 0}</b>\n"
        f"✅ Согласился:    <b>{acc['agreed'] or 0}</b>  ({conv})\n"
        f"❌ Отказал:       <b>{acc['refused'] or 0}</b>\n"
        f"😶 Нет ответа:    <b>{acc['no_response'] or 0}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💸 Донаций:       <b>{acc['donations'] or 0}</b>\n"
        f"💰 Заработано:    <b>R${gross}</b>  (чистыми R${net})\n"
        f"📊 Баланс стенда: R${acc['raised_current'] or 0}\n"
        f"🏃 Прыжков:       <b>{acc['hops'] or 0}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📋 Последние сессии (всего <b>{total_sess}</b>):\n"
        f"{sess_preview}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📋 Все сессии ({total_sess})",
                              callback_data=f"sess:{acc_id}:0")],
        [InlineKeyboardButton(text="↩ К списку", callback_data="accp:0")],
    ])
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


_SESS_PAGE = 5


@dp.callback_query(F.data.startswith("sess:"))
async def sess_list_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return

    try:
        parts  = cb.data.split(":")
        acc_id = parts[1]
        page   = max(0, int(parts[2])) if len(parts) > 2 else 0
    except (IndexError, ValueError):
        await cb.answer("Неверный запрос", show_alert=True); return

    total  = db_v2.count_sessions(acc_id)
    pages  = max(1, (total + _SESS_PAGE - 1) // _SESS_PAGE)
    page   = max(0, min(page, pages - 1))
    sessions = db_v2.get_sessions(acc_id, limit=_SESS_PAGE, offset=page * _SESS_PAGE)

    acc  = db_v2.get_account(acc_id)
    name = (acc["name"] if acc else None) or acc_id

    lines = [f"📋 <b>Сессии: {name}</b>\nстр. {page+1}/{pages}  ·  всего {total}\n"]
    for i, s in enumerate(sessions, page * _SESS_PAGE + 1):
        is_open  = s["ended_at"] is None
        dt_start = time.strftime("%d.%m %H:%M", time.localtime(s["started_at"]))
        dur_str  = "▶ <b>активна сейчас</b>" if is_open else f"⏱ {_fmt_dur(int(s['duration'] or 0))}"
        r    = s["robux_gross"] or 0
        net  = int(r * 0.6)
        don  = s["donations"] or 0
        app_s = s["approached"] or 0
        agr_s = s["agreed"]    or 0
        ref_s = s["refused"]   or 0
        conv_s = f"{agr_s * 100 // app_s}%" if app_s else "—"
        lines.append(
            f"\n<b>#{i}</b>  {dt_start}  {dur_str}\n"
            f"  💬 {app_s} подошёл  ✅ {agr_s} ({conv_s})  ❌ {ref_s}\n"
            f"  💸 {don} дон.  💰 R${r}  (чист. R${net})"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"sess:{acc_id}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="pg_noop"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"sess:{acc_id}:{page+1}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [InlineKeyboardButton(text="↩ К аккаунту", callback_data=f"acc:{acc_id}")],
    ])
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# ── ADMIN: botstat ────────────────────────────────────────────────────────

async def _render_botstat(target, edit: bool = False):
    now  = time.time()
    accs = db_v2.get_all_accounts(limit=500)
    dt   = time.strftime("%d.%m.%Y  %H:%M", time.localtime(now))

    online  = [a for a in accs if (now - (a["last_seen"] or 0)) < 35]
    total_robux = sum(_total_r(a) for a in accs)
    total_net   = int(total_robux * 0.6)
    total_don   = sum(_total_d(a) for a in accs)
    total_app   = sum(_total(a, "approached")  for a in accs)
    total_agr   = sum(_total(a, "agreed")      for a in accs)
    total_ref   = sum(_total(a, "refused")     for a in accs)
    total_nr    = sum(_total(a, "no_response") for a in accs)
    total_hops  = sum(a["hops"]        or 0 for a in accs)
    conv_pct    = total_agr * 100 // total_app if total_app else 0
    conv_bar    = _bar(conv_pct / 100, width=8)

    top5 = sorted(accs, key=_total_r, reverse=True)[:5]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    top_lines = []
    for i, a in enumerate(top5):
        if _total_r(a) == 0:
            break
        is_on = (now - (a["last_seen"] or 0)) < 35
        dot   = "🟢" if is_on else "⚫"
        name  = (a["name"] or a["id"])[:16]
        r     = _total_r(a)
        don   = _total_d(a)
        top_lines.append(f"  {medals[i]} {dot} <b>{name}</b>  R$ {_fmt_num(r)}  ({don} дон.)")
    top_block = "\n".join(top_lines) if top_lines else "  <i>пока нет данных</i>"

    on_lines = []
    for a in sorted(online, key=lambda a: a.get("last_seen") or 0, reverse=True):
        name    = (a["name"] or a["id"])[:18]
        r_all   = _total_r(a)
        r_now   = a.get("robux_gross") or 0
        don     = _total_d(a)
        hops    = a["hops"]       or 0
        agr     = a["agreed"]     or 0
        app     = a["approached"] or 0
        ago_sec = int(now - (a["last_seen"] or now))
        ago_str = f"{ago_sec}с" if ago_sec < 60 else f"{ago_sec//60}м"
        on_lines.append(
            f"  🟢 <b>{name}</b>  <i>(обн. {ago_str} назад)</i>\n"
            f"      💰 Всего R$ {_fmt_num(r_all)}  •  сессия R$ {_fmt_num(r_now)}\n"
            f"      💸 {don} дон.  🏃 {hops} пр.  👥 {agr}/{app}"
        )
    on_block = "\n".join(on_lines) if on_lines else "  <i>нет онлайн ботов</i>"

    text = (
        f"╔══════════════════════════╗\n"
        f"       📊 <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n"
        f"╚══════════════════════════╝\n"
        f"🕐 <i>{dt}</i>\n\n"
        f"━━━━━━  🤖 БОТЫ  ━━━━━━━━━\n"
        f"  Всего аккаунтов: <b>{len(accs)}</b>\n"
        f"  🟢 Онлайн:  <b>{len(online)}</b>\n"
        f"  🔑 Активных ключей: <b>{db_v2.count_licenses()}</b>\n\n"
        f"━━━━━━  💰 ФИНАНСЫ  ━━━━━━\n"
        f"  Gross:       <b>R$ {_fmt_num(total_robux)}</b>\n"
        f"  Net (60%):   <b>R$ {_fmt_num(total_net)}</b>\n"
        f"  Донаций:     <b>{_fmt_num(total_don)}</b>\n\n"
        f"━━━━━━  📈 АКТИВНОСТЬ  ━━━━\n"
        f"  Подошли:     <b>{_fmt_num(total_app)}</b>\n"
        f"  Согласились: <b>{_fmt_num(total_agr)}</b>  <code>{conv_pct}% {conv_bar}</code>\n"
        f"  Отказали:    <b>{_fmt_num(total_ref)}</b>\n"
        f"  Нет ответа:  <b>{_fmt_num(total_nr)}</b>\n"
        f"  Прыжков:     <b>{_fmt_num(total_hops)}</b>\n\n"
        f"━━━━━━  🏆 ТОП-5  ━━━━━━━\n"
        f"{top_block}\n\n"
        f"━━━━━━  🟢 ОНЛАЙН  ━━━━━━\n"
        f"{on_block}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все аккаунты", callback_data="accp:0"),
         InlineKeyboardButton(text="💸 Рефералы",    callback_data="admin_refstats")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_botstat")],
    ])

    msg = target if isinstance(target, Message) else target.message
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        if not isinstance(target, Message):
            await target.answer()
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@dp.message(Command("botstat"))
async def cmd_botstat(msg: Message):
    if not is_admin(msg.from_user.id): return
    await _render_botstat(msg)


@dp.callback_query(F.data == "admin_botstat")
async def admin_botstat_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    await _render_botstat(cb, edit=True)


# ── Тех. поддержка ────────────────────────────────────────────────────────

@dp.message(Command("support"))
async def cmd_support(msg: Message, state: FSMContext):
    await state.clear()
    db_v2.upsert_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.full_name)
    await state.set_state(SupportForm.message)
    await msg.answer(
        "📬 <b>Техническая поддержка</b>\n\n"
        "Опиши свою проблему — передам администратору.\n\n"
        "<i>«❌ Отмена» — выйти.</i>",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )


@dp.message(F.text == "❌ Отмена")
async def cancel_any(msg: Message, state: FSMContext):
    await state.clear()
    lic = db_v2.get_license_by_tg(msg.from_user.id)
    kb  = _user_kb() if (lic and db_v2.is_key_valid(lic)) else _no_key_kb()
    await msg.answer("Отменено.", reply_markup=kb)


@dp.message(SupportForm.message)
async def support_send(msg: Message, state: FSMContext):
    await state.clear()
    user    = db_v2.get_user(msg.from_user.id)
    lic     = db_v2.get_license_by_tg(msg.from_user.id)
    uname   = f"@{user['tg_username']}" if user and user.get("tg_username") else str(msg.from_user.id)
    key_str = lic["key"] if lic else "нет ключа"
    roblox  = (lic.get("roblox_name") or lic.get("roblox_user_id") or "не привязан") if lic else "—"

    admin_text = (
        f"📬 <b>Обращение в поддержку</b>\n\n"
        f"👤 {uname}  (ID: <code>{msg.from_user.id}</code>)\n"
        f"🔑 Ключ: <code>{key_str}</code>\n"
        f"🎮 Roblox: <b>{roblox}</b>\n\n"
        f"💬 <b>Вопрос:</b>\n{msg.text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Ответить", callback_data=f"sup_reply:{msg.from_user.id}"),
    ]])
    await bot.send_message(ADMIN_TG_ID, admin_text, parse_mode="HTML", reply_markup=kb)

    lic_check = db_v2.get_license_by_tg(msg.from_user.id)
    reply_kb  = _user_kb() if (lic_check and db_v2.is_key_valid(lic_check)) else _no_key_kb()
    await msg.answer(
        "✅ <b>Сообщение отправлено!</b>\n\nАдминистратор ответит в ближайшее время.",
        parse_mode="HTML",
        reply_markup=reply_kb,
    )


@dp.callback_query(F.data.startswith("sup_reply:"))
async def sup_reply_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    try:
        target_id = int(cb.data.split(":")[1])
    except (IndexError, ValueError):
        await cb.answer("Неверный запрос", show_alert=True); return
    user  = db_v2.get_user(target_id)
    uname = f"@{user['tg_username']}" if user and user.get("tg_username") else str(target_id)
    await state.set_state(SupportReply.text)
    await state.update_data(target_id=target_id, origin_msg_id=cb.message.message_id)
    await cb.message.answer(
        f"✏️ Напиши ответ для <b>{uname}</b>:\n\n<i>«❌ Отмена» — отменить.</i>",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )
    await cb.answer()


@dp.message(SupportReply.text)
async def sup_reply_send(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data          = await state.get_data()
    await state.clear()
    target_id     = data["target_id"]
    origin_msg_id = data.get("origin_msg_id")
    try:
        await bot.send_message(target_id,
                               f"📩 <b>Ответ от администратора:</b>\n\n{msg.text}",
                               parse_mode="HTML")
        if origin_msg_id:
            try:
                await bot.edit_message_reply_markup(
                    ADMIN_TG_ID, origin_msg_id,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="✅ Отвечено", callback_data="pg_noop"),
                        InlineKeyboardButton(text="💬 Ещё раз", callback_data=f"sup_reply:{target_id}"),
                    ]]),
                )
            except Exception:
                pass
        user  = db_v2.get_user(target_id)
        uname = f"@{user['tg_username']}" if user and user.get("tg_username") else str(target_id)
        await msg.answer(f"✅ Ответ отправлен <b>{uname}</b>!", parse_mode="HTML",
                         reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await msg.answer(f"❌ Не удалось доставить: <code>{e}</code>",
                         parse_mode="HTML", reply_markup=ReplyKeyboardRemove())


# ── Рассылка ──────────────────────────────────────────────────────────────

@dp.message(Command("broadcast"))
async def cmd_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    users = db_v2.get_all_users(limit=10_000)
    count = len(users)
    await state.set_state(BroadcastForm.text)
    await state.update_data(recipient_count=count)
    await msg.answer(
        f"📢 <b>Рассылка</b>\n\nПолучателей: <b>{count}</b>\n\n"
        f"Напиши текст (HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>)\n\n"
        f"<i>«❌ Отмена» — выйти.</i>",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )


@dp.message(BroadcastForm.text)
async def broadcast_text(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    await state.update_data(broadcast_text=msg.text)
    await state.set_state(BroadcastForm.confirm)
    await msg.answer(
        f"📢 <b>Предпросмотр:</b>\n\n{'─'*24}\n{msg.text}\n{'─'*24}\n\n"
        f"Отправить <b>{data['recipient_count']}</b> пользователям?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Отправить всем", callback_data="bc_confirm"),
            InlineKeyboardButton(text="❌ Отмена",         callback_data="bc_cancel"),
        ]]),
    )


@dp.callback_query(F.data == "bc_confirm")
async def bc_confirm(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    data = await state.get_data()
    await state.clear()
    text = data.get("broadcast_text", "")
    if not text:
        await cb.answer("Нет текста", show_alert=True); return
    await cb.message.edit_reply_markup()
    status_msg = await cb.message.answer("📤 Рассылка запущена...")
    users  = db_v2.get_all_users(limit=10_000)
    sent   = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user["tg_id"],
                                   f"📢 <b>Сообщение от администратора:</b>\n\n{text}",
                                   parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n📤 Доставлено: <b>{sent}</b>\n❌ Не доставлено: <b>{failed}</b>",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.callback_query(F.data == "bc_cancel")
async def bc_cancel(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await cb.message.edit_reply_markup()
    await cb.message.answer("Рассылка отменена.", reply_markup=ReplyKeyboardRemove())
    await cb.answer()


# ── Запуск ────────────────────────────────────────────────────────────────

async def main():
    global _bot_username
    db_v2.init_db()

    me = await bot.get_me()
    _bot_username = me.username or ""

    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    user_commands = [
        BotCommand(command="start",     description="🏠 Главная / получить ключ"),
        BotCommand(command="myrefs",    description="👥 Мои рефералы и ссылка"),
        BotCommand(command="mystats",   description="📊 Моя статистика"),
        BotCommand(command="mykey",     description="🔑 Мой ключ"),
        BotCommand(command="dashboard", description="🌐 Панель в браузере"),
        BotCommand(command="refpanel",  description="💸 Реферальная панель"),
        BotCommand(command="getscript", description="📜 Получить лоадер"),
        BotCommand(command="news",      description="📣 Новости"),
        BotCommand(command="guide",     description="📖 Инструкция"),
        BotCommand(command="support",   description="📬 Тех. поддержка"),
        BotCommand(command="help",      description="ℹ️ Помощь"),
    ]
    admin_commands = user_commands + [
        BotCommand(command="botstat",   description="📈 Статистика ботов"),
        BotCommand(command="refstats",  description="💸 Реф. статистика"),
        BotCommand(command="broadcast", description="📢 Рассылка"),
        BotCommand(command="accounts",  description="👥 Список аккаунтов"),
        BotCommand(command="admin",     description="🔧 Панель управления"),
        BotCommand(command="give",      description="🎁 Выдать ключ"),
        BotCommand(command="revoke",    description="🚫 Отозвать ключ"),
    ]

    try:
        await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_TG_ID))
    except Exception as e:
        print(f"[bot] Не удалось установить команды: {e}")

    print(f"[bot] Запуск... @{_bot_username}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
