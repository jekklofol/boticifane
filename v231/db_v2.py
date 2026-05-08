import sqlite3, time, uuid, os, threading, secrets, hashlib

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "farm_data_v2.db")
_lock   = threading.Lock()


def _con():
    c = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    c.row_factory = sqlite3.Row
    # Per-connection performance pragmas
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA cache_size=-20000")  # ~20MB page cache
    c.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
    return c


def init_db():
    with _lock:
        con = _con()
        # WAL mode — once, persistent. Massive speedup for concurrent reads.
        con.execute("PRAGMA journal_mode=WAL")
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

        # ── Migration: nicknames + avatars ──────────────────────────────────
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "nickname" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT NULL")
            con.commit()
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "nickname_changes" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN nickname_changes INTEGER DEFAULT 0")
            con.commit()
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "streak_warned_at" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN streak_warned_at REAL DEFAULT NULL")
            con.commit()
        if "avatar_emoji" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN avatar_emoji TEXT DEFAULT NULL")
            con.execute("ALTER TABLE users ADD COLUMN avatar_grad  TEXT DEFAULT NULL")
            con.commit()
        existing_user_cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "avatar_image" not in existing_user_cols:
            con.execute("ALTER TABLE users ADD COLUMN avatar_image TEXT DEFAULT NULL")
            con.commit()

        dc_cols = {row[1] for row in con.execute("PRAGMA table_info(dc_users)")}
        if "nickname" not in dc_cols:
            con.execute("ALTER TABLE dc_users ADD COLUMN nickname TEXT DEFAULT NULL")
            con.commit()
        dc_cols = {row[1] for row in con.execute("PRAGMA table_info(dc_users)")}
        if "nickname_changes" not in dc_cols:
            con.execute("ALTER TABLE dc_users ADD COLUMN nickname_changes INTEGER DEFAULT 0")
            con.commit()
        if "avatar_emoji" not in dc_cols:
            con.execute("ALTER TABLE dc_users ADD COLUMN avatar_emoji TEXT DEFAULT NULL")
            con.execute("ALTER TABLE dc_users ADD COLUMN avatar_grad  TEXT DEFAULT NULL")
            con.commit()
        dc_cols = {row[1] for row in con.execute("PRAGMA table_info(dc_users)")}
        if "avatar_image" not in dc_cols:
            con.execute("ALTER TABLE dc_users ADD COLUMN avatar_image TEXT DEFAULT NULL")
            con.commit()

        # ── Migration: bonus_robux on accounts ─────────────────────────────
        acc_cols = {row[1] for row in con.execute("PRAGMA table_info(pd_accounts_v2)")}
        if "bonus_robux" not in acc_cols:
            con.execute("ALTER TABLE pd_accounts_v2 ADD COLUMN bonus_robux INTEGER DEFAULT 0")
            con.commit()

        # ── Migration: weekly rankings ──────────────────────────────────────
        con.executescript("""
            CREATE TABLE IF NOT EXISTS weekly_rankings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start REAL    NOT NULL,
                tg_id      INTEGER DEFAULT NULL,
                dc_id      INTEGER DEFAULT NULL,
                robux_week INTEGER DEFAULT 0,
                rank_pos   INTEGER DEFAULT 0,
                prize      INTEGER DEFAULT 0,
                settled    INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_wr_week
                ON weekly_rankings(week_start, robux_week DESC);

            -- Pending Stars payments for nickname changes
            CREATE TABLE IF NOT EXISTS nick_payments (
                payload    TEXT PRIMARY KEY,
                tg_id      INTEGER NOT NULL,
                nickname   TEXT    NOT NULL,
                created_at REAL    NOT NULL,
                used_at    REAL    DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nick_pay_tg ON nick_payments(tg_id, created_at DESC);

            -- Achievements
            CREATE TABLE IF NOT EXISTS achievements (
                tg_id          INTEGER NOT NULL,
                achievement_id TEXT    NOT NULL,
                unlocked_at    REAL    NOT NULL,
                PRIMARY KEY (tg_id, achievement_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ach_tg ON achievements(tg_id);

            -- Daily tasks (reset daily at MSK midnight)
            CREATE TABLE IF NOT EXISTS daily_tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id           INTEGER NOT NULL,
                day_start       REAL    NOT NULL,
                task_type       TEXT    NOT NULL,
                target_value    INTEGER NOT NULL,
                reward_robux    INTEGER NOT NULL,
                completed_at    REAL    DEFAULT NULL,
                claimed_at      REAL    DEFAULT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dt_tg_day ON daily_tasks(tg_id, day_start);

            -- Global chat for all farmers
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id       INTEGER NOT NULL,
                text        TEXT    NOT NULL,
                created_at  REAL    NOT NULL,
                deleted     INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_chat_tg      ON chat_messages(tg_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS chat_mutes (
                tg_id        INTEGER PRIMARY KEY,
                muted_until  REAL    NOT NULL,
                reason       TEXT    DEFAULT ''
            );

            -- Support chat messages (between user and admin)
            CREATE TABLE IF NOT EXISTS support_messages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id          INTEGER NOT NULL,
                direction      TEXT    NOT NULL,    -- 'in' (from user) or 'out' (from admin)
                text           TEXT    NOT NULL,
                created_at     REAL    NOT NULL,
                admin_msg_id   INTEGER DEFAULT NULL,    -- TG msg_id in admin chat (for reply tracking)
                seen_by_user   INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_supp_tg         ON support_messages(tg_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_supp_admin_msg  ON support_messages(admin_msg_id);

            -- Streak milestone rewards (one per milestone per user)
            CREATE TABLE IF NOT EXISTS streak_rewards (
                tg_id        INTEGER NOT NULL,
                milestone    INTEGER NOT NULL,
                reward_robux INTEGER NOT NULL,
                claimed_at   REAL    NOT NULL,
                PRIMARY KEY (tg_id, milestone)
            );

            -- UNIQUE on daily_tasks to prevent duplicate generation under race
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dt_unique
                ON daily_tasks(tg_id, day_start, task_type);

            -- Performance: critical indexes for JOIN paths
            CREATE INDEX IF NOT EXISTS idx_pdacc_lic     ON pd_accounts_v2(license_key);
            CREATE INDEX IF NOT EXISTS idx_lic_tg        ON licenses(tg_id);
            CREATE INDEX IF NOT EXISTS idx_lic_dc        ON licenses(dc_id);
            CREATE INDEX IF NOT EXISTS idx_users_ref     ON users(referred_by);
            CREATE INDEX IF NOT EXISTS idx_dcusers_ref   ON dc_users(referred_by);
            CREATE INDEX IF NOT EXISTS idx_pd_sess_end   ON pd_sessions_v2(ended_at);
            CREATE INDEX IF NOT EXISTS idx_streak_tg     ON streak_rewards(tg_id);
        """)
        con.commit()
        # Run analyze occasionally to keep query planner up to date
        con.execute("PRAGMA optimize")

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
        # ── Weekly ranking update ────────────────────────────────────────────
        overtake_info = None
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
                if lic_row:
                    overtake_info = _update_weekly_robux_con(con, lic_row["tg_id"], lic_row["dc_id"], r_delta)
        con.commit()
        con.close()
        return overtake_info


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
    """Returns list of referrals with their total alltime robux earned.
    Single-query implementation (no N+1)."""
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT u.*,
                   l.key AS lic_key,
                   l.status AS lic_status,
                   l.key_type AS lic_key_type,
                   COALESCE((
                       SELECT SUM(a.robux_alltime + a.robux_gross)
                       FROM pd_accounts_v2 a
                       WHERE a.license_key = l.key
                   ), 0) AS robux_earned
            FROM users u
            LEFT JOIN licenses l
                   ON l.tg_id = u.tg_id AND l.status = 'active'
            WHERE u.referred_by = ?
            ORDER BY u.created_at DESC
        """, (tg_id,)).fetchall()
        con.close()
    result = []
    for r in rows:
        d = dict(r)
        d["has_key"]    = d.get("lic_key") is not None
        d["key_status"] = d.get("lic_status")
        d["key_type"]   = d.get("lic_key_type")
        d["robux_earned"] = d.get("robux_earned") or 0
        result.append(d)
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


# ══════════════════════════════════════════════════════════════════════════════
# GAMIFICATION: levels, weekly rankings, nicknames, webapp profile
# ══════════════════════════════════════════════════════════════════════════════

# ── Level system ──────────────────────────────────────────────────────────────
_ROBUX_PER_LEVEL = 160

_TIERS = [
    (1,  "Новичок",   "🌱", ["Доступ к боту", "Базовая статистика"]),
    (6,  "Фармер",    "💪", ["🎭 Маска аватара", "⚡ Приоритет сервера"]),
    (11, "Грабитель", "🤑", ["🎨 Кастомная тема", "📊 Детальная аналитика"]),
    (16, "Барон",     "👑", ["👑 VIP-значок", "🔑 Доп. ключи", "📢 Топ в боте"]),
    (21, "Легенда",   "🚀", ["🚀 Турбо-режим", "💬 Роль в Discord", "🎰 Ежемес. розыгрыш"]),
]


def calc_level(total_robux: int) -> dict:
    level = min(100, total_robux // _ROBUX_PER_LEVEL + 1)
    xp_in_level = total_robux % _ROBUX_PER_LEVEL
    progress_pct = int(xp_in_level / _ROBUX_PER_LEVEL * 100)

    tier_name = _TIERS[0][1]; tier_emoji = _TIERS[0][2]; tier_perks = _TIERS[0][3]
    next_tier_level = _TIERS[1][0]
    for i, (min_lv, name, emoji, perks) in enumerate(_TIERS):
        if level >= min_lv:
            tier_name = name; tier_emoji = emoji; tier_perks = perks
            next_tier_level = _TIERS[i + 1][0] if i + 1 < len(_TIERS) else 999
    return {
        "level": level,
        "tier": tier_name,
        "tier_emoji": tier_emoji,
        "tier_perks": tier_perks,
        "next_tier_level": next_tier_level,
        "xp_in_level": xp_in_level,
        "xp_needed": _ROBUX_PER_LEVEL,
        "progress_pct": progress_pct,
        "total_robux": total_robux,
        "next_level_at": level * _ROBUX_PER_LEVEL,
    }


def get_all_tiers() -> list[dict]:
    result = []
    for i, (min_lv, name, emoji, perks) in enumerate(_TIERS):
        max_lv = _TIERS[i + 1][0] - 1 if i + 1 < len(_TIERS) else 100
        result.append({
            "min_level": min_lv, "max_level": max_lv,
            "name": name, "emoji": emoji, "perks": perks,
            "robux_required": (min_lv - 1) * _ROBUX_PER_LEVEL,
        })
    return result


# ── Nicknames ─────────────────────────────────────────────────────────────────

NICKNAME_CHANGE_PRICE_STARS = 25


def get_nickname_changes(tg_id: int = None, dc_id: int = None) -> int:
    with _lock:
        con = _con()
        if tg_id:
            row = con.execute("SELECT nickname_changes FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        else:
            row = con.execute("SELECT nickname_changes FROM dc_users WHERE dc_id = ?", (dc_id,)).fetchone()
        con.close()
    return (row[0] if row else 0) or 0


def is_nickname_taken(nickname: str, exclude_tg_id: int = None, exclude_dc_id: int = None) -> bool:
    """Case-insensitive check across both users and dc_users."""
    nick_lower = (nickname or "").strip().lower()
    if not nick_lower:
        return False
    with _lock:
        con = _con()
        u_sql = "SELECT 1 FROM users WHERE LOWER(nickname) = ?"
        u_params = [nick_lower]
        if exclude_tg_id:
            u_sql += " AND tg_id != ?"
            u_params.append(exclude_tg_id)
        if con.execute(u_sql, u_params).fetchone():
            con.close()
            return True
        d_sql = "SELECT 1 FROM dc_users WHERE LOWER(nickname) = ?"
        d_params = [nick_lower]
        if exclude_dc_id:
            d_sql += " AND dc_id != ?"
            d_params.append(exclude_dc_id)
        taken = con.execute(d_sql, d_params).fetchone() is not None
        con.close()
    return taken


def set_nickname(tg_id: int, nickname: str, increment: bool = True) -> bool:
    """Atomically check uniqueness and set. Returns False if taken."""
    nick_clean = (nickname or "").strip()[:24]
    if not nick_clean:
        return False
    nick_lower = nick_clean.lower()
    with _lock:
        con = _con()
        # Atomic check inside lock
        taken_u = con.execute(
            "SELECT 1 FROM users WHERE LOWER(nickname) = ? AND tg_id != ?",
            (nick_lower, tg_id)).fetchone()
        taken_d = con.execute(
            "SELECT 1 FROM dc_users WHERE LOWER(nickname) = ?",
            (nick_lower,)).fetchone()
        if taken_u or taken_d:
            con.close()
            return False
        if increment:
            con.execute(
                "UPDATE users SET nickname = ?, nickname_changes = COALESCE(nickname_changes,0) + 1 WHERE tg_id = ?",
                (nick_clean, tg_id))
        else:
            con.execute("UPDATE users SET nickname = ? WHERE tg_id = ?", (nick_clean, tg_id))
        con.commit()
        con.close()
    return True


def dc_set_nickname(dc_id: int, nickname: str, increment: bool = True) -> bool:
    """Atomically check uniqueness and set for Discord user. Returns False if taken."""
    nick_clean = (nickname or "").strip()[:24]
    if not nick_clean:
        return False
    nick_lower = nick_clean.lower()
    with _lock:
        con = _con()
        taken_u = con.execute(
            "SELECT 1 FROM users WHERE LOWER(nickname) = ?",
            (nick_lower,)).fetchone()
        taken_d = con.execute(
            "SELECT 1 FROM dc_users WHERE LOWER(nickname) = ? AND dc_id != ?",
            (nick_lower, dc_id)).fetchone()
        if taken_u or taken_d:
            con.close()
            return False
        if increment:
            con.execute(
                "UPDATE dc_users SET nickname = ?, nickname_changes = COALESCE(nickname_changes,0) + 1 WHERE dc_id = ?",
                (nick_clean, dc_id))
        else:
            con.execute("UPDATE dc_users SET nickname = ? WHERE dc_id = ?", (nick_clean, dc_id))
        con.commit()
        con.close()
    return True


def get_nickname(tg_id: int) -> str | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT nickname, tg_username, tg_name FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        con.close()
    if not row:
        return None
    return row["nickname"] or row["tg_username"] or row["tg_name"] or str(tg_id)


def dc_get_nickname(dc_id: int) -> str | None:
    with _lock:
        con = _con()
        row = con.execute("SELECT nickname, dc_username, dc_name FROM dc_users WHERE dc_id = ?", (dc_id,)).fetchone()
        con.close()
    if not row:
        return None
    return row["nickname"] or row["dc_username"] or row["dc_name"] or str(dc_id)


# ── Avatar (emoji + gradient) ─────────────────────────────────────────────────

AVATAR_EMOJIS = ['🤑','💰','🎯','💎','🔥','👑','⚡','🚀','🎭','🌊','😈','🦊','🐉','💫','🎪','🏆',
                 '🐱','🐺','👽','🤖','🎮','💀','🌟','🍀','⚔️','🛸']

AVATAR_GRADS = [
    'pink-purple', 'purple-blue', 'gold-orange', 'green-blue',
    'pink-orange', 'blue-green', 'red-pink', 'cyan-purple',
]


def set_avatar(tg_id: int = None, dc_id: int = None, emoji: str = None, grad: str = None):
    if emoji and emoji not in AVATAR_EMOJIS:
        return False
    if grad and grad not in AVATAR_GRADS:
        return False
    with _lock:
        con = _con()
        if tg_id:
            # Setting emoji+grad clears uploaded image
            con.execute("UPDATE users SET avatar_emoji = COALESCE(?, avatar_emoji), avatar_grad = COALESCE(?, avatar_grad), avatar_image = NULL WHERE tg_id = ?",
                        (emoji, grad, tg_id))
        else:
            con.execute("UPDATE dc_users SET avatar_emoji = COALESCE(?, avatar_emoji), avatar_grad = COALESCE(?, avatar_grad), avatar_image = NULL WHERE dc_id = ?",
                        (emoji, grad, dc_id))
        con.commit()
        con.close()
    return True


def set_avatar_image(tg_id: int = None, dc_id: int = None, filename: str = None):
    """Set custom uploaded avatar (filename like '<id>.webp')."""
    with _lock:
        con = _con()
        if tg_id:
            con.execute("UPDATE users SET avatar_image = ? WHERE tg_id = ?", (filename, tg_id))
        else:
            con.execute("UPDATE dc_users SET avatar_image = ? WHERE dc_id = ?", (filename, dc_id))
        con.commit()
        con.close()


# ── Nickname Stars payments (replay-protected) ────────────────────────────────

def create_nick_payment(payload: str, tg_id: int, nickname: str):
    """Record a pending Stars payment for a nickname change."""
    with _lock:
        con = _con()
        # Cleanup payments older than 24h to keep table small
        con.execute("DELETE FROM nick_payments WHERE created_at < ? AND used_at IS NULL",
                    (time.time() - 86400,))
        con.execute(
            "INSERT INTO nick_payments (payload, tg_id, nickname, created_at) VALUES (?, ?, ?, ?)",
            (payload, tg_id, nickname[:24], time.time()))
        con.commit()
        con.close()


def is_pending_nick_payment(payload: str, tg_id: int) -> bool:
    """Check if payload is a known unused payment for this user."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT 1 FROM nick_payments WHERE payload = ? AND tg_id = ? AND used_at IS NULL",
            (payload, tg_id)).fetchone()
        con.close()
    return row is not None


