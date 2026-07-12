import os
import sqlite3
from datetime import datetime
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

init_analytics_db()
