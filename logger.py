import os
import sqlite3
from datetime import datetime, timedelta
import json
import hashlib
from pathlib import Path

_DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.getenv("ANALYTICS_DB_PATH", str(_DATA_DIR / "analytics.db"))


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_analytics_db():
    conn = _connect()
    c = conn.cursor()
    # Tabuľka pre históriu správ
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, 
                  content TEXT, timestamp DATETIME)''')
    # Tabuľka pre udalosti (napr. odporúčanie produktu)
    c.execute('''CREATE TABLE IF NOT EXISTS stats 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, timestamp DATETIME)''')
    # Unified event stream pre externú analytiku (Lovable a pod.)
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_name TEXT NOT NULL,
                  session_id TEXT,
                  message_id TEXT,
                  user_id_hash TEXT,
                  language TEXT,
                  metadata TEXT,
                  timestamp DATETIME,
                  sync_status TEXT DEFAULT 'pending')''')
    c.execute(
        """CREATE TABLE IF NOT EXISTS lead_email_outbox (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_id TEXT NOT NULL UNIQUE,
               lead_content TEXT NOT NULL,
               subject_prefix TEXT DEFAULT '',
               status TEXT NOT NULL DEFAULT 'pending',
               attempts INTEGER NOT NULL DEFAULT 0,
               last_error TEXT,
               created_at DATETIME NOT NULL,
               next_retry_at DATETIME NOT NULL,
               delivered_at DATETIME)"""
    )
    conn.commit()
    conn.close()

def log_message(session_id: str, role: str, content: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

def log_event(event_type: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT INTO stats (event_type, timestamp) VALUES (?, ?)", (event_type, datetime.now()))
    conn.commit()
    conn.close()

def build_user_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

def emit_event(
    event_name: str,
    session_id: str = None,
    message_id: str = None,
    user_id_hash: str = None,
    language: str = None,
    metadata: dict = None,
    timestamp = None,
    sync_status: str = "pending"
):
    conn = _connect()
    c = conn.cursor()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    c.execute(
        """INSERT INTO events
           (event_name, session_id, message_id, user_id_hash, language, metadata, timestamp, sync_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_name,
            session_id,
            message_id,
            user_id_hash,
            language,
            metadata_json,
            timestamp or datetime.now(),
            sync_status
        )
    )
    conn.commit()
    conn.close()


def session_has_messages(session_id: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,))
    row = c.fetchone()
    conn.close()
    return row is not None


def session_has_event(session_id: str, event_name: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM events WHERE session_id = ? AND event_name = ? LIMIT 1",
        (session_id, event_name),
    )
    row = c.fetchone()
    conn.close()
    return row is not None


def load_session_messages(session_id: str, limit: int = 50) -> list:
    """Obnoví konverzáciu zo SQLite pre LLM kontext po redeployi."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT role, content FROM messages
           WHERE session_id = ?
             AND role IN ('user', 'bot')
             AND content NOT LIKE '[KONTAKTNÍ FORMULÁŘ]%'
             AND content NOT LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%'
           ORDER BY id DESC
           LIMIT ?""",
        (session_id, limit),
    )
    rows = c.fetchall()
    conn.close()

    messages = []
    for role, content in reversed(rows):
        llm_role = "assistant" if role == "bot" else "user"
        messages.append({"role": llm_role, "content": content})
    return messages


def load_recommended_urls(session_id: str) -> list:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT metadata FROM events
           WHERE session_id = ? AND event_name = 'product_recommended'
           ORDER BY id ASC""",
        (session_id,),
    )
    urls = []
    for (metadata_json,) in c.fetchall():
        try:
            meta = json.loads(metadata_json or "{}")
            url = meta.get("url")
            if url and url not in urls:
                urls.append(url)
        except (json.JSONDecodeError, TypeError):
            continue
    conn.close()
    return urls


def load_session_transcript(session_id: str, include_lead_messages: bool = True) -> list:
    """Načíta celú konverzáciu pre export leadu / doposlanie e-mailu."""
    conn = _connect()
    c = conn.cursor()
    if include_lead_messages:
        c.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ?
               ORDER BY id ASC""",
            (session_id,),
        )
    else:
        c.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ?
                 AND content NOT LIKE '[KONTAKTNÍ FORMULÁŘ]%'
                 AND content NOT LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%'
               ORDER BY id ASC""",
            (session_id,),
        )
    rows = c.fetchall()
    conn.close()

    history = []
    for role, content in rows:
        llm_role = "assistant" if role == "bot" else "user"
        history.append({"role": llm_role, "content": content})
    return history


def fetch_lead_messages(since: str = None, until: str = None) -> list:
    """Vráti všetky lead správy z DB, voliteľne filtrované podľa dátumu."""
    conn = _connect()
    c = conn.cursor()
    query = """SELECT id, session_id, content, timestamp
               FROM messages
               WHERE role='user'
                 AND (content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%')"""
    params = []
    if since:
        query += " AND datetime(timestamp) >= datetime(?)"
        params.append(since)
    if until:
        query += " AND datetime(timestamp) <= datetime(?)"
        params.append(until)
    query += " ORDER BY id ASC"
    c.execute(query, params)
    rows = [
        {
            "id": row[0],
            "session_id": row[1],
            "content": row[2],
            "timestamp": row[3],
        }
        for row in c.fetchall()
    ]
    conn.close()
    return rows


def session_lead_email_delivered(session_id: str) -> bool:
    return session_has_event(session_id, "lead_email_delivered")


def upsert_lead_email_outbox(
    session_id: str,
    lead_content: str,
    *,
    subject_prefix: str = "",
    last_error: str | None = None,
):
    now = datetime.now()
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO lead_email_outbox
           (session_id, lead_content, subject_prefix, status, attempts, last_error, created_at, next_retry_at)
           VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
             lead_content = excluded.lead_content,
             subject_prefix = excluded.subject_prefix,
             last_error = excluded.last_error,
             next_retry_at = excluded.next_retry_at,
             status = CASE
               WHEN lead_email_outbox.status = 'sent' THEN 'sent'
               ELSE 'pending'
             END
           WHERE lead_email_outbox.status != 'sent'""",
        (session_id, lead_content, subject_prefix, last_error, now, now),
    )
    conn.commit()
    conn.close()


def mark_lead_outbox_delivered(session_id: str):
    now = datetime.now()
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """UPDATE lead_email_outbox
           SET status = 'sent', delivered_at = ?, next_retry_at = ?
           WHERE session_id = ?""",
        (now, now, session_id),
    )
    conn.commit()
    conn.close()


_OUTBOX_RETRY_DELAYS_SEC = [
    60, 120, 300, 600, 1800, 3600, 7200, 14400, 28800, 43200,
]


def _outbox_retry_delay(attempts: int) -> int:
    if attempts < len(_OUTBOX_RETRY_DELAYS_SEC):
        return _OUTBOX_RETRY_DELAYS_SEC[attempts]
    return _OUTBOX_RETRY_DELAYS_SEC[-1]


def record_lead_outbox_failure(session_id: str, error: str):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT attempts FROM lead_email_outbox WHERE session_id = ? AND status = 'pending'",
        (session_id,),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return
    attempts = int(row[0]) + 1
    delay = _outbox_retry_delay(attempts - 1)
    next_retry = datetime.now() + timedelta(seconds=delay)
    c.execute(
        """UPDATE lead_email_outbox
           SET attempts = ?, last_error = ?, next_retry_at = ?
           WHERE session_id = ? AND status = 'pending'""",
        (attempts, (error or "")[:2000], next_retry, session_id),
    )
    conn.commit()
    conn.close()


def fetch_outbox_ready_for_retry(limit: int = 15) -> list[dict]:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT session_id, lead_content, subject_prefix, attempts, last_error
           FROM lead_email_outbox
           WHERE status = 'pending'
             AND datetime(next_retry_at) <= datetime('now')
             AND attempts < 25
           ORDER BY next_retry_at ASC, id ASC
           LIMIT ?""",
        (limit,),
    )
    rows = [
        {
            "session_id": row[0],
            "lead_content": row[1],
            "subject_prefix": row[2] or "",
            "attempts": row[3] or 0,
            "last_error": row[4],
        }
        for row in c.fetchall()
    ]
    conn.close()
    return rows