def consume_nick_payment(payload: str, tg_id: int) -> str | None:
    """Atomically mark payment as used. Returns nickname to apply, or None if invalid/used.
    Race-safe: UPDATE...WHERE used_at IS NULL returns rowcount=1 only once."""
    with _lock:
        con = _con()
        cur = con.execute(
            "UPDATE nick_payments SET used_at = ? WHERE payload = ? AND tg_id = ? AND used_at IS NULL",
            (time.time(), payload, tg_id))
        if cur.rowcount == 0:
            con.close()
            return None
        row = con.execute(
            "SELECT nickname FROM nick_payments WHERE payload = ?", (payload,)).fetchone()
        con.commit()
        con.close()
    return row["nickname"] if row else None


# ── Weekly rankings ───────────────────────────────────────────────────────────

def get_week_start(ts: float | None = None) -> float:
    """Returns Unix timestamp of the most recent Monday 00:00 Moscow time (UTC+3).
    Week resets at end of Sunday MSK = Monday 00:00 MSK."""
    import datetime
    MSK = datetime.timezone(datetime.timedelta(hours=3))
    t = ts if ts is not None else time.time()
    dt_msk = datetime.datetime.fromtimestamp(t, tz=MSK)
    monday_msk = dt_msk - datetime.timedelta(
        days=dt_msk.weekday(),
        hours=dt_msk.hour,
        minutes=dt_msk.minute,
        seconds=dt_msk.second,
        microseconds=dt_msk.microsecond,
    )
    return monday_msk.timestamp()


