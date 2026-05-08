"""
Please Donate Bot v2 — Flask API
=================================
Порт: 5001  (задаётся в config.py через API_PORT)

Запуск:
    python server_v2.py
Публичный доступ:
    cloudflared tunnel --url http://localhost:5001
"""

import time, os, requests, threading, signal, sys, secrets, hashlib
from flask import Flask, request, jsonify, Response, session, redirect, render_template_string
import db_v2
import bot_brain
from config import (API_PORT, API_SECRET, BOT_TOKEN, ADMIN_TG_ID,
                    API_BASE_URL as _CFG_API_BASE_URL,
                    DASH_URL as _CFG_DASH_URL,
                    ADMIN_DASH_PASSWORD as _ADMIN_PASS,
                    ADMIN_URL_PREFIX as _ADMIN_PFX)

app = Flask(__name__)

# Persistent session secret (survives restarts so admin sessions stay valid)
_SESSION_KEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".session_key")
try:
    if os.path.exists(_SESSION_KEY_PATH):
        with open(_SESSION_KEY_PATH, "rb") as f:
            app.secret_key = f.read()
    else:
        app.secret_key = secrets.token_bytes(32)
        with open(_SESSION_KEY_PATH, "wb") as f:
            f.write(app.secret_key)
        try:
            os.chmod(_SESSION_KEY_PATH, 0o600)
        except Exception:
            pass
except Exception:
    app.secret_key = secrets.token_bytes(32)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = True   # we run behind HTTPS via nginx


def _real_ip() -> str:
    """Get real client IP. Trusts proxy headers ONLY when request comes from localhost
    (i.e., from our nginx). Direct external requests use remote_addr."""
    if request.remote_addr in ("127.0.0.1", "::1", None):
        # Behind nginx — trust X-Real-IP (set by our nginx config)
        return (request.headers.get("X-Real-IP")
                or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or "127.0.0.1")
    # Direct connection — don't trust client-supplied headers
    return request.remote_addr or "?"


# ── Admin password hashing ───────────────────────────────────────────────
# Hash the plaintext password from config on startup so we never compare raw strings.
_ADMIN_PASS_HASH = hashlib.sha256((_ADMIN_PASS + API_SECRET).encode()).hexdigest()

def _check_admin_pass(candidate: str) -> bool:
    """Constant-time password comparison."""
    h = hashlib.sha256((candidate + API_SECRET).encode()).hexdigest()
    return secrets.compare_digest(h, _ADMIN_PASS_HASH)

# ── CSRF token helper ───────────────────────────────────────────────────
def _csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]

def _csrf_check() -> bool:
    token = request.form.get("_csrf", "")
    expected = session.get("csrf", "")
    return expected and secrets.compare_digest(token, expected)

import hmac as _hmac
import hashlib as _hashlib

# ── Rate limiter (brute-force protection) ───────────────────────────────────
# Tracks failed auth attempts per IP. After _RL_MAX failures in _RL_WINDOW
# seconds the IP is blocked for _RL_BLOCK seconds.
_rl_fails: dict[str, list] = {}   # ip → [timestamp, ...]
_rl_blocked: dict[str, float] = {}  # ip → blocked_until
_rl_lock = threading.Lock()
_RL_MAX    = 10   # failures before block
_RL_WINDOW = 60   # seconds window
_RL_BLOCK  = 300  # block duration seconds

def _rl_check(ip: str) -> bool:
    """Returns True if IP is allowed, False if blocked."""
    now = time.time()
    with _rl_lock:
        if ip in _rl_blocked:
            if now < _rl_blocked[ip]:
                return False
            else:
                del _rl_blocked[ip]
                _rl_fails.pop(ip, None)
        fails = [t for t in _rl_fails.get(ip, []) if now - t < _RL_WINDOW]
        _rl_fails[ip] = fails
        return True

def _rl_fail(ip: str):
    now = time.time()
    with _rl_lock:
        fails = [t for t in _rl_fails.get(ip, []) if now - t < _RL_WINDOW]
        fails.append(now)
        _rl_fails[ip] = fails
        if len(fails) >= _RL_MAX:
            _rl_blocked[ip] = now + _RL_BLOCK
            print(f"[RL] IP blocked: {ip} ({len(fails)} failures in {_RL_WINDOW}s)")

# ── Session tokens ──────────────────────────────────────────────────────────
# _stokens      — rotated by pd_update (original core.lua compatibility)
# _stokens_ga   — rotated by get_action (thin-client, called every 0.5 s)
# Kept separate so the two endpoints don't clobber each other's tokens.
_stokens: dict[str, str] = {}
_stokens_ga: dict[str, str] = {}
_stokens_lock = threading.Lock()
_uid_to_key: dict[str, str] = {}  # uid → key, set at getscript, used as pd_update fallback
# job_id tracking for simultaneous-session (key-sharing) detection
_job_ids: dict[str, dict] = {}  # key → {job_id, seen_at}
# Per-uid resp_secrets: last 2 secrets kept so rapid reconnects don't break verification
_resp_secrets: dict[tuple[str, str], list] = {}  # (key, uid) → [newest, prev]


def _sign_action(action: dict, secret: str, uid: str) -> str:
    """Signs: action + wait + nt + uid (no timestamp — Roblox os.time() is local, not UTC)."""
    wait_val = action.get("wait") or 0
    if isinstance(wait_val, float) and wait_val == int(wait_val):
        wait_str = str(int(wait_val))
    else:
        wait_str = str(wait_val)
    payload = "|".join([action.get("action", ""), wait_str, action.get("nt", ""), uid])
    h = 0
    for i, c in enumerate(payload):
        h = (h * 1000003 + ord(c) * 31 + ord(secret[i % len(secret)])) & 0xFFFFFFFF
    for c in secret:
        h = (h * 1000003 + ord(c)) & 0xFFFFFFFF
    return format(h, '08x')


def _encode_str_lua(s: str) -> str:
    """Encode string as a Lua char-code table with position-based XOR.
    Prevents trivial code.replace() sniffer bypass — string never appears in plaintext.
    Decode in Lua:  for i=1,#t do s=s..string.char(t[i]~(((i-1)*17+5)%97+3)) end
    """
    result = []
    for i, c in enumerate(s):
        result.append(str(ord(c) ^ ((i * 17 + 5) % 97 + 3)))
    return "{" + ",".join(result) + "}"


_PD_FUNC = (
    # Use bit32.bxor (Roblox/Luau) or fall back to pure-Lua XOR (Lua 5.1 exploits).
    # `~` as binary XOR is Lua 5.3+ only and causes a loadstring syntax error on
    # older exploit VMs, which is why the loader shows "Ошибка загрузки скрипта".
    "local _xor=bit32 and bit32.bxor "
    "or function(a,b) local r,p=0,1 while a>0 or b>0 do "
    "if a%2~=b%2 then r=r+p end "
    "a=math.floor(a/2) b=math.floor(b/2) p=p*2 end return r end\n"
    "local function _pd(t) local s='' for i=1,#t do "
    "s=s..string.char(_xor(t[i],((i-1)*17+5)%97+3)) end return s end\n"
)


def _inject_into_code(code: str, key: str, uid: str, api_url: str, token: str,
                      resp_secret: str, dash_url: str = "", hwid: str = "") -> str:
    """Inject user-specific values directly into the obfuscated code body."""
    replacements = [
        # reads  →  encoded literal
        ('_G.__LICENSE_KEY or ""',   f'_pd({_encode_str_lua(key)})'),
        ('_G.__BOUND_UID   or ""',   f'_pd({_encode_str_lua(uid)})'),
        ('_G.__API_URL     or ""',   f'_pd({_encode_str_lua(api_url)})'),
        ('_G.__SESSION_TOKEN or ""', f'_pd({_encode_str_lua(token)})'),
        ('_G.__RESP_SECRET or ""',   f'_pd({_encode_str_lua(resp_secret)})'),
        ('_G.__DASH_URL or ""',      f'_pd({_encode_str_lua(dash_url)})'),
        ('_G.__DEVICE_HWID or ""',   f'_pd({_encode_str_lua(hwid)})'),
        # clears  →  no-ops
        ('_G.__LICENSE_KEY=nil',   'local _lk=nil'),
        ('_G.__BOUND_UID=nil',     'local _bu=nil'),
        ('_G.__API_URL=nil',       'local _au=nil'),
        ('_G.__SESSION_TOKEN=nil', 'local _st=nil'),
        ('_G.__RESP_SECRET=nil',   'local _rs=nil'),
        ('_G.__DASH_URL=nil',      'local _du=nil'),
        ('_G.__DEVICE_HWID=nil',   'local _dh=nil'),
    ]
    for old, new in replacements:
        code = code.replace(old, new)
    return _PD_FUNC + code

# Кэш активных аккаунтов:
# { uid: { prev_donations, prev_raised, tg_id, session_id, session_start_stats, last_seen } }
_online_cache: dict[str, dict] = {}

# Rate-limit HWID mismatch notifications (max 1 per key per 5 min)
_hwid_alert_cache: dict[str, float] = {}

# Аккаунт считается оффлайн если не было пинга дольше этого времени
_OFFLINE_THRESH = 35  # секунд

# ── Локальный лог сессий ───────────────────────────────────────────────────

_LOG_DIR  = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.path.join(_LOG_DIR, "sessions_log.txt")
_log_lock = threading.Lock()


def _log_session_to_file(name: str, uid: str, started_at: float,
                          ended_at: float, duration: float, delta: dict):
    """Дописывает запись о закрытой сессии в sessions_log.txt."""
    def fmt_dur(s):
        s = int(s)
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        if h:   return f"{h}ч {m}м"
        if m:   return f"{m}м {sec}с"
        return  f"{sec}с"

    dt_start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at))
    dt_end   = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ended_at))
    dur_str  = fmt_dur(max(0, duration))
    app_s    = delta.get("approached",  0)
    agr_s    = delta.get("agreed",      0)
    ref_s    = delta.get("refused",     0)
    nr_s     = delta.get("no_response", 0)
    don_s    = delta.get("donations",   0)
    r_s      = delta.get("robux_gross", 0)
    conv     = f"{agr_s * 100 // app_s}%" if app_s else "—"

    line = (
        f"[{dt_start}] SESSION  {name} (uid:{uid})\n"
        f"  Старт: {dt_start}  →  Конец: {dt_end}  |  Длит: {dur_str}\n"
        f"  Подошёл: {app_s}  Согласился: {agr_s} ({conv})"
        f"  Отказал: {ref_s}  Нет ответа: {nr_s}\n"
        f"  Донаций: {don_s}  Заработано: R${r_s}"
        f"  (чист. R${round(r_s * 0.6)})\n"
        f"{'─' * 60}\n"
    )
    with _log_lock:
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            print(f"[LOG] Ошибка записи в файл: {e}")


# ── Session watcher ────────────────────────────────────────────────────────

_overtake_notif_cooldown: dict[str, float] = {}
_OVERTAKE_COOLDOWN = 1800  # 30 минут между уведомлениями об обгоне


def _send_overtake_notifications(info: dict):
    now = time.time()
    new_rank = info["new_rank"]
    actor_tg_id = info.get("actor_tg_id")

    if actor_tg_id and new_rank <= 10:
        key = f"up_{actor_tg_id}"
        if now - _overtake_notif_cooldown.get(key, 0) > _OVERTAKE_COOLDOWN:
            _overtake_notif_cooldown[key] = now
            if new_rank <= 5:
                _send_tg(actor_tg_id,
                    f"🏆 <b>Ты в топ-5!</b> Место <b>#{new_rank}</b>\n"
                    f"Удержи его до конца недели — и приз твой!")
            else:
                _send_tg(actor_tg_id,
                    f"⚡ Ты поднялся до <b>#{new_rank} места</b> в топе недели — продолжай!")

    for victim in info.get("overtaken", []):
        vtg = victim.get("tg_id")
        if not vtg:
            continue
        key = f"down_{vtg}"
        if now - _overtake_notif_cooldown.get(key, 0) > _OVERTAKE_COOLDOWN:
            _overtake_notif_cooldown[key] = now
            _send_tg(vtg,
                f"😬 <b>Тебя обогнали!</b> Фарми активнее, чтобы удержать место в топе 💪")


def _close_account_session(uid: str, info: dict, ended_at: float):
    """Закрыть сессию одного аккаунта: записать в БД + лог файл."""
    sid = info.get("session_id")
    if not sid:
        return
    acc = db_v2.get_account(uid)
    if not acc:
        return
    snap  = info.get("session_start_stats", {})
    delta = {
        k: max(0, (acc.get(k) or 0) - snap.get(k, 0))
        for k in ("approached", "agreed", "refused",
                  "no_response", "donations", "robux_gross",
                  "hops", "raised_current")
    }
    overtake_info = db_v2.close_session(sid, ended_at, delta)
    if overtake_info:
        _send_overtake_notifications(overtake_info)

    # Рассчитать duration для лога
    started_at = info.get("session_start_stats", {})  # не то — берём из БД
    sess_row   = db_v2.get_sessions(uid, limit=1)
    dur        = (ended_at - sess_row[0]["started_at"]) if sess_row else 0
    name       = acc.get("name") or uid
    _log_session_to_file(name, uid, sess_row[0]["started_at"] if sess_row else ended_at,
                         ended_at, dur, delta)


def _session_watcher():
    """Фоновый поток: закрывает сессии аккаунтов ушедших оффлайн."""
    while True:
        time.sleep(20)
        now      = time.time()
        to_close = [
            (uid, info) for uid, info in list(_online_cache.items())
            if now - info.get("last_seen", 0) > _OFFLINE_THRESH
        ]
        for uid, info in to_close:
            _close_account_session(uid, info, info["last_seen"])
            _online_cache.pop(uid, None)


threading.Thread(target=_session_watcher, daemon=True).start()


# ── Graceful shutdown ──────────────────────────────────────────────────────
# Перехватывает Ctrl+C и SIGTERM (systemd stop / kill).
# Закрывает все активные сессии перед выходом — ничего не теряется.

def _graceful_shutdown(signum, frame):
    print("\n[v2] Получен сигнал завершения — закрываю активные сессии...")
    now = time.time()
    closed = 0
    for uid, info in list(_online_cache.items()):
        try:
            _close_account_session(uid, info, info.get("last_seen", now))
            closed += 1
        except Exception as e:
            print(f"[v2] Ошибка при закрытии сессии {uid}: {e}")
    _online_cache.clear()

    # Подчистить всё что watcher мог пропустить
    stale = db_v2.close_stale_sessions(now)
    print(f"[v2] Закрыто активных: {closed}, зависших: {stale}. Выход.")
    sys.exit(0)


signal.signal(signal.SIGINT,  _graceful_shutdown)
signal.signal(signal.SIGTERM, _graceful_shutdown)


def _send_tg(chat_id: int, text: str):
    """Отправить сообщение в Telegram напрямую через Bot API."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass


def _fmt_time(ts: float | None) -> str:
    if not ts:
        return "—"
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}с назад"
    if diff < 3600:
        return f"{int(diff/60)}мин назад"
    return f"{int(diff/3600)}ч назад"


# ── Активация ключа ────────────────────────────────────────────────────────

@app.route("/v2/activate", methods=["POST"])
def activate():
    data = request.get_json(silent=True) or {}
    key            = data.get("key", "").strip()
    roblox_user_id = str(data.get("roblox_user_id", "")).strip()
    roblox_name    = data.get("roblox_name", "").strip()
    device_id      = data.get("device_id", "").strip()

    if not key or not roblox_user_id:
        return jsonify({"ok": False, "error": "Missing key or roblox_user_id"}), 400

    lic = db_v2.get_license(key)
    if not lic:
        return jsonify({"ok": False, "error": "Key not found"}), 403
    if not db_v2.is_key_valid(lic):
        if lic.get("expires_at") and time.time() > lic["expires_at"]:
            return jsonify({"ok": False, "error": "trial_expired"}), 403
        return jsonify({"ok": False, "error": "Key revoked"}), 403


    first_time = False
    if lic["roblox_user_id"] is None:
        db_v2.bind_license(key, roblox_user_id, roblox_name)
        first_time = True
        _send_tg(lic["tg_id"],
                 f"🟢 <b>Скрипт активирован!</b>\n"
                 f"👤 Аккаунт: <b>{roblox_name}</b>\n"
                 f"🕐 Время: {time.strftime('%H:%M %d.%m.%Y')}")
    # else: additional account on same key — allowed (multi-account per device)

    db_v2.touch_license(key)
    return jsonify({"ok": True, "first_time": first_time})


# ── Получение скрипта (loader делает этот запрос) ─────────────────────────

@app.route("/v2/ping")
def ping():
    return jsonify({"ok": True})


@app.route("/loader.lua")
def serve_loader():
    p = os.path.join(os.path.dirname(__file__), "loader_v2_obf.lua")
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(__file__), "loader_v2.lua")
    if not os.path.exists(p):
        return Response("Loader not found", status=500)
    with open(p, "rb") as f:
        return Response(f.read(), mimetype="text/plain; charset=utf-8")


# ─── Installer (Auto-Deploy .exe) endpoints ────────────────────────────────
# Used by the desktop installer that customers run after buying a license.
# It checks the key, then pulls a manifest with loader-line + gamepass spec
# so we can roll changes server-side without re-shipping the .exe.

_INSTALLER_GAMEPASS_AMOUNTS = [
    5, 10, 15, 25, 50, 100, 150, 250, 500,
    1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000,
]


def _installer_license_payload(lic: dict) -> dict:
    now = time.time()
    expires_at = lic.get("expires_at")
    max_acc = int(lic.get("max_accounts") or 5)
    cur_acc = db_v2.count_allowed_accounts(lic["key"])
    return {
        "ok": True,
        "tg_id": lic.get("tg_id"),
        "type": "trial" if expires_at else "lifetime",
        "expires_at": expires_at,
        "expires_in_days": int((expires_at - now) / 86400) if expires_at else None,
        "max_accounts": max_acc,
        "accounts_used": cur_acc,
        "roblox_user_id": lic.get("roblox_user_id"),
        "roblox_name": lic.get("roblox_name") or "",
    }


@app.route("/v2/installer/check_license", methods=["POST"])
def installer_check_license():
    ip = _real_ip()
    if not _rl_check(ip):
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if not key:
        _rl_fail(ip)
        return jsonify({"ok": False, "error": "missing_key"}), 400

    lic = db_v2.get_license(key)
    if not lic:
        _rl_fail(ip)
        return jsonify({"ok": False, "error": "key_not_found"}), 403
    if not db_v2.is_key_valid(lic):
        _rl_fail(ip)
        if lic.get("expires_at") and time.time() > lic["expires_at"]:
            return jsonify({"ok": False, "error": "expired"}), 403
        return jsonify({"ok": False, "error": "revoked"}), 403

    return jsonify(_installer_license_payload(lic))


@app.route("/v2/installer/manifest", methods=["POST"])
def installer_manifest():
    """Returns everything the installer needs: loader-line, gamepass spec, etc.
    Requires a valid key so that random scrapers can't enumerate the config."""
    ip = _real_ip()
    if not _rl_check(ip):
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if not key:
        _rl_fail(ip)
        return jsonify({"ok": False, "error": "missing_key"}), 400

    lic = db_v2.get_license(key)
    if not lic or not db_v2.is_key_valid(lic):
        _rl_fail(ip)
        return jsonify({"ok": False, "error": "invalid_key"}), 403

    api_url = (_CFG_API_BASE_URL or request.host_url).rstrip("/")
    loader_line = f'loadstring(game:HttpGet("{api_url}/loader.lua"))()'

    return jsonify({
        "ok": True,
        "loader_line": loader_line,
        "loader_url": f"{api_url}/loader.lua",
        "gamepass_amounts": _INSTALLER_GAMEPASS_AMOUNTS,
        "gamepass_name_template": "Donate {amount} R$",
        "place_name": "Beggr Hub",
        "place_description": "auto-created by installer",
        "place_id_pls_donate": 8737602449,
        "bloxstrap_repo": "pizzaboxer/bloxstrap",
        "support_tg": "https://t.me/PlsDonateeBot",
        "license": _installer_license_payload(lic),
    })


