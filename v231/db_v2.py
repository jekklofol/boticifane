import sqlite3, time, uuid, os, threading, secrets, hashlib

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "farm_data_v2.db")
_lock   = threading.Lock()


def _con():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock:
        con = _con()
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id       INTEGER PRIMARY KEY,
                tg_username TEXT,
                tg_name     TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  REAL,
                approved_at REAL,
                referred_by INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id                 INTEGER,
                friend1               TEXT,
                friend2               TEXT,
                friend3               TEXT,
                yt_screenshot         TEXT,
                yt_like_screenshot    TEXT,
                yt_comment_screenshot TEXT,
                status                TEXT DEFAULT 'pending',
                admin_note            TEXT,
                submitted_at          REAL,
                reviewed_at           REAL
            );

            CREATE TABLE IF NOT EXISTS licenses (
                key             TEXT PRIMARY KEY,
                tg_id           INTEGER,
                roblox_user_id  TEXT DEFAULT NULL,
                roblox_name     TEXT DEFAULT NULL,
                status          TEXT DEFAULT 'active',
                activated_at    REAL DEFAULT NULL,
                created_at      REAL,
                last_used       REAL,
                key_type        TEXT DEFAULT 'lifetime',
                expires_at      REAL DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS pd_accounts_v2 (
                id                TEXT PRIMARY KEY,
                license_key       TEXT,
                name              TEXT DEFAULT '',
                approached        INTEGER DEFAULT 0,
                agreed            INTEGER DEFAULT 0,
                refused           INTEGER DEFAULT 0,
                no_response       INTEGER DEFAULT 0,
                hops              INTEGER DEFAULT 0,
                donations         INTEGER DEFAULT 0,
                robux_gross       INTEGER DEFAULT 0,
                raised_current    INTEGER DEFAULT 0,
                last_seen         REAL DEFAULT 0,
                session_start     REAL DEFAULT 0,
                created_at        REAL DEFAULT 0,
                status            TEXT DEFAULT 'Offline',
                robux_alltime        INTEGER DEFAULT 0,
                donations_alltime    INTEGER DEFAULT 0,
                approached_alltime   INTEGER DEFAULT 0,
                agreed_alltime       INTEGER DEFAULT 0,
                refused_alltime      INTEGER DEFAULT 0,
                no_response_alltime  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pd_sessions_v2 (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  TEXT    NOT NULL,
                started_at  REAL    NOT NULL DEFAULT 0,
                ended_at    REAL    DEFAULT NULL,
                duration    REAL    DEFAULT NULL,
                approached  INTEGER DEFAULT 0,
                agreed      INTEGER DEFAULT 0,
                refused     INTEGER DEFAULT 0,
                no_response INTEGER DEFAULT 0,
                donations   INTEGER DEFAULT 0,
                robux_gross INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_pd_sess_acc
                ON pd_sessions_v2(account_id, started_at);
        """)
        con.commit()

        # ── Migration: add alltime columns if missing ──────────────────────
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(pd_accounts_v2)")}
        if "robux_alltime" not in existing_cols:
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN robux_alltime     INTEGER DEFAULT 0")
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN donations_alltime INTEGER DEFAULT 0")
            con.execute("""
                UPDATE pd_accounts_v2 SET
                    robux_alltime     = (
                        SELECT COALESCE(SUM(robux_gross), 0)
                        FROM pd_sessions_v2
                        WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL
                    ),
                    donations_alltime = (
                        SELECT COALESCE(SUM(donations), 0)
                        FROM pd_sessions_v2
                        WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL
                    )
            """)
            con.commit()

        if "approached_alltime" not in existing_cols:
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN approached_alltime  INTEGER DEFAULT 0")
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN agreed_alltime       INTEGER DEFAULT 0")
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN refused_alltime      INTEGER DEFAULT 0")
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN no_response_alltime  INTEGER DEFAULT 0")
            con.execute("""
                UPDATE pd_accounts_v2 SET
                    approached_alltime  = (SELECT COALESCE(SUM(approached),  0) FROM pd_sessions_v2 WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL),
                    agreed_alltime      = (SELECT COALESCE(SUM(agreed),      0) FROM pd_sessions_v2 WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL),
                    refused_alltime     = (SELECT COALESCE(SUM(refused),     0) FROM pd_sessions_v2 WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL),
                    no_response_alltime = (SELECT COALESCE(SUM(no_response), 0) FROM pd_sessions_v2 WHERE account_id = pd_accounts_v2.id AND ended_at IS NOT NULL)
            """)
            con.commit()

        if "hops" not in existing_cols:
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN hops           INTEGER DEFAULT 0")
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN raised_current INTEGER DEFAULT 0")
            con.commit()

        # ── Migration: referral system ──────────────────────────────────────
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "referred_by" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
            con.commit()
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "ref_balance" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN ref_balance INTEGER DEFAULT 0")
            con.commit()

        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "expires_at" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN expires_at REAL DEFAULT NULL")
            con.execute("ALTER TABLE licenses ADD COLUMN key_type TEXT DEFAULT 'lifetime'")
            # Wipe all existing keys — migration to new referral system
            con.execute("DELETE FROM licenses")
            con.execute("UPDATE users SET status = 'pending'")
            con.commit()

        # ── Migration: HWID binding ──────────────────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "hwid" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN hwid TEXT DEFAULT NULL")
            con.commit()

        # ── Migration: IP tracking ───────────────────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "bound_ip" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN bound_ip TEXT DEFAULT NULL")
            con.execute("ALTER TABLE licenses ADD COLUMN ip_violations INTEGER DEFAULT 0")
            con.commit()

        # ── Migration: admin notes / warnings ────────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "admin_notes" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN admin_notes TEXT DEFAULT ''")
            con.execute("ALTER TABLE licenses ADD COLUMN warnings INTEGER DEFAULT 0")
            con.commit()

        # ── Dashboard tokens ─────────────────────────────────────────────────
        con.executescript("""
            CREATE TABLE IF NOT EXISTS dashboard_tokens (
                token       TEXT PRIMARY KEY,
                license_key TEXT NOT NULL,
                created_at  REAL NOT NULL,
                expires_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ref_tokens (
                token      TEXT PRIMARY KEY,
                tg_id      INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interaction_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key  TEXT NOT NULL,
                uid          TEXT NOT NULL,
                account_name TEXT,
                target_name  TEXT,
                action       TEXT NOT NULL,
                message      TEXT,
                event        TEXT,
                created_at   REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ilog_key_ts
                ON interaction_log (license_key, created_at DESC);
        """)
        con.commit()

        con.execute("""
            CREATE TABLE IF NOT EXISTS payout_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id       INTEGER NOT NULL,
                tg_username TEXT DEFAULT '',
                tg_name     TEXT DEFAULT '',
                amount      INTEGER NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  REAL NOT NULL,
                resolved_at REAL DEFAULT NULL,
                admin_note  TEXT DEFAULT ''
            )
        """)
        con.commit()

        con.execute("""
            CREATE TABLE IF NOT EXISTS approved_ips (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key  TEXT NOT NULL,
                ip           TEXT NOT NULL,
                label        TEXT DEFAULT '',
                approved_at  REAL NOT NULL,
                UNIQUE(license_key, ip)
            )
        """)
        con.commit()

        # ── Migration: interaction_log.player_reply ──────────────────────────
        try:
            ilog_cols = {row[1] for row in con.execute("PRAGMA table_info(interaction_log)")}
            if ilog_cols and "player_reply" not in ilog_cols:
                con.execute("ALTER TABLE interaction_log ADD COLUMN player_reply TEXT DEFAULT ''")
                con.commit()
        except Exception:
            pass

        # ── Migration: licenses.resp_secret ──────────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "resp_secret" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN resp_secret TEXT DEFAULT NULL")
            con.commit()

        # ── Migration: clear old HWID values (switching to DeviceId binding) ─
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "device_id_migrated" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN device_id_migrated INTEGER DEFAULT 0")
            con.execute("UPDATE licenses SET hwid = NULL, device_id_migrated = 1")
            con.commit()

        # ── Migration: allowed_accounts table ───────────────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS allowed_accounts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key  TEXT NOT NULL,
                roblox_uid   TEXT NOT NULL,
                roblox_name  TEXT DEFAULT '',
                status       TEXT DEFAULT 'allowed',
                added_at     REAL NOT NULL,
                UNIQUE(license_key, roblox_uid)
            )
        """)
        con.commit()

        # ── Migration: seed allowed_accounts from existing pd_accounts_v2 ──
        seeded = con.execute("SELECT COUNT(*) FROM allowed_accounts").fetchone()[0]
        if seeded == 0:
            existing_accs = con.execute(
                "SELECT DISTINCT id, license_key, name FROM pd_accounts_v2 WHERE license_key IS NOT NULL AND license_key != ''"
            ).fetchall()
            for row in existing_accs:
                con.execute(
                    "INSERT OR IGNORE INTO allowed_accounts (license_key, roblox_uid, roblox_name, status, added_at) VALUES (?, ?, ?, 'allowed', ?)",
                    (row["license_key"], row["id"], row["name"] or "", time.time()))
            if existing_accs:
                con.commit()
                print(f"[DB] Migrated {len(existing_accs)} existing accounts to allowed_accounts")

        # ── Migration: max_accounts on licenses ────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "max_accounts" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN max_accounts INTEGER DEFAULT 5")
            con.commit()

        # ── Discord tables ──────────────────────────────────────────────────
        con.executescript("""
            CREATE TABLE IF NOT EXISTS dc_users (
                dc_id       INTEGER PRIMARY KEY,
                dc_username TEXT DEFAULT '',
                dc_name     TEXT DEFAULT '',
                referred_by INTEGER DEFAULT NULL,
                created_at  REAL,
                ref_balance INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS dc_invites (
                invite_code TEXT PRIMARY KEY,
                dc_id       INTEGER NOT NULL,
                uses        INTEGER DEFAULT 0,
                created_at  REAL NOT NULL
            );
        """)
        con.commit()

        # ── Migration: licenses.dc_id ───────────────────────────────────────
        existing_lic_cols = {row[1] for row in con.execute("PRAGMA table_info(licenses)")}
        if "dc_id" not in existing_lic_cols:
            con.execute("ALTER TABLE licenses ADD COLUMN dc_id INTEGER DEFAULT NULL")
            con.commit()

        # ── Migration: payout_requests.dc_id ───────────────────────────────
        existing_pr_cols = {row[1] for row in con.execute("PRAGMA table_info(payout_requests)")}
        if "dc_id" not in existing_pr_cols:
            con.execute("ALTER TABLE payout_requests ADD COLUMN dc_id INTEGER DEFAULT NULL")
            con.execute("ALTER TABLE payout_requests ADD COLUMN dc_username TEXT DEFAULT ''")
            con.commit()

        con.close()


# ── Users ──────────────────────────────────────────────────────────────────

def upsert_user(tg_id: int, username: str, name: str):
    with _lock:
        con = _con()
        con.execute("""
            INSERT INTO users (tg_id, tg_username, tg_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                tg_username = excluded.tg_username,
                tg_name     = excluded.tg_name
        """, (tg_id, username, name, time.time()))
        con.commit()
        con.close()


def get_user(tg_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        con.close()
        return dict(row) if row else None


def set_user_status(tg_id: int, status: str):
    with _lock:
        con = _con()
        con.execute("UPDATE users SET status = ? WHERE tg_id = ?", (status, tg_id))
        con.commit()
        con.close()


def get_all_users(limit=50, offset=0) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def count_users() -> int:
    with _lock:
        con = _con()
        n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        con.close()
        return n


# ── Applications ───────────────────────────────────────────────────────────

def create_application(tg_id, friend1, friend2, friend3,
                        yt_ss, yt_like_ss, yt_comment_ss) -> int:
    with _lock:
        con = _con()
        cur = con.execute("""
            INSERT INTO applications
                (tg_id, friend1, friend2, friend3,
                 yt_screenshot, yt_like_screenshot, yt_comment_screenshot,
                 submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (tg_id, friend1, friend2, friend3,
               yt_ss, yt_like_ss, yt_comment_ss, time.time()))
        app_id = cur.lastrowid
        con.commit()
        con.close()
        return app_id


def get_pending_applications() -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM applications WHERE status = 'pending' ORDER BY submitted_at ASC"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def get_application(app_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        con.close()
        return dict(row) if row else None


def get_user_application(tg_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM applications WHERE tg_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (tg_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None


def approve_application(app_id: int, note: str = "") -> str:
    """Approve application, generate license key, return key."""
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    with _lock:
        con = _con()
        app = con.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not app:
            con.close()
            raise ValueError("Application not found")
        con.execute("""
            UPDATE applications SET status = 'approved', admin_note = ?, reviewed_at = ?
            WHERE id = ?
        """, (note, time.time(), app_id))
        con.execute("UPDATE users SET status = 'approved', approved_at = ? WHERE tg_id = ?",
                    (time.time(), app["tg_id"]))
        con.execute("""
            INSERT INTO licenses (key, tg_id, created_at, last_used)
            VALUES (?, ?, ?, ?)
        """, (key, app["tg_id"], time.time(), time.time()))
        con.commit()
        con.close()
    return key


def reject_application(app_id: int, note: str):
    with _lock:
        con = _con()
        app = con.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not app:
            con.close()
            raise ValueError("Application not found")
        con.execute("""
            UPDATE applications SET status = 'rejected', admin_note = ?, reviewed_at = ?
            WHERE id = ?
        """, (note, time.time(), app_id))
        con.execute("UPDATE users SET status = 'rejected' WHERE tg_id = ?", (app["tg_id"],))
        con.commit()
        con.close()


def count_pending_applications() -> int:
    with _lock:
        con = _con()
        n = con.execute("SELECT COUNT(*) FROM applications WHERE status = 'pending'").fetchone()[0]
        con.close()
        return n


# ── Licenses ───────────────────────────────────────────────────────────────

def get_license(key: str) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
        con.close()
        return dict(row) if row else None


def get_resp_secret(key: str) -> str:
    with _lock:
        con = _con()
        row = con.execute("SELECT resp_secret FROM licenses WHERE key = ?", (key,)).fetchone()
        con.close()
        return (row[0] or "") if row else ""


def set_resp_secret(key: str, secret: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET resp_secret = ? WHERE key = ?", (secret, key))
        con.commit()
        con.close()


def get_license_by_tg(tg_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM licenses WHERE tg_id = ? ORDER BY created_at DESC LIMIT 1",
            (tg_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None


def bind_license(key: str, roblox_user_id: str, roblox_name: str):
    with _lock:
        con = _con()
        con.execute("""
            UPDATE licenses SET roblox_user_id = ?, roblox_name = ?, activated_at = ?, last_used = ?
            WHERE key = ?
        """, (roblox_user_id, roblox_name, time.time(), time.time(), key))
        con.commit()
        con.close()


def bind_hwid(key: str, hwid: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET hwid = ? WHERE key = ?", (hwid, key))
        con.commit()
        con.close()


def bind_ip(key: str, ip: str):
    """Store the /24 subnet of first IP."""
    subnet = ".".join(ip.split(".")[:3]) if "." in ip else ip
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET bound_ip = ? WHERE key = ?", (subnet, key))
        con.commit()
        con.close()
    approve_ip(key, ip, "первый запуск")


def check_ip(key: str, ip: str) -> tuple[bool, int]:
    """Check if IP is in approved list. Returns (ok, violation_count)."""
    with _lock:
        con = _con()
        # Check approved_ips table
        approved = con.execute(
            "SELECT 1 FROM approved_ips WHERE license_key = ? AND ip = ?",
            (key, ip)).fetchone()
        if approved:
            con.close()
            return True, 0
        # Also check by subnet
        subnet = ".".join(ip.split(".")[:3]) if "." in ip else ip
        approved_sub = con.execute(
            "SELECT 1 FROM approved_ips WHERE license_key = ? AND ip LIKE ?",
            (key, subnet + "%")).fetchone()
        if approved_sub:
            con.close()
            return True, 0
        # Not approved — increment violation counter
        row = con.execute("SELECT ip_violations FROM licenses WHERE key = ?", (key,)).fetchone()
        new_count = ((row["ip_violations"] or 0) if row else 0) + 1
        con.execute("UPDATE licenses SET ip_violations = ? WHERE key = ?", (new_count, key))
        con.commit()
        con.close()
        return False, new_count


def approve_ip(key: str, ip: str, label: str = ""):
    """Add IP to approved list for a key."""
    with _lock:
        con = _con()
        con.execute(
            "INSERT OR IGNORE INTO approved_ips (license_key, ip, label, approved_at) VALUES (?, ?, ?, ?)",
            (key, ip, label, time.time()))
        con.commit()
        con.close()


def revoke_ip(key: str, ip: str):
    """Remove IP from approved list."""
    with _lock:
        con = _con()
        con.execute("DELETE FROM approved_ips WHERE license_key = ? AND ip = ?", (key, ip))
        con.commit()
        con.close()


def get_approved_ips(key: str) -> list[dict]:
    """Get all approved IPs for a key."""
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM approved_ips WHERE license_key = ? ORDER BY approved_at",
            (key,)).fetchall()
        con.close()
    return [dict(r) for r in rows]


def reset_ip_violations(key: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET ip_violations = 0 WHERE key = ?", (key,))
        con.commit()
        con.close()


def get_pending_ips() -> list[dict]:
    """Get keys with unapproved IP violations (for admin review)."""
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT l.key, l.roblox_name, l.bound_ip, l.ip_violations,
                   u.tg_username, l.tg_id
            FROM licenses l
            LEFT JOIN users u ON u.tg_id = l.tg_id
            WHERE l.ip_violations > 0
            ORDER BY l.ip_violations DESC
        """).fetchall()
        con.close()
    return [dict(r) for r in rows]


# ── Allowed accounts per key ───────────────────────────────────────────────

def get_allowed_accounts(key: str) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM allowed_accounts WHERE license_key = ? ORDER BY added_at",
            (key,)).fetchall()
        con.close()
    return [dict(r) for r in rows]


def count_allowed_accounts(key: str) -> int:
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM allowed_accounts WHERE license_key = ? AND status = 'allowed'",
            (key,)).fetchone()[0]
        con.close()
        return n


def is_account_allowed(key: str, roblox_uid: str) -> str | None:
    """Returns 'allowed', 'banned', or None (not registered)."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT status FROM allowed_accounts WHERE license_key = ? AND roblox_uid = ?",
            (key, roblox_uid)).fetchone()
        con.close()
        return row["status"] if row else None


def add_allowed_account(key: str, roblox_uid: str, roblox_name: str = "") -> bool:
    """Add account to allowed list. Returns False if limit reached."""
    with _lock:
        con = _con()
        # Check if already exists
        existing = con.execute(
            "SELECT status FROM allowed_accounts WHERE license_key = ? AND roblox_uid = ?",
            (key, roblox_uid)).fetchone()
        if existing:
            if existing["status"] == "banned":
                con.execute(
                    "UPDATE allowed_accounts SET status = 'allowed', roblox_name = ? WHERE license_key = ? AND roblox_uid = ?",
                    (roblox_name or "", key, roblox_uid))
                con.commit()
            con.close()
            return True
        # Check limit
        lic = con.execute("SELECT max_accounts FROM licenses WHERE key = ?", (key,)).fetchone()
        max_acc = (lic["max_accounts"] or 5) if lic else 5
        count = con.execute(
            "SELECT COUNT(*) FROM allowed_accounts WHERE license_key = ? AND status = 'allowed'",
            (key,)).fetchone()[0]
        if count >= max_acc:
            con.close()
            return False
        con.execute(
            "INSERT OR IGNORE INTO allowed_accounts (license_key, roblox_uid, roblox_name, status, added_at) VALUES (?, ?, ?, 'allowed', ?)",
            (key, roblox_uid, roblox_name, time.time()))
        con.commit()
        con.close()
        return True


def ban_account(key: str, roblox_uid: str):
    """Ban a Roblox account from using this key."""
    with _lock:
        con = _con()
        existing = con.execute(
            "SELECT 1 FROM allowed_accounts WHERE license_key = ? AND roblox_uid = ?",
            (key, roblox_uid)).fetchone()
        if existing:
            con.execute(
                "UPDATE allowed_accounts SET status = 'banned' WHERE license_key = ? AND roblox_uid = ?",
                (key, roblox_uid))
        else:
            con.execute(
                "INSERT INTO allowed_accounts (license_key, roblox_uid, roblox_name, status, added_at) VALUES (?, ?, '', 'banned', ?)",
                (key, roblox_uid, time.time()))
        con.commit()
        con.close()


def remove_allowed_account(key: str, roblox_uid: str):
    with _lock:
        con = _con()
        con.execute("DELETE FROM allowed_accounts WHERE license_key = ? AND roblox_uid = ?",
                    (key, roblox_uid))
        con.commit()
        con.close()


def set_max_accounts(key: str, max_acc: int):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET max_accounts = ? WHERE key = ?", (max_acc, key))
        con.commit()
        con.close()


def touch_license(key: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET last_used = ? WHERE key = ?", (time.time(), key))
        con.commit()
        con.close()


def revoke_license(key: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET status = 'revoked' WHERE key = ?", (key,))
        con.commit()
        con.close()


def reset_license(tg_id: int):
    """Delete all licenses for a user and reset their status so they can get a new key."""
    with _lock:
        con = _con()
        con.execute("DELETE FROM licenses WHERE tg_id = ?", (tg_id,))
        con.execute("UPDATE users SET status = 'active', approved_at = NULL WHERE tg_id = ?", (tg_id,))
        con.commit()
        con.close()


def give_license(tg_id: int) -> str:
    """Create a lifetime license for a user (admin /give)."""
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    with _lock:
        con = _con()
        con.execute("DELETE FROM licenses WHERE tg_id = ?", (tg_id,))
        con.execute("""
            INSERT INTO licenses (key, tg_id, created_at, last_used, key_type, expires_at)
            VALUES (?, ?, ?, ?, 'lifetime', NULL)
        """, (key, tg_id, time.time(), time.time()))
        con.execute("UPDATE users SET status = 'approved', approved_at = ? WHERE tg_id = ?",
                    (time.time(), tg_id))
        con.commit()
        con.close()
    return key


def give_trial_key(tg_id: int) -> str:
    """Issue a 3-day trial key, wiping any previous key."""
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    expires_at = time.time() + 3 * 86400
    with _lock:
        con = _con()
        con.execute("DELETE FROM licenses WHERE tg_id = ?", (tg_id,))
        con.execute("""
            INSERT INTO licenses (key, tg_id, created_at, last_used, key_type, expires_at)
            VALUES (?, ?, ?, ?, 'trial', ?)
        """, (key, tg_id, time.time(), time.time(), expires_at))
        con.execute("UPDATE users SET status = 'approved', approved_at = ? WHERE tg_id = ?",
                    (time.time(), tg_id))
        con.commit()
        con.close()
    return key


def give_lifetime_key(tg_id: int) -> str:
    """Upgrade user to a lifetime key, preserving roblox binding if any."""
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    with _lock:
        con = _con()
        old = con.execute(
            "SELECT roblox_user_id, roblox_name, activated_at FROM licenses WHERE tg_id = ? ORDER BY created_at DESC LIMIT 1",
            (tg_id,)
        ).fetchone()
        con.execute("DELETE FROM licenses WHERE tg_id = ?", (tg_id,))
        con.execute("""
            INSERT INTO licenses (key, tg_id, created_at, last_used, key_type, expires_at,
                                  roblox_user_id, roblox_name, activated_at)
            VALUES (?, ?, ?, ?, 'lifetime', NULL, ?, ?, ?)
        """, (
            key, tg_id, time.time(), time.time(),
            old["roblox_user_id"] if old else None,
            old["roblox_name"]    if old else None,
            old["activated_at"]   if old else None,
        ))
        con.execute("UPDATE users SET status = 'approved', approved_at = ? WHERE tg_id = ?",
                    (time.time(), tg_id))
        con.commit()
        con.close()
    return key


def is_key_valid(lic: dict) -> bool:
    """Return True if license is active and not expired."""
    if not lic or lic.get("status") != "active":
        return False
    expires_at = lic.get("expires_at")
    if expires_at and time.time() > expires_at:
        return False
    return True


def set_referred_by(tg_id: int, ref_id: int):
    """Set who referred this user (only if not already set)."""
    with _lock:
        con = _con()
        con.execute(
            "UPDATE users SET referred_by = ? WHERE tg_id = ? AND referred_by IS NULL",
            (ref_id, tg_id),
        )
        con.commit()
        con.close()


def get_ref_count(tg_id: int) -> int:
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (tg_id,)
        ).fetchone()[0]
        con.close()
        return n


def get_refs(tg_id: int) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM users WHERE referred_by = ? ORDER BY created_at DESC",
            (tg_id,),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def get_top_referrers(limit: int = 20) -> list[dict]:
    """Users sorted by ref count descending."""
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT u.*, COUNT(r.tg_id) AS ref_count
            FROM users u
            LEFT JOIN users r ON r.referred_by = u.tg_id
            GROUP BY u.tg_id
            HAVING ref_count > 0
            ORDER BY ref_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        con.close()
        return [dict(r) for r in rows]


def count_licenses() -> int:
    with _lock:
        con = _con()
        n = con.execute("SELECT COUNT(*) FROM licenses WHERE status = 'active'").fetchone()[0]
        con.close()
        return n


# ── Payout requests ────────────────────────────────────────────────────────

def create_payout_request(tg_id: int, tg_username: str, tg_name: str, amount: int) -> int:
    with _lock:
        con = _con()
        cur = con.execute(
            "INSERT INTO payout_requests (tg_id, tg_username, tg_name, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (tg_id, tg_username, tg_name, amount, time.time()),
        )
        rid = cur.lastrowid
        con.commit()
        con.close()
        return rid


def has_pending_payout(tg_id: int) -> bool:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT id FROM payout_requests WHERE tg_id = ? AND status = 'pending'", (tg_id,)
        ).fetchone()
        con.close()
        return row is not None


def resolve_payout(request_id: int, status: str, admin_note: str = ""):
    """status: 'paid' or 'rejected'"""
    with _lock:
        con = _con()
        row = con.execute("SELECT tg_id, amount FROM payout_requests WHERE id = ?", (request_id,)).fetchone()
        if row and status == "paid":
            con.execute(
                "UPDATE users SET ref_balance = MAX(0, ref_balance - ?) WHERE tg_id = ?",
                (row["amount"], row["tg_id"]),
            )
        con.execute(
            "UPDATE payout_requests SET status=?, resolved_at=?, admin_note=? WHERE id=?",
            (status, time.time(), admin_note, request_id),
        )
        con.commit()
        con.close()
        return dict(row) if row else None


def get_pending_payouts() -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM payout_requests WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def get_all_payouts(limit: int = 50) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM payout_requests ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


# ── pd_accounts_v2 ─────────────────────────────────────────────────────────

def upsert_account(acc_id: str, license_key: str, data: dict):
    with _lock:
        con = _con()
        existing = con.execute(
            "SELECT * FROM pd_accounts_v2 WHERE id = ?", (acc_id,)
        ).fetchone()
        now = time.time()
        if not existing:
            con.execute("""
                INSERT INTO pd_accounts_v2
                    (id, license_key, name, approached, agreed, refused, no_response,
                     hops, donations, robux_gross, raised_current,
                     last_seen, session_start, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                acc_id, license_key,
                data.get("name", ""),
                data.get("approached", 0), data.get("agreed", 0),
                data.get("refused", 0),   data.get("no_response", 0),
                data.get("hops", 0),      data.get("donations", 0),
                data.get("robux_gross", 0), data.get("raised_current", 0),
                now, data.get("session_start", now), now,
                data.get("status", "Active"),
            ))
        else:
            con.execute("""
                UPDATE pd_accounts_v2 SET
                    license_key = ?,
                    name = ?, approached = ?, agreed = ?, refused = ?, no_response = ?,
                    hops = ?, donations = ?, robux_gross = ?, raised_current = ?,
                    last_seen = ?, status = ?
                WHERE id = ?
            """, (
                license_key,
                data.get("name", existing["name"]),
                data.get("approached", 0), data.get("agreed", 0),
                data.get("refused", 0),   data.get("no_response", 0),
                data.get("hops", 0),      data.get("donations", 0),
                data.get("robux_gross", 0), data.get("raised_current", 0),
                now, data.get("status", "Active"),
                acc_id,
            ))
        con.commit()
        con.close()


def get_account(acc_id: str) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM pd_accounts_v2 WHERE id = ?", (acc_id,)).fetchone()
        con.close()
        return dict(row) if row else None


def get_account_by_license(key: str) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM pd_accounts_v2 WHERE license_key = ? ORDER BY last_seen DESC LIMIT 1",
            (key,)
        ).fetchone()
        con.close()
        return dict(row) if row else None