def _update_weekly_robux_con(con, tg_id, dc_id, robux_delta: int) -> dict | None:
    if not tg_id and not dc_id:
        return None
    ws = get_week_start()
    existing = con.execute(
        "SELECT id, robux_week FROM weekly_rankings WHERE week_start = ? AND tg_id IS ? AND dc_id IS ?",
        (ws, tg_id, dc_id)
    ).fetchone()
    old_robux = existing["robux_week"] if existing else 0
    new_robux = old_robux + robux_delta

    overtaken_rows = con.execute("""
        SELECT w.tg_id, w.dc_id,
               COALESCE(u.nickname, u.tg_username, u.tg_name) AS display_name
        FROM weekly_rankings w
        LEFT JOIN users u ON u.tg_id = w.tg_id
        WHERE w.week_start = ? AND w.robux_week > ? AND w.robux_week <= ?
          AND NOT (w.tg_id IS ? AND w.dc_id IS ?)
        ORDER BY w.robux_week DESC
        LIMIT 5
    """, (ws, old_robux, new_robux, tg_id, dc_id)).fetchall()

    if existing:
        con.execute("UPDATE weekly_rankings SET robux_week = robux_week + ? WHERE id = ?",
                    (robux_delta, existing["id"]))
    else:
        con.execute(
            "INSERT INTO weekly_rankings (week_start, tg_id, dc_id, robux_week) VALUES (?, ?, ?, ?)",
            (ws, tg_id, dc_id, robux_delta)
        )

    if not overtaken_rows:
        return None

    new_rank = con.execute(
        "SELECT COUNT(*) FROM weekly_rankings WHERE week_start = ? AND robux_week > ?",
        (ws, new_robux)
    ).fetchone()[0] + 1

    return {
        "new_rank": new_rank,
        "actor_tg_id": tg_id,
        "actor_dc_id": dc_id,
        "overtaken": [
            {
                "tg_id": r["tg_id"],
                "dc_id": r["dc_id"],
                "display_name": r["display_name"] or (f"tg:{r['tg_id']}" if r["tg_id"] else f"dc:{r['dc_id']}"),
            }
            for r in overtaken_rows if r["tg_id"] or r["dc_id"]
        ],
    }