@app.route("/v2/getscript")
def get_script():
    ip  = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)

    key  = request.args.get("key", "").strip()
    uid  = request.args.get("uid", "").strip()

    # Mask key in logs: show only first 4 chars
    key_hint = (key[:4] + "****") if len(key) >= 4 else "????"
    print(f"[GETSCRIPT] key={repr(key_hint)} uid={repr(uid)}")

    if not key or not uid:
        print("[GETSCRIPT] Missing key or uid")
        _rl_fail(ip)
        return Response("Missing key or uid", status=400)

    lic = db_v2.get_license(key)
    if not lic:
        _rl_fail(ip)
        return Response("Key not found", status=403)
    if not db_v2.is_key_valid(lic):
        _rl_fail(ip)
        if lic.get("expires_at") and time.time() > lic["expires_at"]:
            return Response("trial_expired", status=403)
        return Response("Key revoked", status=403)

    now = time.time()

    # ── Account whitelist check ────────────────────────────────────────────
    acc_status = db_v2.is_account_allowed(key, uid)
    if acc_status == "banned":
        return Response("Этот Roblox-аккаунт заблокирован для данного ключа", status=403)

    if acc_status is None:
        # New account — try to auto-add if within limit
        roblox_name = ""
        # Try to get name from Roblox API (best effort)
        try:
            import urllib.request, json as _json
            with urllib.request.urlopen(f"https://users.roblox.com/v1/users/{uid}", timeout=5) as r:
                roblox_name = _json.loads(r.read()).get("name", "")
        except Exception:
            pass
        added = db_v2.add_allowed_account(key, uid, roblox_name)
        if not added:
            _send_tg(lic["tg_id"],
                     f"⚠️ <b>Лимит аккаунтов!</b>\n"
                     f"Новый аккаунт <code>{uid}</code> пытается использовать ключ, "
                     f"но лимит ({lic.get('max_accounts') or 5}) исчерпан.\n"
                     f"Управляй аккаунтами в админке.")
            return Response("Лимит аккаунтов исчерпан. Обратись к админу", status=403)
        _send_tg(lic["tg_id"],
                 f"🆕 <b>Новый аккаунт подключён</b>\n"
                 f"👤 {roblox_name or uid}\n"
                 f"🆔 <code>{uid}</code>\n"
                 f"📊 Аккаунтов: {db_v2.count_allowed_accounts(key)}/{lic.get('max_accounts') or 5}")

    if lic["roblox_user_id"] is None:
        db_v2.bind_license(key, uid, "")

    db_v2.touch_license(key)

    script_path = os.path.join(os.path.dirname(__file__), "obfuscated_script.lua")
    if not os.path.exists(script_path):
        return Response("Script file not found on server", status=500)

    with open(script_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Use configured base URL if set; fall back to request host only as last resort.
    # Hardcoded URL prevents host-header injection (attacker spoofs Host: to redirect bots).
    api_url = _CFG_API_BASE_URL.rstrip("/") if _CFG_API_BASE_URL else request.host_url.rstrip("/")

    token = secrets.token_hex(16)
    resp_secret = secrets.token_hex(16)
    with _stokens_lock:
        _stokens[(key, uid)] = token
        _stokens_ga.pop((key, uid), None)
        _uid_to_key[uid] = key
    with _stokens_lock:
        prev = _resp_secrets.get((key, uid), [None])[0]
        _resp_secrets[(key, uid)] = [resp_secret, prev]

    final_code = _inject_into_code(code, key, uid, api_url, token, resp_secret,
                                    _CFG_DASH_URL or "")
    return Response(final_code, status=200, mimetype="text/plain")


# ── Обновление статистики (каждые 5 сек из Lua) ────────────────────────────

@app.route("/v2/pd_update", methods=["POST"])
def pd_update():
    data = request.get_json(silent=True) or {}
    uid  = str(data.get("id", "")).strip()
    tok  = data.get("session_token", "").strip()

    if not uid or not tok:
        return jsonify({"ok": False, "error": "Missing id or session_token"}), 400

    # Resolve key from session token — client no longer sends key in pd_update,
    # eliminating one plaintext key exposure per 5-second interval.
    with _stokens_lock:
        key = next((k for (k, u), v in _stokens.items() if v == tok and u == uid), None)
        if not key:
            key = next((k for (k, u), v in _stokens_ga.items() if v == tok and u == uid), None)

    if not key:
        # Fast in-memory fallback — set at getscript, survives token rotation.
        # Handles brand-new accounts whose first pd_update arrives with a stale
        # token (e.g. after multiple getscript calls on the same uid).
        with _stokens_lock:
            key = _uid_to_key.get(uid)
        if key:
            with _stokens_lock:
                _stokens[(key, uid)] = tok

    if not key:
        # After server restart, in-memory tokens are lost.
        # Fall back: resolve key by uid from DB (account already exists).
        acc = db_v2.get_account(uid)
        if acc:
            key = acc.get("license_key")
            if key:
                with _stokens_lock:
                    _stokens[(key, uid)] = tok

    if not key:
        return jsonify({"ok": False, "error": "Cannot resolve key"}), 403

    lic = db_v2.get_license(key)
    if not lic:
        return Response("Key not found", status=403)
    if not db_v2.is_key_valid(lic):
        return Response("trial_expired" if (lic.get("expires_at") and time.time() > lic["expires_at"]) else "Key revoked", status=403)
    # pd_update is authenticated by key + roblox_user_id — no session token check needed.
    # (get_action rotates SESSION_TOK on every call, so pd_update would always mismatch.)

    now = time.time()
    db_v2.touch_license(key)

    # Обновляем имя если пустое
    if lic["roblox_name"] == "" and data.get("name"):
        db_v2.bind_license(key, uid, data["name"])

    new_donations = data.get("donations",   0)
    new_raised    = data.get("robux_gross", 0)

    # ── Session tracking ─────────────────────────────────────────────────
    _prev_cached   = _online_cache.get(uid)
    # Capture prev values NOW before any writes to _online_cache (prevents race condition
    # where another thread overwrites cache between our is_new_session check and notification check)
    _snap_donations = _prev_cached.get("prev_donations", 0) if _prev_cached else None
    _snap_raised    = _prev_cached.get("prev_raised",    0) if _prev_cached else None
    _stats_reset   = _prev_cached is not None and (
        new_donations < _snap_donations or
        new_raised    < _snap_raised
    )
    is_new_session = _prev_cached is None or _stats_reset
    if is_new_session:
        # Спасти робуксы от предыдущей незакрытой сессии перед перезаписью
        db_v2.salvage_to_alltime(uid)

    # Сохраняем статистику (перезаписывает текущие поля значениями от Lua)
    db_v2.upsert_account(uid, key, data)

    if is_new_session:
        sid = db_v2.open_session(uid, now)
        _online_cache[uid] = {
            "prev_donations":      new_donations,
            "prev_raised":         new_raised,
            "tg_id":               lic["tg_id"],
            "key":                 key,
            "session_id":          sid,
            "session_start_stats": {
                "approached":    data.get("approached",    0),
                "agreed":        data.get("agreed",        0),
                "refused":       data.get("refused",       0),
                "no_response":   data.get("no_response",   0),
                "donations":     new_donations,
                "robux_gross":   new_raised,
                "hops":          data.get("hops",          0),
                "raised_current": data.get("raised_current", 0),
            },
            "last_seen": now,
        }
    else:
        _online_cache[uid]["last_seen"] = now

    # ── Donation notification ─────────────────────────────────────────────
    # Use snapshotted values (not _online_cache) to avoid race with other threads
    if not is_new_session and _snap_donations is not None and new_donations > _snap_donations:
        gained      = new_raised - (_snap_raised or 0)
        roblox_name = data.get("name", uid)
        _send_tg(lic["tg_id"],
                 f"💸 <b>Новая донация!</b>\n"
                 f"👤 {roblox_name}\n"
                 f"💰 +R$ {gained} (всего: R$ {new_raised})\n"
                 f"🎁 Донаций всего: {new_donations}")

    _online_cache[uid]["prev_donations"] = new_donations
    _online_cache[uid]["prev_raised"]    = new_raised

    return jsonify({"ok": True})


# ── Статистика пользователя ────────────────────────────────────────────────

@app.route("/v2/my_stats")
def my_stats():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)

    key = request.args.get("key", "").strip()
    uid = request.args.get("uid", "").strip()
    if not key or not uid:
        _rl_fail(ip)
        return jsonify({"error": "Missing key or uid"}), 400

    lic = db_v2.get_license(key)
    if not lic:
        _rl_fail(ip)
        return jsonify({"error": "Key not found"}), 404
    if not db_v2.is_key_valid(lic):
        _rl_fail(ip)
        return jsonify({"error": "Key invalid"}), 403
    # Must have a bound roblox_user_id AND it must match
    if not lic["roblox_user_id"] or lic["roblox_user_id"] != uid:
        _rl_fail(ip)
        return jsonify({"error": "Unauthorized"}), 403

    acc = db_v2.get_account_by_license(key)
    return jsonify({
        "license": {
            "status":         lic["status"],
            "roblox_name":    lic["roblox_name"],
            "roblox_user_id": lic["roblox_user_id"],
            "activated_at":   lic["activated_at"],
        },
        "account": dict(acc) if acc else None,
    })


# ── Внутренний эндпоинт для TG-уведомлений от бота ────────────────────────

@app.route("/v2/notify", methods=["POST"])
def notify():
    if not secrets.compare_digest(request.headers.get("X-Secret", ""), API_SECRET):
        return Response("Forbidden", status=403)
    data    = request.get_json(silent=True) or {}
    chat_id = data.get("chat_id")
    text    = data.get("text", "")
    if chat_id and text:
        _send_tg(int(chat_id), text)
    return jsonify({"ok": True})


# ── Общая статистика (для /stats в боте) ──────────────────────────────────

@app.route("/v2/admin_stats")
def admin_stats():
    if not secrets.compare_digest(request.headers.get("X-Secret", ""), API_SECRET):
        return Response("Forbidden", status=403)
    return jsonify({
        "total_users":   db_v2.count_users(),
        "total_keys":    db_v2.count_licenses(),
        "active_now":    db_v2.count_active_accounts(),
        "total_robux":   db_v2.total_robux(),
        "pending_apps":  db_v2.count_pending_applications(),
    })


# ── Bot brain: server-side decision engine ─────────────────────────────────
# The Lua thin-client polls this endpoint every ~0.5 s, sends game state,
# and receives exactly one action to execute. Zero bot logic lives in Lua.

@app.route("/v2/get_action", methods=["POST"])
def get_action():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)

    data = request.get_json(silent=True) or {}
    key  = data.get("key", "").strip()
    uid  = str(data.get("uid", "")).strip()

    if not key or not uid:
        return Response("Missing key or uid", status=400)

    lic = db_v2.get_license(key)
    if not lic:
        _rl_fail(ip)
        return Response("Key not found", status=403)
    if not db_v2.is_key_valid(lic):
        _rl_fail(ip)
        return Response("trial_expired" if (lic.get("expires_at") and time.time() > lic["expires_at"]) else "Key revoked", status=403)
    # Generate new token for pd_update key-resolution (_stokens_ga fallback).
    # No validation here — multiple instances of the same uid (from teleports/reinjection)
    # would permanently 403 each other if we rotated and validated here.
    new_token = secrets.token_hex(16)
    with _stokens_lock:
        _stokens_ga[(key, uid)] = new_token

    # ── Simultaneous session detection ──────────────────────────────────
    # Checks: 1) Different JobId in short window = key sharing
    #          2) Different IP with same key in short window = key sharing
    #          3) Even same JobId but different IP = spoofed JobId
    job_id = data.get("job_id", "")
    now_t = time.time()
    with _stokens_lock:
        prev_job = _job_ids.get((key, uid))

    if prev_job:
        elapsed = now_t - prev_job["seen_at"]
        key_log = key[:4] + "****"

        # Check 1: Different JobId within 15s = impossible for legit user
        if job_id and prev_job.get("job_id") and prev_job["job_id"] != job_id and elapsed < 15:
            print(f"[ALERT] Key sharing: different JobId! key={key_log} gap={elapsed:.1f}s")
            _send_tg(ADMIN_TG_ID,
                     f"🚨 <b>Шаринг ключа!</b>\n"
                     f"🔑 <code>{key_log}</code>\n"
                     f"Разные JobId за {elapsed:.0f}с")
            db_v2.revoke_license(key)
            return Response("Key revoked: simultaneous session detected", status=403)

        # Check 2: Different IP within 30s = likely sharing (even with same JobId)
        prev_ip = prev_job.get("ip", "")
        if prev_ip and ip and prev_ip != ip and elapsed < 30:
            # Same subnet = ok (VPN/router change), different subnet = suspicious
            prev_subnet = ".".join(prev_ip.split(".")[:3]) if "." in prev_ip else prev_ip
            cur_subnet = ".".join(ip.split(".")[:3]) if "." in ip else ip
            if prev_subnet != cur_subnet:
                print(f"[ALERT] Key sharing: different IP subnet! key={key_log} "
                      f"ip1={prev_ip} ip2={ip} gap={elapsed:.1f}s")
                _send_tg(ADMIN_TG_ID,
                         f"🚨 <b>Подозрительная активность!</b>\n"
                         f"🔑 <code>{key_log}</code>\n"
                         f"Разные подсети за {elapsed:.0f}с: {prev_subnet}.x → {cur_subnet}.x")
                # Don't revoke immediately on IP change (VPN), but flag
                db_v2.check_ip(key, ip)

    with _stokens_lock:
        _job_ids[(key, uid)] = {"job_id": job_id, "seen_at": now_t, "ip": ip}

    # Delegate all decision-making to the Python brain
    action = bot_brain.brain.get_action(uid, data)
    action["nt"] = new_token

    # Log interesting interactions (send_chat, events) to dashboard
    act_type = action.get("action", "")
    act_event = action.get("event", "")
    if act_type == "send_chat" or act_event:
        try:
            target_name = ""
            st = bot_brain.brain._states.get(uid)
            if st:
                target_name = st.target_name or ""
            acc_name = data.get("stats", {}).get("name", "") or ""
            if not acc_name:
                nearby = data.get("nearby", [])
                acc_name = uid
            db_v2.log_interaction(
                license_key=key, uid=uid, account_name=acc_name,
                target_name=target_name, action=act_type,
                message=action.get("message", ""), event=act_event,
            )
        except Exception:
            pass

    with _stokens_lock:
        rsec_list = _resp_secrets.get((key, uid), [])
    rsec  = rsec_list[0] if len(rsec_list) > 0 else ""
    rsec2 = rsec_list[1] if len(rsec_list) > 1 else ""
    if rsec:
        base = {k: v for k, v in action.items() if k not in ("sig", "sig2")}
        action["sig"] = _sign_action(base, rsec, uid)
        if rsec2:
            action["sig2"] = _sign_action(base, rsec2, uid)
    return jsonify(action)


_ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin — PD Bot v23</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.06) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
.box{background:var(--surface);border:1px solid var(--border2);border-radius:16px;padding:36px 32px;width:340px;box-shadow:0 0 60px rgba(0,229,255,.06)}
.logo{text-align:center;margin-bottom:28px}
.logo-icon{font-size:36px;display:block;margin-bottom:8px}
.logo h1{font-size:18px;font-weight:800;color:var(--text)}
.logo p{font-size:12px;color:var(--muted);margin-top:3px}
label{display:block;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
input{width:100%;background:#060a14;border:1px solid var(--border2);border-radius:9px;padding:11px 14px;color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:.15s}
input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,229,255,.1)}
.field{margin-bottom:20px}
button{width:100%;background:var(--accent);border:none;border-radius:9px;color:var(--bg);padding:12px;font-size:14px;font-weight:700;font-family:inherit;cursor:pointer;transition:.15s;letter-spacing:.02em}
button:hover{background:#19eeff;transform:translateY(-1px)}
button:active{transform:translateY(0)}
.err{background:rgba(255,59,107,.1);border:1px solid rgba(255,59,107,.2);border-radius:8px;color:var(--red);font-size:13px;padding:10px 12px;margin-bottom:16px;text-align:center}
</style></head><body>
<div class="box">
  <div class="logo"><span class="logo-icon">🔐</span><h1>PD Bot v23</h1><p>Admin Panel</p></div>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <form method="post">
    <div class="field"><label>Пароль</label><input type="password" name="password" placeholder="••••••••" autofocus></div>
    <button type="submit">Войти</button>
  </form>
</div></body></html>"""

_ADMIN_DASH_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin — PD Bot v23</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(0,229,255,.25);border-radius:3px}
body{font-family:'Space Grotesk',-apple-system,sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.06) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;font-size:14px;line-height:1.5}
.hdr{position:sticky;top:0;z-index:100;backdrop-filter:blur(12px);background:var(--bg);border-bottom:1px solid var(--border2);box-shadow:0 1px 30px rgba(0,229,255,.04);display:flex;align-items:center;padding:0 24px;height:52px;gap:16px}
.brand{font-weight:800;font-size:15px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;white-space:nowrap;display:flex;align-items:center;gap:8px}
.brand-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:16px}
.live{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(0,255,135,.4)}70%{box-shadow:0 0 0 6px rgba(0,255,135,0)}100%{box-shadow:0 0 0 0 rgba(0,255,135,0)}}
.hdr-time{font-size:12px;color:var(--muted);font-family:'JetBrains Mono',monospace}
.btn-logout{font-size:12px;color:var(--muted);background:none;border:1px solid var(--border2);border-radius:20px;padding:5px 14px;cursor:pointer;font-family:inherit;text-decoration:none;transition:.2s}
.btn-logout:hover{color:var(--accent);border-color:var(--accent)}
.export-btn{display:inline-block;padding:6px 14px;background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);border-radius:8px;color:var(--accent);font-size:12px;font-weight:600;text-decoration:none;transition:.15s;font-family:inherit}
.export-btn:hover{background:rgba(0,229,255,.14);text-decoration:none}
.ref-card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:10px}
.ref-user{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.ref-badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:700}
.ref-list{display:flex;flex-wrap:wrap;gap:6px}
.wrap{padding:24px;max-width:1700px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px 20px;transition:all .2s ease;animation:fadeInUp .4s ease both}
.card:hover{border-color:rgba(0,229,255,.22);box-shadow:0 0 28px rgba(0,229,255,.07);transform:translateY(-2px)}
.card:nth-child(1){animation-delay:.1s}.card:nth-child(2){animation-delay:.2s}.card:nth-child(3){animation-delay:.3s}.card:nth-child(4){animation-delay:.4s}.card:nth-child(5){animation-delay:.45s}.card:nth-child(6){animation-delay:.5s}
.card-label{font-size:10.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}
.card-val{font-size:30px;font-weight:800;line-height:1}
.card-val.accent{color:var(--accent2)}.card-val.green{color:var(--green)}.card-val.yellow{color:var(--yellow)}.card-val.blue{color:var(--blue)}.card-val.red{color:var(--red)}
.section-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.section-title{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.btn-refresh{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:20px;border:1px solid var(--border2);background:none;color:var(--muted);font-size:12px;font-family:inherit;cursor:pointer;text-decoration:none;transition:.2s}
.btn-refresh:hover{color:var(--accent);border-color:var(--accent)}
.tbl-wrap{overflow-x:auto;border-radius:14px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;background:var(--surface);font-size:12.5px}
thead tr{background:linear-gradient(180deg,var(--surface2),var(--surface))}
th{padding:10px 12px;text-align:left;font-size:10px;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid var(--border);white-space:nowrap;font-family:'Space Grotesk',sans-serif}
td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:middle;color:#7a9abf}
tr:last-child td{border-bottom:none}
tr.clickable:hover td{background:rgba(0,229,255,.03);cursor:pointer}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:20px;font-size:10.5px;font-weight:700;letter-spacing:.03em}
.b-on{background:rgba(0,255,135,.1);color:var(--green)}.b-off{background:rgba(74,96,128,.1);color:#4a6080}.b-rev{background:rgba(255,59,107,.1);color:var(--red)}
.mono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted)}
.name{font-weight:600;color:var(--text)}
.tg-link{color:#38f5c0;text-decoration:none;font-size:12px;font-weight:500}.tg-link:hover{text-decoration:underline}
.r-yellow{color:var(--yellow);font-weight:700}.r-faint{color:#a07c04;font-weight:500}
.btn-rev{background:none;border:1px solid rgba(255,59,107,.25);color:rgba(255,59,107,.7);padding:3px 10px;border-radius:6px;cursor:pointer;font-size:11px;font-family:inherit;transition:.15s}
.btn-rev:hover{background:rgba(255,59,107,.1);border-color:var(--red);color:var(--red)}
form.inl{display:inline}
.footer{margin-top:14px;font-size:11px;color:#1a2840;text-align:right}
.tabs{display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:7px 18px;font-size:12px;font-weight:600;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:20px;cursor:pointer;font-family:inherit;transition:.2s}
.tab:hover{color:var(--text);border-color:var(--border2)}.tab.active{color:var(--bg);background:var(--accent);border-color:var(--accent);font-weight:700}
.tab-panel{display:none}.tab-panel.active{display:block}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal{background:var(--bg);border:1px solid var(--border2);border-radius:20px;width:100%;max-width:900px;max-height:85vh;overflow-y:auto;padding:28px;box-shadow:0 0 80px rgba(0,229,255,.08),0 40px 80px rgba(0,0,0,.6)}
.modal-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.modal-hdr h2{font-size:18px;font-weight:800}
.modal-close{width:32px;height:32px;border-radius:8px;border:1px solid var(--border2);background:none;color:var(--muted);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.modal-close:hover{background:rgba(0,229,255,.06);color:var(--text)}
.modal-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:20px}
.ms{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}
.ms-val{font-size:22px;font-weight:800}.ms-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.ilog{max-height:400px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px}
.ilog-row{display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:11.5px}
.ilog-row:last-child{border-bottom:none}
.ilog-time{font-family:'JetBrains Mono',monospace;color:var(--muted);font-size:10px;min-width:70px;flex-shrink:0}
.ilog-icon{min-width:16px;text-align:center}
.ilog-body{flex:1;color:var(--text)}
.ilog-target{color:var(--accent2);font-weight:600}
.ilog-reply{color:var(--cyan);font-style:italic}
.ilog-event{color:var(--muted);font-size:10px;margin-left:4px}
.ilog-ago{color:var(--muted);font-size:10px;flex-shrink:0;margin-left:auto}
.filter-bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.filter-bar select,.filter-bar input{background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 10px;font-size:11px;font-family:inherit}
.filter-bar select:focus,.filter-bar input:focus{border-color:var(--accent);outline:none}
.sess-list{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px;max-height:250px;overflow-y:auto}
.sess-item{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);font-size:11px;color:var(--muted)}
.sess-item:last-child{border-bottom:none}
.sess-dur{font-family:'JetBrains Mono',monospace;color:var(--text);font-weight:600;min-width:60px}
.sess-stat{font-family:'JetBrains Mono',monospace}
.sess-r{color:var(--yellow);font-weight:600}
@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<div class="hdr">
  <div class="brand"><div class="brand-dot"></div>PD Bot v23 — Admin</div>
  <div class="hdr-right">
    <div class="live"><div class="live-dot"></div>Live</div>
    <span class="hdr-time" id="admin-time">{{ now_str }}</span>
    <a class="btn-logout" href="{{ pfx }}/logout">Выйти</a>
  </div>
</div>
<div class="wrap">
  <div class="cards">
    <div class="card"><div class="card-label">Активных ключей</div><div class="card-val blue" id="stat-total_keys">{{ s.total_keys }}</div></div>
    <div class="card"><div class="card-label">Онлайн сейчас</div><div class="card-val green" id="stat-active_now">{{ s.active_now }}</div></div>
    <div class="card"><div class="card-label">R$ Всего</div><div class="card-val yellow" id="stat-total_robux">{{ s.total_robux }}</div></div>
    <div class="card"><div class="card-label">R$ Завершённых</div><div class="card-val accent" id="stat-total_robux_alltime">{{ s.total_robux_alltime }}</div></div>
    <div class="card"><div class="card-label">Пользователей</div><div class="card-val" id="stat-total_users">{{ s.total_users }}</div></div>
    <div class="card"><div class="card-label">Pending заявок</div><div class="card-val {% if s.pending_apps > 0 %}red{% else %}{% endif %}" id="stat-pending_apps">{{ s.pending_apps }}</div></div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('users')">Пользователи</button>
    <button class="tab" onclick="switchTab('feed')">Лента диалогов</button>
    <button class="tab" onclick="switchTab('analytics')">Аналитика</button>
    <button class="tab" onclick="switchTab('referrals')">Рефералы</button>
    <button class="tab" id="tab-btn-payouts" onclick="switchTab('payouts')">💳 Выплаты</button>
    <button class="tab" onclick="switchTab('exports')">Экспорт</button>
  </div>

  <!-- TAB: Users table -->
  <div id="tab-users" class="tab-panel active">
    <div class="section-hdr">
      <span class="section-title">Аккаунты · {{ rows|length }}</span>
      <a class="btn-refresh" href="{{ pfx }}">↻ Обновить</a>
    </div>
    <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>#</th><th>Юзер</th><th>Roblox</th><th>Ключ</th><th>Статус</th>
        <th>R$ Всего</th><th>Донаты</th><th>Подход / Согл / Отказ</th>
        <th>Последний</th><th></th>
      </tr></thead>
      <tbody>
      {% for r in rows %}
      <tr class="clickable" onclick="openModal('{{ r.key }}')">
        <td class="mono" style="color:#333">{{ loop.index }}</td>
        <td>
          {% if r.dc_id %}
            <span style="background:#5865F2;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;font-weight:700">DC</span>
            {% if r.dc_username %}<a class="tg-link" href="https://discord.com/users/{{ r.dc_id }}" target="_blank" onclick="event.stopPropagation()">@{{ r.dc_username }}</a><br>{% endif %}
            <span class="mono">{{ r.dc_id }}</span>
            {% if r.dc_name %}<br><span style="font-size:11px;color:#444">{{ r.dc_name }}</span>{% endif %}
          {% else %}
            <span style="background:#229ED9;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;font-weight:700">TG</span>
            {% if r.tg_username %}<a class="tg-link" href="https://t.me/{{ r.tg_username }}" target="_blank" onclick="event.stopPropagation()">@{{ r.tg_username }}</a><br>{% endif %}
            <span class="mono">{{ r.tg_id or '—' }}</span>
            {% if r.tg_name %}<br><span style="font-size:11px;color:#444">{{ r.tg_name }}</span>{% endif %}
          {% endif %}
        </td>
        <td>
          {% if r.acc_count > 1 %}
            <span class="name">{{ r.acc_count }} аккаунта</span>
            {% if r.acc_names %}<br><span style="font-size:10px;color:#666">{{ r.acc_names[:3]|join(', ') }}{% if r.acc_names|length > 3 %} +{{ r.acc_names|length - 3 }}{% endif %}</span>{% endif %}
          {% else %}
            <span class="name">{{ r.roblox_name or r.acc_name or '—' }}</span>
            {% if r.roblox_user_id %}<br><span class="mono">{{ r.roblox_user_id }}</span>{% endif %}
          {% endif %}
        </td>
        <td><span class="mono" style="color:#55556a">{{ r.key[:4] }}••••</span></td>
        <td>
          {% if r.lic_status == 'revoked' %}<span class="badge b-rev">REVOKED</span>
          {% elif r.online_count > 0 %}
            <span class="badge b-on">● {% if r.acc_count > 1 %}{{ r.online_count }}/{{ r.acc_count }} {% endif %}ONLINE</span>
          {% else %}
            <span class="badge b-off">{% if r.acc_count > 1 %}{{ r.acc_count }}× {% endif %}OFFLINE</span>
          {% endif %}
        </td>
        <td><span class="r-yellow">{{ (r.robux_gross or 0) + (r.robux_alltime or 0) }}</span></td>
        <td class="mono">{{ (r.donations or 0) + (r.donations_alltime or 0) }}</td>
        <td class="mono">{{ (r.approached or 0) + (r.approached_alltime or 0) }} / {{ (r.agreed or 0) + (r.agreed_alltime or 0) }} / {{ (r.refused or 0) + (r.refused_alltime or 0) }}</td>
        <td class="mono" style="color:#444">{{ r.last_seen_str }}</td>
        <td style="white-space:nowrap" onclick="event.stopPropagation()">
          {% if r.lic_status == 'active' %}
          <form class="inl" method="post" action="{{ pfx }}/revoke/{{ r.key }}" onsubmit="return confirm('Отозвать ключ {{ r.key[:4] }}?')">
            <input type="hidden" name="_csrf" value="{{ csrf }}"><button class="btn-rev" type="submit">Revoke</button>
          </form>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
      {% if not rows %}<tr><td colspan="12" style="text-align:center;color:#333;padding:48px;font-size:13px">Нет данных</td></tr>{% endif %}
      </tbody>
    </table>
    </div>
  </div>

  <!-- TAB: Global feed -->
  <div id="tab-feed" class="tab-panel">
    <div class="section-hdr">
      <span class="section-title">Все диалоги (последние 200)</span>
      <div class="filter-bar">
        <select id="feed-event" onchange="loadFeed()">
          <option value="">Все события</option>
          <option value="agreed">Согласился</option>
          <option value="refused">Отказал</option>
          <option value="no_response">Молчал</option>
          <option value="donated">Задонатил</option>
        </select>
      </div>
    </div>
    <div id="feed-log" class="ilog" style="max-height:600px">
      <div style="text-align:center;color:var(--muted);padding:20px">Загрузка...</div>
    </div>
  </div>

  <!-- TAB: Analytics -->
  <div id="tab-analytics" class="tab-panel">
    <div class="section-hdr">
      <span class="section-title">Аналитика взаимодействий</span>
      <div class="filter-bar" style="display:flex;gap:8px">
        <select id="analytics-key" onchange="loadAnalytics()" style="padding:5px 10px;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:11px;font-family:inherit">
          <option value="">Все аккаунты</option>
          {% for r in rows %}
          <option value="{{ r.key }}">{{ r.roblox_name or r.acc_name or r.key[:8] }}</option>
          {% endfor %}
        </select>
        <select id="analytics-period" onchange="loadAnalytics()" style="padding:5px 10px;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:11px;font-family:inherit">
          <option value="6">6 часов</option>
          <option value="12">12 часов</option>
          <option value="24" selected>24 часа</option>
          <option value="48">48 часов</option>
          <option value="168">Неделя</option>
        </select>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">Взаимодействия по часам</div>
        <div style="position:relative;height:240px"><canvas id="chart-interactions"></canvas></div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">Результаты (согл / отказ / нет отв)</div>
        <div style="position:relative;height:240px"><canvas id="chart-outcomes"></canvas></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">Конверсия по часам (%)</div>
        <div style="position:relative;height:240px"><canvas id="chart-conversion"></canvas></div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px">Сводка за период</div>
        <div id="analytics-summary" style="padding:10px">
          <div style="text-align:center;color:var(--muted)">Загрузка...</div>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB: Referrals -->
  <div id="tab-referrals" class="tab-panel">
    <div class="section-hdr">
      <span class="section-title">Реферальная система</span>
    </div>
    <div id="ref-content" style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
      <div style="text-align:center;color:var(--muted);padding:20px">Загрузка...</div>
    </div>
  </div>

  <!-- TAB: Payouts -->
  <div id="tab-payouts" class="tab-panel">
    <div class="section-hdr">
      <span class="section-title">Заявки на вывод</span>
      <button class="btn-refresh" onclick="loadPayouts()">↻ Обновить</button>
    </div>
    <div id="payouts-content" style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
      <div style="text-align:center;color:var(--muted);padding:20px">Загрузка...</div>
    </div>
  </div>

  <!-- TAB: Exports -->
  <div id="tab-exports" class="tab-panel">
    <div class="section-hdr">
      <span class="section-title">Экспорт данных (CSV)</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:14px;font-weight:700;margin-bottom:8px">📋 Лог диалогов</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Все взаимодействия с игроками: сообщения, ответы, результаты</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="export-btn" href="{{ pfx }}/export/interactions.csv">Все</a>
          <a class="export-btn" href="{{ pfx }}/export/interactions.csv?event=agreed">Согласились</a>
          <a class="export-btn" href="{{ pfx }}/export/interactions.csv?event=refused">Отказали</a>
          <a class="export-btn" href="{{ pfx }}/export/interactions.csv?event=no_response">Нет ответа</a>
        </div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:14px;font-weight:700;margin-bottom:8px">📊 История сессий</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Все игровые сессии: длительность, статистика, робуксы</p>
        <a class="export-btn" href="{{ pfx }}/export/sessions.csv">Скачать CSV</a>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:14px;font-weight:700;margin-bottom:8px">📈 Сводка по ботам</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Общие показатели каждого аккаунта: подходы, конверсия, робуксы</p>
        <a class="export-btn" href="{{ pfx }}/export/summary.csv">Скачать CSV</a>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:14px;font-weight:700;margin-bottom:8px">⏰ Аналитика по часам</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Часовая разбивка: события, конверсия, тренды</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="export-btn" href="{{ pfx }}/export/analytics.csv?hours=24">24ч</a>
          <a class="export-btn" href="{{ pfx }}/export/analytics.csv?hours=48">48ч</a>
          <a class="export-btn" href="{{ pfx }}/export/analytics.csv?hours=168">Неделя</a>
        </div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px">
        <div style="font-size:14px;font-weight:700;margin-bottom:8px">💬 Топ ответов игроков</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Самые частые ответы — для анализа и улучшения скриптов</p>
        <a class="export-btn" href="{{ pfx }}/export/top_replies.csv">Скачать CSV</a>
      </div>
    </div>
  </div>

  <div class="footer">Автообновление каждые 15 сек · Модалка не сбрасывается</div>
</div>

<!-- Detail modal -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-hdr">
      <h2 id="modal-title">Детали</h2>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div id="modal-body">
      <div style="text-align:center;color:var(--muted);padding:40px">Загрузка...</div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
var _chartReady = (typeof Chart !== 'undefined');
const PFX = '{{ pfx }}';
const eventIcons = {agreed:'✅',refused:'❌',no_response:'💤',donated:'💰'};
const eventColors = {agreed:'var(--green)',refused:'var(--red)',no_response:'var(--yellow)',donated:'var(--cyan)'};
const eventLabels = {agreed:'согласился',refused:'отказал',no_response:'молчал',donated:'задонатил'};

function switchTab(id){
  const tabIds=['users','feed','analytics','referrals','payouts','exports'];
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',tabIds[i]===id));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  if(id==='feed') loadFeed();
  if(id==='analytics') loadAnalytics();
  if(id==='referrals') loadReferrals();
  if(id==='payouts') loadPayouts();
}

function renderIlogRow(e){
  const icon = eventIcons[e.event]||'💬';
  const color = eventColors[e.event]||'var(--accent2)';
  let body = '';
  if(e.target_name) body += '<span class="ilog-target">→'+esc(e.target_name)+'</span> ';
  if(e.message) body += esc(e.message)+' ';
  if(e.player_reply) body += '<span class="ilog-reply">[ответ: '+esc(e.player_reply)+']</span> ';
  if(e.event) body += '<span class="ilog-event">['+esc(eventLabels[e.event]||e.event)+']</span>';
  const acc = e.account_name ? '<span style="color:var(--muted);font-size:10px">'+esc(e.account_name)+'</span> ' : '';
  return '<div class="ilog-row"><span class="ilog-time">'+(e._date_str||'')+' '+(e._time_str||'')+'</span>'
    +'<span class="ilog-icon" style="color:'+color+'">'+icon+'</span>'
    +'<span class="ilog-body">'+acc+body+'</span>'
    +'<span class="ilog-ago">'+(e._ago||'')+'</span></div>';
}

function esc(s){if(!s)return '';const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function loadFeed(){
  const ev = document.getElementById('feed-event').value;
  let url = PFX+'/api/interactions_all?limit=200';
  if(ev) url += '&event='+ev;
  fetch(url).then(r=>r.json()).then(d=>{
    const box = document.getElementById('feed-log');
    if(!d.log||!d.log.length){box.innerHTML='<div style="text-align:center;color:var(--muted);padding:20px">Нет данных</div>';return;}
    box.innerHTML = d.log.map(renderIlogRow).join('');
  });
}

function safeFetch(url){
  return fetch(url,{credentials:'same-origin'}).then(r=>{
    if(r.status===403||r.status===401){window.location.href=PFX+'/login';throw new Error('session expired');}
    const ct=r.headers.get('content-type')||'';
    if(!ct.includes('application/json')){return r.text().then(t=>{throw new Error('Ответ не JSON: '+t.substring(0,120))});}
    return r.json();
  });
}

function openModal(key){
  document.getElementById('modal').classList.add('open');
  document.getElementById('modal-title').textContent = 'Загрузка...';
  document.getElementById('modal-body').innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px">Загрузка...</div>';

  Promise.all([
    safeFetch(PFX+'/api/user/'+key),
    safeFetch(PFX+'/api/interactions/'+key+'?limit=200'),
  ]).then(([userData, iData])=>{
    if(userData.error){document.getElementById('modal-body').innerHTML='<div style="color:var(--red)">Не найдено</div>';return;}
    const lic = userData.license||{};
    const accounts = userData.accounts||[];
    const user = userData.user||{};
    const ilog = iData.log||[];

    const isdc = !!lic.dc_id;
    const platformBadge = isdc ? '[DC] ' : '[TG] ';
    const displayName = isdc
      ? (lic.dc_username ? '@'+lic.dc_username : 'DC:'+lic.dc_id)
      : (user.tg_username ? '@'+user.tg_username : 'ID '+lic.tg_id);
    document.getElementById('modal-title').textContent = platformBadge + displayName + ' — ' + key.slice(0,4)+'••••';

    let totalR = 0, totalD = 0, totalApp = 0, totalAgr = 0, totalRef = 0, online = 0, totalBooth = 0;
    accounts.forEach(a=>{
      totalR += (a.robux_alltime||0) + (a.robux_gross||0);
      totalD += (a.donations_alltime||0) + (a.donations||0);
      totalApp += (a.approached_alltime||0) + (a.approached||0);
      totalAgr += (a.agreed_alltime||0) + (a.agreed||0);
      totalRef += (a.refused_alltime||0) + (a.refused||0);
      totalBooth += (a.raised_current||0);
      if(a._online) online++;
    });
    const conv = totalApp ? Math.round(totalAgr*100/totalApp) : 0;

    let html = '';

    // Stats cards
    html += '<div class="modal-stats">';
    html += '<div class="ms"><div class="ms-val" style="color:var(--yellow)">'+totalR+'</div><div class="ms-lbl">R$ заработано</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--accent)">'+Math.round(totalR*0.6)+'</div><div class="ms-lbl">R$ чистыми (60%)</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--cyan)">'+totalBooth+'</div><div class="ms-lbl">R$ на стенде</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--green)">'+totalD+'</div><div class="ms-lbl">Донатов</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--blue)">'+totalApp+'</div><div class="ms-lbl">Подходов</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--accent2)">'+totalAgr+'</div><div class="ms-lbl">Согласий</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--red)">'+totalRef+'</div><div class="ms-lbl">Отказов</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--cyan)">'+conv+'%</div><div class="ms-lbl">Конверсия</div></div>';
    html += '<div class="ms"><div class="ms-val" style="color:var(--green)">'+online+'/'+accounts.length+'</div><div class="ms-lbl">Онлайн</div></div>';
    html += '</div>';

    // Control panel
    const warns = lic.warnings||0;
    const notes = lic.admin_notes||'';
    const keyType = lic.key_type||'lifetime';
    const licStatus = lic.status||'active';

    html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">';
    html += '<div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px">Управление</div>';
    html += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">';
    // Info row
    html += '<div style="font-size:11px;color:var(--muted);display:flex;gap:16px;width:100%;flex-wrap:wrap">';
    if(isdc){
      html += '<span><span style="background:#5865F2;color:#fff;font-size:10px;padding:1px 6px;border-radius:3px;font-weight:700">DISCORD</span> ';
      html += (lic.dc_username?'@'+esc(lic.dc_username):'')+'</span>';
    } else {
      html += '<span><span style="background:#229ED9;color:#fff;font-size:10px;padding:1px 6px;border-radius:3px;font-weight:700">TELEGRAM</span> ';
      html += (user.tg_username?'@'+esc(user.tg_username):'')+'</span>';
    }
    html += '<span>Тип: <strong style="color:var(--text)">'+keyType+'</strong></span>';
    html += '<span>Статус: <strong style="color:'+(licStatus==='active'?'var(--green)':'var(--red)')+'">'+licStatus+'</strong></span>';
    html += '<span>Предупреждений: <strong style="color:'+(warns>=2?'var(--red)':warns>=1?'var(--yellow)':'var(--text)')+'">'+warns+'/3</strong></span>';
    html += '</div>';
    html += '</div>';
    // Buttons
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">';
    if(licStatus==='active'){
      html += '<button onclick="adminAction(&apos;warn&apos;,&apos;'+key+'&apos;,this)" style="padding:6px 14px;border-radius:8px;border:1px solid rgba(234,179,8,.3);background:rgba(234,179,8,.08);color:var(--yellow);font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">⚠ Предупреждение</button>';
      html += '<button onclick="adminAction(&apos;revoke&apos;,&apos;'+key+'&apos;,this)" style="padding:6px 14px;border-radius:8px;border:1px solid rgba(239,68,68,.3);background:rgba(239,68,68,.08);color:var(--red);font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">Отозвать ключ</button>';
      if(keyType==='trial'){
        html += '<button onclick="extendKey(&apos;'+key+'&apos;)" style="padding:6px 14px;border-radius:8px;border:1px solid rgba(34,197,94,.3);background:rgba(34,197,94,.08);color:var(--green);font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">+ Продлить</button>';
      }
    }
    html += '</div>';
    // Admin notes
    html += '<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:12px">';
    html += '<textarea id="admin-notes" rows="2" style="flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:8px;font-size:11px;font-family:inherit;resize:vertical" placeholder="Заметки администратора...">'+esc(notes)+'</textarea>';
    html += '<button onclick="saveNotes(&apos;'+key+'&apos;,this)" style="padding:8px 14px;border-radius:8px;border:1px solid var(--border2);background:none;color:var(--muted);font-size:11px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap">Сохранить</button>';
    html += '</div>';
    html += '</div>';

    // Allowed Roblox accounts management
    html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">';
    html += '<div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px">Roblox-аккаунты ключа</div>';
    html += '<div id="acc-list-'+key.replace(/[^a-zA-Z0-9]/g,"")+'"></div>';
    html += '<div style="display:flex;gap:6px;margin-top:8px">';
    html += '<input id="new-acc-'+key.replace(/[^a-zA-Z0-9]/g,"")
+'" type="text" placeholder="Ник или ID Roblox" style="flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:6px 10px;font-size:11px;font-family:inherit">';
    html += '<button onclick="addAccount(&apos;'+key+'&apos;)" style="padding:6px 12px;border-radius:6px;border:1px solid rgba(34,197,94,.3);background:rgba(34,197,94,.08);color:var(--green);font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">+ Добавить</button>';
    html += '</div>';
    html += '</div>';
    loadAccounts(''+key+'');

    // Accounts
    if(accounts.length){
      html += '<div style="margin-bottom:16px"><div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Аккаунты ('+accounts.length+')</div>';
      accounts.forEach(a=>{
        const dot = a._online ? '<span style="color:var(--green)">●</span>' : '<span style="color:#333">●</span>';
        html += '<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:8px">';
        html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
        html += dot+' <strong>'+esc(a.name||a.roblox_user_id||'—')+'</strong>';
        html += ' <span class="mono">'+esc(a.roblox_user_id||'')+'</span>';
        html += '</div>';
        html += '<div style="display:flex;gap:16px;font-size:11px;color:var(--muted);flex-wrap:wrap">';
        const _gross = (a.robux_alltime||0)+(a.robux_gross||0);
        const _net = Math.round(_gross * 0.6);
        html += '<span>R$: <strong style="color:var(--yellow)">'+_gross+'</strong> <span style="color:var(--muted);font-size:10px">(~'+_net+' чист.)</span></span>';
        if(a.raised_current) html += '<span>Стенд: <strong style="color:var(--cyan)">'+(a.raised_current||0)+'</strong></span>';
        html += '<span>Донаты: <strong>'+((a.donations_alltime||0)+(a.donations||0))+'</strong></span>';
        html += '<span>Подх: '+((a.approached_alltime||0)+(a.approached||0))+'</span>';
        html += '<span>Согл: '+((a.agreed_alltime||0)+(a.agreed||0))+'</span>';
        html += '<span>Отк: '+((a.refused_alltime||0)+(a.refused||0))+'</span>';
        html += '<span>Хопы: '+(a.hops||0)+'</span>';
        if(a._last_seen_str) html += '<span style="margin-left:auto">⏱ '+esc(a._last_seen_str)+'</span>';
        html += '</div>';
        // Sessions
        if(a.sessions && a.sessions.length){
          html += '<details style="margin-top:8px"><summary style="font-size:10px;font-weight:700;color:var(--muted);cursor:pointer;text-transform:uppercase">Сессии ('+a.sessions.length+')</summary>';
          html += '<div class="sess-list" style="margin-top:6px">';
          a.sessions.forEach(s=>{
            html += '<div class="sess-item">';
            html += '<span style="font-family:JetBrains Mono,monospace;color:var(--text);font-weight:600;min-width:55px">'+(s._dur_str||'—')+'</span>';
            html += '<span>👤'+(s.approached||0)+'</span>';
            html += '<span style="color:var(--yellow);font-weight:600">R$'+(s.robux_gross||0)+'</span>';
            html += '<span>🎁'+(s.donations||0)+'</span>';
            html += '<span style="margin-left:auto;font-size:10px;color:#444">'+(s._date_str||'—')+'</span>';
            html += '</div>';
          });
          html += '</div></details>';
        }
        html += '</div>';
      });
      html += '</div>';
    }

    // Interaction log
    html += '<div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Лог диалогов ('+ilog.length+')</div>';
    if(ilog.length){
      html += '<div class="ilog">';
      ilog.forEach(e=>{html += renderIlogRow(e);});
      html += '</div>';
    } else {
      html += '<div style="text-align:center;color:var(--muted);padding:20px;background:var(--surface);border-radius:12px">Пока нет данных</div>';
    }

    document.getElementById('modal-body').innerHTML = html;
  }).catch(e=>{
    document.getElementById('modal-body').innerHTML = '<div style="color:var(--red)">Ошибка загрузки: '+e+'</div>';
  });
}

function closeModal(){document.getElementById('modal').classList.remove('open');}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});

function adminAction(action, key, btn){
  const msgs = {warn:'Выдать предупреждение?',revoke:'Отозвать ключ? Это необратимо!'};
  if(!confirm(msgs[action]||'Подтвердить?')) return;
  btn.disabled = true;
  btn.textContent = '...';
  fetch(PFX+'/api/'+action+'/'+key,{method:'POST',headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if(d.revoked) alert('Ключ отозван (3 предупреждения)');
      else if(action==='warn') alert('Предупреждение выдано ('+d.warnings+'/3)');
      else alert('Готово');
      location.reload();
    }).catch(()=>{btn.disabled=false;btn.textContent='Ошибка';});
}

function extendKey(key){
  const hours = prompt('На сколько часов продлить?','24');
  if(!hours) return;
  fetch(PFX+'/api/extend/'+key,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hours:parseInt(hours)})})
    .then(r=>r.json()).then(d=>{if(d.ok)alert('Продлено на '+d.hours+'ч');else alert(d.error||'Ошибка');});
}

function saveNotes(key, btn){
  const notes = document.getElementById('admin-notes').value;
  btn.textContent = '...';
  fetch(PFX+'/api/notes/'+key,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes:notes})})
    .then(r=>r.json()).then(d=>{btn.textContent=d.ok?'Сохранено':'Ошибка';setTimeout(()=>{btn.textContent='Сохранить'},1500);});
}

// Auto-refresh stats every 15s without page reload (keeps modal open)
setInterval(()=>{
  if(document.getElementById('modal').classList.contains('open')) return;
  safeFetch(PFX+'/api/overview').then(d=>{
    if(!d||d.error) return;
    // Update header stats
    const ids=['total_keys','active_now','total_robux','total_robux_alltime','total_users','pending_apps'];
    const vals=[d.stats.total_keys,d.stats.active_now,d.stats.total_robux,d.stats.total_robux_alltime,d.stats.total_users,d.stats.pending_apps];
    ids.forEach((id,i)=>{const el=document.getElementById('stat-'+id);if(el)el.textContent=vals[i];});
    // Update time
    const tEl=document.getElementById('admin-time');if(tEl)tEl.textContent=d.now;
  }).catch(()=>{});
}, 15000);

// ── IP Management ───────────────────────────────────────────────────
function loadAccounts(key){
  const kId=key.replace(/[^a-zA-Z0-9]/g,'');
  safeFetch(PFX+'/api/accounts/'+key).then(d=>{
    if(!d||!d.accounts) return;
    const wrap=document.getElementById('acc-list-'+kId);
    if(!wrap) return;
    const kId2=key.replace(/[^a-zA-Z0-9]/g,'');
    let h='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">';
    h+='<span style="font-size:10px;color:var(--muted)">Аккаунтов: '+d.accounts.filter(a=>a.status==='allowed').length+'/'+d.max_accounts+'</span>';
    h+='<span style="margin-left:auto;font-size:10px;color:var(--muted)">Лимит:</span>';
    h+='<input id="max-acc-'+kId2+'" type="number" min="1" max="50" value="'+d.max_accounts+'" style="width:50px;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:4px 6px;font-size:11px;text-align:center;font-family:inherit">';
    h+='<button onclick="setMaxAccounts(&apos;'+key+'&apos;,&apos;'+kId2+'&apos;)" style="padding:4px 10px;border-radius:6px;border:1px solid rgba(59,130,246,.3);background:rgba(59,130,246,.08);color:var(--accent);font-size:10px;font-weight:600;cursor:pointer;font-family:inherit">Сохранить</button>';
    h+='</div>';
    h+='<div style="display:flex;flex-direction:column;gap:4px">';
    d.accounts.forEach(a=>{
      const isBanned = a.status==='banned';
      const color = isBanned ? 'var(--red)' : 'var(--green)';
      const badge = isBanned ? '🚫' : '✅';
      h+='<div style="display:flex;align-items:center;gap:8px;padding:4px 8px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;font-size:11px">';
      h+='<span>'+badge+'</span>';
      h+='<span style="color:'+color+';font-weight:600">'+esc(a.roblox_name||'?')+'</span>';
      h+='<span class="mono" style="color:var(--muted);font-size:10px">'+esc(a.roblox_uid)+'</span>';
      h+='<span style="color:var(--muted);font-size:9px;margin-left:auto">'+a.added_str+'</span>';
      if(!isBanned){
        h+=`<button onclick="banAccount('${key}','${a.roblox_uid}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:10px;padding:0 4px" title="Заблокировать">🚫</button>`;
      } else {
        h+=`<button onclick="unbanAccount('${key}','${a.roblox_uid}')" style="background:none;border:none;color:var(--green);cursor:pointer;font-size:10px;padding:0 4px" title="Разблокировать">✅</button>`;
      }
      h+=`<button onclick="removeAccount('${key}','${a.roblox_uid}')" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:10px;padding:0 2px" title="Удалить">✕</button>`;
      h+='</div>';
    });
    if(!d.accounts.length) h+='<div style="color:var(--muted);font-size:10px;padding:4px">нет привязанных аккаунтов</div>';
    h+='</div>';
    wrap.innerHTML=h;
  }).catch(()=>{});
}

function addAccount(key){
  const kId=key.replace(/[^a-zA-Z0-9]/g,'');
  const input=document.getElementById('new-acc-'+kId);
  const val=input.value.trim();
  if(!val){alert('Введи ник или ID');return;}
  fetch(PFX+'/api/add_account/'+key,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({roblox:val})})
    .then(r=>r.json()).then(d=>{if(d.ok){input.value='';loadAccounts(key);}else alert(d.error||'Ошибка');});
}

function banAccount(key,uid){
  if(!confirm('Заблокировать аккаунт '+uid+'?')) return;
  fetch(PFX+'/api/ban_account/'+key,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({roblox_uid:uid})})
    .then(r=>r.json()).then(d=>{if(d.ok) loadAccounts(key);});
}

function unbanAccount(key,uid){
  fetch(PFX+'/api/unban_account/'+key,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({roblox_uid:uid})})
    .then(r=>r.json()).then(d=>{if(d.ok) loadAccounts(key);});
}

function removeAccount(key,uid){
  if(!confirm('Удалить аккаунт '+uid+' из списка?')) return;
  fetch(PFX+'/api/remove_account/'+key,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({roblox_uid:uid})})
    .then(r=>r.json()).then(d=>{if(d.ok) loadAccounts(key);});
}

function setMaxAccounts(key,kId){
  const input=document.getElementById('max-acc-'+kId);
  const val=parseInt(input.value);
  if(isNaN(val)||val<1||val>50){alert('Лимит от 1 до 50');return;}
  fetch(PFX+'/api/set_max_accounts/'+key,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({max_accounts:val})})
    .then(r=>r.json()).then(d=>{if(d.ok){input.style.borderColor='var(--green)';setTimeout(()=>input.style.borderColor='var(--border)',1500);loadAccounts(key);}else alert(d.error||'Ошибка');});
}

// ── Analytics ───────────────────────────────────────────────────────
let _chartI=null, _chartO=null, _chartC=null;
function loadAnalytics(){
  const hours = document.getElementById('analytics-period').value;
  const key = document.getElementById('analytics-key').value;
  safeFetch(PFX+'/api/analytics?hours='+hours+(key?'&key='+encodeURIComponent(key):'')).then(d=>{
    if(!d||d.error) return;
    const h = d.hours||[];
    const labels = h.map(x=>x.hour_label);
    const totals = h.map(x=>x.total);
    const agreed = h.map(x=>x.agreed);
    const refused = h.map(x=>x.refused);
    const noResp = h.map(x=>x.no_response);
    const msgs = h.map(x=>x.messages);
    const conv = h.map(x=>{
      const app = x.agreed+x.refused+x.no_response;
      return app ? Math.round(x.agreed*100/app) : 0;
    });

    if(!_chartReady){document.getElementById('tab-analytics').innerHTML='<div style="text-align:center;color:var(--muted);padding:40px">Графики недоступны — Chart.js заблокирован браузером.<br>Отключи блокировщик трекеров для этого сайта.</div>';return;}

    const chartOpts = {responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#6b6b80',font:{size:10}}}},scales:{x:{ticks:{color:'#6b6b80',font:{size:9},maxRotation:45},grid:{color:'rgba(255,255,255,.04)'}},y:{ticks:{color:'#6b6b80',font:{size:10}},grid:{color:'rgba(255,255,255,.04)'}}}};

    // Chart 1: Interactions by hour
    if(_chartI) _chartI.destroy();
    _chartI = new Chart(document.getElementById('chart-interactions'),{type:'bar',data:{labels,datasets:[
      {label:'Сообщений',data:msgs,backgroundColor:'rgba(124,106,255,.3)',borderColor:'rgba(124,106,255,.8)',borderWidth:1},
      {label:'Всего событий',data:totals,backgroundColor:'rgba(255,255,255,.08)',borderColor:'rgba(255,255,255,.2)',borderWidth:1}
    ]},options:chartOpts});

    // Chart 2: Outcomes stacked
    if(_chartO) _chartO.destroy();
    _chartO = new Chart(document.getElementById('chart-outcomes'),{type:'bar',data:{labels,datasets:[
      {label:'Согласился',data:agreed,backgroundColor:'rgba(34,197,94,.5)',borderColor:'rgba(34,197,94,.8)',borderWidth:1},
      {label:'Отказал',data:refused,backgroundColor:'rgba(239,68,68,.5)',borderColor:'rgba(239,68,68,.8)',borderWidth:1},
      {label:'Нет ответа',data:noResp,backgroundColor:'rgba(234,179,8,.4)',borderColor:'rgba(234,179,8,.8)',borderWidth:1}
    ]},options:{...chartOpts,scales:{...chartOpts.scales,x:{...chartOpts.scales.x,stacked:true},y:{...chartOpts.scales.y,stacked:true}}}});

    // Chart 3: Conversion %
    if(_chartC) _chartC.destroy();
    _chartC = new Chart(document.getElementById('chart-conversion'),{type:'line',data:{labels,datasets:[
      {label:'Конверсия %',data:conv,borderColor:'rgba(34,197,94,.8)',backgroundColor:'rgba(34,197,94,.1)',fill:true,tension:.3,pointRadius:2}
    ]},options:{...chartOpts,scales:{...chartOpts.scales,y:{...chartOpts.scales.y,min:0,max:100}}}});

    // Summary
    const tTotal = h.reduce((s,x)=>s+x.total,0);
    const tAgreed = h.reduce((s,x)=>s+x.agreed,0);
    const tRefused = h.reduce((s,x)=>s+x.refused,0);
    const tNoResp = h.reduce((s,x)=>s+x.no_response,0);
    const tDonated = h.reduce((s,x)=>s+x.donated,0);
    const tMsgs = h.reduce((s,x)=>s+x.messages,0);
    const tApp = tAgreed+tRefused+tNoResp;
    const tConv = tApp ? Math.round(tAgreed*100/tApp) : 0;
    const convColor = tConv>=30?'var(--green)':tConv>=15?'var(--yellow)':'var(--red)';

    document.getElementById('analytics-summary').innerHTML =
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:var(--accent2)">'+tTotal+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">ВСЕГО СОБЫТИЙ</div></div>'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:var(--blue)">'+tMsgs+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">СООБЩЕНИЙ</div></div>'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:var(--green)">'+tAgreed+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">СОГЛАСИЛИСЬ</div></div>'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:var(--red)">'+tRefused+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">ОТКАЗАЛИ</div></div>'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:var(--yellow)">'+tNoResp+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px">НЕТ ОТВЕТА</div></div>'+
      '<div style="padding:12px;background:var(--surface2);border-radius:10px;text-align:center"><div style="font-size:24px;font-weight:800;color:'+convColor+'">'+tConv+'%</div><div style="font-size:10px;color:var(--muted);margin-top:2px">КОНВЕРСИЯ</div></div>'+
      '</div>';
  }).catch(e=>{
    document.getElementById('analytics-summary').innerHTML='<div style="color:var(--red)">Ошибка: '+e+'</div>';
  });
}

// ── Referrals ───────────────────────────────────────────────────────
function loadReferrals(){
  const wrap = document.getElementById('ref-content');
  wrap.innerHTML='<div style="text-align:center;color:var(--muted);padding:20px">Загрузка...</div>';
  safeFetch(PFX+'/api/referrals').then(d=>{
    if(!d||d.error){wrap.innerHTML='<div style="color:var(--red)">Ошибка</div>';return;}
    const refs = d.referrers||[];
    if(!refs.length){wrap.innerHTML='<div style="text-align:center;color:var(--muted);padding:30px">Нет рефералов</div>';return;}
    let html='<div style="margin-bottom:16px;font-size:12px;color:var(--muted)">Всего рефереров: <strong style="color:var(--text)">'+refs.length+'</strong></div>';
    refs.forEach((r,i)=>{
      const tierColor = r.ref_count>=5?'var(--green)':r.ref_count>=2?'var(--yellow)':'var(--muted)';
      const tierLabel = r.ref_count>=5?'GOLD (10% R$)':r.ref_count>=2?'LIFETIME':'';
      html+='<div class="ref-card">';
      html+='<div class="ref-user">';
      html+='<span style="font-size:16px;font-weight:800;color:var(--accent2);min-width:28px">#'+(i+1)+'</span>';
      html+='<div><strong>'+(r.tg_username?'@'+esc(r.tg_username):'ID '+r.tg_id)+'</strong>';
      html+=' <span class="ref-badge" style="background:rgba(124,106,255,.12);color:'+tierColor+'">'+r.ref_count+' реф.</span>';
      if(tierLabel) html+=' <span class="ref-badge" style="background:rgba(34,197,94,.1);color:'+tierColor+'">'+tierLabel+'</span>';
      html+='</div></div>';
      if(r.refs&&r.refs.length){
        html+='<div class="ref-list">';
        r.refs.forEach(ref=>{
          const col=ref.has_key?'var(--green)':'var(--muted)';
          html+='<span style="padding:4px 10px;background:var(--surface);border:1px solid var(--border);border-radius:6px;font-size:11px">';
          html+='<span style="color:'+col+'">'+(ref.tg_username?'@'+esc(ref.tg_username):'ID '+ref.tg_id)+'</span>';
          if(ref.has_key&&ref.robux) html+=' <span style="color:var(--yellow);font-size:10px">R$'+ref.robux+'</span>';
          html+='</span>';
        });
        html+='</div>';
      }
      html+='</div>';
    });
    wrap.innerHTML=html;
  }).catch(e=>{wrap.innerHTML='<div style="color:var(--red)">Ошибка: '+e+'</div>';});
}

function loadPayouts(){
  const wrap = document.getElementById('payouts-content');
  wrap.innerHTML='<div style="text-align:center;color:var(--muted);padding:20px">Загрузка...</div>';
  safeFetch(PFX+'/api/payouts').then(d=>{
    if(!d||d.error){wrap.innerHTML='<div style="color:var(--red)">Ошибка</div>';return;}
    const payouts = d.payouts||[];
    if(!payouts.length){wrap.innerHTML='<div style="text-align:center;color:var(--muted);padding:30px">Заявок нет</div>';return;}
    const pending = payouts.filter(p=>p.status==='pending');
    let html='';
    if(pending.length){
      html+='<div style="font-size:13px;font-weight:700;color:var(--yellow);margin-bottom:14px">⏳ Ожидают: '+pending.length+'</div>';
    }
    payouts.forEach(p=>{
      const isPending = p.status==='pending';
      const statusColor = p.status==='paid'?'var(--green)':p.status==='rejected'?'var(--red)':'var(--yellow)';
      const statusLabel = p.status==='paid'?'✅ Выплачено':p.status==='rejected'?'❌ Отклонено':'⏳ Ожидает';
      const dt = p.created_at ? new Date(p.created_at*1000).toLocaleString('ru') : '—';
      const uname = p.tg_username ? '@'+esc(p.tg_username) : esc(p.tg_name)||('ID '+p.tg_id);
      html+='<div style="background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:12px">';
      html+='<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">';
      html+='<span style="font-size:13px;font-weight:700;color:var(--accent2)">#'+p.id+'</span>';
      html+='<span style="font-size:13px"><a href="https://t.me/'+esc(p.tg_username||'')+'" target="_blank" style="color:var(--accent2);text-decoration:none">'+uname+'</a></span>';
      html+='<span style="font-size:11px;color:var(--muted)">ID: '+p.tg_id+'</span>';
      html+='<span style="font-size:14px;font-weight:800;color:var(--green)">R$ '+p.amount.toLocaleString()+'</span>';
      html+='<span style="font-size:11px;color:var(--muted)">'+dt+'</span>';
      html+='<span style="font-size:11px;padding:2px 8px;border-radius:6px;background:rgba(255,255,255,.05);color:'+statusColor+'">'+statusLabel+'</span>';
      if(isPending){
        html+='<button onclick="resolvePayout('+p.id+',&apos;paid&apos;)" style="margin-left:auto;background:var(--green);color:#000;border:none;border-radius:8px;padding:6px 14px;font-size:12px;font-weight:700;cursor:pointer">✅ Выплачено</button>';
        html+='<button onclick="resolvePayout('+p.id+',&apos;rejected&apos;)" style="background:var(--red);color:#fff;border:none;border-radius:8px;padding:6px 14px;font-size:12px;font-weight:700;cursor:pointer">❌ Отклонить</button>';
      }
      html+='</div></div>';
    });
    wrap.innerHTML=html;
  }).catch(e=>{wrap.innerHTML='<div style="color:var(--red)">Ошибка: '+e+'</div>';});
}

function resolvePayout(id, action){
  if(!confirm(action==='paid'?'Подтвердить выплату?':'Отклонить заявку?')) return;
  fetch(PFX+'/api/payout_resolve/'+id, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})})
    .then(r=>r.json()).then(d=>{
      if(d.ok) loadPayouts();
      else alert('Ошибка: '+(d.error||'неизвестно'));
    });
}
</script>
</body></html>"""


def _fmt_ago(ts):
    if not ts:
        return "—"
    diff = time.time() - float(ts)
    if diff < 60:
        return f"{int(diff)}с назад"
    if diff < 3600:
        return f"{int(diff/60)}мин назад"
    if diff < 86400:
        return f"{int(diff/3600)}ч назад"
    return time.strftime("%d.%m %H:%M", time.localtime(float(ts)))


@app.route(_ADMIN_PFX + "/login", methods=["GET", "POST"])
def admin_login():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)
    if request.method == "POST":
        if _check_admin_pass(request.form.get("password", "")):
            session["admin"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect(_ADMIN_PFX)
        _rl_fail(ip)
        return render_template_string(_ADMIN_LOGIN_HTML, error="Неверный пароль")
    return render_template_string(_ADMIN_LOGIN_HTML, error=None)


@app.route(_ADMIN_PFX + "/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(_ADMIN_PFX + "/login")


@app.route(_ADMIN_PFX)
def admin_dashboard():
    if not session.get("admin"):
        return redirect(_ADMIN_PFX + "/login")
    # Group raw rows (one per account) by license key
    raw_rows = db_v2.get_admin_overview()
    grouped: dict[str, dict] = {}
    for r in raw_rows:
        k = r["key"]
        if k not in grouped:
            g = dict(r)
            g.update(acc_count=0, online_count=0, acc_names=[],
                     robux_gross=0, robux_alltime=0,
                     donations=0, donations_alltime=0,
                     approached=0, agreed=0, refused=0,
                     approached_alltime=0, agreed_alltime=0, refused_alltime=0,
                     is_online=0, last_seen=None)
            grouped[k] = g
        g = grouped[k]
        if r.get("acc_id"):
            g["acc_count"] += 1
            if r["is_online"]:
                g["online_count"] += 1
                g["is_online"] = 1
            name = r.get("acc_name") or ""
            if name and name not in g["acc_names"]:
                g["acc_names"].append(name)
            for f in ("robux_gross", "robux_alltime", "donations", "donations_alltime",
                      "approached", "agreed", "refused",
                      "approached_alltime", "agreed_alltime", "refused_alltime"):
                g[f] = (g.get(f) or 0) + (r.get(f) or 0)
            if (r.get("last_seen") or 0) > (g.get("last_seen") or 0):
                g["last_seen"] = r["last_seen"]
                if name:
                    g["acc_name"] = name
    rows = sorted(grouped.values(), key=lambda r: r.get("last_seen") or 0, reverse=True)
    for r in rows:
        r["last_seen_str"] = _fmt_ago(r.get("last_seen"))
        r["created_str"]   = _fmt_ago(r.get("lic_created"))
    stats = {
        "total_keys":        db_v2.count_licenses(),
        "active_now":        db_v2.count_active_accounts(),
        "total_robux":       db_v2.total_robux(),
        "total_robux_alltime": db_v2.total_robux_alltime(),
        "total_users":       db_v2.count_users(),
        "pending_apps":      db_v2.count_pending_applications(),
    }
    now_str = time.strftime("%d.%m.%Y %H:%M:%S")
    csrf = _csrf_token()
    return render_template_string(_ADMIN_DASH_HTML, rows=rows, s=stats, now_str=now_str, csrf=csrf, pfx=_ADMIN_PFX)


@app.route(_ADMIN_PFX + "/revoke/<key>", methods=["POST"])
def admin_revoke_key(key):
    if not session.get("admin"):
        return Response("Forbidden", 403)
    if not _csrf_check():
        return Response("Invalid CSRF token", 403)
    db_v2.revoke_license(key)
    return redirect(_ADMIN_PFX)


# ── Admin API: data endpoints ────────────────────────────────────────────

@app.route(_ADMIN_PFX + "/api/user/<key>")
def admin_api_user_detail(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = db_v2.get_user_dashboard_data(key)
    if not data:
        return jsonify({"error": "not found"}), 404
    now = time.time()
    cutoff = now - 35
    accounts = data["accounts"]
    for acc in accounts:
        acc["_online"] = (acc.get("last_seen") or 0) > cutoff
        acc["_last_seen_str"] = _fmt_ago(acc.get("last_seen"))
        for s in acc.get("sessions", []):
            dur = s.get("duration") or 0
            h, m = int(dur) // 3600, (int(dur) % 3600) // 60
            s["_dur_str"] = f"{h}ч {m}м" if h else f"{m}м"
            s["_date_str"] = time.strftime("%d.%m %H:%M",
                                           time.localtime(s["started_at"])) if s.get("started_at") else "—"
    lic = data["license"]
    # Attach dc_user info if this is a Discord license
    dc_user = None
    if lic.get("dc_id"):
        dc_user = db_v2.dc_get_user(lic["dc_id"])
        if dc_user:
            lic["dc_username"] = dc_user.get("dc_username", "")
            lic["dc_name"]     = dc_user.get("dc_name", "")
    return jsonify({"license": lic, "user": data["user"], "dc_user": dc_user, "accounts": accounts})


@app.route(_ADMIN_PFX + "/api/interactions/<key>")
def admin_api_interactions_key(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    limit = max(1, min(int(request.args.get("limit", 200)), 500))
    uid = request.args.get("uid", "")
    event = request.args.get("event", "")
    ilog = db_v2.get_interaction_log(key, limit=limit, uid=uid, event=event)
    now = time.time()
    for e in ilog:
        e["_time_str"] = time.strftime("%H:%M:%S", time.localtime(e["created_at"]))
        e["_date_str"] = time.strftime("%d.%m", time.localtime(e["created_at"]))
        ago = int(now - e["created_at"])
        if ago < 60:
            e["_ago"] = f"{ago}с"
        elif ago < 3600:
            e["_ago"] = f"{ago // 60}м"
        else:
            e["_ago"] = f"{ago // 3600}ч"
    return jsonify({"log": ilog, "total": len(ilog)})


@app.route(_ADMIN_PFX + "/api/interactions_all")
def admin_api_interactions_global():
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    limit = max(1, min(int(request.args.get("limit", 100)), 500))
    event = request.args.get("event", "")
    ilog = db_v2.get_all_interaction_log(limit=limit, event=event)
    now = time.time()
    for e in ilog:
        e["_time_str"] = time.strftime("%H:%M:%S", time.localtime(e["created_at"]))
        e["_date_str"] = time.strftime("%d.%m", time.localtime(e["created_at"]))
    return jsonify({"log": ilog})


# ── Admin API: actions ───────────────────────────────────────────────────

@app.route(_ADMIN_PFX + "/api/warn/<key>", methods=["POST"])
def admin_api_warn(key):
    if not session.get("admin"):
        return Response("Forbidden", 403)
    db_v2.add_warning(key)
    lic = db_v2.get_license(key)
    warnings = lic.get("warnings", 0) if lic else 0
    # Auto-revoke at 3 warnings
    if warnings >= 3:
        db_v2.revoke_license(key)
        return jsonify({"ok": True, "warnings": warnings, "revoked": True})
    return jsonify({"ok": True, "warnings": warnings})


@app.route(_ADMIN_PFX + "/api/notes/<key>", methods=["POST"])
def admin_api_notes(key):
    if not session.get("admin"):
        return Response("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    notes = str(data.get("notes", ""))[:500]
    db_v2.set_admin_notes(key, notes)
    return jsonify({"ok": True})


@app.route(_ADMIN_PFX + "/api/extend/<key>", methods=["POST"])
def admin_api_extend(key):
    if not session.get("admin"):
        return Response("Forbidden", 403)
    data = request.get_json(silent=True) or {}
    hours = int(data.get("hours", 24))
    if hours < 1 or hours > 8760:
        return jsonify({"ok": False, "error": "1-8760 hours"}), 400
    db_v2.extend_license(key, hours)
    return jsonify({"ok": True, "hours": hours})


@app.route(_ADMIN_PFX + "/api/revoke/<key>", methods=["POST"])
def admin_api_revoke(key):
    if not session.get("admin"):
        return Response("Forbidden", 403)
    db_v2.revoke_license(key)
    return jsonify({"ok": True})


# ── Admin API: account management ────────────────────────────────────────

@app.route(_ADMIN_PFX + "/api/accounts/<key>")
def admin_api_accounts(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    accs = db_v2.get_allowed_accounts(key)
    lic = db_v2.get_license(key)
    max_acc = (lic.get("max_accounts") or 5) if lic else 5
    for a in accs:
        a["added_str"] = time.strftime("%d.%m %H:%M", time.localtime(a["added_at"]))
    return jsonify({"accounts": accs, "max_accounts": max_acc})


@app.route(_ADMIN_PFX + "/api/add_account/<key>", methods=["POST"])
def admin_api_add_account(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    roblox_input = data.get("roblox", "").strip()
    if not roblox_input:
        return jsonify({"error": "no roblox id/name"}), 400
    # Resolve: if it's a number, treat as UID; otherwise lookup by username
    roblox_uid = ""
    roblox_name = ""
    if roblox_input.isdigit():
        roblox_uid = roblox_input
        try:
            import urllib.request, json as _json
            with urllib.request.urlopen(f"https://users.roblox.com/v1/users/{roblox_uid}", timeout=5) as r:
                roblox_name = _json.loads(r.read()).get("name", "")
        except Exception:
            pass
    else:
        # Lookup by username
        try:
            import urllib.request, json as _json
            req = urllib.request.Request(
                "https://users.roblox.com/v1/usernames/users",
                data=_json.dumps({"usernames": [roblox_input], "excludeBannedUsers": False}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                resp_data = _json.loads(r.read())
                if resp_data.get("data") and len(resp_data["data"]) > 0:
                    roblox_uid = str(resp_data["data"][0]["id"])
                    roblox_name = resp_data["data"][0].get("name", roblox_input)
        except Exception:
            pass
        if not roblox_uid:
            return jsonify({"error": f"Roblox аккаунт '{roblox_input}' не найден"}), 404
    ok = db_v2.add_allowed_account(key, roblox_uid, roblox_name)
    if not ok:
        return jsonify({"error": "Лимит аккаунтов исчерпан"}), 400
    return jsonify({"ok": True, "roblox_uid": roblox_uid, "roblox_name": roblox_name})


@app.route(_ADMIN_PFX + "/api/ban_account/<key>", methods=["POST"])
def admin_api_ban_account(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    roblox_uid = data.get("roblox_uid", "").strip()
    if not roblox_uid:
        return jsonify({"error": "no roblox_uid"}), 400
    db_v2.ban_account(key, roblox_uid)
    return jsonify({"ok": True})


@app.route(_ADMIN_PFX + "/api/unban_account/<key>", methods=["POST"])
def admin_api_unban_account(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    roblox_uid = data.get("roblox_uid", "").strip()
    if not roblox_uid:
        return jsonify({"error": "no roblox_uid"}), 400
    db_v2.add_allowed_account(key, roblox_uid)
    return jsonify({"ok": True})


@app.route(_ADMIN_PFX + "/api/remove_account/<key>", methods=["POST"])
def admin_api_remove_account(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    roblox_uid = data.get("roblox_uid", "").strip()
    if not roblox_uid:
        return jsonify({"error": "no roblox_uid"}), 400
    db_v2.remove_allowed_account(key, roblox_uid)
    return jsonify({"ok": True})


@app.route(_ADMIN_PFX + "/api/set_max_accounts/<key>", methods=["POST"])
def admin_api_set_max_accounts(key):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    max_acc = data.get("max_accounts", 5)
    if not isinstance(max_acc, int) or max_acc < 1 or max_acc > 50:
        return jsonify({"error": "invalid max (1-50)"}), 400
    db_v2.set_max_accounts(key, max_acc)
    return jsonify({"ok": True})


@app.route(_ADMIN_PFX + "/api/overview")
def admin_api_overview():
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    rows = db_v2.get_admin_overview()
    now = time.time()
    cutoff = now - 35
    accounts = []
    for r in rows:
        platform = "dc" if r.get("dc_id") else "tg"
        accounts.append({
            "key": r["key"], "tg_id": r["tg_id"],
            "tg_username": r.get("tg_username", ""),
            "dc_id": r.get("dc_id"),
            "dc_username": r.get("dc_username", ""),
            "platform": platform,
            "roblox_name": r.get("roblox_name") or r.get("acc_name") or "",
            "roblox_user_id": r.get("roblox_user_id") or "",
            "lic_status": r.get("lic_status", ""),
            "is_online": bool(r.get("is_online")),
            "robux_gross": r.get("robux_gross") or 0,
            "robux_alltime": r.get("robux_alltime") or 0,
            "donations": r.get("donations") or 0,
            "donations_alltime": r.get("donations_alltime") or 0,
            "approached": r.get("approached") or 0,
            "approached_alltime": r.get("approached_alltime") or 0,
            "agreed": r.get("agreed") or 0,
            "agreed_alltime": r.get("agreed_alltime") or 0,
            "refused": r.get("refused") or 0,
            "refused_alltime": r.get("refused_alltime") or 0,
            "raised_current": r.get("raised_current") or 0,
            "last_seen_str": _fmt_ago(r.get("last_seen")),
        })
    stats = {
        "total_keys": db_v2.count_licenses(),
        "active_now": db_v2.count_active_accounts(),
        "total_robux": db_v2.total_robux(),
        "total_robux_alltime": db_v2.total_robux_alltime(),
        "total_users": db_v2.count_users(),
        "pending_apps": db_v2.count_pending_applications(),
    }
    return jsonify({"accounts": accounts, "stats": stats, "now": time.strftime("%d.%m.%Y %H:%M:%S")})


@app.route(_ADMIN_PFX + "/api/analytics")
def admin_api_analytics():
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    hours = max(1, min(int(request.args.get("hours", 24)), 168))
    key = request.args.get("key", "")
    now = time.time()
    cutoff = now - hours * 3600
    data = db_v2.get_hourly_analytics(cutoff, license_key=key)
    return jsonify({"hours": data, "period": hours})


# ══════════════════════════════════════════════════════════════════════════════
# WEBAPP API  — /webapp/*  and  /miniapp
# ══════════════════════════════════════════════════════════════════════════════

import hashlib as _hl, hmac as _hmac

_MINIAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "miniapp")


_INITDATA_MAX_AGE = 86400  # 24 hours


def _verify_tg_initdata(init_data: str) -> int | None:
    """Verify Telegram WebApp initData HMAC + freshness. Returns tg_id or None."""
    try:
        from urllib.parse import unquote, parse_qsl
        parts = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
        check_hash = parts.pop("hash", "")
        if not check_hash:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parts.items()))
        secret = _hmac.new(b"WebAppData", BOT_TOKEN.encode(), _hl.sha256).digest()
        expected = _hmac.new(secret, data_check.encode(), _hl.sha256).hexdigest()
        if not secrets.compare_digest(expected, check_hash):
            return None
        # Freshness: initData older than 24h is rejected
        try:
            auth_date = int(parts.get("auth_date", "0"))
        except (TypeError, ValueError):
            return None
        if not auth_date or time.time() - auth_date > _INITDATA_MAX_AGE:
            return None
        import json as _j
        user = _j.loads(parts.get("user", "{}"))
        uid = user.get("id")
        return int(uid) if uid else None
    except Exception:
        return None


def _require_tg_auth() -> int | None:
    """Get authenticated tg_id from request. Returns None if not authenticated."""
    init_data = request.headers.get("X-Tg-Init-Data", "")
    if not init_data:
        return None
    return _verify_tg_initdata(init_data)


# ── Webapp rate limiter (per IP, per minute) ─────────────────────────────────
_webapp_rl: dict[str, list] = {}
_webapp_rl_lock = threading.Lock()
_WEBAPP_RL_MAX    = 90    # requests per minute per IP
_WEBAPP_RL_WINDOW = 60


def _webapp_rate_check() -> bool:
    ip = _real_ip()
    now = time.time()
    with _webapp_rl_lock:
        # Periodic cleanup
        if len(_webapp_rl) > 5000:
            for k in list(_webapp_rl.keys()):
                if not _webapp_rl[k] or now - max(_webapp_rl[k]) > _WEBAPP_RL_WINDOW * 2:
                    del _webapp_rl[k]
        recent = [t for t in _webapp_rl.get(ip, []) if now - t < _WEBAPP_RL_WINDOW]
        if len(recent) >= _WEBAPP_RL_MAX:
            _webapp_rl[ip] = recent
            return False
        recent.append(now)
        _webapp_rl[ip] = recent
        return True


@app.after_request
def _no_cache_webapp(resp):
    """Disable caching on /webapp/* responses so Mini App always sees fresh data."""
    if request.path.startswith("/webapp/"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/miniapp")
def miniapp_index():
    try:
        with open(os.path.join(_MINIAPP_DIR, "index.html"), encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except FileNotFoundError:
        return "Mini App not found", 404


@app.route("/miniapp/<path:filename>")
def miniapp_static(filename):
    from flask import send_from_directory
    return send_from_directory(_MINIAPP_DIR, filename)


@app.route("/webapp/profile")
def webapp_profile():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    profile = db_v2.get_webapp_profile(tg_id=tg_id)
    if not profile:
        return jsonify({"error": "no active license"}), 404
    return jsonify(profile)


def _merge_live_leaderboard(rows: list, ws: float) -> list:
    tg_to_row = {r["tg_id"]: r for r in rows if r.get("tg_id")}
    for uid, info in list(_online_cache.items()):
        tg_id = info.get("tg_id")
        if not tg_id:
            continue
        start_robux = (info.get("session_start_stats") or {}).get("robux_gross") or 0
        acc = db_v2.get_account(uid)
        if not acc:
            continue
        current_robux = acc.get("robux_gross") or 0
        delta = max(0, current_robux - start_robux)
        if delta <= 0:
            continue
        if tg_id in tg_to_row:
            tg_to_row[tg_id]["robux_week"] = (tg_to_row[tg_id].get("robux_week") or 0) + delta
        else:
            user = db_v2.get_user(tg_id)
            name = ((user.get("nickname") or user.get("tg_username") or user.get("tg_name")) if user else None) or f"tg:{tg_id}"
            new_row = {
                "tg_id": tg_id, "dc_id": None, "robux_week": delta,
                "week_start": ws, "display_name": name, "source": "tg", "rank_pos": 0,
            }
            rows.append(new_row)
            tg_to_row[tg_id] = new_row
    rows.sort(key=lambda x: x.get("robux_week") or 0, reverse=True)
    for i, r in enumerate(rows):
        r["rank_pos"] = i + 1
    return rows


@app.route("/webapp/leaderboard")
def webapp_leaderboard():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    period = request.args.get("period", "week")
    if period == "week":
        ws = db_v2.get_week_start()
    elif period == "prev":
        ws = db_v2.get_week_start() - 7 * 86400
    else:
        ws = None
    rows = db_v2.get_weekly_leaderboard(ws, limit=50) if ws is not None else db_v2.get_weekly_leaderboard(limit=50)
    if period == "week":
        rows = _merge_live_leaderboard(rows, ws)
    week_ends = (db_v2.get_week_start() + 7 * 86400) if period == "week" else None
    return jsonify({"leaderboard": rows, "week_ends": week_ends, "period": period})


@app.route("/webapp/levels")
def webapp_levels():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    return jsonify({"tiers": db_v2.get_all_tiers(), "robux_per_level": db_v2._ROBUX_PER_LEVEL})


@app.route("/webapp/my_accounts")
def webapp_my_accounts():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    return jsonify({"accounts": db_v2.get_my_accounts(tg_id)})


@app.route("/webapp/chart")
def webapp_chart():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    try:
        days = min(30, max(1, int(request.args.get("days", 7))))
    except (ValueError, TypeError):
        days = 7
    data = db_v2.get_robux_by_days(tg_id=tg_id, days=days)
    return jsonify({"chart": data, "days": days})


@app.route("/webapp/setnick", methods=["POST"])
def webapp_setnick():
    """First nickname change is free, after that requires Stars payment."""
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401

    body = request.get_json(silent=True) or {}
    nick = (body.get("nickname", "") or "").strip()
    if not nick or len(nick) > 24:
        return jsonify({"error": "nickname 1-24 chars"}), 400

    changes = db_v2.get_nickname_changes(tg_id=tg_id)
    if changes >= 1:
        return jsonify({
            "error": "payment_required",
            "message": f"Смена ника стоит {db_v2.NICKNAME_CHANGE_PRICE_STARS} ⭐",
            "price_stars": db_v2.NICKNAME_CHANGE_PRICE_STARS,
        }), 402

    if not db_v2.set_nickname(tg_id, nick):
        return jsonify({"error": "nickname_taken", "message": "Этот ник уже занят"}), 409
    return jsonify({"ok": True, "nickname": nick, "free": True})


@app.route("/webapp/check_nick")
def webapp_check_nick():
    """Live availability check (used by Mini App as user types)."""
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    nick = (request.args.get("n", "") or "").strip()
    if not nick or len(nick) > 24:
        return jsonify({"available": False, "reason": "invalid"}), 200
    taken = db_v2.is_nickname_taken(nick, exclude_tg_id=tg_id)
    return jsonify({"available": not taken})


@app.route("/webapp/nick_invoice", methods=["POST"])
def webapp_nick_invoice():
    """Create a Telegram Stars invoice link for nickname change.
    Stores payload→nickname mapping in DB to prevent replay/swap."""
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401

    body = request.get_json(silent=True) or {}
    nick = (body.get("nickname", "") or "").strip()
    if not nick or len(nick) > 24:
        return jsonify({"error": "nickname 1-24 chars"}), 400

    # Pre-check uniqueness BEFORE creating the invoice — don't waste user's stars
    if db_v2.is_nickname_taken(nick, exclude_tg_id=tg_id):
        return jsonify({"error": "nickname_taken", "message": "Этот ник уже занят"}), 409

    payload = f"nick:{tg_id}:{secrets.token_hex(8)}"
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
            json={
                "title": "Смена ника",
                "description": f"Установить новый ник: {nick}",
                "payload": payload,
                "currency": "XTR",
                "prices": [{"label": "Смена ника", "amount": db_v2.NICKNAME_CHANGE_PRICE_STARS}],
            }, timeout=10).json()
    except Exception:
        return jsonify({"error": "invoice failed"}), 500
    if not resp.get("ok"):
        return jsonify({"error": "invoice failed"}), 500

    # Record payload BEFORE returning URL so payment can be verified later
    db_v2.create_nick_payment(payload, tg_id, nick)
    return jsonify({"invoice_url": resp["result"]})


@app.route("/webapp/setavatar", methods=["POST"])
def webapp_setavatar():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401

    body = request.get_json(silent=True) or {}
    emoji = body.get("emoji")
    grad  = body.get("grad")
    if emoji and emoji not in db_v2.AVATAR_EMOJIS:
        return jsonify({"error": "invalid emoji"}), 400
    if grad and grad not in db_v2.AVATAR_GRADS:
        return jsonify({"error": "invalid gradient"}), 400
    db_v2.set_avatar(tg_id=tg_id, emoji=emoji, grad=grad)
    return jsonify({"ok": True, "emoji": emoji, "grad": grad})


@app.route("/webapp/avatars")
def webapp_avatars():
    return jsonify({
        "emojis": db_v2.AVATAR_EMOJIS,
        "grads": db_v2.AVATAR_GRADS,
    })


# ── Achievements ──────────────────────────────────────────────────────────────

@app.route("/webapp/achievements")
def webapp_achievements():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    new_unlocks = db_v2.check_achievements(tg_id)
    unlocked = db_v2.get_user_achievements(tg_id)
    unlocked_ids = {a["id"] for a in unlocked}
    all_list = []
    for a in db_v2.ACHIEVEMENTS:
        all_list.append({**a, "unlocked": a["id"] in unlocked_ids,
                         "unlocked_at": next((u["unlocked_at"] for u in unlocked if u["id"] == a["id"]), None)})
    return jsonify({
        "achievements": all_list,
        "total": len(db_v2.ACHIEVEMENTS),
        "unlocked_count": len(unlocked_ids),
        "new_unlocks": [db_v2.ACHIEVEMENTS_BY_ID[i] for i in new_unlocks if i in db_v2.ACHIEVEMENTS_BY_ID],
    })


# ── Daily tasks ───────────────────────────────────────────────────────────────

@app.route("/webapp/tasks")
def webapp_tasks():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    tasks = db_v2.get_or_generate_daily_tasks(tg_id)
    next_reset = db_v2.get_day_start() + 86400
    return jsonify({"tasks": tasks, "next_reset": next_reset})


@app.route("/webapp/tasks/claim", methods=["POST"])
def webapp_tasks_claim():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    body = request.get_json(silent=True) or {}
    try:
        task_id = int(body.get("task_id", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid task_id"}), 400
    if not task_id:
        return jsonify({"error": "task_id required"}), 400
    result = db_v2.claim_daily_task(tg_id, task_id)
    if not result:
        return jsonify({"error": "task not claimable"}), 409
    return jsonify({"ok": True, **result})


# ── Public user card ──────────────────────────────────────────────────────────

@app.route("/webapp/user_card")
def webapp_user_card():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    if not _require_tg_auth():
        return jsonify({"error": "auth required"}), 401
    try:
        target_id = int(request.args.get("id", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid id"}), 400
    if not target_id:
        return jsonify({"error": "id required"}), 400
    card = db_v2.get_public_profile(target_id)
    if not card:
        return jsonify({"error": "not found"}), 404
    return jsonify(card)


# ── Referrals ─────────────────────────────────────────────────────────────────

_bot_username_cache: dict = {"value": None, "fetched_at": 0}


def _get_bot_username() -> str:
    """Cached bot username (TTL 1 hour). Avoids hitting getMe on every request."""
    now = time.time()
    if _bot_username_cache["value"] and now - _bot_username_cache["fetched_at"] < 3600:
        return _bot_username_cache["value"]
    try:
        resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=5).json()
        username = resp.get("result", {}).get("username", "")
        if username:
            _bot_username_cache["value"] = username
            _bot_username_cache["fetched_at"] = now
        return username
    except Exception:
        return _bot_username_cache.get("value") or ""


@app.route("/webapp/referrals")
def webapp_referrals():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    data = db_v2.get_webapp_referrals(tg_id)
    bot_username = _get_bot_username()
    data["ref_link"] = f"https://t.me/{bot_username}?start=ref_{tg_id}" if bot_username else f"?start=ref_{tg_id}"
    return jsonify(data)


# ── Global chat ───────────────────────────────────────────────────────────────

@app.route("/webapp/chat/messages")
def webapp_chat_messages():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    try:
        since_id = int(request.args.get("since_id", 0))
    except (ValueError, TypeError):
        since_id = 0
    messages = db_v2.chat_get_recent(limit=50, since_id=since_id)
    return jsonify({"messages": messages, "you": tg_id})


@app.route("/webapp/chat/send", methods=["POST"])
def webapp_chat_send():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401

    # Must have an active license to write
    lic = db_v2.get_license_by_tg(tg_id)
    if not lic or not db_v2.is_key_valid(lic):
        return jsonify({"error": "Только пользователи с активным ключом могут писать в чат"}), 403

    body = request.get_json(silent=True) or {}
    text = (body.get("text", "") or "").strip()
    if not text:
        return jsonify({"error": "пустое сообщение"}), 400
    if len(text) > 500:
        return jsonify({"error": "слишком длинное (макс. 500 символов)"}), 400

    is_muted, until, reason = db_v2.chat_is_muted(tg_id)
    if is_muted:
        mins_left = max(1, int((until - time.time()) / 60))
        return jsonify({"error": f"Ты в муте на ещё {mins_left} мин" + (f" ({reason})" if reason else "")}), 403

    if not db_v2.chat_rate_check(tg_id, max_per_min=5):
        return jsonify({"error": "слишком часто, подожди"}), 429

    mid = db_v2.chat_send(tg_id, text)
    if not mid:
        return jsonify({"error": "не получилось"}), 500
    return jsonify({"ok": True, "id": mid})


# ── Support chat ──────────────────────────────────────────────────────────────

@app.route("/webapp/support/messages")
def webapp_support_messages():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    msgs = db_v2.support_history(tg_id, limit=100)
    db_v2.support_mark_read(tg_id)
    return jsonify({"messages": msgs})


@app.route("/webapp/support/unread")
def webapp_support_unread():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    return jsonify({"unread": db_v2.support_unread_count(tg_id)})


@app.route("/webapp/support/send", methods=["POST"])
def webapp_support_send():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    body = request.get_json(silent=True) or {}
    text = (body.get("text", "") or "").strip()
    if not text:
        return jsonify({"error": "пустое сообщение"}), 400
    if len(text) > 2000:
        return jsonify({"error": "слишком длинное (макс. 2000 символов)"}), 400
    if not db_v2.support_rate_check(tg_id, max_per_min=5):
        return jsonify({"error": "слишком много сообщений, подожди немного"}), 429

    user = db_v2.get_user(tg_id) or {}
    name = user.get("nickname") or user.get("tg_username") or user.get("tg_name") or str(tg_id)

    admin_msg_id = None
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_TG_ID,
                "text": (
                    f"💬 <b>Поддержка · {name}</b>\n"
                    f"<a href='tg://user?id={tg_id}'>tg://{tg_id}</a> · из Mini App\n\n"
                    f"{text}\n\n"
                    f"<i>Ответь на это сообщение — отправлю пользователю</i>"
                ),
                "parse_mode": "HTML",
            }, timeout=10).json()
        if resp.get("ok"):
            admin_msg_id = resp["result"]["message_id"]
    except Exception as e:
        print(f"[support] forward failed: {e}")

    msg_id = db_v2.support_save(tg_id, "in", text, admin_msg_id=admin_msg_id)
    return jsonify({"ok": True, "id": msg_id})


@app.route("/webapp/cashout", methods=["POST"])
def webapp_cashout():
    if not _webapp_rate_check():
        return jsonify({"error": "rate limited"}), 429
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401
    body = request.get_json(silent=True) or {}
    try:
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "invalid amount"}), 400
    if amount < 50:
        return jsonify({"error": "minimum 50 R$"}), 400
    if db_v2.has_pending_payout(tg_id):
        return jsonify({"error": "already pending"}), 409
    balance = db_v2.get_ref_balance(tg_id)
    if amount > balance:
        return jsonify({"error": "insufficient balance"}), 400
    user = db_v2.get_user(tg_id)
    rid = db_v2.create_payout_request(
        tg_id, user.get("tg_username", "") if user else "",
        user.get("tg_name", "") if user else "",
        amount,
    )
    return jsonify({"ok": True, "request_id": rid, "amount": amount})


# ── Custom avatar upload ─────────────────────────────────────────────────────
_AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatars")
os.makedirs(_AVATAR_DIR, exist_ok=True)
_AVATAR_MAX_BYTES = 2 * 1024 * 1024     # 2 MB upload limit
_AVATAR_OUT_SIZE  = 256                  # 256x256 final
_AVATAR_RATE_LIMIT_PER_HOUR = 8
_AVATAR_MAX_DIMENSION = 4096

# Set Pillow decompression bomb limit ONCE at module load (thread-safe)
try:
    from PIL import Image as _PILImage
    _PILImage.MAX_IMAGE_PIXELS = _AVATAR_MAX_DIMENSION * _AVATAR_MAX_DIMENSION
except ImportError:
    pass

# Per-user upload counters
_avatar_upload_log: dict[int, list] = {}
_avatar_upload_lock = threading.Lock()


def _avatar_rate_check(tg_id: int) -> bool:
    now = time.time()
    with _avatar_upload_lock:
        # Cleanup stale entries
        if len(_avatar_upload_log) > 5000:
            for k in list(_avatar_upload_log.keys()):
                if not _avatar_upload_log[k] or now - max(_avatar_upload_log[k]) > 7200:
                    del _avatar_upload_log[k]
        recent = [t for t in _avatar_upload_log.get(tg_id, []) if now - t < 3600]
        if len(recent) >= _AVATAR_RATE_LIMIT_PER_HOUR:
            _avatar_upload_log[tg_id] = recent
            return False
        recent.append(now)
        _avatar_upload_log[tg_id] = recent
        return True


def _validate_image_bytes(data: bytes) -> bool:
    if len(data) < 16:
        return False
    if data.startswith(b"\xff\xd8\xff"):
        return True  # JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True  # PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True  # WebP
    return False


@app.route("/webapp/upload_avatar", methods=["POST"])
def webapp_upload_avatar():
    tg_id = _require_tg_auth()
    if not tg_id:
        return jsonify({"error": "auth required"}), 401

    if not _avatar_rate_check(tg_id):
        return jsonify({"error": "rate limited, try later"}), 429

    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400

    # 1. Read with hard size cap, then drain the rest of the stream
    raw = f.stream.read(_AVATAR_MAX_BYTES + 1)
    if len(raw) > _AVATAR_MAX_BYTES:
        try:
            while f.stream.read(65536):
                pass
        except Exception:
            pass
        return jsonify({"error": "file too large (max 2MB)"}), 413

    # 2. Magic-number check
    if not _validate_image_bytes(raw):
        return jsonify({"error": "only JPEG/PNG/WebP allowed"}), 400

    # 3. Pillow decode + verify + re-encode (strips EXIF, embedded scripts)
    try:
        from PIL import Image, ImageOps
        from io import BytesIO

        # First pass: integrity check on a fresh buffer
        with Image.open(BytesIO(raw)) as probe:
            # Reject too-large dimensions BEFORE full decode
            if probe.width > _AVATAR_MAX_DIMENSION or probe.height > _AVATAR_MAX_DIMENSION:
                return jsonify({"error": "image dimensions too large"}), 400
            probe.verify()

        # Second pass: actual processing
        img = Image.open(BytesIO(raw))
        img.load()  # force full decode now (catches truncated)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if img.mode in ("LA", "PA", "P") else "RGB")
        # Center-crop to square
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top  = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_AVATAR_OUT_SIZE, _AVATAR_OUT_SIZE), Image.LANCZOS)
        if img.mode != "RGB":
            bg = Image.new("RGB", img.size, (10, 8, 19))
            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = bg

        # Atomic write: tmpfile → rename
        out_path = os.path.join(_AVATAR_DIR, f"{tg_id}.webp")
        tmp_path = out_path + f".tmp.{secrets.token_hex(4)}"
        img.save(tmp_path, format="WEBP", quality=85, method=6)
        img.close()
        os.replace(tmp_path, out_path)
    except Exception:
        return jsonify({"error": "invalid image"}), 400

    filename = f"{tg_id}.webp"
    db_v2.set_avatar_image(tg_id=tg_id, filename=filename)
    return jsonify({"ok": True, "image": filename, "url": f"/avatars/{filename}?v={int(time.time())}"})


@app.route("/avatars/<path:filename>")
def serve_avatar(filename):
    # Strict allowlist: only "<digits>.webp"
    import re
    if not re.match(r"^\d+\.webp$", filename):
        return "not found", 404
    from flask import send_from_directory
    try:
        resp = send_from_directory(_AVATAR_DIR, filename)
        resp.headers["Content-Type"] = "image/webp"
        resp.headers["Cache-Control"] = "public, max-age=300"
        resp.headers["Content-Security-Policy"] = "default-src 'none'"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp
    except Exception:
        return "not found", 404


# ── Weekly settlement watcher ─────────────────────────────────────────────────

def _weekly_watcher():
    import datetime
    while True:
        time.sleep(3600)
        try:
            now = time.time()
            current_ws = db_v2.get_week_start(now)
            prev_ws = current_ws - 7 * 86400
            last_settled = db_v2.get_last_settled_week()
            if last_settled is None or last_settled < prev_ws:
                winners = db_v2.settle_weekly_rankings(prev_ws)
                if winners:
                    print(f"[weekly] Settled {len(winners)} winners for week {prev_ws}")
                    for w in winners:
                        if w["prize"] and w["tg_id"]:
                            _send_tg(w["tg_id"],
                                f"🏆 <b>Итоги недели!</b>\n\n"
                                f"Ты занял <b>#{w['rank']}</b> место в топе фармеров!\n"
                                f"Заработано за неделю: <b>{w['robux']} R$</b>\n"
                                f"Приз зачислен: <b>+{w['prize']} R$</b> на баланс 🎁")
                    top1 = winners[0]
                    db_v2.chat_send_system(
                        f"🏆 Итоги недели!\n\n"
                        f"Победитель — {top1['display_name']}, нафармил {top1['robux']} R$ "
                        f"и забирает +{top1['prize']} R$ бонусом 🎁\n\n"
                        f"💡 Это мог бы быть ты, если бы фармил с RoBeggr."
                    )
        except Exception as e:
            print(f"[weekly] watcher error: {e}")

threading.Thread(target=_weekly_watcher, daemon=True, name="weekly-watcher").start()


# ── Streak warning watcher ───────────────────────────────────────────────────
# Reminds users with active streaks who haven't farmed today, before midnight MSK.

def _streak_warning_watcher():
    import datetime
    MSK = datetime.timezone(datetime.timedelta(hours=3))
    while True:
        time.sleep(900)  # 15 min
        try:
            now_msk = datetime.datetime.fromtimestamp(time.time(), tz=MSK)
            # Send warnings only between 21:00 and 23:30 MSK
            if not (21 <= now_msk.hour <= 23):
                continue
            today_num = int((time.time() + 10800) / 86400)
            users_at_risk = db_v2.get_users_at_risk_streak(today_num, min_streak=3)
            for u in users_at_risk:
                # Time until next MSK midnight
                total_min = max(0, (24 - now_msk.hour) * 60 - now_msk.minute)
                hours_left = total_min // 60
                minutes_left = total_min % 60
                if hours_left > 0:
                    time_left = f"{hours_left}ч {minutes_left:02d}м"
                else:
                    time_left = f"{minutes_left} мин"

                streak = u["streak"]
                streak_word = _streak_word(streak)
                lines = [
                    f"🔥 <b>Не забудь зайти сегодня!</b>",
                    "",
                    f"У тебя серия из <b>{streak} {streak_word}</b>. Если сегодня не зафармишь — серия сгорит и придётся начинать с нуля.",
                ]
                if u["next_milestone"]:
                    days_to_go = u["next_milestone"] - streak
                    if days_to_go > 0:
                        lines.append("")
                        lines.append(f"🎁 Через <b>{days_to_go} {_day_word(days_to_go)}</b> получишь награду <b>+{u['next_reward']} R$</b>.")
                lines += ["", f"⏰ До конца дня по МСК: <b>{time_left}</b>"]
                _send_tg(u["tg_id"], "\n".join(lines))
                db_v2.mark_streak_warned(u["tg_id"])
        except Exception as e:
            print(f"[streak-watcher] error: {e}")


def _streak_word(n: int) -> str:
    """Pluralization for 'дней'."""
    n = abs(n) % 100
    if 11 <= n <= 14: return "дней"
    n = n % 10
    if n == 1: return "день"
    if 2 <= n <= 4: return "дня"
    return "дней"


def _day_word(n: int) -> str:
    return _streak_word(n)


threading.Thread(target=_streak_warning_watcher, daemon=True, name="streak-warning").start()


# ── Memory cleanup watcher ──────────────────────────────────────────────────
# Periodically purges expired entries from in-memory dicts to prevent slow leaks.

def _memory_cleanup_watcher():
    while True:
        time.sleep(600)  # every 10 min
        try:
            now = time.time()
            # _stokens / _stokens_ga — drop tokens older than 1 hour
            with _stokens_lock if "_stokens_lock" in globals() else threading.Lock():
                pass
            try:
                cutoff = now - 3600
                for d in (_stokens, _stokens_ga):
                    for k in list(d.keys()):
                        # values are tokens — we don't track timestamps, so drop if dict is huge
                        pass
                # When dicts grow too big, just clear oldest half (simpler than tracking ts)
                for d in (_stokens, _stokens_ga):
                    if len(d) > 10000:
                        keys = list(d.keys())[:len(d) // 2]
                        for k in keys:
                            d.pop(k, None)
            except Exception:
                pass

            # _avatar_upload_log
            with _avatar_upload_lock:
                for k in list(_avatar_upload_log.keys()):
                    if not _avatar_upload_log[k] or now - max(_avatar_upload_log[k]) > 7200:
                        del _avatar_upload_log[k]

            # _webapp_rl
            with _webapp_rl_lock:
                for k in list(_webapp_rl.keys()):
                    if not _webapp_rl[k] or now - max(_webapp_rl[k]) > _WEBAPP_RL_WINDOW * 2:
                        del _webapp_rl[k]
        except Exception as e:
            print(f"[memcleanup] {e}")


threading.Thread(target=_memory_cleanup_watcher, daemon=True, name="mem-cleanup").start()


# ── Export endpoints ──────────────────────────────────────────────────

import csv
import io

@app.route(_ADMIN_PFX + "/export/interactions.csv")
def export_interactions():
    if not session.get("admin"):
        return Response("Forbidden", 403)
    key = request.args.get("key", "")
    event = request.args.get("event", "")
    ilog = db_v2.get_interaction_log(key, limit=10000, event=event) if key else db_v2.get_all_interaction_log(limit=10000, event=event)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Время", "Аккаунт", "UID", "Цель", "Сообщение", "Ответ", "Событие"])
    for e in ilog:
        w.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["created_at"])),
            e.get("account_name", ""), e.get("uid", ""),
            e.get("target_name", ""), e.get("message", ""),
            e.get("player_reply", ""), e.get("event", ""),
        ])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=interactions.csv"})


@app.route(_ADMIN_PFX + "/export/sessions.csv")
def export_sessions():
    if not session.get("admin"):
        return Response("Forbidden", 403)
    key = request.args.get("key", "")
    sessions = db_v2.get_all_sessions(key=key, limit=5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Аккаунт", "Начало", "Конец", "Длительность(мин)", "Подошёл", "Согласился", "Отказал", "Нет ответа", "Донаций", "Робукс"])
    for s in sessions:
        dur_min = round((s.get("duration") or 0) / 60, 1)
        w.writerow([
            s.get("account_id", ""),
            time.strftime("%Y-%m-%d %H:%M", time.localtime(s["started_at"])) if s.get("started_at") else "",
            time.strftime("%Y-%m-%d %H:%M", time.localtime(s["ended_at"])) if s.get("ended_at") else "active",
            dur_min, s.get("approached", 0), s.get("agreed", 0),
            s.get("refused", 0), s.get("no_response", 0),
            s.get("donations", 0), s.get("robux_gross", 0),
        ])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sessions.csv"})


@app.route(_ADMIN_PFX + "/export/summary.csv")
def export_summary():
    if not session.get("admin"):
        return Response("Forbidden", 403)
    rows = db_v2.get_admin_overview()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Roblox", "UID", "TG", "Ключ", "Тип", "Статус", "Подошёл", "Согласился", "Отказал", "Конверсия%", "Донаций", "Робукс"])
    for r in rows:
        app = (r.get("approached") or 0) + (r.get("approached_alltime") or 0)
        agr = (r.get("agreed") or 0) + (r.get("agreed_alltime") or 0)
        ref = (r.get("refused") or 0) + (r.get("refused_alltime") or 0)
        conv = round(agr * 100 / app) if app else 0
        w.writerow([
            r.get("roblox_name") or r.get("acc_name") or "",
            r.get("roblox_user_id") or "", r.get("tg_username") or "",
            r["key"][:4] + "****", r.get("key_type") or "",
            r.get("lic_status") or "", app, agr, ref, conv,
            (r.get("donations") or 0) + (r.get("donations_alltime") or 0),
            (r.get("robux_gross") or 0) + (r.get("robux_alltime") or 0),
        ])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=summary.csv"})


@app.route(_ADMIN_PFX + "/export/analytics.csv")
def export_analytics():
    if not session.get("admin"):
        return Response("Forbidden", 403)
    hours = max(1, min(int(request.args.get("hours", 24)), 168))
    data = db_v2.get_hourly_analytics(time.time() - hours * 3600)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Час", "Всего", "Сообщений", "Согласился", "Отказал", "Нет ответа", "Донат", "Конверсия%"])
    for h in data:
        app = h["agreed"] + h["refused"] + h["no_response"]
        conv = round(h["agreed"] * 100 / app) if app else 0
        w.writerow([h["hour_label"], h["total"], h["messages"], h["agreed"], h["refused"], h["no_response"], h["donated"], conv])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=analytics.csv"})


@app.route(_ADMIN_PFX + "/export/top_replies.csv")
def export_top_replies():
    if not session.get("admin"):
        return Response("Forbidden", 403)
    replies = db_v2.get_top_replies(limit=200)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ответ", "Событие", "Количество"])
    for r in replies:
        w.writerow([r["player_reply"], r["event"], r["cnt"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=top_replies.csv"})


# ── Referral API ─────────────────────────────────────────────────────

@app.route(_ADMIN_PFX + "/api/referrals")
def admin_api_referrals():
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    top = db_v2.get_top_referrers(limit=50)
    result = []
    for r in top:
        refs = db_v2.get_refs(r["tg_id"])
        ref_details = []
        for ref in refs:
            lic = db_v2.get_license_by_tg(ref["tg_id"])
            ref_details.append({
                "tg_id": ref["tg_id"],
                "tg_username": ref.get("tg_username") or "",
                "status": ref.get("status") or "",
                "has_key": bool(lic),
                "robux": (lic.get("robux_alltime") or 0) if lic else 0,
            })
        result.append({
            "tg_id": r["tg_id"],
            "tg_username": r.get("tg_username") or "",
            "ref_count": r["ref_count"],
            "refs": ref_details,
        })
    return jsonify({"referrers": result})


# ── Admin: payout requests ────────────────────────────────────────────
@app.route(_ADMIN_PFX + "/api/payouts")
def admin_api_payouts():
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({"payouts": db_v2.get_all_payouts(limit=100)})


@app.route(_ADMIN_PFX + "/api/payout_resolve/<int:rid>", methods=["POST"])
def admin_payout_resolve(rid):
    if not session.get("admin"):
        return jsonify({"error": "forbidden"}), 403
    action = request.json.get("action")  # "paid" or "rejected"
    if action not in ("paid", "rejected"):
        return jsonify({"error": "invalid action"}), 400
    info = db_v2.resolve_payout(rid, action)
    if not info:
        return jsonify({"error": "not found"}), 404
    # Notify user via TG
    try:
        if action == "paid":
            _send_tg(info["tg_id"], f"✅ Выплата R$ {info['amount']} подтверждена! Спасибо за рефералов 🙌")
        else:
            _send_tg(info["tg_id"], f"❌ Заявка на вывод R$ {info['amount']} отклонена. Напиши нам если есть вопросы.")
    except Exception:
        pass
    return jsonify({"ok": True})


# ── Honeypot: /admin returns 404 for scanners ─────────────────────────
@app.route("/admin", defaults={"path": ""})
@app.route("/admin/<path:path>")
def admin_honeypot(path):
    return Response("Not Found", status=404)


# ── Referral Dashboard ──────────────────────────────────────────────────

_REF_DASH_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Реферальная панель — PD Bot</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff;--gold:#ffd166}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(0,229,255,.2);border-radius:3px}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.05) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;font-size:14px;line-height:1.5}

.hdr{position:sticky;top:0;z-index:100;backdrop-filter:blur(20px);background:rgba(4,6,12,.92);border-bottom:1px solid var(--border2);display:flex;align-items:center;padding:0 24px;height:56px;gap:14px;box-shadow:0 1px 30px rgba(0,229,255,.04)}
.brand{font-weight:800;font-size:16px;display:flex;align-items:center;gap:10px;letter-spacing:-.01em}
.brand-icon{width:34px;height:34px;background:linear-gradient(135deg,rgba(0,229,255,.2),rgba(56,245,192,.15));border:1px solid var(--border2);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px}
.brand-name{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr-badge{font-size:10px;font-weight:700;background:rgba(0,229,255,.1);color:var(--accent);padding:3px 12px;border-radius:20px;letter-spacing:.08em;border:1px solid rgba(0,229,255,.15)}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.hdr-user{font-size:12px;color:var(--muted)}

.wrap{padding:28px 24px;max-width:1100px;margin:0 auto}

@keyframes fadeInUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
.fade{animation:fadeInUp .4s ease both}
.fade-1{animation-delay:.05s}.fade-2{animation-delay:.1s}.fade-3{animation-delay:.15s}.fade-4{animation-delay:.2s}.fade-5{animation-delay:.25s}

/* Hero */
.hero{background:linear-gradient(135deg,rgba(0,229,255,.06),rgba(56,245,192,.04));border:1px solid var(--border2);border-radius:20px;padding:28px 32px;margin-bottom:24px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;top:-60px;right:-60px;width:240px;height:240px;background:radial-gradient(circle,rgba(0,229,255,.07),transparent 65%);pointer-events:none}
.hero-row{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.hero-avatar{width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,rgba(0,229,255,.15),rgba(56,245,192,.1));border:1px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:var(--accent);font-family:'JetBrains Mono',monospace}
.hero-info h2{font-size:20px;font-weight:800;letter-spacing:-.02em}
.hero-info p{font-size:12px;color:var(--muted);margin-top:2px}
.hero-right{margin-left:auto;text-align:right}
.balance-val{font-size:28px;font-weight:800;color:var(--gold);font-family:'JetBrains Mono',monospace;line-height:1}
.balance-rub{font-size:13px;color:var(--muted);margin-top:3px}
.balance-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}

/* Stats row */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin-bottom:24px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;position:relative;overflow:hidden;transition:all .2s ease;cursor:default}
.stat:hover{border-color:var(--border2);box-shadow:0 0 28px rgba(0,229,255,.07);transform:translateY(-2px)}
.stat::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.stat.c-cyan::before{background:linear-gradient(90deg,var(--cyan),transparent)}
.stat.c-green::before{background:linear-gradient(90deg,var(--green),transparent)}
.stat.c-gold::before{background:linear-gradient(90deg,var(--gold),transparent)}
.stat.c-blue::before{background:linear-gradient(90deg,var(--blue),transparent)}
.stat.c-accent::before{background:linear-gradient(90deg,var(--accent2),transparent)}
.stat-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.stat-val{font-size:26px;font-weight:800;line-height:1;font-family:'JetBrains Mono',monospace}
.stat-val.cyan{color:var(--cyan)}.stat-val.green{color:var(--green)}.stat-val.gold{color:var(--gold)}.stat-val.blue{color:var(--blue)}.stat-val.accent{color:var(--accent2)}
.stat-sub{font-size:11px;color:var(--muted);margin-top:5px}

/* Rate card */
.rate-bar{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 20px;margin-bottom:24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.rate-item{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.rate-item strong{color:var(--text);font-family:'JetBrains Mono',monospace}
.rate-sep{width:1px;height:20px;background:var(--border2)}

/* Section */
.section-hdr{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.section-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.section-count{font-size:11px;color:var(--accent);background:rgba(0,229,255,.08);padding:2px 10px;border-radius:12px;font-weight:700;border:1px solid rgba(0,229,255,.12)}

/* Ref cards */
.refs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.ref-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px;transition:all .2s ease}
.ref-card:hover{border-color:var(--border2);box-shadow:0 0 24px rgba(0,229,255,.06);transform:translateY(-1px)}
.ref-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.ref-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.ref-dot.on{background:var(--green);box-shadow:0 0 8px rgba(0,255,135,.4);animation:pdot 2s infinite}
@keyframes pdot{0%,100%{box-shadow:0 0 8px rgba(0,255,135,.4)}50%{box-shadow:0 0 14px rgba(0,255,135,.6)}}
.ref-dot.off{background:#1e2a3a}
.ref-name{font-weight:700;font-size:14px}
.ref-id{font-size:10px;color:var(--muted);font-family:'JetBrains Mono',monospace}
.ref-badges{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
.rbadge{font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;letter-spacing:.03em}
.rb-active{background:rgba(0,255,135,.1);color:var(--green);border:1px solid rgba(0,255,135,.2)}
.rb-trial{background:rgba(255,193,7,.1);color:var(--yellow);border:1px solid rgba(255,193,7,.2)}
.rb-revoked{background:rgba(255,59,107,.1);color:var(--red);border:1px solid rgba(255,59,107,.2)}
.rb-nokey{background:rgba(74,96,128,.15);color:var(--muted);border:1px solid rgba(74,96,128,.2)}
.ref-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px}
.rs{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:10px;text-align:center}
.rs-val{font-size:16px;font-weight:800;font-family:'JetBrains Mono',monospace}
.rs-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:3px}
.ref-cut{background:linear-gradient(135deg,rgba(255,209,102,.06),rgba(0,229,255,.04));border:1px solid rgba(255,209,102,.15);border-radius:10px;padding:10px 14px;display:flex;align-items:center;justify-content:space-between}
.cut-label{font-size:11px;color:var(--muted)}
.cut-val{font-size:15px;font-weight:800;color:var(--gold);font-family:'JetBrains Mono',monospace}
.cut-rub{font-size:10px;color:var(--muted);margin-top:1px;text-align:right}

/* Empty state */
.empty{text-align:center;padding:60px 20px;color:var(--muted)}
.empty-icon{font-size:40px;margin-bottom:12px;opacity:.4}
.empty h3{font-size:16px;font-weight:700;color:var(--text);margin-bottom:6px}

/* Footer */
.footer{text-align:center;padding:24px;font-size:11px;color:#2a3a4a}

@media(max-width:600px){
  .hero-row{flex-direction:column;align-items:flex-start}
  .hero-right{margin-left:0}
  .stats{grid-template-columns:repeat(2,1fr)}
  .refs-grid{grid-template-columns:1fr}
  .rate-bar{gap:10px}
}
</style></head><body>

<div class="hdr">
  <div class="brand"><div class="brand-icon">💸</div><span class="brand-name">PD Bot</span></div>
  <span class="hdr-badge">РЕФЕРАЛЫ</span>
  <div class="hdr-right"><span class="hdr-user" id="hdr-user">{{ tg_uname }}</span></div>
</div>

<div class="wrap">
  <!-- Hero -->
  <div class="hero fade fade-1">
    <div class="hero-row">
      <div class="hero-avatar">{{ tg_uname[:1].upper() if tg_uname else '#' }}</div>
      <div class="hero-info">
        <h2>{{ tg_uname or ('ID ' + tg_id|string) }}</h2>
        <p>Реферальная программа · 10% с заработка каждого приглашённого</p>
      </div>
      <div class="hero-right">
        <div class="balance-label">Накоплено</div>
        <div class="balance-val" id="bal-robux">{{ ref_balance }}</div>
        <div class="balance-rub">≈ <span id="bal-rub">{{ "%.0f"|format(ref_balance * 0.5) }}</span> ₽</div>
      </div>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats">
    <div class="stat c-cyan fade fade-1">
      <div class="stat-label">Всего рефералов</div>
      <div class="stat-val cyan" id="stat-total-refs">{{ total_refs }}</div>
      <div class="stat-sub">приглашено тобой</div>
    </div>
    <div class="stat c-green fade fade-2">
      <div class="stat-label">Зарабатывают</div>
      <div class="stat-val green" id="stat-earning-refs">{{ earning_refs }}</div>
      <div class="stat-sub">с активным ботом</div>
    </div>
    <div class="stat c-accent fade fade-3">
      <div class="stat-label">Онлайн сейчас</div>
      <div class="stat-val accent" id="stat-online-refs">{{ online_refs }}</div>
      <div class="stat-sub">работают прямо сейчас</div>
    </div>
    <div class="stat c-gold fade fade-4">
      <div class="stat-label">R$ заработали</div>
      <div class="stat-val gold" id="stat-total-robux">{{ total_ref_robux }}</div>
      <div class="stat-sub">суммарно все рефералы</div>
    </div>
    <div class="stat c-gold fade fade-5">
      <div class="stat-label">Моя доля (10%)</div>
      <div class="stat-val gold" id="stat-my-cut">{{ my_total_cut }}</div>
      <div class="stat-sub">≈ <span id="stat-my-cut-rub">{{ "%.0f"|format(my_total_cut * 0.5) }}</span> ₽</div>
    </div>
  </div>

  <!-- Rate -->
  <div class="rate-bar fade fade-2">
    <div class="rate-item">💱 <strong>1 R$</strong> = 0.5 ₽</div>
    <div class="rate-sep"></div>
    <div class="rate-item">📊 Твой процент: <strong>10%</strong></div>
    <div class="rate-sep"></div>
    <div class="rate-item">💰 Накоплено: <strong>{{ ref_balance }} R$</strong> ≈ <strong>{{ "%.0f"|format(ref_balance * 0.5) }} ₽</strong></div>
    <div class="rate-sep"></div>
    <div class="rate-item">⏱ Авто-обновление каждые <strong>30 сек</strong></div>
  </div>

  <!-- Ref list -->
  <div class="fade fade-3">
    <div class="section-hdr">
      <span class="section-title">Приглашённые</span>
      <span class="section-count">{{ total_refs }}</span>
    </div>

    {% if refs %}
    <div class="refs-grid">
    {% for r in refs %}
      <div class="ref-card">
        <div class="ref-head">
          <div class="ref-dot {{ 'on' if r.is_online else 'off' }}"></div>
          <div>
            <div class="ref-name">{{ ('@' + r.tg_username) if r.tg_username else (r.tg_name or ('ID ' + r.tg_id|string)) }}</div>
            <div class="ref-id">tg_id: {{ r.tg_id }}</div>
          </div>
          <div class="ref-badges">
            {% if not r.has_key %}
              <span class="rbadge rb-nokey">нет ключа</span>
            {% elif r.key_status == 'active' and r.key_type == 'trial' %}
              <span class="rbadge rb-trial">TRIAL</span>
            {% elif r.key_status == 'active' %}
              <span class="rbadge rb-active">ACTIVE</span>
            {% else %}
              <span class="rbadge rb-revoked">{{ (r.key_status or 'revoked')|upper }}</span>
            {% endif %}
          </div>
        </div>
        <div class="ref-stats">
          <div class="rs">
            <div class="rs-val" style="color:var(--yellow)">{{ r.robux_earned }}</div>
            <div class="rs-lbl">R$ заработал</div>
          </div>
          <div class="rs">
            <div class="rs-val" style="color:var(--blue)">{{ r.accounts_count }}</div>
            <div class="rs-lbl">Аккаунтов</div>
          </div>
          <div class="rs">
            <div class="rs-val" style="color:{{ 'var(--green)' if r.is_online else 'var(--muted)' }}">{{ '🟢' if r.is_online else '⚫' }}</div>
            <div class="rs-lbl">{{ 'Онлайн' if r.is_online else 'Оффлайн' }}</div>
          </div>
        </div>
        <div class="ref-cut">
          <div>
            <div class="cut-label">Моя доля с этого реферала</div>
            <div class="cut-rub">≈ {{ "%.0f"|format(r.my_cut * 0.5) }} ₽</div>
          </div>
          <div style="text-align:right">
            <div class="cut-val">R$ {{ r.my_cut }}</div>
          </div>
        </div>
      </div>
    {% endfor %}
    </div>
    {% else %}
    <div class="empty">
      <div class="empty-icon">👥</div>
      <h3>Рефералов пока нет</h3>
      <p>Поделись своей ссылкой — получай 10% с их заработка</p>
    </div>
    {% endif %}
  </div>
</div>

<div class="footer">PD Bot · Реферальная панель · Авто-обновление каждые 30 сек</div>

<script>
(function(){
  const token = new URLSearchParams(location.search).get('token');
  if (!token) return;
  function refresh(){
    fetch('/ref/api/stats?token='+encodeURIComponent(token))
    .then(r=>r.ok?r.json():null).then(d=>{
      if(!d) return;
      const s = d.stats || {};
      const set = (id,v) => { const el=document.getElementById(id); if(el) el.textContent=v; };
      set('bal-robux',          s.ref_balance||0);
      set('bal-rub',            Math.round((s.ref_balance||0)*0.5));
      set('stat-total-refs',    s.total_refs||0);
      set('stat-earning-refs',  s.earning_refs||0);
      set('stat-online-refs',   s.online_refs||0);
      set('stat-total-robux',   s.total_ref_robux||0);
      set('stat-my-cut',        s.my_total_cut||0);
      set('stat-my-cut-rub',    Math.round((s.my_total_cut||0)*0.5));
    }).catch(()=>{});
  }
  setInterval(refresh, 30000);
})();
</script>
</body></html>"""


@app.route("/ref")
def ref_dashboard():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)
    token = request.args.get("token", "").strip()
    if not token:
        return Response("Ссылка недействительна. Получи новую через бота: /refpanel", status=400)
    tg_id = db_v2.validate_ref_token(token)
    if not tg_id:
        return Response("Ссылка истекла или недействительна. Получи новую через бота: /refpanel", status=403)

    data = db_v2.get_ref_dashboard_data(tg_id)
    if not data:
        return Response("Данные не найдены", status=404)

    user = data.get("user", {})
    tg_uname = "@" + user["tg_username"] if user.get("tg_username") else None

    return render_template_string(
        _REF_DASH_HTML,
        token=token,
        tg_uname=tg_uname or ("ID " + str(tg_id)),
        tg_id=tg_id,
        ref_balance=data["ref_balance"],
        total_refs=data["total_refs"],
        earning_refs=data["earning_refs"],
        online_refs=data["online_refs"],
        total_ref_robux=data["total_ref_robux"],
        my_total_cut=data["my_total_cut"],
        refs=data["refs"],
    )


@app.route("/ref/api/stats")
def ref_api_stats():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "Missing token"}), 400
    tg_id = db_v2.validate_ref_token(token)
    if not tg_id:
        return jsonify({"error": "Token invalid or expired"}), 403
    data = db_v2.get_ref_dashboard_data(tg_id)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"stats": {
        "ref_balance":     data["ref_balance"],
        "total_refs":      data["total_refs"],
        "earning_refs":    data["earning_refs"],
        "online_refs":     data["online_refs"],
        "total_ref_robux": data["total_ref_robux"],
        "my_total_cut":    data["my_total_cut"],
    }})


# ── User Dashboard ──────────────────────────────────────────────────────

_USER_DASH_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PD AutoFarm — Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0d0d0f;--surface:#141418;--surface2:#1a1a20;--surface3:#1f1f28;
  --border:rgba(255,255,255,0.06);--border2:rgba(255,255,255,0.12);
  --text:#f0f0f5;--muted:#6b6b80;
  --red:#ff3333;--gold:#ffd700;--green:#00e676;--yellow:#ffb300;--orange:#ff6b35;
  --glass:rgba(255,255,255,0.03);--glass2:rgba(255,255,255,0.06);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,51,51,.3);border-radius:3px}
html{scroll-behavior:smooth}
body{
  font-family:'Space Grotesk',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;font-size:14px;line-height:1.5;
  background-image:radial-gradient(ellipse 80% 60% at 50% -10%,rgba(255,51,51,0.07),transparent);
}
.hdr{
  position:sticky;top:0;z-index:100;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  background:rgba(13,13,15,0.85);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 24px;height:58px;gap:14px;
}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:17px;white-space:nowrap;color:var(--text)}
.brand-rs{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,#ff3333,#cc0000);
  display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:900;color:#fff;letter-spacing:-.5px;
  box-shadow:0 0 18px rgba(255,51,51,0.4);
}
.brand span{background:linear-gradient(90deg,#ff3333,#ff6b6b);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hdr-badge{
  font-size:9px;font-weight:800;letter-spacing:.12em;
  padding:3px 10px;border-radius:20px;
  background:rgba(255,51,51,0.12);color:var(--red);border:1px solid rgba(255,51,51,0.2);
  display:flex;align-items:center;gap:5px;
}
.hdr-badge::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--red);animation:pulse-live 1.5s infinite}
@keyframes pulse-live{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(255,51,51,.5)}50%{opacity:.7;box-shadow:0 0 0 4px rgba(255,51,51,0)}}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.hdr-time{font-size:11px;color:var(--muted);font-family:'Inter',sans-serif}
.wrap{padding:28px 24px;max-width:1180px;margin:0 auto}
.hero{
  background:linear-gradient(135deg,rgba(255,51,51,0.06) 0%,rgba(255,215,0,0.03) 100%);
  border:1px solid rgba(255,51,51,0.15);border-radius:24px;
  padding:28px 32px;margin-bottom:24px;position:relative;overflow:hidden;
}
.hero::before{
  content:'';position:absolute;top:-60px;right:-40px;
  width:280px;height:280px;
  background:radial-gradient(circle,rgba(255,51,51,0.08),transparent 70%);
  pointer-events:none;
}
.hero::after{
  content:'';position:absolute;bottom:-40px;left:30%;
  width:200px;height:200px;
  background:radial-gradient(circle,rgba(255,215,0,0.05),transparent 70%);
  pointer-events:none;
}
.hero-row{display:flex;align-items:center;gap:20px;flex-wrap:wrap;position:relative;z-index:1}
.hero-avatar{
  width:60px;height:60px;border-radius:16px;
  background:linear-gradient(135deg,rgba(255,51,51,0.2),rgba(255,215,0,0.1));
  border:1px solid rgba(255,51,51,0.3);
  display:flex;align-items:center;justify-content:center;
  font-size:26px;font-weight:900;color:var(--red);flex-shrink:0;
}
.hero-info h2{font-size:22px;font-weight:800;margin-bottom:3px;letter-spacing:-.3px}
.hero-info p{font-size:12px;color:var(--muted)}
.hero-status{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.status-pill{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.04em}
.s-active{background:rgba(0,230,118,.08);color:var(--green);border:1px solid rgba(0,230,118,.25)}
.s-trial{background:rgba(255,179,0,.08);color:var(--yellow);border:1px solid rgba(255,179,0,.25)}
.s-expired{background:rgba(255,51,51,.08);color:var(--red);border:1px solid rgba(255,51,51,.25)}
.hero-key{font-size:11px;color:var(--muted);font-family:'Inter',monospace;display:flex;align-items:center;gap:6px}
.key-badge{padding:2px 8px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--muted);border:1px solid var(--border)}
.trial-bar{margin-top:14px;padding:12px 16px;background:rgba(255,179,0,0.06);border:1px solid rgba(255,179,0,0.15);border-radius:12px;position:relative;z-index:1}
.trial-bar p{font-size:11px;color:var(--yellow);font-weight:600}
@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:24px}
.stat{
  background:var(--surface);border:1px solid var(--border);border-radius:18px;
  padding:20px;position:relative;overflow:hidden;
  transition:transform .2s,border-color .2s,box-shadow .2s;
  animation:fadeUp .5s ease both;
}
.stat:hover{transform:translateY(-3px);box-shadow:0 8px 32px rgba(0,0,0,0.4)}
.stat:nth-child(1){animation-delay:.05s}.stat:nth-child(2){animation-delay:.1s}
.stat:nth-child(3){animation-delay:.15s}.stat:nth-child(4){animation-delay:.2s}
.stat:nth-child(5){animation-delay:.25s}.stat:nth-child(6){animation-delay:.3s}
.stat-accent{position:absolute;top:0;left:0;right:0;height:2px;border-radius:2px 2px 0 0}
.stat-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:6px}
.stat-val{font-size:30px;font-weight:800;line-height:1;letter-spacing:-.5px}
.stat-sub{font-size:11px;color:var(--muted);margin-top:5px}
.c-red{color:var(--red)}.c-gold{color:var(--gold)}.c-green{color:var(--green)}
.c-yellow{color:var(--yellow)}.c-orange{color:var(--orange)}.c-text{color:var(--text)}
.section{margin-bottom:28px}
.section-hdr{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.section-title{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.section-badge{font-size:11px;font-weight:700;padding:2px 10px;border-radius:12px;background:rgba(255,51,51,.1);color:var(--red);border:1px solid rgba(255,51,51,.2)}
.acc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
.acc-card{
  background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:22px;
  transition:transform .2s,border-color .2s,box-shadow .2s;
}
.acc-card:hover{transform:translateY(-2px);border-color:rgba(255,51,51,0.2);box-shadow:0 6px 28px rgba(255,51,51,0.06)}
.acc-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.acc-indicator{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.acc-indicator.online{background:var(--green);box-shadow:0 0 10px rgba(0,230,118,.5);animation:acc-pulse 2s infinite}
.acc-indicator.offline{background:var(--surface3);border:1px solid var(--border2)}
@keyframes acc-pulse{0%,100%{box-shadow:0 0 6px rgba(0,230,118,.4)}50%{box-shadow:0 0 14px rgba(0,230,118,.7)}}
.acc-name-wrap .acc-name{font-weight:700;font-size:15px;margin-bottom:1px}
.acc-name-wrap .acc-id{font-size:10px;color:var(--muted);font-family:'Inter',monospace}
.acc-status-tag{margin-left:auto;font-size:9px;font-weight:800;padding:3px 9px;border-radius:10px;letter-spacing:.08em}
.acc-status-tag.on{background:rgba(0,230,118,.1);color:var(--green);border:1px solid rgba(0,230,118,.2)}
.acc-status-tag.off{background:var(--surface2);color:var(--muted);border:1px solid var(--border)}
.acc-numbers{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.acc-num{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:12px 8px;text-align:center}
.acc-num-val{font-size:19px;font-weight:800;line-height:1}
.acc-num-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-top:4px}
.acc-conv-wrap{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin-bottom:12px}
.acc-conv-header{display:flex;justify-content:space-between;align-items:center;font-size:11px;margin-bottom:8px}
.acc-conv-label{color:var(--muted);font-weight:600}
.acc-conv-pct{font-weight:800;font-size:13px}
.conv-bar{height:5px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;margin-bottom:6px}
.conv-fill{height:100%;border-radius:3px;transition:width .4s ease}
.acc-conv-detail{display:flex;justify-content:space-between;font-size:10px;color:var(--muted)}
.acc-sessions{margin-top:4px}
.acc-sessions summary{
  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);cursor:pointer;padding:8px 0;
  transition:color .2s;user-select:none;list-style:none;
  display:flex;align-items:center;gap:6px;
}
.acc-sessions summary::before{content:'\25B6';font-size:8px;transition:transform .2s}
.acc-sessions[open] summary::before{transform:rotate(90deg)}
.acc-sessions summary:hover{color:var(--text)}
.sess-list{margin-top:6px;display:flex;flex-direction:column;gap:0}
.sess-row{
  display:flex;align-items:center;gap:10px;
  padding:8px 0;border-top:1px solid var(--border);
  font-size:11px;color:var(--muted);
}
.sess-dur{font-family:'Inter',monospace;color:var(--text);font-weight:600;min-width:56px;font-size:12px}
.sess-chip{display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600;white-space:nowrap}
.chip-r{background:rgba(255,215,0,.1);color:var(--gold);border:1px solid rgba(255,215,0,.2)}
.chip-d{background:rgba(0,230,118,.08);color:var(--green);border:1px solid rgba(0,230,118,.15)}
.chip-p{background:rgba(255,255,255,.05);color:var(--muted);border:1px solid var(--border)}
.sess-date{margin-left:auto;font-size:10px;color:#444;white-space:nowrap}
.charts-grid{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px}
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:22px}
.chart-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:16px}
.chart-wrap{position:relative;height:200px}
.an-controls{display:flex;align-items:center;gap:10px;margin-left:auto}
.period-sel{
  padding:5px 12px;background:var(--surface2);border:1px solid var(--border);
  color:var(--text);border-radius:10px;font-size:11px;font-family:'Space Grotesk',sans-serif;
  cursor:pointer;outline:none;
}
.period-sel:focus{border-color:rgba(255,51,51,.3)}
.last-update{font-size:10px;color:var(--muted)}
.summary-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
.sum-item{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px;text-align:center}
.sum-val{font-size:24px;font-weight:800;line-height:1;margin-bottom:4px}
.sum-lbl{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.footer{
  text-align:center;padding:32px 24px;
  font-size:11px;color:var(--muted);
  border-top:1px solid var(--border);
  margin-top:8px;
}
.footer strong{color:var(--red)}
@media(max-width:900px){
  .charts-grid{grid-template-columns:1fr}
  .summary-grid{grid-template-columns:repeat(3,1fr)}
}
@media(max-width:640px){
  .wrap{padding:16px}
  .hero{padding:20px}
  .hero-row{flex-direction:column;align-items:flex-start}
  .hero-status{margin-left:0;align-items:flex-start}
  .stats{grid-template-columns:repeat(2,1fr)}
  .acc-grid{grid-template-columns:1fr}
  .summary-grid{grid-template-columns:repeat(2,1fr)}
  .hdr{padding:0 16px}
  .brand span{display:none}
}
</style></head><body>

<div class="hdr">
  <div class="brand">
    <div class="brand-rs">R$</div>
    <span>PD AutoFarm</span>
  </div>
  <div class="hdr-badge">LIVE DASHBOARD</div>
  <div class="hdr-right">
    <span class="hdr-time">{{ now_str }}</span>
  </div>
</div>

<div class="wrap">

  <div class="hero">
    <div class="hero-row">
      <div class="hero-avatar">{{ lic.roblox_name[:1]|upper if lic.roblox_name else '?' }}</div>
      <div class="hero-info">
        <h2>{{ lic.roblox_name or 'Not linked' }}</h2>
        <p>Roblox UID: {{ lic.roblox_user_id or '&mdash;' }}{% if user and user.tg_username %} &nbsp;&middot;&nbsp; Telegram: @{{ user.tg_username }}{% endif %}</p>
      </div>
      <div class="hero-status">
        {% if lic.status == 'active' and lic.key_type == 'trial' %}
          <span class="status-pill s-trial">TRIAL &nbsp;{{ trial_left }}</span>
        {% elif lic.status == 'active' %}
          <span class="status-pill s-active">ACTIVE</span>
        {% else %}
          <span class="status-pill s-expired">{{ lic.status|upper }}</span>
        {% endif %}
        <div class="hero-key">
          <span class="key-badge">{{ lic.key_type|upper }}</span>
          <span>{{ lic.key[:4] }}&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;</span>
        </div>
      </div>
    </div>
    {% if lic.status == 'active' and lic.key_type == 'trial' %}
    <div class="trial-bar">
      <p>Trial time remaining: {{ trial_left }}</p>
    </div>
    {% endif %}
  </div>

  <div class="stats">
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,var(--gold),transparent)"></div>
      <div class="stat-label">Total R$</div>
      <div class="stat-val c-gold" id="stat-robux">{{ total_robux_alltime }}</div>
      <div class="stat-sub">all time</div>
    </div>
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,var(--green),transparent)"></div>
      <div class="stat-label">Net R$ (60%)</div>
      <div class="stat-val c-green" id="stat-net">{{ net_robux }}</div>
      <div class="stat-sub">after Roblox cut</div>
    </div>
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,var(--red),transparent)"></div>
      <div class="stat-label">Donations</div>
      <div class="stat-val c-red" id="stat-donations">{{ total_donations }}</div>
      <div class="stat-sub">total received</div>
    </div>
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,var(--yellow),transparent)"></div>
      <div class="stat-label">Session R$</div>
      <div class="stat-val c-yellow" id="stat-session">{{ session_robux }}</div>
      <div class="stat-sub">current session</div>
    </div>
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,var(--orange),transparent)"></div>
      <div class="stat-label">Booth R$</div>
      <div class="stat-val c-orange" id="stat-booth">{{ total_booth }}</div>
      <div class="stat-sub">currently raised</div>
    </div>
    <div class="stat">
      <div class="stat-accent" style="background:linear-gradient(90deg,#a78bfa,transparent)"></div>
      <div class="stat-label">Approached</div>
      <div class="stat-val c-text" id="stat-approached">{{ total_approached }}</div>
      <div class="stat-sub">
        <span id="stat-agreed" style="color:var(--green)">{{ total_agreed }}</span> agreed &nbsp;&middot;&nbsp;
        <span id="stat-conv">{{ conv_rate }}%</span>
      </div>
    </div>
  </div>

  <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px;padding:12px 18px;background:var(--surface);border:1px solid var(--border);border-radius:14px">
    <div style="width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse-live 1.5s infinite;flex-shrink:0"></div>
    <span style="font-size:12px;font-weight:700;color:var(--text)"><span id="stat-online">{{ online_count }}</span> / {{ accounts|length }} accounts online</span>
  </div>

  {% if accounts %}
  <div class="section">
    <div class="section-hdr">
      <span class="section-title">Accounts</span>
      <span class="section-badge">{{ accounts|length }}</span>
    </div>
    <div class="acc-grid">
    {% for acc in accounts %}
      {% set acc_approached = (acc.approached_alltime or 0) + (acc.approached or 0) %}
      {% set acc_agreed = (acc.agreed_alltime or 0) + (acc.agreed or 0) %}
      {% set acc_refused = (acc.refused_alltime or 0) + (acc.refused or 0) %}
      {% set acc_noresp = (acc.no_response_alltime or 0) + (acc.no_response or 0) %}
      {% set acc_conv = (acc_agreed * 100 // acc_approached) if acc_approached else 0 %}
      <div class="acc-card">
        <div class="acc-head">
          <div class="acc-indicator {{ 'online' if acc._online else 'offline' }}"></div>
          <div class="acc-name-wrap">
            <div class="acc-name">{{ acc.name or 'No name' }}</div>
            <div class="acc-id">ID: {{ acc.id }}</div>
          </div>
          <div class="acc-status-tag {{ 'on' if acc._online else 'off' }}">{{ 'ONLINE' if acc._online else 'OFFLINE' }}</div>
        </div>
        <div class="acc-numbers">
          <div class="acc-num">
            <div class="acc-num-val c-gold">{{ (acc.robux_alltime or 0) + (acc.robux_gross or 0) }}</div>
            <div class="acc-num-lbl">Gross R$</div>
          </div>
          <div class="acc-num">
            <div class="acc-num-val c-green">{{ ((acc.robux_alltime or 0) + (acc.robux_gross or 0)) * 6 // 10 }}</div>
            <div class="acc-num-lbl">Net R$</div>
          </div>
          <div class="acc-num">
            <div class="acc-num-val c-yellow">{{ acc.raised_current or 0 }}</div>
            <div class="acc-num-lbl">Booth R$</div>
          </div>
          <div class="acc-num">
            <div class="acc-num-val c-red">{{ (acc.donations_alltime or 0) + (acc.donations or 0) }}</div>
            <div class="acc-num-lbl">Donations</div>
          </div>
          <div class="acc-num">
            <div class="acc-num-val" style="color:#a78bfa">{{ acc_approached }}</div>
            <div class="acc-num-lbl">Approached</div>
          </div>
          <div class="acc-num">
            <div class="acc-num-val {{ 'c-green' if acc_conv >= 30 else 'c-yellow' if acc_conv >= 15 else 'c-red' }}">{{ acc_conv }}%</div>
            <div class="acc-num-lbl">Conv.</div>
          </div>
        </div>
        <div class="acc-conv-wrap">
          <div class="acc-conv-header">
            <span class="acc-conv-label">Conversion rate</span>
            <span class="acc-conv-pct {{ 'c-green' if acc_conv >= 30 else 'c-yellow' if acc_conv >= 15 else 'c-red' }}">{{ acc_conv }}%</span>
          </div>
          <div class="conv-bar">
            <div class="conv-fill" style="width:{{ [acc_conv,100]|min }}%;background:{{ 'var(--green)' if acc_conv >= 30 else 'var(--yellow)' if acc_conv >= 15 else 'var(--red)' }}"></div>
          </div>
          <div class="acc-conv-detail">
            <span>{{ acc_agreed }} agreed</span>
            <span>{{ acc_refused }} refused</span>
            <span>{{ acc_noresp }} no resp.</span>
          </div>
        </div>
        {% if acc.sessions %}
        <details class="acc-sessions">
          <summary>Sessions ({{ acc.sessions|length }})</summary>
          <div class="sess-list">
            {% for s in acc.sessions %}
            <div class="sess-row">
              <span class="sess-dur">{{ s._dur_str }}</span>
              <span class="sess-chip chip-r">R${{ s.robux_gross or 0 }}</span>
              <span class="sess-chip chip-d">{{ s.donations or 0 }} don.</span>
              <span class="sess-chip chip-p">{{ s.approached or 0 }} appr.</span>
              <span class="sess-date">{{ s._date_str }}</span>
            </div>
            {% endfor %}
          </div>
        </details>
        {% endif %}
      </div>
    {% endfor %}
    </div>
  </div>
  {% endif %}

  <div class="section">
    <div class="section-hdr">
      <span class="section-title">Analytics</span>
      <div class="an-controls">
        <select id="period-sel" class="period-sel" onchange="loadAnalytics()">
          <option value="24">24 hours</option>
          <option value="48">48 hours</option>
          <option value="168">7 days</option>
        </select>
        <span class="last-update" id="last-update">loading...</span>
      </div>
    </div>
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-title">Interactions by hour</div>
        <div class="chart-wrap"><canvas id="chart-hours"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Results breakdown</div>
        <div class="chart-wrap"><canvas id="chart-results"></canvas></div>
      </div>
    </div>
    <div class="chart-card" style="margin-bottom:16px">
      <div class="chart-title">Conversion % over time</div>
      <div style="position:relative;height:140px"><canvas id="chart-conv"></canvas></div>
    </div>
    <div class="summary-grid">
      <div class="sum-item"><div class="sum-val c-green" id="sum-agreed">&mdash;</div><div class="sum-lbl">Agreed</div></div>
      <div class="sum-item"><div class="sum-val c-red" id="sum-refused">&mdash;</div><div class="sum-lbl">Refused</div></div>
      <div class="sum-item"><div class="sum-val c-yellow" id="sum-noresp">&mdash;</div><div class="sum-lbl">No response</div></div>
      <div class="sum-item"><div class="sum-val" id="sum-total" style="color:#a78bfa">&mdash;</div><div class="sum-lbl">Total events</div></div>
      <div class="sum-item"><div class="sum-val" id="sum-conv" style="color:var(--text)">&mdash;</div><div class="sum-lbl">Conversion</div></div>
      <div class="sum-item"><div class="sum-val c-gold" id="sum-robux">&mdash;</div><div class="sum-lbl">R$ in period</div></div>
    </div>
  </div>

</div>

<div class="footer">
  <strong>PD AutoFarm</strong> &nbsp;&bull;&nbsp; Auto-farming Robux since 2024 &nbsp;&bull;&nbsp; Live updates every 30s
</div>

<script>
(function(){
  const TOKEN = new URLSearchParams(window.location.search).get('token');
  if(!TOKEN) return;

  const chartDefaults = {
    responsive:true,
    maintainAspectRatio:false,
    plugins:{
      legend:{labels:{color:'#6b6b80',font:{size:10,family:"'Space Grotesk', sans-serif"},boxWidth:10,padding:12}}
    },
    scales:{
      x:{ticks:{color:'#6b6b80',font:{size:9},maxRotation:45},grid:{color:'rgba(255,255,255,0.04)'}},
      y:{ticks:{color:'#6b6b80',font:{size:10}},grid:{color:'rgba(255,255,255,0.04)'}}
    }
  };

  let cH=null, cR=null, cC=null;

  function loadAnalytics(){
    const hours = document.getElementById('period-sel').value;
    fetch('/dashboard/api/stats?token='+encodeURIComponent(TOKEN)+'&hours='+hours)
      .then(r=>r.ok?r.json():null)
      .then(d=>{
        if(!d) return;

        const map = {
          'stat-robux':d.robux,'stat-net':d.net,'stat-donations':d.donations,
          'stat-session':d.session_r,'stat-booth':d.booth,
          'stat-approached':d.approached,'stat-agreed':d.agreed,
          'stat-conv':(d.conv!==undefined?d.conv+'%':undefined),'stat-online':d.online
        };
        for(const[id,val] of Object.entries(map)){
          const el=document.getElementById(id);
          if(el&&val!==undefined) el.textContent=val;
        }

        const h=d.hours||[];
        if(!h.length){document.getElementById('last-update').textContent='No data';return;}
        const labels=h.map(x=>x.hour_label||x.hour||'');
        const agreed=h.map(x=>x.agreed||0);
        const refused=h.map(x=>x.refused||0);
        const noResp=h.map(x=>x.no_response||0);
        const robuxH=h.map(x=>x.robux_gross||0);
        const conv=h.map(x=>{
          const tot=(x.agreed||0)+(x.refused||0)+(x.no_response||0);
          return tot?Math.round((x.agreed||0)*100/tot):0;
        });
        const tA=agreed.reduce((s,v)=>s+v,0);
        const tR=refused.reduce((s,v)=>s+v,0);
        const tN=noResp.reduce((s,v)=>s+v,0);

        if(typeof Chart==='undefined') return;

        if(cH) cH.destroy();
        cH=new Chart(document.getElementById('chart-hours'),{type:'bar',data:{labels,datasets:[
          {label:'Agreed',data:agreed,backgroundColor:'rgba(0,230,118,.45)',borderColor:'rgba(0,230,118,.8)',borderWidth:1},
          {label:'Refused',data:refused,backgroundColor:'rgba(255,51,51,.4)',borderColor:'rgba(255,51,51,.8)',borderWidth:1},
          {label:'No resp',data:noResp,backgroundColor:'rgba(255,179,0,.38)',borderColor:'rgba(255,179,0,.8)',borderWidth:1},
        ]},options:{...chartDefaults,scales:{
          x:{...chartDefaults.scales.x,stacked:true},
          y:{...chartDefaults.scales.y,stacked:true}
        }}});

        if(cR) cR.destroy();
        cR=new Chart(document.getElementById('chart-results'),{type:'doughnut',data:{
          labels:['Agreed','Refused','No response'],
          datasets:[{
            data:[tA,tR,tN],
            backgroundColor:['rgba(0,230,118,.6)','rgba(255,51,51,.6)','rgba(255,179,0,.5)'],
            borderColor:['rgba(0,230,118,.9)','rgba(255,51,51,.9)','rgba(255,179,0,.9)'],
            borderWidth:1,hoverOffset:4
          }]
        },options:{
          responsive:true,maintainAspectRatio:false,cutout:'65%',
          plugins:{legend:{position:'bottom',labels:{color:'#6b6b80',font:{size:10},boxWidth:10,padding:10}}}
        }});

        if(cC) cC.destroy();
        cC=new Chart(document.getElementById('chart-conv'),{type:'line',data:{labels,datasets:[
          {
            label:'Conv %',data:conv,
            borderColor:'rgba(255,51,51,.8)',backgroundColor:'rgba(255,51,51,.07)',
            fill:true,tension:.38,pointRadius:2,pointBackgroundColor:'rgba(255,51,51,.9)'
          }
        ]},options:{...chartDefaults,scales:{
          x:chartDefaults.scales.x,
          y:{...chartDefaults.scales.y,min:0,max:100}
        }}});

        const tConv=tA+tR+tN?Math.round(tA*100/(tA+tR+tN)):0;
        const convEl=document.getElementById('sum-conv');
        convEl.textContent=tConv+'%';
        convEl.style.color=tConv>=30?'var(--green)':tConv>=15?'var(--yellow)':'var(--red)';
        document.getElementById('sum-agreed').textContent=tA;
        document.getElementById('sum-refused').textContent=tR;
        document.getElementById('sum-noresp').textContent=tN;
        document.getElementById('sum-total').textContent=tA+tR+tN;
        document.getElementById('sum-robux').textContent=d.stats?d.stats.robux_period||0:robuxH.reduce((s,v)=>s+v,0);
        const now=new Date();
        document.getElementById('last-update').textContent='updated '+now.getHours()+':'+String(now.getMinutes()).padStart(2,'0');
      }).catch(()=>{});
  }

  loadAnalytics();
  setInterval(loadAnalytics,30000);
})();
</script>
</body></html>"""


@app.route("/dashboard")
def user_dashboard():
    ip = _real_ip()
    if not _rl_check(ip):
        return Response("Too many requests", status=429)

    token = request.args.get("token", "").strip()
    if not token:
        _rl_fail(ip)
        return Response("Ссылка недействительна. Получи новую через бота: /dashboard",
                        status=400, content_type="text/plain; charset=utf-8")

    key = db_v2.validate_dashboard_token(token)
    if not key:
        _rl_fail(ip)
        return Response("Ссылка истекла или недействительна. Получи новую через бота: /dashboard",
                        status=403, content_type="text/plain; charset=utf-8")

    data = db_v2.get_user_dashboard_data(key)
    if not data:
        return Response("Ключ не найден", status=404,
                        content_type="text/plain; charset=utf-8")

    lic = data["license"]
    if not db_v2.is_key_valid(lic):
        return Response("Ключ недействителен", status=403,
                        content_type="text/plain; charset=utf-8")

    accounts = data["accounts"]
    now = time.time()
    cutoff = now - 35

    # Prep account data
    total_robux_alltime = 0
    total_donations = 0
    total_approached = 0
    total_agreed = 0
    session_robux = 0
    total_booth = 0
    online_count = 0

    for acc in accounts:
        acc["_online"] = (acc.get("last_seen") or 0) > cutoff
        if acc["_online"]:
            online_count += 1
        total_robux_alltime += (acc.get("robux_alltime") or 0) + (acc.get("robux_gross") or 0)
        total_donations += (acc.get("donations_alltime") or 0) + (acc.get("donations") or 0)
        total_approached += (acc.get("approached_alltime") or 0) + (acc.get("approached") or 0)
        total_agreed += (acc.get("agreed_alltime") or 0) + (acc.get("agreed") or 0)
        session_robux += acc.get("robux_gross") or 0
        total_booth += acc.get("raised_current") or 0

        for s in acc.get("sessions", []):
            dur = s.get("duration") or 0
            h, m = int(dur) // 3600, (int(dur) % 3600) // 60
            s["_dur_str"] = f"{h}ч {m}м" if h else f"{m}м"
            s["_date_str"] = time.strftime("%d.%m %H:%M",
                                           time.localtime(s["started_at"])) if s.get("started_at") else "—"

    conv_rate = (total_agreed * 100 // total_approached) if total_approached else 0
    net_robux = int(total_robux_alltime * 0.6)

    trial_left = ""
    if lic.get("key_type") == "trial" and lic.get("expires_at"):
        rem = max(0, lic["expires_at"] - now)
        trial_left = f"{int(rem // 3600)}ч {int((rem % 3600) // 60)}м"

    now_str = time.strftime("%d.%m.%Y %H:%M:%S")

    return render_template_string(
        _USER_DASH_HTML,
        lic=lic, user=data["user"], accounts=accounts,
        total_robux_alltime=total_robux_alltime, net_robux=net_robux,
        total_donations=total_donations, session_robux=session_robux, total_booth=total_booth,
        total_approached=total_approached, total_agreed=total_agreed,
        conv_rate=conv_rate, online_count=online_count,
        trial_left=trial_left, now_str=now_str,
    )


@app.route("/dashboard/api/stats")
def dashboard_api_stats():
    token = request.args.get("token", "").strip()
    if not token:
        return Response("", status=400)
    key = db_v2.validate_dashboard_token(token)
    if not key:
        return Response("", status=403)
    hours = max(1, min(int(request.args.get("hours", 24)), 168))
    now = time.time()
    cutoff = now - hours * 3600
    hourly = db_v2.get_hourly_analytics(cutoff, license_key=key)
    data = db_v2.get_user_dashboard_data(key)
    stats = {}
    if data:
        accounts = data["accounts"]
        cutoff35 = now - 35
        stats = {
            "online": sum(1 for a in accounts if (a.get("last_seen") or 0) > cutoff35),
            "robux_alltime": sum((a.get("robux_alltime") or 0) + (a.get("robux_gross") or 0) for a in accounts),
            "donations": sum((a.get("donations_alltime") or 0) + (a.get("donations") or 0) for a in accounts),
            "approached": sum((a.get("approached_alltime") or 0) + (a.get("approached") or 0) for a in accounts),
            "agreed": sum((a.get("agreed_alltime") or 0) + (a.get("agreed") or 0) for a in accounts),
            "session_robux": sum(a.get("robux_gross") or 0 for a in accounts),
            "booth": sum(a.get("raised_current") or 0 for a in accounts),
        }
        total_a = stats["approached"]
        stats["conv_rate"] = (stats["agreed"] * 100 // total_a) if total_a else 0
        stats["net_robux"] = int(stats["robux_alltime"] * 0.6)
        stats["robux_period"] = stats["session_robux"]
    return jsonify({"hours": hourly, "stats": stats})


if __name__ == "__main__":
    db_v2.init_db()

    # Спасти незакрытые робуксы от предыдущего запуска (перенести в alltime)
    db_v2.salvage_all_orphaned()

    # Закрыть зависшие сессии от предыдущего запуска
    stale = db_v2.close_stale_sessions()
    if stale:
        print(f"[v2] Закрыто {stale} зависших сессий после перезапуска")

    # Заголовок в лог-файле
    with _log_lock:
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(
                    f"\n{'═' * 60}\n"
                    f"  СЕРВЕР ЗАПУЩЕН: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    f"  (порт {API_PORT})\n"
                    f"{'═' * 60}\n"
                )
        except Exception:
            pass

    print(f"[v2] API запущен на порту {API_PORT}")
    print(f"[v2] Лог сессий: {_LOG_PATH}")
    app.run(host="0.0.0.0", port=API_PORT, debug=False)