def get_all_accounts_by_license(key: str) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM pd_accounts_v2 WHERE license_key = ? ORDER BY last_seen DESC",
            (key,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def count_active_accounts() -> int:
    """Accounts seen in the last 15 seconds."""
    cutoff = time.time() - 15
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM pd_accounts_v2 WHERE last_seen > ?", (cutoff,)
        ).fetchone()[0]
        con.close()
        return n


def total_robux() -> int:
    with _lock:
        con = _con()
        n = con.execute("""
            SELECT COALESCE(SUM(a.robux_gross) + SUM(a.robux_alltime), 0)
            FROM pd_accounts_v2 a
            JOIN licenses l ON a.license_key = l.key
            WHERE l.status = 'active'
        """).fetchone()[0]
        con.close()
        return n


# ── Orphaned session salvage ───────────────────────────────────────────────

def salvage_to_alltime(acc_id: str):
    """Move non-zero current-session stats to alltime (handles orphaned sessions
    that were never properly closed, e.g. after server restart)."""
    with _lock:
        con = _con()
        con.execute("""
            UPDATE pd_accounts_v2
            SET robux_alltime      = robux_alltime      + robux_gross,
                donations_alltime  = donations_alltime  + donations,
                approached_alltime = approached_alltime + approached,
                agreed_alltime     = agreed_alltime     + agreed,
                refused_alltime    = refused_alltime    + refused,
                no_response_alltime= no_response_alltime+ no_response,
                robux_gross = 0, donations = 0,
                approached = 0, agreed = 0, refused = 0, no_response = 0
            WHERE id = ? AND (robux_gross > 0 OR donations > 0 OR approached > 0)
        """, (acc_id,))
        now = time.time()
        con.execute("""
            UPDATE pd_sessions_v2
            SET ended_at = ?, duration = MAX(0, ? - started_at)
            WHERE account_id = ? AND ended_at IS NULL
        """, (now, now, acc_id))
        con.commit()
        con.close()