def get_weekly_leaderboard(week_start: float | None = None, limit: int = 20) -> list[dict]:
    ws = week_start or get_week_start()
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT w.*, w.robux_week,
                   u.tg_username, u.tg_name, u.nickname AS tg_nick,
                   d.dc_username, d.dc_name, d.nickname AS dc_nick
            FROM weekly_rankings w
            LEFT JOIN users u ON u.tg_id = w.tg_id
            LEFT JOIN dc_users d ON d.dc_id = w.dc_id
            WHERE w.week_start = ?
            ORDER BY w.robux_week DESC
            LIMIT ?
        """, (ws, limit)).fetchall()
        con.close()
    result = []
    for i, r in enumerate(rows):
        d = dict(r)
        if d.get("tg_id"):
            d["display_name"] = d.get("tg_nick") or d.get("tg_username") or d.get("tg_name") or f"tg:{d['tg_id']}"
            d["source"] = "tg"
        else:
            d["display_name"] = d.get("dc_nick") or d.get("dc_username") or d.get("dc_name") or f"dc:{d['dc_id']}"
            d["source"] = "dc"
        d["rank_pos"] = i + 1
        result.append(d)
    return result


def get_user_weekly_rank(tg_id: int | None = None, dc_id: int | None = None) -> dict:
    ws = get_week_start()
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT robux_week FROM weekly_rankings WHERE week_start = ? AND tg_id IS ? AND dc_id IS ?",
            (ws, tg_id, dc_id)
        ).fetchone()
        if not row:
            con.close()
            return {"robux_week": 0, "rank_pos": 0, "week_start": ws}
        robux_week = row["robux_week"]
        rank_pos = con.execute(
            "SELECT COUNT(*) FROM weekly_rankings WHERE week_start = ? AND robux_week > ?",
            (ws, robux_week)
        ).fetchone()[0] + 1
        con.close()
    return {"robux_week": robux_week, "rank_pos": rank_pos, "week_start": ws}


def settle_weekly_rankings(week_start: float) -> list[dict]:
    prizes = {1: 100, 2: 25, 3: 25, 4: 25, 5: 25}
    notified = []
    with _lock:
        con = _con()
        already = con.execute(
            "SELECT COUNT(*) FROM weekly_rankings WHERE week_start = ? AND settled = 1",
            (week_start,)
        ).fetchone()[0]
        if already:
            con.close()
            return []
        rows = con.execute("""
            SELECT w.id, w.tg_id, w.dc_id, w.robux_week,
                   u.tg_username, u.tg_name, u.nickname AS tg_nick,
                   d.dc_username, d.dc_name, d.nickname AS dc_nick
            FROM weekly_rankings w
            LEFT JOIN users u ON u.tg_id = w.tg_id
            LEFT JOIN dc_users d ON d.dc_id = w.dc_id
            WHERE w.week_start = ?
            ORDER BY w.robux_week DESC LIMIT 10
        """, (week_start,)).fetchall()
        for i, r in enumerate(rows):
            prize = prizes.get(i + 1, 0)
            con.execute("UPDATE weekly_rankings SET rank_pos = ?, prize = ?, settled = 1 WHERE id = ?",
                        (i + 1, prize, r["id"]))
            if prize > 0:
                if r["tg_id"]:
                    con.execute("UPDATE users SET ref_balance = ref_balance + ? WHERE tg_id = ?",
                                (prize, r["tg_id"]))
                elif r["dc_id"]:
                    con.execute("UPDATE dc_users SET ref_balance = ref_balance + ? WHERE dc_id = ?",
                                (prize, r["dc_id"]))
                if r["tg_id"]:
                    display_name = r["tg_nick"] or r["tg_username"] or r["tg_name"] or f"tg:{r['tg_id']}"
                else:
                    display_name = r["dc_nick"] or r["dc_username"] or r["dc_name"] or f"dc:{r['dc_id']}"
                notified.append({"tg_id": r["tg_id"], "dc_id": r["dc_id"],
                                  "rank": i + 1, "prize": prize, "robux": r["robux_week"],
                                  "display_name": display_name})
        con.commit()
        con.close()
    return notified


def get_last_settled_week() -> float | None:
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT MAX(week_start) FROM weekly_rankings WHERE settled = 1"
        ).fetchone()
        con.close()
    return row[0] if row and row[0] else None


# ── Activity streak ──────────────────────────────────────────────────────────

# (milestone_days, reward_robux)
STREAK_MILESTONES = [
    (10,  100),
    (30,  1000),
    (90,  5000),
]


def _msk_day_num(ts: float) -> int:
    """MSK day number since epoch (UTC+3)."""
    return int((ts + 3 * 3600) / 86400)


def get_active_day_numbers(tg_id: int, limit_days: int = 400) -> set[int]:
    """Returns set of MSK day numbers where user had at least one ended session."""
    if not tg_id:
        return set()
    cutoff = time.time() - limit_days * 86400
    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT DISTINCT CAST((s.ended_at + 10800) / 86400 AS INTEGER) AS day_num
            FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            JOIN licenses    l ON l.key = a.license_key
            WHERE l.tg_id = ? AND s.ended_at IS NOT NULL AND s.ended_at >= ?
        """, (tg_id, cutoff)).fetchall()
        con.close()
    return {r["day_num"] for r in rows if r["day_num"] is not None}


def compute_streak(tg_id: int) -> int:
    """Current consecutive activity streak in days (MSK). Includes today.
    If today not active but yesterday was, streak still counts (today is grace)."""
    if not tg_id:
        return 0
    days = get_active_day_numbers(tg_id)
    if not days:
        return 0
    today_num = _msk_day_num(time.time())
    cur = today_num if today_num in days else (today_num - 1)
    if cur not in days:
        return 0
    streak = 0
    while cur in days:
        streak += 1
        cur -= 1
    return streak


def get_claimed_milestones(tg_id: int) -> set[int]:
    if not tg_id:
        return set()
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT milestone FROM streak_rewards WHERE tg_id = ?", (tg_id,)).fetchall()
        con.close()
    return {r["milestone"] for r in rows}


def check_streak_rewards(tg_id: int, streak: int | None = None) -> list[dict]:
    """Auto-claim eligible streak milestones. Returns newly awarded rewards.
    If streak is provided, skips re-computation (used to avoid double work)."""
    if not tg_id:
        return []
    if streak is None:
        streak = compute_streak(tg_id)
    new_rewards = []
    with _lock:
        con = _con()
        already = {r["milestone"] for r in con.execute(
            "SELECT milestone FROM streak_rewards WHERE tg_id = ?", (tg_id,)).fetchall()}
        for milestone, reward in STREAK_MILESTONES:
            if streak >= milestone and milestone not in already:
                cur = con.execute(
                    "INSERT OR IGNORE INTO streak_rewards (tg_id, milestone, reward_robux, claimed_at) VALUES (?, ?, ?, ?)",
                    (tg_id, milestone, reward, time.time()))
                if cur.rowcount > 0:
                    con.execute(
                        "UPDATE users SET ref_balance = COALESCE(ref_balance, 0) + ? WHERE tg_id = ?",
                        (reward, tg_id))
                    new_rewards.append({"milestone": milestone, "reward_robux": reward})
        if new_rewards:
            con.commit()
        con.close()
    return new_rewards


def get_users_at_risk_streak(today_num: int, min_streak: int = 3) -> list[dict]:
    """Returns users who:
    - had activity yesterday (in MSK day = today_num - 1)
    - have NO activity today (today_num)
    - have streak >= min_streak
    - haven't been warned today yet
    Used by streak warning watcher."""
    # Use range-queries on ended_at so SQLite can use idx_pd_sess_end (CAST in WHERE
    # would prevent index usage and force a full table scan).
    today_start_unix     = today_num * 86400 - 10800
    today_end_unix       = today_start_unix + 86400
    yesterday_start_unix = today_start_unix - 86400

    with _lock:
        con = _con()
        rows = con.execute("""
            SELECT DISTINCT l.tg_id
            FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            JOIN licenses        l ON l.key = a.license_key
            JOIN users           u ON u.tg_id = l.tg_id
            WHERE l.tg_id IS NOT NULL
              AND s.ended_at >= ? AND s.ended_at < ?
              AND COALESCE(u.streak_warned_at, 0) < ?
              AND l.tg_id NOT IN (
                  SELECT DISTINCT l2.tg_id
                  FROM pd_sessions_v2 s2
                  JOIN pd_accounts_v2 a2 ON a2.id = s2.account_id
                  JOIN licenses        l2 ON l2.key = a2.license_key
                  WHERE s2.ended_at >= ? AND s2.ended_at < ?
              )
        """, (yesterday_start_unix, today_start_unix, today_start_unix,
              today_start_unix, today_end_unix)).fetchall()
        candidate_ids = [r["tg_id"] for r in rows]
        con.close()

    result = []
    for tg_id in candidate_ids:
        streak = compute_streak(tg_id)
        if streak < min_streak:
            continue
        # Determine next milestone reward to motivate
        claimed = get_claimed_milestones(tg_id)
        next_m = None
        next_r = None
        for m, r in STREAK_MILESTONES:
            if m not in claimed:
                next_m, next_r = m, r
                break
        result.append({
            "tg_id": tg_id,
            "streak": streak,
            "next_milestone": next_m,
            "next_reward": next_r,
        })
    return result


