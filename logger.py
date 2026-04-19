import sqlite3
from datetime import datetime
import json
import hashlib

DB_PATH = "analytics.db"

def init_analytics_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

def log_event(event_type: str):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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

init_analytics_db()