def salvage_all_orphaned():
    """On server start, move ALL non-zero current stats to alltime and close
    open sessions. Prevents data loss from ungraceful shutdowns."""
    with _lock:
        con = _con()
        count = con.execute(
            "SELECT COUNT(*) FROM pd_accounts_v2 WHERE robux_gross > 0 OR donations > 0"
        ).fetchone()[0]
        if count > 0:
            con.execute("""
                UPDATE pd_accounts_v2
                SET robux_alltime      = robux_alltime      + robux_gross,
                    donations_alltime  = donations_alltime  + donations,
                    approached_alltime = approached_alltime + approached,
                    agreed_alltime     = agreed_alltime     + agreed,
                    refused_alltime    = refused_alltime    + refused,
                    no_response_alltime= no_response_alltime+ no_response,
                    robux_gross = 0, donations = 0,
                    approached = 0, agreed = 0, refused = 0, no_response = 0
                WHERE robux_gross > 0 OR donations > 0 OR approached > 0
            """)
            now = time.time()
            con.execute("""
                UPDATE pd_sessions_v2
                SET ended_at = ?, duration = MAX(0, ? - started_at)
                WHERE ended_at IS NULL
            """, (now, now))
            con.commit()
            print(f"[DB] Salvaged orphaned stats from {count} accounts")
        con.close()