def mark_streak_warned(tg_id: int):
    with _lock:
        con = _con()
        con.execute("UPDATE users SET streak_warned_at = ? WHERE tg_id = ?",
                    (time.time(), tg_id))
        con.commit()
        con.close()


def get_streak_info(tg_id: int) -> dict:
    """Returns full streak status: current, claimed, next milestone, new rewards just claimed."""
    streak = compute_streak(tg_id)
    new_rewards = check_streak_rewards(tg_id, streak=streak)
    claimed = get_claimed_milestones(tg_id)
    next_milestone = None
    next_reward = None
    for m, r in STREAK_MILESTONES:
        if m not in claimed:
            next_milestone = m
            next_reward = r
            break
    all_milestones = [
        {"days": m, "reward": r, "claimed": (m in claimed)}
        for m, r in STREAK_MILESTONES
    ]
    return {
        "streak": streak,
        "next_milestone": next_milestone,
        "next_reward": next_reward,
        "milestones": all_milestones,
        "new_rewards": new_rewards,
    }


# ── Webapp profile ────────────────────────────────────────────────────────────

def get_webapp_profile(tg_id: int | None = None, dc_id: int | None = None) -> dict | None:
    with _lock:
        con = _con()
        if tg_id:
            user = con.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            lic  = con.execute(
                "SELECT * FROM licenses WHERE tg_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                (tg_id,)
            ).fetchone()
        else:
            user = con.execute("SELECT * FROM dc_users WHERE dc_id = ?", (dc_id,)).fetchone()
            lic  = con.execute(
                "SELECT * FROM licenses WHERE dc_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                (dc_id,)
            ).fetchone()

        if not lic:
            con.close()
            return None

        stats = con.execute("""
            SELECT
                COALESCE(SUM(robux_alltime + robux_gross), 0)   AS total_robux,
                COALESCE(SUM(donations_alltime + donations), 0) AS total_donations,
                COALESCE(SUM(approached_alltime + approached), 0) AS total_approached,
                COALESCE(SUM(agreed_alltime + agreed), 0)       AS total_agreed,
                COALESCE(SUM(refused_alltime + refused), 0)     AS total_refused,
                COALESCE(SUM(bonus_robux), 0)                   AS bonus_robux
            FROM pd_accounts_v2 WHERE license_key = ?
        """, (lic["key"],)).fetchone()

        sessions_count = con.execute("""
            SELECT COUNT(*) FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            WHERE a.license_key = ? AND s.ended_at IS NOT NULL
        """, (lic["key"],)).fetchone()[0]

        best_session = con.execute("""
            SELECT MAX(s.robux_gross) FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            WHERE a.license_key = ?
        """, (lic["key"],)).fetchone()[0] or 0

        con.close()

    total_robux = stats["total_robux"] or 0
    total_approached = stats["total_approached"] or 0
    total_agreed = stats["total_agreed"] or 0
    conversion = int(total_agreed / total_approached * 100) if total_approached else 0
    lvl = calc_level(total_robux)

    if tg_id:
        display_name = (user["nickname"] if user and user["nickname"] else None) or \
                       (user["tg_username"] if user else None) or str(tg_id)
    else:
        display_name = (user["nickname"] if user and user["nickname"] else None) or \
                       (user["dc_username"] if user else None) or str(dc_id)

    weekly = get_user_weekly_rank(tg_id=tg_id, dc_id=dc_id)
    member_since = user["created_at"] if user else 0
    days_member = int((time.time() - (member_since or time.time())) / 86400)

    avatar_emoji = (user["avatar_emoji"] if user else None) or None
    avatar_grad  = (user["avatar_grad"]  if user else None) or None
    avatar_image = (user["avatar_image"] if user else None) or None
    nick_changes = (user["nickname_changes"] if user else 0) or 0

    # Activity streak (only meaningful for tg users)
    streak_data = get_streak_info(tg_id) if tg_id else {"streak": 0, "next_milestone": None, "next_reward": None, "milestones": [], "new_rewards": []}

    return {
        "display_name": display_name,
        "days_member": days_member,
        "key_type": lic["key_type"],
        "total_robux": total_robux,
        "total_donations": stats["total_donations"] or 0,
        "total_approached": total_approached,
        "total_agreed": total_agreed,
        "total_refused": stats["total_refused"] or 0,
        "conversion_pct": conversion,
        "bonus_robux": stats["bonus_robux"] or 0,
        "sessions_count": sessions_count,
        "best_session": best_session,
        "week_rank": weekly["rank_pos"],
        "week_robux": weekly["robux_week"],
        "avatar_emoji": avatar_emoji,
        "avatar_grad": avatar_grad,
        "avatar_image": avatar_image,
        "nickname_changes": nick_changes,
        "nickname_change_price": NICKNAME_CHANGE_PRICE_STARS,
        "streak": streak_data["streak"],
        "streak_next_milestone": streak_data["next_milestone"],
        "streak_next_reward": streak_data["next_reward"],
        "streak_milestones": streak_data["milestones"],
        "streak_new_rewards": streak_data["new_rewards"],
        **lvl,
    }


# ── Chart data ────────────────────────────────────────────────────────────────

def get_day_start(ts: float | None = None) -> float:
    """Returns Unix timestamp of today 00:00 Moscow time."""
    import datetime
    MSK = datetime.timezone(datetime.timedelta(hours=3))
    t = ts if ts is not None else time.time()
    dt = datetime.datetime.fromtimestamp(t, tz=MSK)
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


# ── Achievements ─────────────────────────────────────────────────────────────

ACHIEVEMENTS = [
    {"id": "first_donation", "name": "Первый донат",  "icon": "🎁", "desc": "Получи первый донат",         "tier": "bronze"},
    {"id": "robux_100",      "name": "Сотка",          "icon": "💵", "desc": "Заработай 100 R$",            "tier": "bronze"},
    {"id": "robux_1k",       "name": "Тысяча",         "icon": "💰", "desc": "Заработай 1 000 R$",          "tier": "silver"},
    {"id": "robux_10k",      "name": "Десять тысяч",   "icon": "💎", "desc": "Заработай 10 000 R$",         "tier": "gold"},
    {"id": "robux_100k",     "name": "Магнат",         "icon": "👑", "desc": "Заработай 100 000 R$",        "tier": "platinum"},
    {"id": "donations_50",   "name": "Полтос",         "icon": "🎯", "desc": "50 успешных донатов",         "tier": "bronze"},
    {"id": "donations_500",  "name": "Пятисотник",     "icon": "🏹", "desc": "500 успешных донатов",        "tier": "silver"},
    {"id": "donations_5k",   "name": "Король донатов", "icon": "⚔️", "desc": "5 000 успешных донатов",      "tier": "gold"},
    {"id": "level_10",       "name": "Опытный",        "icon": "⚡", "desc": "Уровень 10",                  "tier": "bronze"},
    {"id": "level_25",       "name": "Эксперт",        "icon": "💫", "desc": "Уровень 25",                  "tier": "silver"},
    {"id": "level_50",       "name": "Легенда",        "icon": "🚀", "desc": "Уровень 50",                  "tier": "gold"},
    {"id": "top3_week",      "name": "Призёр",         "icon": "🏆", "desc": "Топ-3 за неделю",             "tier": "silver"},
    {"id": "top1_week",      "name": "Чемпион",        "icon": "🥇", "desc": "Топ-1 за неделю",             "tier": "gold"},
    {"id": "ref_5",          "name": "Друг друзей",    "icon": "🤝", "desc": "Привёл 5 друзей",             "tier": "silver"},
    {"id": "ref_25",         "name": "Лидер",          "icon": "👥", "desc": "Привёл 25 друзей",            "tier": "gold"},
    {"id": "tasks_30",       "name": "Трудоголик",     "icon": "📋", "desc": "Выполни 30 ежедневок",        "tier": "silver"},
]
ACHIEVEMENTS_BY_ID = {a["id"]: a for a in ACHIEVEMENTS}