def _pick_best_lead_content(rows: list[tuple]) -> str | None:
    """Preferuje plný formulár pred pasívnym záchytom."""
    full = None
    passive = None
    for content, in rows:
        if content.startswith("[KONTAKTNÍ FORMULÁŘ]"):
            full = content
        elif content.startswith("[PASIVNÍ ZÁCHYT KONTAKTU]") and passive is None:
            passive = content
    return full or passive


def sync_undelivered_leads_to_outbox() -> int:
    """
    Nájde session s lead správou bez udalosti lead_email_delivered a zaradí do outboxu.
    Vráti počet novo pridaných / aktualizovaných záznamov.
    """
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """SELECT DISTINCT session_id FROM messages
           WHERE role = 'user'
             AND (content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%')"""
    )
    session_ids = [row[0] for row in c.fetchall()]
    added = 0
    for session_id in session_ids:
        if session_lead_email_delivered(session_id):
            continue
        c.execute(
            """SELECT 1 FROM lead_email_outbox
               WHERE session_id = ? AND status = 'sent' LIMIT 1""",
            (session_id,),
        )
        if c.fetchone():
            continue
        c.execute(
            """SELECT content FROM messages
               WHERE session_id = ? AND role = 'user'
                 AND (content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%')
               ORDER BY id ASC""",
            (session_id,),
        )
        lead_content = _pick_best_lead_content(c.fetchall())
        if not lead_content:
            continue
        c.execute(
            "SELECT 1 FROM lead_email_outbox WHERE session_id = ? LIMIT 1",
            (session_id,),
        )
        exists = c.fetchone() is not None
        now = datetime.now()
        if exists:
            c.execute(
                """UPDATE lead_email_outbox
                   SET lead_content = ?, status = 'pending', next_retry_at = ?
                   WHERE session_id = ? AND status != 'sent'""",
                (lead_content, now, session_id),
            )
        else:
            c.execute(
                """INSERT INTO lead_email_outbox
                   (session_id, lead_content, subject_prefix, status, attempts, last_error, created_at, next_retry_at)
                   VALUES (?, ?, '', 'pending', 0, NULL, ?, ?)""",
                (session_id, lead_content, now, now),
            )
        added += 1
    conn.commit()
    conn.close()
    return added


init_analytics_db()