# ── pd_sessions_v2 ─────────────────────────────────────────────────────────

def open_session(account_id: str, started_at: float) -> int:
    """Create a new open session row, return its id."""
    with _lock:
        con = _con()
        cur = con.execute(
            "INSERT INTO pd_sessions_v2 (account_id, started_at) VALUES (?, ?)",
            (account_id, started_at),
        )
        sid = cur.lastrowid
        con.commit()
        con.close()
        return sid


def close_session(session_id: int, ended_at: float, delta: dict):
    """Close a session: write ended_at, duration, and per-session stat deltas.
    Also accumulates robux_alltime / donations_alltime on the account row so
    historical totals are never lost when the Lua script restarts."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT started_at, account_id FROM pd_sessions_v2 WHERE id = ?", (session_id,)
        ).fetchone()
        duration  = max(0.0, ended_at - (row["started_at"] if row else ended_at))
        r_delta   = max(0, delta.get("robux_gross", 0))
        d_delta   = max(0, delta.get("donations",   0))
        con.execute(
            """UPDATE pd_sessions_v2
               SET ended_at=?, duration=?,
                   approached=?, agreed=?, refused=?, no_response=?,
                   donations=?, robux_gross=?
               WHERE id=?""",
            (
                ended_at, duration,
                max(0, delta.get("approached",  0)),
                max(0, delta.get("agreed",      0)),
                max(0, delta.get("refused",     0)),
                max(0, delta.get("no_response", 0)),
                d_delta, r_delta,
                session_id,
            ),
        )
        # Accumulate into alltime totals and reset current fields to 0
        # so that current+alltime never double-counts when account is offline
        if row and row["account_id"]:
            con.execute(
                """UPDATE pd_accounts_v2
                   SET robux_alltime        = robux_alltime        + ?,
                       donations_alltime    = donations_alltime    + ?,
                       approached_alltime   = approached_alltime   + ?,
                       agreed_alltime       = agreed_alltime       + ?,
                       refused_alltime      = refused_alltime      + ?,
                       no_response_alltime  = no_response_alltime  + ?,
                       robux_gross   = 0,
                       donations     = 0,
                       approached    = 0,
                       agreed        = 0,
                       refused       = 0,
                       no_response   = 0
                   WHERE id = ?""",
                (
                    r_delta, d_delta,
                    max(0, delta.get("approached",  0)),
                    max(0, delta.get("agreed",      0)),
                    max(0, delta.get("refused",     0)),
                    max(0, delta.get("no_response", 0)),
                    row["account_id"],
                ),
            )
        # ── Referral 10% payout ─────────────────────────────────────────────
        # Find: account → license_key → license.tg_id → users.referred_by
        # If referrer has ref_count >= 2 (has lifetime), credit 10% of r_delta
        if r_delta > 0 and row and row["account_id"]:
            acc_row = con.execute(
                "SELECT license_key FROM pd_accounts_v2 WHERE id = ?",
                (row["account_id"],),
            ).fetchone()
            if acc_row and acc_row["license_key"]:
                lic_row = con.execute(
                    "SELECT tg_id, dc_id FROM licenses WHERE key = ?",
                    (acc_row["license_key"],),
                ).fetchone()
                if lic_row and lic_row["tg_id"]:
                    user_row = con.execute(
                        "SELECT referred_by FROM users WHERE tg_id = ?",
                        (lic_row["tg_id"],),
                    ).fetchone()
                    if user_row and user_row["referred_by"]:
                        referrer_id = user_row["referred_by"]
                        ref_count = con.execute(
                            "SELECT COUNT(*) FROM users WHERE referred_by = ?",
                            (referrer_id,),
                        ).fetchone()[0]
                        if ref_count >= 1:
                            reward = max(1, int(r_delta * 0.10))
                            con.execute(
                                "UPDATE users SET ref_balance = ref_balance + ? WHERE tg_id = ?",
                                (reward, referrer_id),
                            )
                elif lic_row and lic_row["dc_id"]:
                    dc_user_row = con.execute(
                        "SELECT referred_by FROM dc_users WHERE dc_id = ?",
                        (lic_row["dc_id"],),
                    ).fetchone()
                    if dc_user_row and dc_user_row["referred_by"]:
                        referrer_dc_id = dc_user_row["referred_by"]
                        ref_count = con.execute(
                            "SELECT COUNT(*) FROM dc_users WHERE referred_by = ?",
                            (referrer_dc_id,),
                        ).fetchone()[0]
                        if ref_count >= 1:
                            reward = max(1, int(r_delta * 0.10))
                            con.execute(
                                "UPDATE dc_users SET ref_balance = ref_balance + ? WHERE dc_id = ?",
                                (reward, referrer_dc_id),
                            )
        con.commit()
        con.close()


def get_ref_balance(tg_id: int) -> int:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT ref_balance FROM users WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        con.close()
        return row["ref_balance"] if row else 0


def reset_ref_balance(tg_id: int):
    """Admin: mark ref balance as paid out (reset to 0)."""
    with _lock:
        con = _con()
        con.execute("UPDATE users SET ref_balance = 0 WHERE tg_id = ?", (tg_id,))
        con.commit()
        con.close()


def get_refs_with_earnings(tg_id: int) -> list[dict]:
    """Returns list of referrals with their total alltime robux earned."""
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM users WHERE referred_by = ? ORDER BY created_at DESC",
            (tg_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            lic = con.execute(
                "SELECT key FROM licenses WHERE tg_id = ? AND status = 'active'",
                (r["tg_id"],),
            ).fetchone()
            earned = 0
            if lic:
                accs = con.execute(
                    "SELECT COALESCE(SUM(robux_alltime), 0) + COALESCE(SUM(robux_gross), 0) AS total FROM pd_accounts_v2 WHERE license_key = ?",
                    (lic["key"],),
                ).fetchone()
                if accs:
                    earned = accs["total"]
            d["robux_earned"] = earned
            result.append(d)
        con.close()
        return result


def get_sessions(account_id: str, limit: int = 10, offset: int = 0) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            """SELECT * FROM pd_sessions_v2
               WHERE account_id = ?
               ORDER BY started_at DESC
               LIMIT ? OFFSET ?""",
            (account_id, limit, offset),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def count_sessions(account_id: str) -> int:
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM pd_sessions_v2 WHERE account_id = ?",
            (account_id,),
        ).fetchone()[0]
        con.close()
        return n


def close_stale_sessions(now: float | None = None) -> int:
    """Close all sessions that have no ended_at (server restart recovery).
    Returns number of sessions closed."""
    if now is None:
        now = time.time()
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT id, started_at FROM pd_sessions_v2 WHERE ended_at IS NULL"
        ).fetchall()
        for r in rows:
            dur = max(0.0, now - r["started_at"])
            con.execute(
                "UPDATE pd_sessions_v2 SET ended_at=?, duration=? WHERE id=?",
                (now, dur, r["id"]),
            )
        con.commit()
        con.close()
        return len(rows)


def get_all_accounts(limit: int = 50, offset: int = 0) -> list[dict]:
    """All pd_accounts_v2 ordered by last_seen desc, joined with owner tg_id."""
    with _lock:
        con = _con()
        rows = con.execute(
            """SELECT a.*, l.tg_id AS owner_tg_id
               FROM pd_accounts_v2 a
               LEFT JOIN licenses l ON a.license_key = l.key
               ORDER BY a.last_seen DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