def get_user_achievements(tg_id: int) -> list[dict]:
    """Returns list of unlocked achievement IDs with metadata."""
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT achievement_id, unlocked_at FROM achievements WHERE tg_id = ? ORDER BY unlocked_at DESC",
            (tg_id,)).fetchall()
        con.close()
    return [{**ACHIEVEMENTS_BY_ID.get(r["achievement_id"], {"id": r["achievement_id"]}),
             "unlocked_at": r["unlocked_at"]}
            for r in rows if r["achievement_id"] in ACHIEVEMENTS_BY_ID]


def _unlock_achievement(con, tg_id: int, ach_id: str) -> bool:
    """Returns True if newly unlocked, False if already had."""
    cur = con.execute(
        "INSERT OR IGNORE INTO achievements (tg_id, achievement_id, unlocked_at) VALUES (?, ?, ?)",
        (tg_id, ach_id, time.time()))
    return cur.rowcount > 0


def check_achievements(tg_id: int) -> list[str]:
    """Check all achievement conditions for user, unlock new ones. Returns new unlocks."""
    if not tg_id:
        return []
    with _lock:
        con = _con()
        # Aggregate stats
        stats = con.execute("""
            SELECT
                COALESCE(SUM(a.robux_alltime + a.robux_gross), 0)         AS total_robux,
                COALESCE(SUM(a.donations_alltime + a.donations), 0)       AS total_donations
            FROM pd_accounts_v2 a
            JOIN licenses l ON a.license_key = l.key
            WHERE l.tg_id = ?
        """, (tg_id,)).fetchone()
        ref_count = con.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (tg_id,)).fetchone()[0]
        completed_tasks = con.execute(
            "SELECT COUNT(*) FROM daily_tasks WHERE tg_id = ? AND completed_at IS NOT NULL",
            (tg_id,)).fetchone()[0]

        already = {r["achievement_id"] for r in con.execute(
            "SELECT achievement_id FROM achievements WHERE tg_id = ?", (tg_id,)).fetchall()}

        total_robux = stats["total_robux"] or 0
        total_dons = stats["total_donations"] or 0
        level = min(100, total_robux // _ROBUX_PER_LEVEL + 1)
        weekly = con.execute(
            "SELECT robux_week FROM weekly_rankings WHERE week_start = ? AND tg_id = ?",
            (get_week_start(), tg_id)).fetchone()
        weekly_rank = 0
        if weekly:
            weekly_rank = con.execute(
                "SELECT COUNT(*) FROM weekly_rankings WHERE week_start = ? AND robux_week > ?",
                (get_week_start(), weekly["robux_week"])).fetchone()[0] + 1

        rules = [
            ("first_donation", total_dons >= 1),
            ("robux_100",      total_robux >= 100),
            ("robux_1k",       total_robux >= 1_000),
            ("robux_10k",      total_robux >= 10_000),
            ("robux_100k",     total_robux >= 100_000),
            ("donations_50",   total_dons >= 50),
            ("donations_500",  total_dons >= 500),
            ("donations_5k",   total_dons >= 5_000),
            ("level_10",       level >= 10),
            ("level_25",       level >= 25),
            ("level_50",       level >= 50),
            ("top3_week",      0 < weekly_rank <= 3),
            ("top1_week",      weekly_rank == 1),
            ("ref_5",          ref_count >= 5),
            ("ref_25",         ref_count >= 25),
            ("tasks_30",       completed_tasks >= 30),
        ]
        new_unlocks = []
        for ach_id, cond in rules:
            if cond and ach_id not in already:
                if _unlock_achievement(con, tg_id, ach_id):
                    new_unlocks.append(ach_id)
        if new_unlocks:
            con.commit()
        con.close()
    return new_unlocks


# ── Daily tasks ──────────────────────────────────────────────────────────────

import random as _random

_TASK_POOL = [
    # (task_type, [target options], [reward options], label_template)
    ("farm_robux",     [50, 100, 200, 500],   [3, 6, 10, 25],  "Заработать {target} R$ сегодня"),
    ("farm_donations", [3, 5, 10, 20],        [3, 6, 10, 20],  "Собрать {target} донатов"),
    ("farm_minutes",   [30, 60, 120, 240],    [3, 6, 12, 25],  "Фармить {target} минут"),
    ("farm_sessions",  [1, 3, 5, 10],         [2, 5, 10, 20],  "Завершить {target} сессий"),
]


def get_or_generate_daily_tasks(tg_id: int) -> list[dict]:
    day_start = get_day_start()
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT * FROM daily_tasks WHERE tg_id = ? AND day_start = ?",
            (tg_id, day_start)).fetchall()
        if not rows:
            # Pick 3 different task types. INSERT OR IGNORE protects against
            # duplicate generation if two requests race (UNIQUE on tg_id+day_start+task_type).
            picked_types = _random.sample(_TASK_POOL, k=3)
            for ttype, targets, rewards, _ in picked_types:
                idx = _random.randint(0, len(targets) - 1)
                con.execute(
                    "INSERT OR IGNORE INTO daily_tasks (tg_id, day_start, task_type, target_value, reward_robux) VALUES (?, ?, ?, ?, ?)",
                    (tg_id, day_start, ttype, targets[idx], rewards[idx]))
            con.commit()
            rows = con.execute(
                "SELECT * FROM daily_tasks WHERE tg_id = ? AND day_start = ?",
                (tg_id, day_start)).fetchall()

        # Compute current progress for each task
        # Today's sessions for this user's accounts
        sessions_today = con.execute("""
            SELECT s.robux_gross, s.donations, s.duration
            FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            JOIN licenses l ON l.key = a.license_key
            WHERE l.tg_id = ? AND s.ended_at IS NOT NULL AND s.ended_at >= ?
        """, (tg_id, day_start)).fetchall()
        sum_robux = sum(s["robux_gross"] or 0 for s in sessions_today)
        sum_dons  = sum(s["donations"]   or 0 for s in sessions_today)
        sum_min   = sum((s["duration"]   or 0) / 60 for s in sessions_today)
        cnt_sess  = len(sessions_today)

        result = []
        labels = {t[0]: t[3] for t in _TASK_POOL}
        for r in rows:
            d = dict(r)
            ttype = d["task_type"]
            if ttype == "farm_robux":     progress = min(sum_robux, d["target_value"])
            elif ttype == "farm_donations": progress = min(sum_dons, d["target_value"])
            elif ttype == "farm_minutes":   progress = min(int(sum_min), d["target_value"])
            elif ttype == "farm_sessions":  progress = min(cnt_sess, d["target_value"])
            else: progress = 0
            d["progress"] = progress
            d["label"] = labels.get(ttype, ttype).format(target=d["target_value"])
            d["completed"] = progress >= d["target_value"]
            d["claimed"] = d["claimed_at"] is not None
            # Auto-mark completed_at if just achieved
            if d["completed"] and not d["completed_at"]:
                con.execute("UPDATE daily_tasks SET completed_at = ? WHERE id = ?",
                            (time.time(), d["id"]))
                d["completed_at"] = time.time()
            result.append(d)
        if any(r["completed"] and not r["completed_at"] for r in result):
            con.commit()
        con.close()
    return result