def count_all_accounts() -> int:
    with _lock:
        con = _con()
        n = con.execute("SELECT COUNT(*) FROM pd_accounts_v2").fetchone()[0]
        con.close()
        return n


def total_robux_alltime() -> int:
    with _lock:
        con = _con()
        n = con.execute("""
            SELECT COALESCE(SUM(a.robux_alltime), 0)
            FROM pd_accounts_v2 a
            JOIN licenses l ON a.license_key = l.key
            WHERE l.status = 'active'
        """).fetchone()[0]
        con.close()
        return n


def reset_hwid(key: str):
    """Reset HWID binding for a license key."""
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET hwid = NULL WHERE key = ?", (key,))
        con.commit()
        con.close()


def add_warning(key: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET warnings = COALESCE(warnings, 0) + 1 WHERE key = ?", (key,))
        con.commit()
        con.close()


def set_admin_notes(key: str, notes: str):
    with _lock:
        con = _con()
        con.execute("UPDATE licenses SET admin_notes = ? WHERE key = ?", (notes, key))
        con.commit()
        con.close()


def extend_license(key: str, hours: int):
    """Extend expiration by N hours (or set if not set)."""
    with _lock:
        con = _con()
        row = con.execute("SELECT expires_at FROM licenses WHERE key = ?", (key,)).fetchone()
        if row:
            base = row["expires_at"] or time.time()
            if base < time.time():
                base = time.time()
            con.execute("UPDATE licenses SET expires_at = ? WHERE key = ?",
                        (base + hours * 3600, key))
            con.commit()
        con.close()


def get_admin_overview() -> list[dict]:
    """All licenses joined with user info and account stats, ordered by activity."""
    cutoff = time.time() - 35  # online threshold
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT
                l.key, l.tg_id, l.dc_id, l.roblox_user_id, l.roblox_name,
                l.status AS lic_status, l.created_at AS lic_created, l.last_used,
                l.hwid, l.key_type, l.expires_at,
                l.admin_notes, l.warnings, l.bound_ip, l.ip_violations,
                u.tg_username, u.tg_name,
                dc.dc_username, dc.dc_name,
                a.id AS acc_id, a.name AS acc_name,
                a.approached, a.agreed, a.refused, a.no_response,
                a.donations, a.robux_gross,
                a.robux_alltime, a.donations_alltime,
                a.approached_alltime, a.agreed_alltime, a.refused_alltime,
                a.raised_current,
                a.last_seen, a.session_start, a.hops,
                a.status AS acc_status,
                CASE WHEN a.last_seen > ? THEN 1 ELSE 0 END AS is_online
            FROM licenses l
            LEFT JOIN users u ON u.tg_id = l.tg_id
            LEFT JOIN dc_users dc ON dc.dc_id = l.dc_id
            LEFT JOIN pd_accounts_v2 a ON a.license_key = l.key
            ORDER BY COALESCE(a.last_seen, 0) DESC, l.last_used DESC
        """, (cutoff,)).fetchall()
        con.close()
        return [dict(r) for r in rows]


def get_user_dashboard_data(key: str) -> dict | None:
    """Get all data needed for user dashboard: license + accounts + sessions."""
    with _lock:
        con = _con()
        lic = con.execute("SELECT * FROM licenses WHERE key = ?", (key,)).fetchone()
        if not lic:
            con.close()
            return None
        lic = dict(lic)
        accounts = con.execute(
            "SELECT * FROM pd_accounts_v2 WHERE license_key = ? ORDER BY last_seen DESC",
            (key,)
        ).fetchall()
        accounts = [dict(a) for a in accounts]
        for acc in accounts:
            sessions = con.execute(
                "SELECT * FROM pd_sessions_v2 WHERE account_id = ? ORDER BY started_at DESC LIMIT 20",
                (acc["id"],)
            ).fetchall()
            acc["sessions"] = [dict(s) for s in sessions]
        user = con.execute("SELECT * FROM users WHERE tg_id = ?", (lic["tg_id"],)).fetchone()
        con.close()
        return {
            "license": lic,
            "user": dict(user) if user else None,
            "accounts": accounts,
        }


# ── Dashboard tokens ──────────────────────────────────────────────────────

_DASH_TOKEN_TTL = 30 * 24 * 3600  # 30 days

def create_dashboard_token(license_key: str) -> str:
    """Generate a short-lived token for dashboard access. Returns the token."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        con = _con()
        # Clean up expired tokens for this key
        con.execute("DELETE FROM dashboard_tokens WHERE license_key = ? OR expires_at < ?",
                    (license_key, now))
        con.execute(
            "INSERT INTO dashboard_tokens (token, license_key, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, license_key, now, now + _DASH_TOKEN_TTL),
        )
        con.commit()
        con.close()
    return token


def validate_dashboard_token(token: str) -> str | None:
    """Validate token, return license_key if valid, None if expired/invalid."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT license_key, expires_at FROM dashboard_tokens WHERE token = ?",
            (token,),
        ).fetchone()
        con.close()
    if not row:
        return None
    if time.time() > row["expires_at"]:
        return None
    return row["license_key"]


def cleanup_dashboard_tokens():
    """Remove all expired tokens."""
    with _lock:
        con = _con()
        con.execute("DELETE FROM dashboard_tokens WHERE expires_at < ?", (time.time(),))
        con.commit()
        con.close()


# ── Referral dashboard tokens ─────────────────────────────────────────────

def create_ref_token(tg_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now   = time.time()
    with _lock:
        con = _con()
        con.execute("DELETE FROM ref_tokens WHERE tg_id = ? OR expires_at < ?", (tg_id, now))
        con.execute(
            "INSERT INTO ref_tokens (token, tg_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, tg_id, now, now + _DASH_TOKEN_TTL),
        )
        con.commit()
        con.close()
    return token


def validate_ref_token(token: str) -> int | None:
    """Return tg_id if token is valid, else None."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT tg_id, expires_at FROM ref_tokens WHERE token = ?", (token,)
        ).fetchone()
        con.close()
    if not row:
        return None
    if time.time() > row["expires_at"]:
        return None
    return row["tg_id"]


def get_ref_dashboard_data(tg_id: int) -> dict:
    """Full referral stats for the ref dashboard page."""
    with _lock:
        con = _con()
        user = con.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        if not user:
            con.close()
            return {}

        ref_balance = user["ref_balance"] or 0
        online_cutoff = time.time() - 90

        refs_rows = con.execute(
            "SELECT * FROM users WHERE referred_by = ? ORDER BY created_at DESC",
            (tg_id,),
        ).fetchall()

        refs       = []
        total_ref_robux = 0
        earning_refs    = 0
        online_refs     = 0

        for r in refs_rows:
            d = dict(r)
            lic = con.execute(
                "SELECT key, status, key_type FROM licenses WHERE tg_id = ? ORDER BY created_at DESC LIMIT 1",
                (r["tg_id"],),
            ).fetchone()

            d["has_key"]    = lic is not None
            d["key_status"] = lic["status"]   if lic else None
            d["key_type"]   = lic["key_type"] if lic else None

            robux_earned   = 0
            accounts_count = 0
            last_seen      = None
            is_online      = False

            if lic:
                row_acc = con.execute(
                    """SELECT COUNT(*) AS cnt,
                       COALESCE(SUM(robux_alltime),0)+COALESCE(SUM(robux_gross),0) AS total_robux,
                       MAX(last_seen) AS last_seen
                       FROM pd_accounts_v2 WHERE license_key = ?""",
                    (lic["key"],),
                ).fetchone()
                if row_acc:
                    robux_earned   = row_acc["total_robux"] or 0
                    accounts_count = row_acc["cnt"] or 0
                    last_seen      = row_acc["last_seen"]
                    is_online      = bool(last_seen and last_seen > online_cutoff)

            d["robux_earned"]   = robux_earned
            d["my_cut"]         = int(robux_earned * 0.1)
            d["accounts_count"] = accounts_count
            d["last_seen"]      = last_seen
            d["is_online"]      = is_online

            if robux_earned > 0:
                earning_refs += 1
            if is_online:
                online_refs += 1
            total_ref_robux += robux_earned
            refs.append(d)

        con.close()

        return {
            "user":            dict(user),
            "ref_balance":     ref_balance,
            "refs":            refs,
            "total_refs":      len(refs),
            "earning_refs":    earning_refs,
            "online_refs":     online_refs,
            "total_ref_robux": total_ref_robux,
            "my_total_cut":    int(total_ref_robux * 0.1),
        }