def claim_daily_task(tg_id: int, task_id: int) -> dict | None:
    """Claim reward for completed task. Returns reward info or None if invalid."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT * FROM daily_tasks WHERE id = ? AND tg_id = ?",
            (task_id, tg_id)).fetchone()
        if not row or row["claimed_at"] or not row["completed_at"]:
            con.close()
            return None
        # Mark claimed atomically
        cur = con.execute(
            "UPDATE daily_tasks SET claimed_at = ? WHERE id = ? AND tg_id = ? AND claimed_at IS NULL",
            (time.time(), task_id, tg_id))
        if cur.rowcount == 0:
            con.close()
            return None
        # Add reward to ref_balance (cashable)
        con.execute(
            "UPDATE users SET ref_balance = COALESCE(ref_balance, 0) + ? WHERE tg_id = ?",
            (row["reward_robux"], tg_id))
        con.commit()
        con.close()
    return {"reward_robux": row["reward_robux"], "task_id": task_id}


# ── Public profile (for cards in leaderboard) ────────────────────────────────

def get_public_profile(tg_id: int) -> dict | None:
    """Returns ONLY public-safe fields for displaying another user's card."""
    with _lock:
        con = _con()
        user = con.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        if not user:
            con.close()
            return None
        lic = con.execute(
            "SELECT key, key_type FROM licenses WHERE tg_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (tg_id,)).fetchone()
        total_robux = 0
        if lic:
            r = con.execute(
                "SELECT COALESCE(SUM(robux_alltime + robux_gross), 0) AS t FROM pd_accounts_v2 WHERE license_key = ?",
                (lic["key"],)).fetchone()
            total_robux = r["t"] or 0
        ref_count = con.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (tg_id,)).fetchone()[0]
        ach_rows = con.execute(
            "SELECT achievement_id, unlocked_at FROM achievements WHERE tg_id = ? ORDER BY unlocked_at DESC LIMIT 6",
            (tg_id,)).fetchall()
        weekly = con.execute(
            "SELECT robux_week FROM weekly_rankings WHERE week_start = ? AND tg_id = ?",
            (get_week_start(), tg_id)).fetchone()
        weekly_rank = 0
        weekly_robux = 0
        if weekly:
            weekly_robux = weekly["robux_week"]
            weekly_rank = con.execute(
                "SELECT COUNT(*) FROM weekly_rankings WHERE week_start = ? AND robux_week > ?",
                (get_week_start(), weekly["robux_week"])).fetchone()[0] + 1
        con.close()

    lvl = calc_level(total_robux)
    display_name = (user["nickname"] or user["tg_username"] or user["tg_name"] or str(tg_id))
    days_member = int((time.time() - (user["created_at"] or time.time())) / 86400)
    return {
        "display_name": display_name,
        "days_member": days_member,
        "total_robux": total_robux,
        "ref_count": ref_count,
        "week_rank": weekly_rank,
        "week_robux": weekly_robux,
        "avatar_emoji": user["avatar_emoji"],
        "avatar_grad":  user["avatar_grad"],
        "avatar_image": user["avatar_image"],
        "achievements": [ACHIEVEMENTS_BY_ID.get(a["achievement_id"]) for a in ach_rows
                         if a["achievement_id"] in ACHIEVEMENTS_BY_ID],
        "level": lvl["level"],
        "tier": lvl["tier"],
        "tier_emoji": lvl["tier_emoji"],
    }


# ── Referrals webapp data ────────────────────────────────────────────────────

def get_webapp_referrals(tg_id: int) -> dict:
    user = get_user(tg_id)
    if not user:
        return {"error": "user not found"}
    ref_balance = user.get("ref_balance", 0) or 0
    refs_data = get_refs_with_earnings(tg_id)
    total_ref_robux = sum(r.get("robux_earned", 0) for r in refs_data)
    earning = sum(1 for r in refs_data if r.get("robux_earned", 0) > 0)
    # Strip personally-identifying data, keep only safe display fields
    refs_safe = []
    for r in refs_data:
        nick = r.get("nickname") or r.get("tg_username") or "user"
        refs_safe.append({
            "tg_id": r.get("tg_id"),
            "display_name": nick,
            "has_key": r.get("has_key", False),
            "robux_earned": r.get("robux_earned", 0),
            "my_cut": int(r.get("robux_earned", 0) * 0.10),
        })
    return {
        "ref_count": len(refs_safe),
        "earning_count": earning,
        "ref_balance": ref_balance,
        "total_ref_robux": total_ref_robux,
        "my_total_cut": int(total_ref_robux * 0.10),
        "refs": refs_safe,
    }


def get_my_accounts(tg_id: int) -> list[dict]:
    """Returns the user's Roblox accounts with aggregated lifetime stats and online status."""
    if not tg_id:
        return []
    online_cutoff = time.time() - 35
    with _lock:
        con = _con()
        lic = con.execute(
            "SELECT key FROM licenses WHERE tg_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (tg_id,)).fetchone()
        if not lic:
            con.close()
            return []
        rows = con.execute("""
            SELECT
                a.id,
                a.name,
                a.last_seen,
                a.session_start,
                a.created_at,
                a.status,
                a.hops,
                COALESCE(a.robux_alltime, 0)        AS robux_alltime,
                COALESCE(a.robux_gross, 0)          AS robux_gross,
                COALESCE(a.donations_alltime, 0)    AS donations_alltime,
                COALESCE(a.donations, 0)            AS donations,
                COALESCE(a.approached_alltime, 0)   AS approached_alltime,
                COALESCE(a.approached, 0)           AS approached,
                COALESCE(a.agreed_alltime, 0)       AS agreed_alltime,
                COALESCE(a.agreed, 0)               AS agreed,
                COALESCE(a.refused_alltime, 0)      AS refused_alltime,
                COALESCE(a.refused, 0)              AS refused,
                COALESCE(a.bonus_robux, 0)          AS bonus_robux,
                (SELECT COUNT(*) FROM pd_sessions_v2 WHERE account_id = a.id AND ended_at IS NOT NULL) AS sessions_count,
                (SELECT COALESCE(MAX(robux_gross), 0) FROM pd_sessions_v2 WHERE account_id = a.id) AS best_session
            FROM pd_accounts_v2 a
            WHERE a.license_key = ?
            ORDER BY a.last_seen DESC, a.created_at DESC
        """, (lic["key"],)).fetchall()
        con.close()
    result = []
    for r in rows:
        d = dict(r)
        d["online"] = (d["last_seen"] or 0) > online_cutoff
        d["robux_total"]      = d["robux_alltime"]   + d["robux_gross"]
        d["donations_total"]  = d["donations_alltime"] + d["donations"]
        d["approached_total"] = d["approached_alltime"] + d["approached"]
        d["agreed_total"]     = d["agreed_alltime"] + d["agreed"]
        d["refused_total"]    = d["refused_alltime"] + d["refused"]
        d["conversion_pct"]   = int(d["agreed_total"] / d["approached_total"] * 100) if d["approached_total"] else 0
        result.append(d)
    return result


def get_robux_by_days(tg_id: int | None = None, dc_id: int | None = None,
                      days: int = 7) -> list[dict]:
    with _lock:
        con = _con()
        if tg_id:
            lic = con.execute(
                "SELECT key FROM licenses WHERE tg_id = ? AND status = 'active' LIMIT 1",
                (tg_id,)
            ).fetchone()
        else:
            lic = con.execute(
                "SELECT key FROM licenses WHERE dc_id = ? AND status = 'active' LIMIT 1",
                (dc_id,)
            ).fetchone()
        if not lic:
            con.close()
            return []
        since = time.time() - days * 86400
        rows = con.execute("""
            SELECT
                CAST(s.ended_at / 86400 AS INTEGER) * 86400 AS day_ts,
                COALESCE(SUM(s.robux_gross), 0) AS robux,
                COALESCE(SUM(s.donations), 0) AS donations,
                COUNT(*) AS sessions
            FROM pd_sessions_v2 s
            JOIN pd_accounts_v2 a ON a.id = s.account_id
            WHERE a.license_key = ? AND s.ended_at IS NOT NULL AND s.ended_at >= ?
            GROUP BY day_ts ORDER BY day_ts
        """, (lic["key"], since)).fetchall()
        con.close()
    import datetime
    result = []
    for r in rows:
        d = dict(r)
        d["day_label"] = datetime.datetime.utcfromtimestamp(d["day_ts"]).strftime("%d.%m")
        result.append(d)
    return result


# ── Global chat ───────────────────────────────────────────────────────────────

def chat_is_muted(tg_id: int) -> tuple[bool, float, str]:
    """Returns (is_muted, until_ts, reason)."""
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT muted_until, reason FROM chat_mutes WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        con.close()
    if not row:
        return False, 0, ""
    until = row["muted_until"] or 0
    if until <= time.time():
        return False, 0, ""
    return True, until, (row["reason"] or "")


def chat_mute(tg_id: int, hours: float, reason: str = ""):
    until = time.time() + hours * 3600
    with _lock:
        con = _con()
        con.execute(
            "INSERT OR REPLACE INTO chat_mutes (tg_id, muted_until, reason) VALUES (?, ?, ?)",
            (tg_id, until, reason[:200]))
        con.commit()
        con.close()


def chat_unmute(tg_id: int):
    with _lock:
        con = _con()
        con.execute("DELETE FROM chat_mutes WHERE tg_id = ?", (tg_id,))
        con.commit()
        con.close()


def chat_rate_check(tg_id: int, max_per_min: int = 5) -> bool:
    """Returns True if user is under rate limit."""
    cutoff = time.time() - 60
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE tg_id = ? AND created_at > ?",
            (tg_id, cutoff)).fetchone()[0]
        con.close()
    return n < max_per_min