# ── Interaction log ──────────────────────────────────────────────────────

def log_interaction(license_key: str, uid: str, account_name: str,
                    target_name: str, action: str, message: str = "",
                    event: str = ""):
    now = time.time()
    with _lock:
        con = _con()
        con.execute(
            "INSERT INTO interaction_log "
            "(license_key, uid, account_name, target_name, action, message, event, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (license_key, uid, account_name or "", target_name or "",
             action, message or "", event or "", now),
        )
        # Keep only last 500 per key
        con.execute(
            "DELETE FROM interaction_log WHERE license_key = ? AND id NOT IN "
            "(SELECT id FROM interaction_log WHERE license_key = ? ORDER BY created_at DESC LIMIT 500)",
            (license_key, license_key),
        )
        con.commit()
        con.close()


def get_interaction_log(license_key: str, limit: int = 50,
                        uid: str = "", event: str = "") -> list[dict]:
    with _lock:
        con = _con()
        sql = "SELECT * FROM interaction_log WHERE license_key = ?"
        params: list = [license_key]
        if uid:
            sql += " AND uid = ?"
            params.append(uid)
        if event:
            sql += " AND event = ?"
            params.append(event)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(sql, params).fetchall()
        con.close()
    return [dict(r) for r in rows]


def get_all_interaction_log(limit: int = 100, event: str = "") -> list[dict]:
    with _lock:
        con = _con()
        sql = "SELECT * FROM interaction_log"
        params: list = []
        if event:
            sql += " WHERE event = ?"
            params.append(event)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(sql, params).fetchall()
        con.close()
    return [dict(r) for r in rows]


def get_interaction_stats(license_key: str) -> dict:
    """Aggregate interaction stats from interaction_log for a license key."""
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT uid AS account_uid,
                   SUM(CASE WHEN event='agreed' THEN 1 ELSE 0 END) as agreed,
                   SUM(CASE WHEN event='refused' THEN 1 ELSE 0 END) as refused,
                   SUM(CASE WHEN event='no_response' THEN 1 ELSE 0 END) as no_response,
                   SUM(CASE WHEN event='donated' THEN 1 ELSE 0 END) as donated,
                   COUNT(*) as total
            FROM interaction_log
            WHERE license_key = ?
            GROUP BY uid
        """, (license_key,)).fetchall()
        con.close()
    return {"accounts": [dict(r) for r in rows]}


def get_hourly_analytics(since: float, license_key: str = "") -> list[dict]:
    """Aggregate interaction_log by hour for analytics charts."""
    with _lock:
        con = _con()
        sql = """
            SELECT
                CAST(created_at / 3600 AS INTEGER) * 3600 AS hour_ts,
                COUNT(*) AS total,
                SUM(CASE WHEN event='agreed' THEN 1 ELSE 0 END) AS agreed,
                SUM(CASE WHEN event='refused' THEN 1 ELSE 0 END) AS refused,
                SUM(CASE WHEN event='no_response' THEN 1 ELSE 0 END) AS no_response,
                SUM(CASE WHEN event='donated' THEN 1 ELSE 0 END) AS donated,
                SUM(CASE WHEN action='send_chat' THEN 1 ELSE 0 END) AS messages
            FROM interaction_log
            WHERE created_at >= ?"""
        params: list = [since]
        if license_key:
            sql += " AND license_key = ?"
            params.append(license_key)
        sql += " GROUP BY hour_ts ORDER BY hour_ts"
        rows = con.execute(sql, params).fetchall()
        con.close()
    result = []
    for r in rows:
        d = dict(r)
        d["hour_label"] = time.strftime("%d.%m %H:00", time.localtime(d["hour_ts"]))
        result.append(d)
    return result


def get_all_sessions(key: str = "", limit: int = 5000) -> list[dict]:
    with _lock:
        con = _con()
        if key:
            rows = con.execute(
                """SELECT s.*, a.name, a.license_key FROM pd_sessions_v2 s
                   JOIN pd_accounts_v2 a ON a.id = s.account_id
                   WHERE a.license_key = ? ORDER BY s.started_at DESC LIMIT ?""",
                (key, limit)).fetchall()
        else:
            rows = con.execute(
                """SELECT s.*, a.name, a.license_key FROM pd_sessions_v2 s
                   JOIN pd_accounts_v2 a ON a.id = s.account_id
                   ORDER BY s.started_at DESC LIMIT ?""",
                (limit,)).fetchall()
        con.close()
    return [dict(r) for r in rows]


def get_top_replies(limit: int = 200) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT player_reply, event, COUNT(*) as cnt
            FROM interaction_log
            WHERE player_reply IS NOT NULL AND player_reply != ''
            GROUP BY player_reply, event
            ORDER BY cnt DESC LIMIT ?
        """, (limit,)).fetchall()
        con.close()
    return [dict(r) for r in rows]


def get_license_by_tg(tg_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM licenses WHERE tg_id = ?", (tg_id,)).fetchone()
        con.close()
    return dict(row) if row else None


# ── Discord users ──────────────────────────────────────────────────────────

def dc_upsert_user(dc_id: int, username: str, name: str):
    with _lock:
        con = _con()
        con.execute("""
            INSERT INTO dc_users (dc_id, dc_username, dc_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dc_id) DO UPDATE SET
                dc_username = excluded.dc_username,
                dc_name     = excluded.dc_name
        """, (dc_id, username, name, time.time()))
        con.commit()
        con.close()


def dc_get_user(dc_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM dc_users WHERE dc_id = ?", (dc_id,)).fetchone()
        con.close()
        return dict(row) if row else None


def dc_count_users() -> int:
    with _lock:
        con = _con()
        n = con.execute("SELECT COUNT(*) FROM dc_users").fetchone()[0]
        con.close()
        return n


def dc_set_referred_by(dc_id: int, ref_dc_id: int):
    with _lock:
        con = _con()
        con.execute(
            "UPDATE dc_users SET referred_by = ? WHERE dc_id = ? AND referred_by IS NULL",
            (ref_dc_id, dc_id),
        )
        con.commit()
        con.close()


def dc_get_ref_count(dc_id: int) -> int:
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM dc_users WHERE referred_by = ?", (dc_id,)
        ).fetchone()[0]
        con.close()
        return n


def dc_get_ref_balance(dc_id: int) -> int:
    with _lock:
        con = _con()
        row = con.execute("SELECT ref_balance FROM dc_users WHERE dc_id = ?", (dc_id,)).fetchone()
        con.close()
        return row["ref_balance"] if row else 0


def dc_reset_ref_balance(dc_id: int):
    with _lock:
        con = _con()
        con.execute("UPDATE dc_users SET ref_balance = 0 WHERE dc_id = ?", (dc_id,))
        con.commit()
        con.close()


def dc_get_refs(dc_id: int) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM dc_users WHERE referred_by = ? ORDER BY created_at DESC", (dc_id,)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]


# ── Discord licenses ───────────────────────────────────────────────────────

def dc_get_license_by_dc(dc_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM licenses WHERE dc_id = ? ORDER BY created_at DESC LIMIT 1", (dc_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None


def dc_give_trial_key(dc_id: int) -> str:
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    expires_at = time.time() + 3 * 86400
    with _lock:
        con = _con()
        con.execute("DELETE FROM licenses WHERE dc_id = ?", (dc_id,))
        con.execute("""
            INSERT INTO licenses (key, dc_id, created_at, last_used, key_type, expires_at)
            VALUES (?, ?, ?, ?, 'trial', ?)
        """, (key, dc_id, time.time(), time.time(), expires_at))
        con.commit()
        con.close()
    return key


def dc_give_lifetime_key(dc_id: int) -> str:
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    with _lock:
        con = _con()
        old = con.execute(
            "SELECT roblox_user_id, roblox_name, activated_at FROM licenses WHERE dc_id = ? ORDER BY created_at DESC LIMIT 1",
            (dc_id,)
        ).fetchone()
        con.execute("DELETE FROM licenses WHERE dc_id = ?", (dc_id,))
        con.execute("""
            INSERT INTO licenses (key, dc_id, created_at, last_used, key_type, expires_at,
                                  roblox_user_id, roblox_name, activated_at)
            VALUES (?, ?, ?, ?, 'lifetime', NULL, ?, ?, ?)
        """, (
            key, dc_id, time.time(), time.time(),
            old["roblox_user_id"] if old else None,
            old["roblox_name"]    if old else None,
            old["activated_at"]   if old else None,
        ))
        con.commit()
        con.close()
    return key


def dc_give_license(dc_id: int) -> str:
    key = "-".join([uuid.uuid4().hex[:4].upper() for _ in range(4)])
    with _lock:
        con = _con()
        con.execute("DELETE FROM licenses WHERE dc_id = ?", (dc_id,))
        con.execute("""
            INSERT INTO licenses (key, dc_id, created_at, last_used, key_type, expires_at)
            VALUES (?, ?, ?, ?, 'lifetime', NULL)
        """, (key, dc_id, time.time(), time.time()))
        con.commit()
        con.close()
    return key


# ── Discord invites ────────────────────────────────────────────────────────

def dc_upsert_invite(invite_code: str, dc_id: int, uses: int = 0):
    with _lock:
        con = _con()
        con.execute("""
            INSERT INTO dc_invites (invite_code, dc_id, uses, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(invite_code) DO UPDATE SET uses = excluded.uses
        """, (invite_code, dc_id, uses, time.time()))
        con.commit()
        con.close()


def dc_get_invite(invite_code: str) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT * FROM dc_invites WHERE invite_code = ?", (invite_code,)).fetchone()
        con.close()
        return dict(row) if row else None


def dc_get_user_invite(dc_id: int) -> dict | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM dc_invites WHERE dc_id = ? ORDER BY created_at DESC LIMIT 1", (dc_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None


def dc_get_all_invites() -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute("SELECT * FROM dc_invites").fetchall()
        con.close()
        return [dict(r) for r in rows]