def chat_send(tg_id: int, text: str) -> int | None:
    """Save message. Returns id or None if not allowed."""
    text = (text or "").strip()
    if not text:
        return None
    text = text[:500]
    with _lock:
        con = _con()
        cur = con.execute(
            "INSERT INTO chat_messages (tg_id, text, created_at) VALUES (?, ?, ?)",
            (tg_id, text, time.time()))
        mid = cur.lastrowid
        con.commit()
        con.close()
    return mid


def chat_send_system(text: str) -> int | None:
    """Post a system announcement to the chat (tg_id=0). Length up to 1000 chars."""
    text = (text or "").strip()
    if not text:
        return None
    text = text[:1000]
    with _lock:
        con = _con()
        cur = con.execute(
            "INSERT INTO chat_messages (tg_id, text, created_at) VALUES (?, ?, ?)",
            (0, text, time.time()))
        mid = cur.lastrowid
        con.commit()
        con.close()
    return mid


def chat_get_recent(limit: int = 50, since_id: int = 0) -> list[dict]:
    """Returns recent chat messages with author display info, ordered oldest→newest."""
    with _lock:
        con = _con()
        if since_id:
            rows = con.execute("""
                SELECT m.id, m.tg_id, m.text, m.created_at,
                       u.nickname AS nickname,
                       u.tg_username AS tg_username,
                       u.tg_name AS tg_name,
                       u.avatar_emoji AS avatar_emoji,
                       u.avatar_grad  AS avatar_grad,
                       u.avatar_image AS avatar_image
                FROM chat_messages m
                LEFT JOIN users u ON u.tg_id = m.tg_id
                WHERE m.id > ? AND m.deleted = 0
                ORDER BY m.id ASC LIMIT ?
            """, (since_id, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT * FROM (
                    SELECT m.id, m.tg_id, m.text, m.created_at,
                           u.nickname AS nickname,
                           u.tg_username AS tg_username,
                           u.tg_name AS tg_name,
                           u.avatar_emoji AS avatar_emoji,
                           u.avatar_grad  AS avatar_grad,
                           u.avatar_image AS avatar_image
                    FROM chat_messages m
                    LEFT JOIN users u ON u.tg_id = m.tg_id
                    WHERE m.deleted = 0
                    ORDER BY m.id DESC LIMIT ?
                ) ORDER BY id ASC
            """, (limit,)).fetchall()
        con.close()
    result = []
    for r in rows:
        d = dict(r)
        if d["tg_id"] == 0:
            d["display_name"] = "RoBeggr"
            d["is_system"] = 1
        else:
            d["display_name"] = d.get("nickname") or d.get("tg_username") or d.get("tg_name") or f"u{d['tg_id']}"
            d["is_system"] = 0
        result.append(d)
    return result


def chat_delete_by_admin(message_id: int):
    with _lock:
        con = _con()
        con.execute("UPDATE chat_messages SET deleted = 1 WHERE id = ?", (message_id,))
        con.commit()
        con.close()


# ── Support chat ──────────────────────────────────────────────────────────────

def support_save(tg_id: int, direction: str, text: str, admin_msg_id: int = None) -> int:
    """Save a support message. direction: 'in' (from user) or 'out' (from admin)."""
    if direction not in ("in", "out"):
        raise ValueError("direction must be 'in' or 'out'")
    text = (text or "").strip()[:2000]
    with _lock:
        con = _con()
        seen = 1 if direction == "in" else 0  # outgoing-from-admin = unread by user
        cur = con.execute(
            "INSERT INTO support_messages (tg_id, direction, text, created_at, admin_msg_id, seen_by_user) VALUES (?, ?, ?, ?, ?, ?)",
            (tg_id, direction, text, time.time(), admin_msg_id, seen))
        mid = cur.lastrowid
        con.commit()
        con.close()
    return mid


def support_history(tg_id: int, limit: int = 100) -> list[dict]:
    with _lock:
        con = _con()
        rows = con.execute(
            "SELECT id, direction, text, created_at, seen_by_user FROM support_messages WHERE tg_id = ? ORDER BY created_at ASC LIMIT ?",
            (tg_id, limit)).fetchall()
        con.close()
    return [dict(r) for r in rows]


def support_find_user_by_admin_msg(admin_msg_id: int) -> int | None:
    """Find tg_id of user whose forwarded message has this admin chat msg_id."""
    if not admin_msg_id:
        return None
    with _lock:
        con = _con()
        row = con.execute(
            "SELECT tg_id FROM support_messages WHERE admin_msg_id = ? LIMIT 1",
            (admin_msg_id,)).fetchone()
        con.close()
    return row["tg_id"] if row else None


def support_unread_count(tg_id: int) -> int:
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM support_messages WHERE tg_id = ? AND direction = 'out' AND seen_by_user = 0",
            (tg_id,)).fetchone()[0]
        con.close()
    return n or 0


def support_mark_read(tg_id: int):
    with _lock:
        con = _con()
        con.execute(
            "UPDATE support_messages SET seen_by_user = 1 WHERE tg_id = ? AND direction = 'out' AND seen_by_user = 0",
            (tg_id,))
        con.commit()
        con.close()


def support_rate_check(tg_id: int, max_per_min: int = 5) -> bool:
    """Returns True if user hasn't exceeded recent message rate."""
    cutoff = time.time() - 60
    with _lock:
        con = _con()
        n = con.execute(
            "SELECT COUNT(*) FROM support_messages WHERE tg_id = ? AND direction = 'in' AND created_at > ?",
            (tg_id, cutoff)).fetchone()[0]
        con.close()
    return n < max_per_min
